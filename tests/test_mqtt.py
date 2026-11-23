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


if __name__ == "__main__":
    unittest.main()
