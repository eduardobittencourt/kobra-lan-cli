"""Offline unit tests for guarded print lifecycle controls (pause, resume, cancel)."""
import hashlib
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import Mock, patch

from kobra_lan.config import ProtocolError
from kobra_lan.control import (
    CANCEL_ALLOWED,
    ControlUncertain,
    PAUSE_ALLOWED,
    RESUME_ALLOWED,
    control_print,
    validate_filename,
)
from kobra_lan.mqtt import MQTT, MQTTClosed, MQTTFailure, MQTTIOFailure
from kobra_lan.profiles import ProfileLocalError, Registry
from kobra_lan.upload import device_lock
from kobra_lan.watch import PREPARATION_STATES
from test_client import config
from test_diagnostics import INFO
from test_profiles import fixture


def qualified_config():
    cfg = config()
    cfg.printer_id = INFO["deviceId"]
    cfg.mqtt_port = 9883
    cfg.client_cert = "synthetic-cert"
    cfg.client_key = "synthetic-key"
    cfg.tls_sha256 = "0" * 64
    cfg.mqtt_username = "synthetic-user"
    cfg.mqtt_password = "synthetic-password"
    return cfg


def report_with(state="busy", project=None, **overrides):
    data = {**INFO, "state": state, "project": project, **overrides}
    return {"code": 200, "data": data}


def project_dict(state="printing", *, filename="sample.gcode", task_id="-1", **extra):
    data = {
        "state": state,
        "filename": filename,
        "task_id": task_id,
        "progress": 25,
        "curr_layer": 10,
        "total_layers": 100,
    }
    data.update(extra)
    return data


class ControlPreflightTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.state_dir = self.root / "state"
        self.cfg = qualified_config()
        self.client = Mock(spec=MQTT)
        self.session = Mock()
        self.session.__enter__ = Mock(return_value=self.client)
        self.session.__exit__ = Mock(return_value=False)

    def test_validate_filename_rejects_unsafe_and_accepts_printable_names(self):
        for valid in ("sample.gcode", "my model (v2).gcode", "part_01-final.gcode"):
            self.assertEqual(validate_filename(valid), valid)
        for bad in ("", "   ", ".", "..", "../a.gcode", "dir/a.gcode", "dir\\a.gcode",
                    "https://example.test/a.gcode", "a.gcode?x=1", "a.gcode#frag",
                    "a\x1b[31mb.gcode", "a\nb.gcode", "a\x00b.gcode", "a" * 256, None):
            with self.subTest(bad=bad):
                with self.assertRaises(ProtocolError):
                    validate_filename(bad)

    def test_unqualified_targets_refuse_without_publishing(self):
        bad_reports = (
            report_with("busy", project_dict("printing"), version="2.0.2.3"),
            report_with("busy", project_dict("printing"), model="Other Printer"),
            report_with("busy", project_dict("printing"), modelId=99999),
            report_with("busy", project_dict("printing"), deviceId="WrongDevice"),
            report_with("busy", project_dict("printing"), version=None),
        )
        for report in bad_reports:
            with self.subTest(report=report), patch("kobra_lan.control.MQTT", return_value=self.session):
                self.client.reset_mock()
                self.client.query.return_value = report
                with self.assertRaises(ProtocolError) as ctx:
                    control_print(self.cfg, "pause", self.state_dir)
                self.assertEqual(getattr(ctx.exception, "exit_code", 2), 2)
                self.client.control_once.assert_not_called()

    def test_tls_pin_mismatch_exits_2_without_sending_credentials_or_control(self):
        ctx_mock = Mock()
        sock = Mock()
        ctx_mock.wrap_socket.return_value = sock
        sock.getpeercert.return_value = b"unexpected synthetic cert"
        with patch("kobra_lan.mqtt.ssl.SSLContext", return_value=ctx_mock), \
                patch("kobra_lan.mqtt.socket.create_connection"):
            with self.assertRaises(MQTTFailure) as ctx:
                control_print(self.cfg, "cancel", self.state_dir)
        self.assertEqual(ctx.exception.code, "pin_mismatch")
        self.assertEqual(ctx.exception.exit_code, 2)
        sock.sendall.assert_not_called()

    def test_state_preconditions_block_invalid_idle_already_reached_transitional_and_unknown_states(self):
        disallowed = {
            "pause": [
                report_with("free", None),
                report_with("free", {}),
                report_with("busy", None),
                report_with("busy", {}),
                report_with("busy", project_dict("paused")),
                report_with("busy", project_dict("pausing")),
                report_with("busy", project_dict("resuming")),
                report_with("busy", project_dict("stopping")),
                report_with("busy", project_dict("nozzle_heating")),
                report_with("busy", project_dict("unrecognized")),
            ],
            "resume": [
                report_with("free", None),
                report_with("busy", project_dict("printing")),
                report_with("busy", project_dict("resuming")),
                report_with("busy", project_dict("pausing")),
                report_with("busy", project_dict("stopping")),
                report_with("busy", project_dict("nozzle_heating")),
                report_with("busy", project_dict("unrecognized")),
            ],
            "cancel": [
                report_with("free", None),
                report_with("free", {}),
                report_with("free", project_dict("printing")),
                report_with("busy", None),
                report_with("busy", project_dict("pausing")),
                report_with("busy", project_dict("resuming")),
                report_with("busy", project_dict("stopping")),
                report_with("busy", project_dict("stoped")),
                report_with("busy", project_dict("canceled")),
                report_with("busy", project_dict("unrecognized")),
            ],
        }
        for action, reports in disallowed.items():
            for report in reports:
                with self.subTest(action=action, state=report["data"]["state"], proj=report["data"]["project"]), \
                        patch("kobra_lan.control.MQTT", return_value=self.session):
                    self.client.reset_mock()
                    self.client.query.return_value = report
                    with self.assertRaises(ProtocolError) as ctx:
                        control_print(self.cfg, action, self.state_dir)
                    self.assertNotIsInstance(ctx.exception, ControlUncertain)
                    self.client.control_once.assert_not_called()

    def test_filename_guard_mismatch_or_hostile_active_filename_blocks_publish(self):
        cases = (
            report_with("busy", project_dict("printing", filename="other.gcode")),
            report_with("busy", project_dict("printing", filename="")),
            report_with("busy", project_dict("printing", filename="https://example.test/sample.gcode")),
        )
        for report in cases:
            with self.subTest(filename=report["data"]["project"]["filename"]), \
                    patch("kobra_lan.control.MQTT", return_value=self.session):
                self.client.reset_mock()
                self.client.query.return_value = report
                with self.assertRaisesRegex(ProtocolError, "--filename"):
                    control_print(self.cfg, "pause", self.state_dir, expected_filename="sample.gcode")
                self.client.control_once.assert_not_called()

    def test_taskid_forwarding_uses_validated_task_id_or_taskid_and_falls_back_to_placeholder(self):
        cases = (
            ({"task_id": "job_42"}, "job_42"),
            ({"task_id": "", "taskid": "alt-99"}, "alt-99"),
            ({"task_id": "-1"}, "-1"),
            ({"task_id": "https://example.test/?secret=1"}, "-1"),
            ({"task_id": ["bad"]}, "-1"),
        )
        for extra, expected_taskid in cases:
            with self.subTest(extra=extra), \
                    patch("kobra_lan.control.MQTT", return_value=self.session), \
                    patch("kobra_lan.control.time.sleep"):
                self.client.reset_mock()
                self.client.query.side_effect = [
                    report_with("busy", project_dict("printing", **extra)),
                    report_with("busy", project_dict("paused", **extra)),
                ]
                self.client.control_once.return_value = {"code": 0, "msgid": "mid-1"}
                result = control_print(self.cfg, "pause", self.state_dir)
                self.client.control_once.assert_called_once_with("pause", taskid=expected_taskid)
                self.assertEqual(result["taskid"], expected_taskid)
                for snapshot_key in ("before_project", "project"):
                    if "task_id" in result[snapshot_key]:
                        self.assertEqual(result[snapshot_key]["task_id"], expected_taskid)
                    if "taskid" in result[snapshot_key]:
                        self.assertEqual(result[snapshot_key]["taskid"], expected_taskid)
                    self.assertNotIn("secret=1", str(result[snapshot_key]))


class ControlExecutionAndSafetyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.state_dir = self.root / "state"
        self.cfg = qualified_config()
        self.client = Mock(spec=MQTT)
        self.session = Mock()
        self.session.__enter__ = Mock(return_value=self.client)
        self.session.__exit__ = Mock(return_value=False)

    def test_confirmed_transitions_for_pause_resume_and_cancel(self):
        cases = (
            ("pause", "pause", report_with("busy", project_dict("printing")),
             [report_with("busy", project_dict("pausing")), report_with("busy", project_dict("paused"))],
             "control_observed_paused"),
            ("resume", "resume", report_with("busy", project_dict("paused")),
             [report_with("busy", project_dict("printing"))],
             "control_observed_resumed"),
            ("resume", "resume", report_with("busy", project_dict("paused")),
             [report_with("busy", project_dict("nozzle_heating"))],
             "control_observed_resumed"),
            ("cancel", "stop", report_with("busy", project_dict("printing")),
             [report_with("free", None)],
             "control_observed_stopped"),
            ("cancel", "stop", report_with("busy", project_dict("nozzle_heating")),
             [report_with("busy", project_dict("stoped"))],
             "control_observed_stopped"),
            ("cancel", "stop", report_with("busy", project_dict("paused")),
             [report_with("busy", project_dict("canceled"))],
             "control_observed_stopped"),
        )
        for action, wire_action, preflight, post_reports, expected_status in cases:
            with self.subTest(action=action, expected_status=expected_status,
                              pre=preflight["data"]["project"]["state"]), \
                    patch("kobra_lan.control.MQTT", return_value=self.session), \
                    patch("kobra_lan.control.time.sleep") as sleep:
                self.client.reset_mock()
                preflight_hostile = {
                    "code": 200,
                    "data": {
                        **preflight["data"],
                        "urls": {"fileUploadurl": "http://192.0.2.10:18910/gcode_upload?s=SECRET_TOKEN"},
                        "secret_field": "PRIVATE",
                    },
                }
                self.client.query.side_effect = [preflight_hostile, *post_reports]
                self.client.control_once.return_value = {"code": 0, "msgid": "mid-ok"}
                result = control_print(self.cfg, action, self.state_dir, expected_filename="sample.gcode")
                self.assertEqual(result["action"], action)
                self.assertEqual(result["wire_action"], wire_action)
                self.assertEqual(result["status"], expected_status)
                self.assertFalse(result["dry_run"])
                self.assertTrue(result["experimental"])
                self.assertTrue(result["hardware_control_validated"])
                self.assertEqual(result["expected_filename"], "sample.gcode")
                self.assertEqual(result["ack"], {"code": 0, "msgid": "mid-ok"})
                self.assertNotIn("urls", result["before"])
                self.assertNotIn("secret_field", result["before"])
                self.assertIn("after", result)
                self.assertIn("project", result)
                self.client.control_once.assert_called_once_with(wire_action, taskid="-1")
                self.assertEqual(sleep.call_count, len(post_reports) - 1)
                for call in self.client.query.call_args_list:
                    self.assertEqual(call.args, ("info",))
                    self.assertEqual(call.kwargs, {"require_fresh": True})

    def test_all_preparation_states_allow_cancel_and_block_pause_and_resume(self):
        self.assertEqual(PAUSE_ALLOWED, frozenset({"printing"}))
        self.assertEqual(RESUME_ALLOWED, frozenset({"paused"}))
        self.assertTrue(PREPARATION_STATES <= CANCEL_ALLOWED)
        for prep in sorted(PREPARATION_STATES):
            with self.subTest(prep=prep), \
                    patch("kobra_lan.control.MQTT", return_value=self.session), \
                    patch("kobra_lan.control.time.sleep"):
                self.client.reset_mock()
                self.client.query.side_effect = [
                    report_with("busy", project_dict(prep)),
                    report_with("free", None),
                ]
                self.client.control_once.return_value = {"code": 0, "msgid": "mid-prep"}
                result = control_print(self.cfg, "cancel", self.state_dir)
                self.assertEqual(result["status"], "control_observed_stopped")
                self.client.control_once.assert_called_once_with("stop", taskid="-1")

    def test_acknowledged_not_confirmed_polls_5_times_and_exits_cleanly_without_retry(self):
        with patch("kobra_lan.control.MQTT", return_value=self.session), \
                patch("kobra_lan.control.time.sleep") as sleep:
            self.client.query.side_effect = [
                report_with("busy", project_dict("printing")),
                *[report_with("busy", project_dict("pausing")) for _ in range(5)],
            ]
            self.client.control_once.return_value = {"code": 0, "msgid": "mid-slow"}
            result = control_print(self.cfg, "pause", self.state_dir)
        self.assertEqual(result["status"], "control_acknowledged_not_confirmed")
        self.assertTrue(result["experimental"])
        self.assertTrue(result["hardware_control_validated"])
        self.assertEqual(result["ack"], {"code": 0, "msgid": "mid-slow"})
        self.assertEqual(result["project"]["state"], "pausing")
        self.assertEqual(self.client.control_once.call_count, 1)
        self.assertEqual(self.client.query.call_count, 6)
        self.assertEqual(sleep.call_count, 4)

    def test_post_publish_failures_return_uncertain_partial_result_with_exact_exit_class_and_no_retry(self):
        cases = (
            ("ack_timeout", MQTTFailure("control", "timeout", "timeout", 3), None, 3, False),
            ("ack_io", MQTTIOFailure("control", timed_out=True), None, 3, False),
            ("ack_closed", MQTTClosed("control", "protocol_rejected", "closed"), None, 3, False),
            ("ack_rejected", ProtocolError("Print control was rejected"), None, 2, False),
            ("poll_timeout", None, MQTTFailure("status", "timeout", "timeout", 3), 3, True),
            ("poll_disconnect", None, ConnectionResetError("reset"), 3, True),
            ("poll_protocol", None, ProtocolError("Malformed MQTT publish"), 2, True),
        )
        for name, ack_err, poll_err, expected_exit, has_ack in cases:
            with self.subTest(case=name), \
                    patch("kobra_lan.control.MQTT", return_value=self.session), \
                    patch("kobra_lan.control.time.sleep"):
                self.client.reset_mock()
                if ack_err is not None:
                    self.client.query.side_effect = [report_with("busy", project_dict("printing"))]
                    self.client.control_once.side_effect = ack_err
                else:
                    self.client.query.side_effect = [
                        report_with("busy", project_dict("printing")),
                        report_with("busy", project_dict("pausing")),
                        poll_err,
                    ]
                    self.client.control_once.side_effect = None
                    self.client.control_once.return_value = {"code": 0, "msgid": "mid-ack"}
                with self.assertRaises(ControlUncertain) as ctx:
                    control_print(self.cfg, "pause", self.state_dir)
                self.assertEqual(ctx.exception.exit_code, expected_exit)
                partial = ctx.exception.result
                self.assertEqual(partial["status"], "control_uncertain_no_retry")
                self.assertEqual(partial["action"], "pause")
                self.assertEqual(partial["wire_action"], "pause")
                self.assertTrue(partial["experimental"])
                self.assertTrue(partial["hardware_control_validated"])
                self.assertIn("before", partial)
                self.assertIn("before_project", partial)
                if has_ack:
                    self.assertEqual(partial["ack"], {"code": 0, "msgid": "mid-ack"})
                    self.assertEqual(partial["project"]["state"], "pausing")
                else:
                    self.assertNotIn("ack", partial)
                self.assertEqual(self.client.control_once.call_count, 1)

    def test_post_publish_keyboard_interrupt_preserves_partial_evidence_without_retry(self):
        for stage in ("ack", "poll"):
            with self.subTest(stage=stage), \
                    patch("kobra_lan.control.MQTT", return_value=self.session), \
                    patch("kobra_lan.control.time.sleep"):
                self.client.reset_mock()
                if stage == "ack":
                    self.client.query.side_effect = [report_with("busy", project_dict("printing"))]
                    self.client.control_once.side_effect = KeyboardInterrupt()
                else:
                    self.client.query.side_effect = [
                        report_with("busy", project_dict("printing")),
                        report_with("busy", project_dict("pausing")),
                        KeyboardInterrupt(),
                    ]
                    self.client.control_once.side_effect = None
                    self.client.control_once.return_value = {"code": 0, "msgid": "mid-int"}
                with self.assertRaises(ControlUncertain) as ctx:
                    control_print(self.cfg, "pause", self.state_dir)
                self.assertEqual(ctx.exception.exit_code, 130)
                self.assertEqual(ctx.exception.result["status"], "control_uncertain_no_retry")
                self.assertIn("before", ctx.exception.result)
                self.assertIn("before_project", ctx.exception.result)
                if stage == "poll":
                    self.assertEqual(ctx.exception.result["ack"], {"code": 0, "msgid": "mid-int"})
                    self.assertEqual(ctx.exception.result["project"]["state"], "pausing")
                else:
                    self.assertNotIn("ack", ctx.exception.result)
                self.assertEqual(self.client.control_once.call_count, 1)

    def test_lock_contention_against_upload_start_and_sibling_control_refuses_before_mqtt(self):
        device = hashlib.sha256(self.cfg.printer_id.encode()).hexdigest()[:16]
        device_dir = self.state_dir / device
        for holder in ("upload", "start", "control"):
            with self.subTest(holder=holder), \
                    patch("kobra_lan.control.MQTT", side_effect=AssertionError("must not connect")) as mqtt:
                with device_lock(device_dir, holder):
                    with self.assertRaisesRegex(ProtocolError, "Another device operation is active"):
                        control_print(self.cfg, "pause", self.state_dir)
                mqtt.assert_not_called()

    def test_unsafe_or_replaced_state_directory_refuses_before_publish(self):
        device = hashlib.sha256(self.cfg.printer_id.encode()).hexdigest()[:16]
        device_dir = self.state_dir / device
        self.state_dir.mkdir(parents=True, mode=0o700)

        # Case 1: symlinked device directory
        decoy = self.root / "decoy"
        decoy.mkdir(mode=0o700)
        os.symlink(decoy, device_dir)
        with patch("kobra_lan.control.MQTT", side_effect=AssertionError("must not connect")):
            with self.assertRaises(OSError):
                control_print(self.cfg, "cancel", self.state_dir)
        self.assertTrue(device_dir.is_symlink())
        self.assertEqual(list(decoy.iterdir()), [])
        device_dir.unlink()

        # Case 2: permissive 0755 device directory (permissions unchanged)
        device_dir.mkdir(mode=0o755)
        device_dir.chmod(0o755)
        with patch("kobra_lan.control.MQTT", side_effect=AssertionError("must not connect")):
            with self.assertRaises(ProfileLocalError):
                control_print(self.cfg, "cancel", self.state_dir)
        self.assertEqual(stat.S_IMODE(device_dir.stat().st_mode), 0o755)
        device_dir.chmod(0o700)

        # Case 3: replaced state directory between pre-flight query and publish
        detached = self.root / "detached"

        def query_and_swap(*args, **kwargs):
            self.state_dir.rename(detached)
            device_dir.mkdir(parents=True, mode=0o700)
            return report_with("busy", project_dict("printing"))

        with patch("kobra_lan.control.MQTT", return_value=self.session):
            self.client.query.side_effect = query_and_swap
            with self.assertRaisesRegex(ProtocolError, "state location changed"):
                control_print(self.cfg, "pause", self.state_dir)
        self.client.control_once.assert_not_called()

    def test_existing_profiles_receipts_markers_and_observations_remain_byte_for_byte_unchanged(self):
        digest = hashlib.sha256(self.cfg.printer_id.encode()).hexdigest()
        prefix = digest[:16]
        registry = Registry(self.root / "profiles-private")
        with registry.lock():
            fixture(registry.reserve("bench"), device=self.cfg.printer_id)
            registry.register("bench", "2.0.2.2")
        upload_dir = self.state_dir / prefix
        starts_dir = self.state_dir / "starts" / prefix
        obs_dir = self.state_dir / "observations" / prefix
        for d in (upload_dir, starts_dir, obs_dir):
            d.mkdir(parents=True, mode=0o700)
        preserved_files = [
            upload_dir / ("a" * 64 + ".attempt"),
            upload_dir / ("a" * 64 + ".json"),
            starts_dir / ("b" * 64 + ".attempt"),
            starts_dir / ("b" * 64 + ".json"),
            obs_dir / ("obs-" + "c" * 32 + ".json"),
        ]
        for path in preserved_files:
            path.write_bytes(b'{"synthetic":true}\n')
            path.chmod(0o600)
        all_preserved = [*preserved_files, *(p for p in (self.root / "profiles-private").rglob("*") if p.is_file())]
        before = {p: (stat.S_IMODE(p.stat().st_mode), p.read_bytes()) for p in all_preserved}

        # Run both a confirmed pause and an uncertain cancel
        with patch("kobra_lan.control.MQTT", return_value=self.session), \
                patch("kobra_lan.control.time.sleep"):
            self.client.query.side_effect = [
                report_with("busy", project_dict("printing")),
                report_with("busy", project_dict("paused")),
            ]
            self.client.control_once.return_value = {"code": 0, "msgid": "mid-1"}
            res = control_print(self.cfg, "pause", self.state_dir)
            self.assertEqual(res["status"], "control_observed_paused")

            self.client.query.side_effect = [report_with("busy", project_dict("paused"))]
            self.client.control_once.side_effect = TimeoutError()
            with self.assertRaises(ControlUncertain):
                control_print(self.cfg, "cancel", self.state_dir)

        after = {p: (stat.S_IMODE(p.stat().st_mode), p.read_bytes()) for p in all_preserved}
        self.assertEqual(before, after)
        # Only .device.lock may be added inside upload_dir; starts_dir and obs_dir have no new files.
        self.assertEqual({p.name for p in upload_dir.iterdir()},
                         {"a" * 64 + ".attempt", "a" * 64 + ".json", ".device.lock"})
        self.assertEqual({p.name for p in starts_dir.iterdir()}, {"b" * 64 + ".attempt", "b" * 64 + ".json"})
        self.assertEqual({p.name for p in obs_dir.iterdir()}, {"obs-" + "c" * 32 + ".json"})


if __name__ == "__main__":
    unittest.main()
