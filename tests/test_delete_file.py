"""Offline tests for guarded stored-file deletion."""
from contextlib import redirect_stderr, redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import MagicMock, Mock, call, patch

from kobra_lan.cli import main
from kobra_lan.config import ProtocolError
from kobra_lan.delete_file import DeleteUncertain, delete_file
from kobra_lan.jobs import job_info, list_jobs
from kobra_lan.mqtt import MQTT, MQTTClosed, MQTTFailure
from kobra_lan.profiles import ProfileLocalError
from kobra_lan.start import attempt_id, review_digest
from kobra_lan.upload import atomic_json, describe, device_lock, execute, reserve_at
from kobra_lan.watch import persist_observation
from test_client import GCODE
from test_control import qualified_config, report_with
from test_jobs import make_plan


class DeleteLeaseTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.device_dir = self.root / "device"

    def test_delete_uses_only_the_shared_lease(self):
        with device_lock(self.device_dir, "delete"):
            self.assertEqual({p.name for p in self.device_dir.iterdir()}, {".device.lock"})
            for operation in ("upload", "start", "control", "delete"):
                with self.subTest(operation=operation), self.assertRaisesRegex(ProtocolError, "active"):
                    with device_lock(self.device_dir, operation):
                        self.fail("Concurrent device operation acquired the lease")

    def test_delete_refuses_symlink_and_non_private_directory(self):
        actual = self.root / "actual"
        actual.mkdir(mode=0o700)
        self.device_dir.symlink_to(actual, target_is_directory=True)
        with self.assertRaises((OSError, ProfileLocalError)):
            with device_lock(self.device_dir, "delete"):
                self.fail("Symlink acquired the lease")
        self.assertEqual(list(actual.iterdir()), [])
        self.device_dir.unlink()
        self.device_dir.mkdir()
        self.device_dir.chmod(0o755)
        with self.assertRaises(ProfileLocalError):
            with device_lock(self.device_dir, "delete"):
                self.fail("Non-private device directory acquired the lease")
        self.assertEqual(self.device_dir.stat().st_mode & 0o777, 0o755)


class DeleteFileTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.state_dir = self.root / "state"
        self.config = qualified_config()
        self.device = hashlib.sha256(self.config.printer_id.encode()).hexdigest()
        self.device_dir = self.state_dir / self.device[:16]
        self.filename = "sample.gcode"
        self.entry = {"filename": self.filename, "size": 1234, "is_dir": False}
        self.before = report_with("free", None, urls={"fileUploadurl": "https://example.test?token=secret"})
        self.ack = {"code": 0, "msgid": "synthetic-id"}
        self.report = {"action": "deleteBatch", "state": "success"}
        self.client = Mock(spec=MQTT)
        self.client.delete_file_once.return_value = {"ack": self.ack, "report": self.report}
        self.session = MagicMock()
        self.session.__enter__.return_value = self.client
        self.sleep = self.enterContext(patch("kobra_lan.delete_file.time.sleep"))

    def listing(self, *records):
        return {"code": 200, "data": {"records": list(records)}}

    def run_delete(self, *responses):
        self.client.query.side_effect = responses
        with patch("kobra_lan.delete_file.MQTT", return_value=self.session) as mqtt:
            try:
                return delete_file(self.config, self.filename, self.state_dir)
            finally:
                mqtt.assert_called_once_with(self.config)

    def test_delete_lock_refuses_before_printer_access(self):
        with patch("kobra_lan.delete_file.MQTT") as mqtt:
            for operation in ("upload", "start", "control", "delete"):
                with self.subTest(operation=operation), device_lock(self.device_dir, operation):
                    with self.assertRaisesRegex(ProtocolError, "active"):
                        delete_file(self.config, self.filename, self.state_dir)
        mqtt.assert_not_called()

    def test_confirmed_removal_uses_one_session_and_leaves_optional_directories_absent(self):
        result = self.run_delete(self.before, self.listing({**self.entry, "url": "secret"}),
                                 self.listing(), report_with("free"))
        self.assertEqual(result["status"], "delete_observed_removed")
        self.assertTrue(result["experimental"])
        self.assertFalse(result["dry_run"])
        self.assertFalse(result["hardware_delete_validated"])
        self.assertEqual(result["before_listing"], self.entry)
        self.assertNotIn("urls", result["before"])
        self.assertEqual(result["ack"], self.ack)
        self.assertEqual(result["report"], self.report)
        self.assertEqual(result["after"]["state"], "free")
        self.assertEqual(result["local_state"], {
            "preserved": True, "matching_upload_receipts": 0, "matching_start_receipts": 0,
        })
        self.assertEqual({p.name for p in self.state_dir.iterdir()}, {self.device_dir.name})
        listing_call = call("file", "listLocal", {"page_num": 1, "page_size": 200, "path": "/"})
        self.assertEqual(self.client.query.call_args_list, [
            call("info", require_fresh=True), listing_call, listing_call, call("info", require_fresh=True),
        ])
        self.client.delete_file_once.assert_called_once()
        self.assertEqual(self.client.delete_file_once.call_args.args, (self.filename,))
        self.session.__enter__.assert_called_once()
        self.sleep.assert_not_called()

    def test_delayed_removal_and_bounded_acknowledged_outcome(self):
        present = self.listing(self.entry)
        for polls, status, sleeps in (
            ([present, self.listing()], "delete_observed_removed", 1),
            ([present, present, present], "delete_acknowledged_not_confirmed", 2),
        ):
            with self.subTest(status=status):
                self.client.reset_mock()
                self.sleep.reset_mock()
                result = self.run_delete(self.before, present, *polls, self.before)
                self.assertEqual(result["status"], status)
                self.assertEqual(result["after_listing"], polls[-1]["data"]["records"])
                self.assertEqual(self.client.query.call_count, len(polls) + 3)
                self.assertEqual(self.sleep.call_args_list, [call(1)] * sleeps)
                self.client.delete_file_once.assert_called_once()

    def test_preflight_refusals_do_not_publish(self):
        cases = (
            ((report_with("busy", {"filename": self.filename}),), "target file is active"),
            ((report_with("free", {"filename": self.filename}),), "target file is active"),
            ((report_with("paused", {"filename": "other"}),), "requires an idle printer"),
            ((report_with("free", {"filename": "other"}),), "requires an idle printer"),
            ((report_with("preparing", None),), "requires an idle printer"),
            ((report_with("free", version="2.0.2.3"),), "qualified Kobra X"),
            ((report_with("free", deviceId="Different"),), "qualified Kobra X"),
            ((self.before, self.listing()), "not found"),
            ((self.before, self.listing({**self.entry, "is_dir": True})), "does not accept directories"),
            ((self.before, self.listing({**self.entry, "is_dir": 1})), "does not accept directories"),
            ((self.before, self.listing(self.entry, self.entry)), "ambiguous"),
        )
        for responses, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(ProtocolError, "(?i)" + message) as caught:
                    self.run_delete(*responses)
                self.assertNotIsInstance(caught.exception, DeleteUncertain)
                self.client.delete_file_once.assert_not_called()

    def test_preflight_refuses_unknown_directory_status(self):
        unknown_entries = (
            {"filename": self.filename},
            *({**self.entry, "is_dir": value} for value in (None, "", "0", [], 0.0, 2)),
        )
        for entry in unknown_entries:
            with self.subTest(entry=entry), self.assertRaisesRegex(ProtocolError, "did not establish"):
                self.run_delete(self.before, self.listing(entry))
        self.client.delete_file_once.assert_not_called()

    def test_preflight_accepts_integer_zero_for_a_regular_file(self):
        result = self.run_delete(self.before, self.listing({**self.entry, "is_dir": 0}), self.listing(), self.before)
        self.assertEqual(result["status"], "delete_observed_removed")
        self.client.delete_file_once.assert_called_once()

    def test_replaced_device_directory_refused_before_delete_publish(self):
        def responses():
            yield self.before
            self.device_dir.rename(self.state_dir / "moved")
            self.device_dir.mkdir(mode=0o700)
            yield self.listing(self.entry)

        self.client.query.side_effect = responses()
        with patch("kobra_lan.delete_file.MQTT", return_value=self.session):
            with self.assertRaisesRegex(ProtocolError, "state location changed"):
                delete_file(self.config, self.filename, self.state_dir)
        self.client.delete_file_once.assert_not_called()

    def test_tls_pin_mismatch_refuses_without_sending_credentials(self):
        tls = Mock()
        sock = tls.wrap_socket.return_value
        sock.getpeercert.return_value = b"unexpected synthetic cert"
        with patch("kobra_lan.mqtt.ssl.SSLContext", return_value=tls), patch("kobra_lan.mqtt.socket.create_connection"):
            with self.assertRaises(MQTTFailure) as caught:
                delete_file(self.config, self.filename, self.state_dir)
        self.assertEqual((caught.exception.code, caught.exception.exit_code), ("pin_mismatch", 2))
        sock.sendall.assert_not_called()

    def test_failure_after_ack_retains_partial_evidence_without_replay(self):
        for error, exit_code in (
            (TimeoutError(), 3),
            (MQTTFailure("file_delete", "timeout", "timeout", 3), 3),
            (MQTTClosed("file_delete", "protocol_rejected", "closed"), 3),
            (ProtocolError("malformed report"), 2),
            (KeyboardInterrupt(), 130),
        ):
            with self.subTest(error=error):
                self.client.reset_mock()

                def fail(filename, *, on_ack, on_report):
                    on_ack(self.ack)
                    raise error

                self.client.delete_file_once.side_effect = fail
                with self.assertRaises(DeleteUncertain) as caught:
                    self.run_delete(self.before, self.listing(self.entry))
                failure = caught.exception
                self.assertEqual(failure.exit_code, exit_code)
                self.assertIn("files list", str(failure))
                self.assertEqual(failure.result["status"], "delete_uncertain_no_retry")
                self.assertEqual(failure.result["ack"], self.ack)
                self.assertEqual(failure.result["before_listing"], self.entry)
                self.assertNotIn("report", failure.result)
                self.client.delete_file_once.assert_called_once()
                self.assertEqual(self.client.query.call_count, 2)

    def test_timeout_after_report_retains_evidence_without_ack_or_replay(self):
        def fail(filename, *, on_ack, on_report):
            on_report(self.report)
            raise TimeoutError()

        self.client.delete_file_once.side_effect = fail
        with self.assertRaises(DeleteUncertain) as caught:
            self.run_delete(self.before, self.listing(self.entry))
        failure = caught.exception
        self.assertEqual(failure.exit_code, 3)
        self.assertEqual(failure.result["status"], "delete_uncertain_no_retry")
        self.assertEqual(failure.result["report"], self.report)
        self.assertNotIn("ack", failure.result)
        self.client.delete_file_once.assert_called_once()
        self.assertEqual(self.client.query.call_count, 2)

    def test_failed_post_delete_qualification_preserves_listing_and_report(self):
        with self.assertRaises(DeleteUncertain) as caught:
            self.run_delete(self.before, self.listing(self.entry), self.listing(), report_with("free", version="other"))
        self.assertEqual(caught.exception.exit_code, 2)
        self.assertEqual(caught.exception.result["status"], "delete_uncertain_no_retry")
        self.assertEqual(caught.exception.result["after_listing"], [])
        self.assertEqual(caught.exception.result["report"], self.report)
        self.client.delete_file_once.assert_called_once()

    def test_text_and_root_json_preserve_partial_evidence_and_exit_class(self):
        for mode in ([], ["--json"]):
            for error, expected, code in (
                (None, 0, None),
                (ProtocolError("malformed report"), 2, "validation_failed"),
                (TimeoutError(), 3, "operation_failed"),
                (KeyboardInterrupt(), 130, "interrupted"),
            ):
                with self.subTest(mode=mode, exit_code=expected):
                    self.client.reset_mock()
                    self.client.query.side_effect = [self.before, self.listing(self.entry), self.listing(), self.before]

                    def send(filename, *, on_ack, on_report):
                        self.assertEqual(filename, self.filename)
                        on_ack(self.ack)
                        if error is not None:
                            raise error
                        return {"ack": self.ack, "report": self.report}

                    self.client.delete_file_once.side_effect = send
                    out, err = io.StringIO(), io.StringIO()
                    argv = [*mode, "--state-dir", str(self.state_dir), "files", "delete", self.filename, "--execute"]
                    with patch("kobra_lan.cli.Registry") as registry, \
                            patch("kobra_lan.delete_file.MQTT", return_value=self.session), \
                            redirect_stdout(out), redirect_stderr(err):
                        registry.return_value.access.return_value.__enter__.return_value = (self.config, {})
                        self.assertEqual(main(argv), expected)
                    self.client.delete_file_once.assert_called_once()
                    self.assertEqual(err.getvalue(), "")
                    status = "delete_observed_removed" if expected == 0 else "delete_uncertain_no_retry"
                    self.assertIn(status, out.getvalue())
                    self.assertIn(self.ack["msgid"], out.getvalue())
                    self.assertNotIn("token=secret", out.getvalue())
                    if mode:
                        data = json.loads(out.getvalue())
                        self.assertEqual(data["ok"], expected == 0)
                        self.assertEqual(data["result"]["ack"], self.ack)
                        self.assertEqual(data.get("error", {}).get("code"), code)
                    elif code:
                        self.assertIn("Error (" + code + ")", out.getvalue())

    def test_preserved_receipts_still_support_history_and_block_duplicate_upload(self):
        path = self.root / self.filename
        path.write_bytes(GCODE)
        _, manifest = describe(path, self.filename)
        sha = manifest["sha256"]
        with device_lock(self.device_dir, "delete") as device_fd:
            reserve_at(device_fd, manifest)
            atomic_json(self.device_dir / (sha + ".json"), {
                **manifest, "status": "uploaded_verified_by_listing_and_metadata",
            }, directory_fd=device_fd)
        starts = self.state_dir / "starts" / self.device[:16]
        starts.mkdir(parents=True, mode=0o700)
        plan = make_plan(self.device, sha, filename=self.filename)
        identity = attempt_id(self.device, sha, None)
        atomic_json(starts / (sha + ".attempt"), {"sha256": sha, "plan_sha256": plan["plan_sha256"]})
        atomic_json(starts / (sha + ".json"), {**plan, "dry_run": False, "status": "start_acknowledged_not_confirmed"})
        successor = attempt_id(self.device, sha, identity)
        atomic_json(starts / (successor + ".json"), {
            **plan, "plan_sha256": review_digest(plan, identity), "dry_run": False,
            "status": "start_reserved", "attempt_id": successor, "previous_attempt_id": identity,
        })
        obs_id = persist_observation(
            self.state_dir, self.device, 1700000000, self.filename,
            {"outcome": "unknown", "reason": "deadline_expired", "phase": "printing"},
        )
        other_hash = "a" * 64
        atomic_json(self.device_dir / (other_hash + ".json"), {"sha256": other_hash, "remote_filename": "other.gcode"})
        (self.device_dir / ("b" * 64 + ".json")).symlink_to(self.device_dir / (sha + ".json"))
        corrupt = starts / ("c" * 64 + ".json")
        corrupt.write_text("{")
        corrupt.chmod(0o600)

        def snapshot():
            return {
                p.relative_to(self.state_dir): (stat.S_IMODE(p.lstat().st_mode),
                                                p.read_bytes() if p.is_file() and not p.is_symlink() else None)
                for p in self.state_dir.rglob("*")
            }

        before_state = snapshot()
        before_jobs = list_jobs(self.config, self.state_dir)
        before_details = [job_info(self.config, self.state_dir, key) for key in (identity, obs_id)]
        result = self.run_delete(self.before, self.listing(self.entry), self.listing(), self.before)
        self.assertEqual(result["local_state"], {
            "preserved": True, "matching_upload_receipts": 1, "matching_start_receipts": 2,
        })
        self.assertEqual(snapshot(), before_state)
        self.assertEqual(list_jobs(self.config, self.state_dir), before_jobs)
        self.assertEqual([job_info(self.config, self.state_dir, key) for key in (identity, obs_id)], before_details)
        with patch("kobra_lan.upload.MQTT") as mqtt, self.assertRaisesRegex(ProtocolError, "already attempted"):
            execute(self.config, path, sha, self.state_dir, self.filename)
        mqtt.assert_not_called()
