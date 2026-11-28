"""Offline unit tests for single-shot MQTT print lifecycle controls."""
import json
import unittest
from unittest.mock import Mock, patch

from kobra_lan.config import ProtocolError
from kobra_lan.mqtt import BASE, MQTT, MQTTClosed, MQTTFailure, packet, string
from test_client import config


def sent_publish_payload(sock):
    raw = sock.sendall.call_args_list[0].args[0]
    assert raw[0] == 0x30
    pos = raw.index(b"{")
    return json.loads(raw[pos:])


class MQTTControlOnceTests(unittest.TestCase):
    def test_query_rejects_all_lifecycle_control_actions(self):
        client = MQTT(config())
        client.sock = Mock()
        for action in ("pause", "resume", "stop", "cancel", "start"):
            with self.subTest(action=action):
                with self.assertRaises(ProtocolError):
                    client.query("print", action)
        client.sock.sendall.assert_not_called()

    def test_control_once_rejects_unknown_actions_and_invalid_taskid_without_publish(self):
        client = MQTT(config())
        client.sock = Mock()
        for action in ("start", "cancel", "delete", "query", "", None):
            with self.subTest(action=action):
                with self.assertRaises(ProtocolError):
                    client.control_once(action)
        for bad_taskid in ("", "bad/id", "https://example.test", "a" * 129, 123, None):
            with self.subTest(taskid=bad_taskid):
                with self.assertRaises(ProtocolError):
                    client.control_once("pause", taskid=bad_taskid)
        client.sock.sendall.assert_not_called()

    def test_control_once_publishes_expected_topic_and_accepts_qos0_and_qos1_acks(self):
        cfg = config()
        expected_topic = f"{BASE}/slicer/printer/{cfg.type_id}/{cfg.printer_id}/print"
        for action, taskid, qos in (("pause", "-1", 0), ("resume", "task_42", 1), ("stop", "-1", 1)):
            with self.subTest(action=action, qos=qos):
                client = MQTT(cfg)
                client.sock = Mock()
                packets = []

                def receive(deadline):
                    if not packets:
                        payload = sent_publish_payload(client.sock)
                        self.assertEqual(payload["type"], "print")
                        self.assertEqual(payload["action"], action)
                        self.assertEqual(payload["data"], {"taskid": taskid})
                        raw = client.sock.sendall.call_args_list[0].args[0]
                        self.assertIn(string(expected_topic), raw)
                        mid = payload["msgid"]
                        # Unrelated control/other packets are ignored until our correlated ACK arrives.
                        packets.append((0xd0, b""))
                        packets.append((0x30, string("root/response") + json.dumps({"code": 0, "msgid": "other"}).encode()))
                        ack_body = string("root/response")
                        if qos == 1:
                            ack_body += b"\x00\x07"
                        ack_body += json.dumps({"code": 0, "msgid": mid}).encode()
                        packets.append((0x32 if qos == 1 else 0x30, ack_body))
                    return packets.pop(0)

                with patch.object(client, "receive", side_effect=receive):
                    ack = client.control_once(action, taskid=taskid)
                self.assertEqual(ack["code"], 0)
                self.assertEqual(ack["msgid"], sent_publish_payload(client.sock)["msgid"])
                sent = [call.args[0] for call in client.sock.sendall.call_args_list]
                if qos == 1:
                    self.assertEqual(len(sent), 2)
                    self.assertEqual(sent[1], packet(0x40, b"\x00\x07"))
                else:
                    self.assertEqual(len(sent), 1)

    def test_control_once_rejects_nonzero_or_boolean_codes_without_republishing(self):
        for bad_code in (1, -1, 500, None, False, "0"):
            with self.subTest(code=bad_code):
                client = MQTT(config())
                client.sock = Mock()

                def receive(deadline):
                    mid = sent_publish_payload(client.sock)["msgid"]
                    return 0x30, string("root/response") + json.dumps({"code": bad_code, "msgid": mid}).encode()

                with patch.object(client, "receive", side_effect=receive):
                    with self.assertRaisesRegex(ProtocolError, "rejected"):
                        client.control_once("pause")
                self.assertEqual(client.sock.sendall.call_count, 1)

    def test_control_once_never_republishes_on_timeout_close_or_malformed_packets(self):
        cases = (
            ("timeout", MQTTFailure("control", "timeout", "MQTT response timeout (command was not retried)", 3), MQTTFailure),
            ("socket_timeout", TimeoutError(), TimeoutError),
            ("closed", MQTTClosed("control", "protocol_rejected", "MQTT connection closed"), MQTTClosed),
            ("truncated_publish", (0x30, b"\x00"), ProtocolError),
            ("truncated_topic", (0x30, b"\x00\x10short"), ProtocolError),
            ("invalid_utf8_topic", (0x30, b"\x00\x02\xff\xfe{}"), ProtocolError),
            ("unsupported_qos2", (0x34, string("root/response") + b"\x00\x01{}"), ProtocolError),
            ("truncated_qos1_pid", (0x32, string("root/response") + b"\x00"), ProtocolError),
            ("malformed_response_json", (0x30, string("root/response") + b"not-json"), ProtocolError),
            ("non_dict_response_json", (0x30, string("root/response") + b"[]"), ProtocolError),
        )
        for name, outcome, expected_exc in cases:
            with self.subTest(case=name):
                client = MQTT(config())
                client.sock = Mock()
                if isinstance(outcome, BaseException):
                    patcher = patch.object(client, "receive", side_effect=outcome)
                else:
                    patcher = patch.object(client, "receive", return_value=outcome)
                with patcher:
                    with self.assertRaises(expected_exc):
                        client.control_once("stop")
                self.assertEqual(client.sock.sendall.call_count, 1)


class MQTTDeleteOnceTests(unittest.TestCase):
    def setUp(self):
        self.client = MQTT(config())
        self.client.sock = Mock()
        self.on_ack = Mock()

    def publish(self, topic, data, *, qos=0, retained=False):
        pid = b"\x00\x07" if qos else b""
        header = 0x30 | (qos << 1) | retained
        return header, string(topic) + pid + json.dumps(data).encode()

    def ack(self, **fields):
        request = sent_publish_payload(self.client.sock)
        return self.publish("root/response", {"msgid": request["msgid"], "code": 0, **fields})

    def report(self, *, qos=0, retained=False, **fields):
        request = sent_publish_payload(self.client.sock)
        data = {"type": "file", "action": "deleteBatch", "state": "success", "msgid": request["msgid"],
                "data": None, "unexpected": "secret", **fields}
        return self.publish("root/file/report", data, qos=qos, retained=retained)

    def test_single_publish_with_correlated_report_and_qos1_puback(self):
        def receive(deadline):
            yield self.ack(msgid="unrelated")
            yield self.ack()
            self.on_ack.assert_called_once_with({"code": 0, "msgid": sent_publish_payload(self.client.sock)["msgid"]})
            yield self.report(qos=1, code=200)

        packets = receive(None)
        with patch.object(self.client, "receive", side_effect=lambda _: next(packets)):
            result = self.client.delete_file_once("model.gcode", on_ack=self.on_ack)
        request = sent_publish_payload(self.client.sock)
        self.assertEqual(request["type"], "file")
        self.assertEqual(request["action"], "deleteBatch")
        self.assertEqual(request["data"], {"root": "local", "files": [{"path": "/", "filename": "model.gcode"}]})
        cfg = self.client.config
        sent = [call.args[0] for call in self.client.sock.sendall.call_args_list]
        self.assertIn(string(f"{BASE}/slicer/printer/{cfg.type_id}/{cfg.printer_id}/file"), sent[0])
        self.assertEqual(sent[1:], [packet(0x40, b"\x00\x07")])
        self.assertEqual(result, {"ack": {"code": 0, "msgid": request["msgid"]},
                                  "report": {"action": "deleteBatch", "state": "success", "code": 200}})

    def test_uncorrelated_report_requires_ack_and_fresh_timestamp_and_ignores_retained(self):
        def receive():
            stamp = sent_publish_payload(self.client.sock)["timestamp"]
            yield self.report(msgid="other", timestamp=stamp, state="failed")
            yield self.report(retained=True, state="failed")
            mid = sent_publish_payload(self.client.sock)["msgid"]
            yield self.publish("root/response", {"msgid": mid, "code": 9}, retained=True)
            yield self.ack()
            yield self.report(msgid="other", timestamp=stamp - 1, state="failed")
            yield self.report(msgid="other", timestamp=stamp + 6000, state="failed")
            yield self.report(msgid="other", timestamp=stamp)

        packets = receive()
        with patch.object(self.client, "receive", side_effect=lambda _: next(packets)):
            result = self.client.delete_file_once("model.gcode", on_ack=self.on_ack)
        self.on_ack.assert_called_once_with(result["ack"])
        self.assertEqual(result["report"], {"action": "deleteBatch", "state": "success"})
        self.client.sock.sendall.assert_called_once()

    def test_correlated_report_before_ack_still_waits_for_ack(self):
        def receive():
            yield self.report()
            self.on_ack.assert_not_called()
            yield self.ack()

        packets = receive()
        with patch.object(self.client, "receive", side_effect=lambda _: next(packets)):
            result = self.client.delete_file_once("model.gcode", on_ack=self.on_ack)
        self.on_ack.assert_called_once_with(result["ack"])

    def test_ack_rejection_failure_report_and_malformed_packets_never_republish(self):
        cases = (
            (lambda: self.ack(code=1), "rejected"),
            (lambda: self.ack(code=False), "rejected"),
            (lambda: self.report(state="failed"), "rejected"),
            (lambda: self.report(code=500), "rejected"),
            (lambda: (0x32, b"\x00"), "Malformed MQTT publish"),
            (lambda: (0x30, string("root/file/report") + b"{"), "Malformed MQTT file deletion response"),
        )
        for receive, message in cases:
            with self.subTest(message=message):
                self.client.sock.reset_mock()
                with patch.object(self.client, "receive", side_effect=lambda _: receive()):
                    with self.assertRaisesRegex(ProtocolError, message):
                        self.client.delete_file_once("model.gcode")
                self.client.sock.sendall.assert_called_once()

    def test_timeout_after_ack_preserves_callback_evidence(self):
        def receive():
            yield self.ack()
            raise self.client._timeout()

        packets = receive()
        with patch.object(self.client, "receive", side_effect=lambda _: next(packets)):
            with self.assertRaises(MQTTFailure) as caught:
                self.client.delete_file_once("model.gcode", on_ack=self.on_ack)
        self.assertEqual(caught.exception.exit_code, 3)
        self.on_ack.assert_called_once_with({"code": 0, "msgid": sent_publish_payload(self.client.sock)["msgid"]})
        self.client.sock.sendall.assert_called_once()

    def test_timeout_after_correlated_report_preserves_callback_evidence(self):
        on_report = Mock()

        def receive():
            yield self.report(code=200)
            on_report.assert_called_once_with({"action": "deleteBatch", "state": "success", "code": 200})
            raise self.client._timeout()

        packets = receive()
        with patch.object(self.client, "receive", side_effect=lambda _: next(packets)):
            with self.assertRaises(MQTTFailure) as caught:
                self.client.delete_file_once("model.gcode", on_ack=self.on_ack, on_report=on_report)
        self.assertEqual(caught.exception.exit_code, 3)
        self.on_ack.assert_not_called()
        self.client.sock.sendall.assert_called_once()

    def test_query_and_invalid_delete_filename_refuse_before_publish(self):
        with self.assertRaises(ProtocolError):
            self.client.query("file", "deleteBatch")
        for name in ("...", "../model.gcode", "https://example.test?token=secret"):
            with self.subTest(name=name), self.assertRaises(ProtocolError):
                self.client.delete_file_once(name)
        self.client.sock.sendall.assert_not_called()


class MQTTVideoAndPeripherieTests(unittest.TestCase):
    def setUp(self):
        self.client = MQTT(config())
        self.client.sock = Mock()

    def publish(self, topic, data, *, qos=0, retained=False):
        pid = b"\x00\x09" if qos else b""
        header = 0x30 | (qos << 1) | retained
        return header, string(topic) + pid + json.dumps(data).encode()

    def ack(self, **fields):
        request = sent_publish_payload(self.client.sock)
        return self.publish("root/response", {"msgid": request["msgid"], "code": 0, **fields})

    def video_report(self, action, state, *, qos=0, retained=False, **fields):
        request = sent_publish_payload(self.client.sock)
        data = {
            "type": "video",
            "action": action,
            "state": state,
            "code": 200,
            "msgid": "printer-generated-id",
            "timestamp": request["timestamp"],
            "data": None,
            **fields,
        }
        return self.publish("root/video/report", data, qos=qos, retained=retained)

    def test_query_allows_peripherie_and_rejects_video_mutations(self):
        def receive():
            request = sent_publish_payload(self.client.sock)
            yield self.ack()
            yield self.publish(
                "root/peripherie/report",
                {
                    "type": "peripherie",
                    "action": "query",
                    "code": 200,
                    "msgid": "printer-peripherie-id",
                    "timestamp": request["timestamp"],
                    "data": {"camera": 1, "multiColorBox": 1, "udisk": 0},
                },
            )

        packets = receive()
        with patch.object(self.client, "receive", side_effect=lambda _: next(packets)):
            result = self.client.query("peripherie", "query", require_fresh=True)
        request = sent_publish_payload(self.client.sock)
        self.assertEqual(request["type"], "peripherie")
        self.assertEqual(request["action"], "query")
        self.assertEqual(result["data"]["camera"], 1)

        self.client.sock.reset_mock()
        for kind, action in (
            ("video", "startCapture"),
            ("video", "stopCapture"),
            ("video", "query"),
            ("peripherie", "set"),
        ):
            with self.subTest(kind=kind, action=action), self.assertRaises(ProtocolError):
                self.client.query(kind, action)
        self.client.sock.sendall.assert_not_called()

    def test_start_video_capture_once_handles_intermediate_states_and_qos1(self):
        def receive():
            stamp = sent_publish_payload(self.client.sock)["timestamp"]
            yield self.video_report("startCapture", "failed", timestamp=stamp)  # before ACK -> ignored
            yield self.video_report("startCapture", "failed", retained=True)
            yield self.ack()
            yield self.video_report("startCapture", "initSuccess")
            yield self.video_report("startCapture", "joinSuccess")
            yield self.video_report("startCapture", "pushStarted", qos=1)

        packets = receive()
        with patch.object(self.client, "receive", side_effect=lambda _: next(packets)):
            result = self.client.start_video_capture_once()
        request = sent_publish_payload(self.client.sock)
        cfg = self.client.config
        sent = [call.args[0] for call in self.client.sock.sendall.call_args_list]
        self.assertIn(string(f"{BASE}/slicer/printer/{cfg.type_id}/{cfg.printer_id}/video"), sent[0])
        self.assertEqual(request["type"], "video")
        self.assertEqual(request["action"], "startCapture")
        self.assertIsNone(request["data"])
        self.assertEqual(sent[1:], [packet(0x40, b"\x00\x09")])
        self.assertEqual(result["ack"], {"code": 0, "msgid": request["msgid"]})
        self.assertEqual(
            result["report"],
            {
                "action": "startCapture",
                "state": "pushStarted",
                "states": ["initSuccess", "joinSuccess", "pushStarted"],
                "code": 200,
            },
        )

    def test_stop_video_capture_once_waits_for_ack_and_push_stopped(self):
        def receive():
            yield self.ack()
            yield self.video_report("startCapture", "pushStarted")  # wrong action -> ignored
            yield self.video_report("stopCapture", "pushStopped")

        packets = receive()
        with patch.object(self.client, "receive", side_effect=lambda _: next(packets)):
            result = self.client.stop_video_capture_once()
        request = sent_publish_payload(self.client.sock)
        self.assertEqual(request["type"], "video")
        self.assertEqual(request["action"], "stopCapture")
        self.assertEqual(result["report"]["state"], "pushStopped")
        self.client.sock.sendall.assert_called_once()

    def test_video_capture_rejections_and_errors_never_retry(self):
        cases = (
            ("start", lambda: [self.ack(code=1)], ProtocolError, "rejected"),
            ("start", lambda: [self.ack(), self.video_report("startCapture", "pushFailed")], ProtocolError, "rejected"),
            ("start", lambda: [self.ack(), self.video_report("startCapture", "pushStarted", code=500)], ProtocolError, "rejected"),
            ("stop", lambda: [self.ack(code=False)], ProtocolError, "rejected"),
            ("stop", lambda: [self.ack(), self.video_report("stopCapture", "initSuccess")], ProtocolError, "rejected"),
            ("stop", lambda: [self.ack(), self.video_report("stopCapture", [])], ProtocolError, "rejected"),
            ("start", lambda: [self.ack(), self.video_report("startCapture", {"bad": 1})], ProtocolError, "rejected"),
            ("stop", lambda: [(0x30, string("root/video/report") + b"not-json")], ProtocolError, "Malformed MQTT video response"),
            ("stop", lambda: [self.ack(), self.client._timeout()], MQTTFailure, "timeout"),
        )
        for mode, make_items, exc_type, regex in cases:
            with self.subTest(mode=mode, regex=regex):
                self.client.sock.reset_mock()
                items = None

                def receive(_deadline):
                    nonlocal items
                    if items is None:
                        items = iter(make_items())
                    item = next(items)
                    if isinstance(item, BaseException):
                        raise item
                    return item

                action_fn = (
                    self.client.start_video_capture_once
                    if mode == "start"
                    else self.client.stop_video_capture_once
                )
                with patch.object(self.client, "receive", side_effect=receive):
                    with self.assertRaisesRegex(exc_type, regex):
                        action_fn()
                self.client.sock.sendall.assert_called_once()

    def test_video_capture_keeps_correlated_terminal_report_before_ack(self):
        def receive():
            request = sent_publish_payload(self.client.sock)
            yield self.video_report("startCapture", "pushStarted", msgid=request["msgid"])
            yield self.video_report("stopCapture", "pushStopped", msgid="unrelated")
            yield self.ack()

        packets = receive()
        with patch.object(self.client, "receive", side_effect=lambda _: next(packets)):
            result = self.client.start_video_capture_once()
        self.assertEqual(result["report"]["state"], "pushStarted")
        self.assertEqual(result["report"]["states"], ["pushStarted"])
        self.client.sock.sendall.assert_called_once()


class MQTTQueryFreshnessTests(unittest.TestCase):
    def setUp(self):
        self.client = MQTT(config())
        self.client.sock = Mock()

    def publish(self, topic, data, *, qos=0, retained=False):
        pid = b"\x00\x05" if qos else b""
        header = 0x30 | (qos << 1) | retained
        return header, string(topic) + pid + json.dumps(data).encode()

    def ack(self):
        request = sent_publish_payload(self.client.sock)
        return self.publish("root/response", {"msgid": request["msgid"], "code": 0})

    def info_report(self, *, timestamp, state, msgid="printer-report", retained=False):
        return self.publish(
            "root/info/report",
            {"type": "info", "action": "query", "code": 200, "msgid": msgid,
             "timestamp": timestamp, "data": {"state": state}},
            retained=retained,
        )

    def test_query_rejects_invalid_skew_and_min_timestamp_before_publish(self):
        for kwargs in (
            {"max_backward_skew_ms": -1},
            {"max_backward_skew_ms": True},
            {"max_backward_skew_ms": 1.5},
            {"min_timestamp": True},
            {"min_timestamp": "12345"},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(ProtocolError):
                self.client.query("info", require_fresh=True, **kwargs)
        self.client.sock.sendall.assert_not_called()

    def test_query_bounded_backward_skew_post_ack_and_min_timestamp(self):
        def receive():
            request = sent_publish_payload(self.client.sock)
            sent = request["timestamp"]
            # Uncorrelated report before ACK must be ignored even if within skew window.
            yield self.info_report(timestamp=sent - 1000, state="pre_ack")
            yield self.ack()
            # Retained report must be ignored even after ACK and within skew window.
            yield self.info_report(timestamp=sent, state="retained", retained=True)
            # Outside backward skew window (> 5000 ms behind) must be ignored.
            yield self.info_report(timestamp=sent - 5001, state="too_old")
            # Outside forward skew window (> 5000 ms ahead) must be ignored.
            yield self.info_report(timestamp=sent + 6000, state="too_future")
            # Non-increasing timestamps (<= min_timestamp) must be ignored even within skew window.
            yield self.info_report(timestamp=sent - 2000, state="not_increasing_lt")
            yield self.info_report(timestamp=sent - 1500, state="not_increasing_eq")
            # Valid post-ACK report behind host clock within 5000 ms and strictly > min_timestamp.
            yield self.info_report(timestamp=sent - 1200, state="accepted")

        packets = receive()
        with patch.object(self.client, "receive", side_effect=lambda _: next(packets)):
            sent_anchor = int(__import__("time").time() * 1000)
            with patch("kobra_lan.mqtt.time.time", return_value=sent_anchor / 1000.0):
                result = self.client.query(
                    "info",
                    require_fresh=True,
                    max_backward_skew_ms=5000,
                    min_timestamp=sent_anchor - 1500,
                )
        self.assertEqual(result["data"]["state"], "accepted")
        self.assertEqual(result["timestamp"], sent_anchor - 1200)
        self.client.sock.sendall.assert_called_once()

    def test_query_accepts_exact_backward_skew_boundary_and_default_rejects_negative_skew(self):
        anchor_ms = 1700000010000
        # Default max_backward_skew_ms=0 rejects -1 ms, accepts 0 ms.
        def receive_default():
            yield self.ack()
            yield self.info_report(timestamp=anchor_ms - 1, state="rejected_neg")
            yield self.info_report(timestamp=anchor_ms, state="accepted_zero")

        packets = receive_default()
        with patch("kobra_lan.mqtt.time.time", return_value=anchor_ms / 1000.0), \
                patch.object(self.client, "receive", side_effect=lambda _: next(packets)):
            res = self.client.query("info", require_fresh=True)
        self.assertEqual(res["data"]["state"], "accepted_zero")

        # Explicit max_backward_skew_ms=5000 accepts exact -5000 ms boundary.
        self.client.sock.reset_mock()
        def receive_boundary():
            yield self.ack()
            yield self.info_report(timestamp=anchor_ms - 5000, state="accepted_boundary")

        packets = receive_boundary()
        with patch("kobra_lan.mqtt.time.time", return_value=anchor_ms / 1000.0), \
                patch.object(self.client, "receive", side_effect=lambda _: next(packets)):
            res = self.client.query("info", require_fresh=True, max_backward_skew_ms=5000)
        self.assertEqual(res["data"]["state"], "accepted_boundary")


if __name__ == "__main__":
    unittest.main()
