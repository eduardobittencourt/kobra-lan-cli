"""Offline checks for the public command tree and presentation boundary."""
import contextlib
import io
import unittest
from unittest.mock import patch

from kobra_lan.cli import ArgumentFailure, build_parser, main


class CommandTreeTests(unittest.TestCase):
    def test_print_plan_and_start_help_expose_only_slot_map(self):
        for command in ("plan", "start"):
            out = io.StringIO()
            with self.subTest(command=command), contextlib.redirect_stdout(out), self.assertRaises(SystemExit) as caught:
                main(["print", command, "--help"])
            self.assertEqual(caught.exception.code, 0)
            self.assertIn("--slot-map PAINT_INDEX=SLOT", out.getvalue())
            self.assertNotIn("--slot", out.getvalue().split())

    def test_every_leaf_has_help_without_operations(self):
        leaves = [("printer", c) for c in ("discover", "pair", "list", "info", "use", "remove")]
        leaves += [("slots", "list")]
        leaves += [("camera", c) for c in ("status", "snapshot", "pipe")]
        leaves += [("files", c) for c in ("list", "info", "upload", "delete")]
        leaves += [("gcode", "inspect"), ("print", "plan"), ("print", "start"), ("print", "watch"),
                   ("print", "pause"), ("print", "resume"), ("print", "cancel")]
        leaves += [("jobs", "list"), ("jobs", "info")]
        leaves += [(c,) for c in ("status", "doctor", "completion")]
        for leaf in leaves:
            with self.subTest(leaf=leaf), patch("kobra_lan.cli.Registry") as registry:
                with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as exit:
                    main([*leaf, "--help"])
                self.assertEqual(exit.exception.code, 0)
                registry.assert_not_called()

    def test_removed_commands_and_missing_groups_fail_before_access(self):
        for argv in (["file", "x"], ["upload", "x"], ["inspect", "x"], ["start", "x"],
                     ["slots"], ["camera"], ["files"], ["printer"], ["gcode"], ["print"], ["jobs"],
                     ["status", "--printer", "bench"], ["--print", "bench", "status"]):
            with self.subTest(argv=argv), patch("kobra_lan.cli.Registry") as registry:
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(main(argv), 2)
                registry.assert_not_called()

    def test_root_options_before_commands(self):
        args = build_parser().parse_args(["--printer", "bench", "--state-dir", "state", "files", "list"])
        self.assertEqual(args.selected_printer, "bench")
        self.assertEqual(str(args.state_dir), "state")
        self.assertEqual(args.files_command, "list")

    def test_execution_options_cannot_be_abbreviated(self):
        parser = build_parser()
        for argv in (["files", "upload", "a.gcode", "--sha256", "0" * 64, "--exec"],
                     ["files", "upload", "a.gcode", "--execute", "--sha", "0" * 64],
                     ["files", "delete", "a.gcode", "--exec"],
                     ["print", "pause", "--exec"],
                     ["print", "cancel", "--execute", "--file", "a.gcode"]):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(ArgumentFailure):
                parser.parse_args(argv)

    def test_delete_help_exposes_idle_requirement_preservation_and_uncertainty(self):
        for argv, phrases in (
            (["files"], ("delete", "read-only", "idle printer", "--execute")),
            (["files", "delete"], ("idle printer", "no active job", "local receipts and markers",
                                   "files list", "Do not resend blindly", "hardware_delete_validated: true", "--execute")),
            (["camera"], ("status", "snapshot", "pipe", "startCapture", "--no-start-capture")),
            (["camera", "status"], ("Read-only", "18088", "hardware_camera_validated: true")),
            (["camera", "snapshot"], ("--output PATH", "--timeout SECONDS", "--overwrite", "--no-start-capture", "ffmpeg")),
            (["camera", "pipe"], ("--timeout SECONDS", "--max-bytes BYTES", "--no-start-capture", "--json")),
            (["printer"], ("discover", "pair", "list", "info", "use", "remove", "read-only")),
            (["printer", "discover"], ("ac:3dprinter:fdm", "--timeout SECONDS", "--interface IPv4",
                                       "unauthenticated", "hardware_discovery_validated: true", "printer pair")),
            (["print", "watch"], ("--timeout SECONDS", "--quiet", "stderr")),
        ):
            with self.subTest(argv=argv), patch("kobra_lan.cli.Registry") as registry:
                out = io.StringIO()
                with contextlib.redirect_stdout(out), self.assertRaises(SystemExit) as caught:
                    main([*argv, "--help"])
                self.assertEqual(caught.exception.code, 0)
                normalized = " ".join(out.getvalue().split())
                for phrase in phrases:
                    self.assertIn(phrase, normalized)
                registry.assert_not_called()


class OutputTests(unittest.TestCase):
    def test_both_formats_keep_safe_partial_evidence_and_empty_results(self):
        import json
        from kobra_lan.cli_output import emit
        result = {"records": [], "missing": None, "default": None, "experimental": True,
                  "status": "start_uncertain_no_retry", "sha256": "a" * 64,
                  "remote_byte_hash_verified": False,
                  "checks": [{"stage": "tls_pin", "status": "failed"}]}
        for mode in (False, True):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                emit(mode, result, code="diagnostic_failed", message="Inspect checks")
            text = out.getvalue()
            self.assertIn("a" * 64, text)
            self.assertIn("start_uncertain_no_retry", text)
            self.assertIn("tls_pin", text)
            if mode:
                report = json.loads(text)
                self.assertEqual(report["schema_version"], 1)
                self.assertFalse(report["ok"])
                self.assertEqual({k: v for k, v in report["result"].items() if k != "qualification"}, result)
            else:
                self.assertIn("Records: none", text)
                self.assertIn("Missing: unknown", text)
                self.assertIn("Default: none", text)
                self.assertIn("firmware 2.0.2.2", text)

    def test_success_and_failures_exit_in_both_formats(self):
        import json
        from kobra_lan.config import ProtocolError
        from kobra_lan.mqtt import MQTTFailure
        for mode in ([], ["--json"]):
            for effect, expected in ((None, 0), (ProtocolError("Validation failed"), 2),
                                     (OSError("private contents"), 3),
                                     (MQTTFailure("status", "timeout", "MQTT response timeout", 3), 3)):
                out, err = io.StringIO(), io.StringIO()
                with patch("kobra_lan.cli.Registry") as registry, patch("kobra_lan.cli.snapshot") as snapshot:
                    registry.return_value.access.return_value.__enter__.return_value = (object(), {})
                    snapshot.return_value = {"state": "free"}
                    snapshot.side_effect = effect
                    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                        self.assertEqual(main([*mode, "status"]), expected)
                    snapshot.assert_called_once()
                self.assertEqual(err.getvalue(), "")
                self.assertNotIn("private contents", out.getvalue())
                if mode:
                    report = json.loads(out.getvalue())
                    self.assertEqual(report["ok"], expected == 0)
                    self.assertEqual(report["schema_version"], 1)
                else:
                    self.assertIn("Qualified:", out.getvalue())

    def test_device_terminal_controls_and_urls_are_not_rendered(self):
        from kobra_lan.cli_output import emit
        for mode in (False, True):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                emit(mode, {"printerName": "\x1b[31mhttps://example.test/?token=synthetic-secret"})
            self.assertNotIn("synthetic-secret", out.getvalue())
            self.assertNotIn("\x1b", out.getvalue())


class SafeArgumentTests(unittest.TestCase):
    def test_hostile_inputs_never_echo_or_open_access(self):
        import json
        secret = "https://example.test/?token=SYNTHETIC_PRIVATE\x1b[31m"
        cases = [[secret], ["slots", secret], ["camera", secret], ["files", secret], ["printer", "pair"],
                 ["printer", "discover", "--timeout", "0"],
                 ["printer", "discover", "--timeout", "16"],
                 ["printer", "discover", "--timeout", secret],
                 ["printer", "discover", "--interface", secret],
                 ["printer", "discover", "--interface", "not-an-ip"],
                 ["printer", "discover", "--interface", "192.0.2.010"],
                 ["printer", "discover", secret],
                 ["camera", "snapshot"],
                 ["camera", "snapshot", "--output", "frame.bmp"],
                 ["camera", "snapshot", "--output", "frame.jpg", "--timeout", "0"],
                 ["camera", "snapshot", "--output", "frame.jpg", "--timeout", "61"],
                 ["camera", "snapshot", "--output", "frame.jpg", "--timeout", secret],
                 ["files", "upload", secret],
                 ["files", "upload", secret, "--execute", "--sha256", secret],
                 ["files", "delete", secret],
                 ["files", "delete", secret, "--execute"],
                 ["files", "delete", "../a.gcode", "--execute"],
                 ["files", "delete", "has\\separator", "--execute"],
                 ["files", "delete", "control\ncharacter", "--execute"],
                 ["files", "delete", "a" * 256, "--execute"],
                 ["files", "delete", "...", "--execute"],
                 ["files", "delete", "", "--execute"],
                 ["print", "start", secret, "--name", "a.gcode", "--slot-map", "0=1",
                  "--auto-leveling", "on", "--vibration-compensation", "off",
                  "--flow-calibration", "off", "--execute", "--plan-sha256", secret],
                 ["jobs", "list", "--kind", secret],
                 ["jobs", "list", "--limit", secret],
                 ["jobs", "list", "--limit", "0"],
                 ["jobs", "list", "--limit", "501"],
                 ["jobs", "info", secret],
                 ["print", "pause"],
                 ["print", "resume"],
                 ["print", "cancel"],
                 ["print", "pause", "--filename", secret],
                 ["print", "pause", "--execute", "--filename", secret],
                 ["print", "resume", "--execute", "--filename", ""],
                 ["print", "cancel", "--execute", "--filename", "../escape.gcode"]]
        for mode in ([], ["--json"]):
            for case in cases:
                with self.subTest(case=case, mode=mode), patch("kobra_lan.cli.Registry") as registry:
                    out, err = io.StringIO(), io.StringIO()
                    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                        self.assertEqual(main([*mode, *case]), 2)
                    registry.assert_not_called()
                    self.assertNotIn("SYNTHETIC_PRIVATE", out.getvalue() + err.getvalue())
                    self.assertEqual(err.getvalue(), "")
                    if mode:
                        self.assertEqual(json.loads(out.getvalue())["error"]["code"], "invalid_arguments")

    def test_root_json_does_not_consume_option_values_or_operands(self):
        from kobra_lan.cli import root_json
        self.assertFalse(root_json(["--config", "--json", "status"]))
        self.assertFalse(root_json(["files", "info", "--json"]))
        self.assertTrue(root_json(["--config=unused", "--printer", "bench", "--json", "unknown"]))

    def test_invalid_slot_mapping_never_echoes_or_opens_access(self):
        import json
        secret = "https://example.test/?token=SYNTHETIC_SLOT_VALUE\x1b[31m"
        cases = [[], ["--slot", secret], ["--slot-map", "0=1", "--slot", secret],
                 ["--slot-map", "0=1", "--slot-map", "00=2"], ["--slot-map"]]
        cases += [["--slot-map", value] for value in
                  (secret, "0=" + secret, "missing", "x=1", "0=x", "1=5", "1=01", "-1=2",
                   "1=2\n", "1 =2", "+1=2", "１=2", "1=２")]
        common = ["a.gcode", "--name", "a.gcode", "--auto-leveling", "on",
                  "--vibration-compensation", "off", "--flow-calibration", "off"]
        for command in ("plan", "start"):
            execution = ["--execute", "--plan-sha256", "a" * 64] if command == "start" else []
            for mode in ([], ["--json"]):
                for case in cases:
                    out, err = io.StringIO(), io.StringIO()
                    with self.subTest(command=command, mode=mode, case=case), \
                            patch("kobra_lan.cli.Registry") as registry, contextlib.redirect_stdout(out), \
                            contextlib.redirect_stderr(err):
                        self.assertEqual(main([*mode, "print", command, *common, *execution, *case]), 2)
                        registry.assert_not_called()
                        self.assertEqual(err.getvalue(), "")
                        rendered = out.getvalue()
                        self.assertNotIn("SYNTHETIC_SLOT_VALUE", rendered)
                        self.assertIn("--slot-map", rendered)
                        if mode:
                            report = json.loads(rendered)
                            self.assertEqual(set(report), {"schema_version", "ok", "error"})
                            self.assertEqual(report["schema_version"], 1)
                            self.assertFalse(report["ok"])
                            self.assertEqual(report["error"]["code"], "invalid_arguments")
                        else:
                            self.assertEqual(rendered.count("Error (invalid_arguments):"), 1)

    def test_missing_execution_controls_direct_to_review_commands(self):
        for mode in ([], ["--json"]):
            out = io.StringIO()
            with patch("kobra_lan.cli.Registry") as registry, contextlib.redirect_stdout(out):
                self.assertEqual(main([*mode, "files", "delete", "a.gcode"]), 2)
            self.assertIn("kobra-lan files list", out.getvalue())
            self.assertIn("--execute", out.getvalue())
            registry.assert_not_called()

        for argv, guidance in ((['files', 'upload', 'a.gcode'], 'gcode inspect'),
                               (['print', 'start', 'a.gcode'], 'print plan'),
                               (['print', 'pause'], '--execute'),
                               (['print', 'resume'], '--execute'),
                               (['print', 'cancel'], '--execute')):
            out = io.StringIO()
            with patch('kobra_lan.cli.Registry') as registry, contextlib.redirect_stdout(out):
                self.assertEqual(main(argv), 2)
            registry.assert_not_called()
            self.assertIn(guidance, out.getvalue())

    def test_print_control_outcomes_render_cleanly_in_text_and_json_modes(self):
        import json
        from kobra_lan.control import ControlUncertain
        confirmed = {
            "action": "pause",
            "wire_action": "pause",
            "device_digest": "a" * 64,
            "model": "Anycubic Kobra X",
            "firmware": "2.0.2.2",
            "status": "control_observed_paused",
            "dry_run": False,
            "experimental": True,
            "hardware_control_validated": True,
            "taskid": "-1",
            "before": {"state": "busy"},
            "before_project": {"state": "printing", "filename": "sample.gcode"},
            "ack": {"code": 0, "msgid": "mid-1"},
            "after": {"state": "busy"},
            "project": {"state": "paused", "filename": "sample.gcode"},
        }
        unconfirmed = {**confirmed, "status": "control_acknowledged_not_confirmed",
                       "project": {"state": "pausing", "filename": "sample.gcode"}}
        uncertain_io = {**confirmed, "status": "control_uncertain_no_retry"}
        cases = (
            (["print", "pause", "--execute"], confirmed, None, 0, None, "control_observed_paused"),
            (["print", "resume", "--execute", "--filename", "sample.gcode"], unconfirmed, None, 0, None,
             "control_acknowledged_not_confirmed"),
            (["print", "cancel", "--execute"], None, ControlUncertain(uncertain_io, exit_code=3), 3,
             "operation_failed", "control_uncertain_no_retry"),
            (["print", "cancel", "--execute"], None, ControlUncertain(uncertain_io, exit_code=2), 2,
             "validation_failed", "control_uncertain_no_retry"),
            (["print", "cancel", "--execute"], None, ControlUncertain(uncertain_io, exit_code=130), 130,
             "interrupted", "control_uncertain_no_retry"),
        )
        for argv, ret, exc, expected_exit, expected_code, expected_status in cases:
            for mode in ([], ["--json"]):
                with self.subTest(argv=argv, mode=mode, expected_status=expected_status):
                    out, err = io.StringIO(), io.StringIO()
                    with patch("kobra_lan.cli.Registry") as registry, \
                            patch("kobra_lan.cli.control_print", return_value=ret, side_effect=exc) as ctrl, \
                            contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                        registry.return_value.access.return_value.__enter__.return_value = (object(), {})
                        self.assertEqual(main([*mode, *argv]), expected_exit)
                    ctrl.assert_called_once()
                    self.assertEqual(err.getvalue(), "")
                    rendered = out.getvalue()
                    self.assertIn(expected_status, rendered)
                    if mode:
                        envelope = json.loads(rendered)
                        self.assertEqual(envelope["schema_version"], 1)
                        self.assertEqual(envelope["ok"], expected_exit == 0)
                        self.assertEqual(envelope["result"]["status"], expected_status)
                        self.assertTrue(envelope["result"]["experimental"])
                        self.assertTrue(envelope["result"]["hardware_control_validated"])
                        if expected_code is not None:
                            self.assertEqual(envelope["error"]["code"], expected_code)
                    else:
                        self.assertIn("Experimental: yes", rendered)
                        self.assertIn("Hardware control validated: yes", rendered)
                        if expected_code is not None:
                            self.assertIn(f"Error ({expected_code}):", rendered)


class CameraCliTests(unittest.TestCase):
    def test_camera_pipe_rejects_global_json_before_target_lookup(self):
        import json
        out, err = io.StringIO(), io.StringIO()
        with patch("kobra_lan.cli.Registry") as registry, \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            self.assertEqual(main(["--json", "camera", "pipe"]), 2)
        registry.assert_not_called()
        self.assertEqual(err.getvalue(), "")
        envelope = json.loads(out.getvalue())
        self.assertEqual(envelope["schema_version"], 1)
        self.assertFalse(envelope["ok"])
        self.assertEqual(envelope["error"]["code"], "invalid_arguments")

    def test_camera_pipe_routes_errors_and_interrupt_to_stderr_only(self):
        from kobra_lan.camera import CameraOperationError

        # Bad args without --json -> stderr only, empty stdout, exit 2.
        out, err = io.StringIO(), io.StringIO()
        with patch("kobra_lan.cli.Registry") as registry, \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            self.assertEqual(main(["camera", "pipe", "--timeout", "0"]), 2)
        registry.assert_not_called()
        self.assertEqual(out.getvalue(), "")
        self.assertIn("Error (invalid_arguments):", err.getvalue())

        # Operational error -> stderr only, empty stdout, exit 3.
        out, err = io.StringIO(), io.StringIO()
        out.buffer = io.BytesIO()
        with patch("kobra_lan.cli.Registry") as registry, \
                patch("kobra_lan.cli.camera_pipe", side_effect=CameraOperationError("stream unavailable")), \
                patch("kobra_lan.cli.sys.stdout", out), contextlib.redirect_stderr(err):
            registry.return_value.access.return_value.__enter__.return_value = (object(), {})
            self.assertEqual(main(["camera", "pipe"]), 3)
        self.assertEqual(out.getvalue(), "")
        self.assertIn("Error (operation_failed): stream unavailable", err.getvalue())

        # KeyboardInterrupt -> stderr notice, exit 130.
        out, err = io.StringIO(), io.StringIO()
        out.buffer = io.BytesIO()
        with patch("kobra_lan.cli.Registry") as registry, \
                patch("kobra_lan.cli.camera_pipe", side_effect=KeyboardInterrupt()), \
                patch("kobra_lan.cli.sys.stdout", out), contextlib.redirect_stderr(err):
            registry.return_value.access.return_value.__enter__.return_value = (object(), {})
            self.assertEqual(main(["camera", "pipe"]), 130)
        self.assertEqual(out.getvalue(), "")
        self.assertIn("interrupted", err.getvalue().lower())

        # Success / broken pipe -> exit 0, no text envelope on stdout.
        out, err = io.StringIO(), io.StringIO()
        out.buffer = io.BytesIO()
        with patch("kobra_lan.cli.Registry") as registry, \
                patch("kobra_lan.cli.camera_pipe", return_value={"bytes_written": 16, "broken_pipe": True}) as pipe_fn, \
                patch("kobra_lan.cli.sys.stdout", out), contextlib.redirect_stderr(err):
            registry.return_value.access.return_value.__enter__.return_value = (object(), {})
            self.assertEqual(main(["camera", "pipe", "--max-bytes", "65536", "--no-start-capture"]), 0)
        pipe_fn.assert_called_once()
        self.assertEqual(pipe_fn.call_args.kwargs["max_bytes"], 65536)
        self.assertFalse(pipe_fn.call_args.kwargs["allow_start_capture"])
        self.assertEqual(out.getvalue(), "")
        self.assertEqual(err.getvalue(), "")

    def test_camera_status_and_snapshot_render_in_text_and_json_and_precheck_ffmpeg(self):
        import json
        import tempfile
        from pathlib import Path

        status_payload = {
            "device_digest": "a" * 64,
            "model": "Anycubic Kobra X",
            "firmware": "2.0.2.2",
            "printer_state": "free",
            "camera_present": True,
            "timelapse_supported": True,
            "stream_url_announced": True,
            "stream_protocol": "http-flv",
            "stream_port": 18088,
            "experimental": True,
            "hardware_camera_validated": True,
        }
        for mode in ([], ["--json"]):
            out, err = io.StringIO(), io.StringIO()
            with patch("kobra_lan.cli.Registry") as registry, \
                    patch("kobra_lan.cli.camera_status", return_value=status_payload) as status_fn, \
                    contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                registry.return_value.access.return_value.__enter__.return_value = (object(), {})
                self.assertEqual(main([*mode, "camera", "status"]), 0)
            status_fn.assert_called_once()
            self.assertEqual(err.getvalue(), "")
            if mode:
                report = json.loads(out.getvalue())
                self.assertTrue(report["ok"])
                self.assertEqual(report["result"]["stream_port"], 18088)
                self.assertTrue(report["result"]["hardware_camera_validated"])
            else:
                self.assertIn("Camera present: yes", out.getvalue())
                self.assertIn("Hardware camera validated: yes", out.getvalue())

        # Missing ffmpeg on camera snapshot exits 3 before Registry lookup.
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "bed.jpg"
            for mode in ([], ["--json"]):
                out, err = io.StringIO(), io.StringIO()
                with patch("kobra_lan.cli.Registry") as registry, \
                        patch("kobra_lan.camera.shutil.which", return_value=None), \
                        contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                    self.assertEqual(main([*mode, "camera", "snapshot", "--output", str(target)]), 3)
                registry.assert_not_called()
                self.assertEqual(err.getvalue(), "")
                if mode:
                    report = json.loads(out.getvalue())
                    self.assertEqual(report["error"]["code"], "operation_failed")
                    self.assertIn("ffmpeg", report["error"]["message"])
                else:
                    self.assertIn("Error (operation_failed):", out.getvalue())
                    self.assertIn("ffmpeg", out.getvalue())


class PrinterDiscoverCliTests(unittest.TestCase):
    def test_discover_rejects_global_target_selectors_before_network(self):
        import json
        for flag_args in (["--printer", "bench"], ["--config", "/tmp/unused.json"]):
            for mode in ([], ["--json"]):
                out, err = io.StringIO(), io.StringIO()
                with self.subTest(flag_args=flag_args, mode=mode), \
                        patch("kobra_lan.cli.Registry") as registry, \
                        patch("kobra_lan.cli.discover_printers") as discover_fn, \
                        contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                    self.assertEqual(main([*mode, *flag_args, "printer", "discover"]), 2)
                registry.assert_not_called()
                discover_fn.assert_not_called()
                self.assertEqual(err.getvalue(), "")
                if mode:
                    report = json.loads(out.getvalue())
                    self.assertFalse(report["ok"])
                    self.assertEqual(report["error"]["code"], "validation_failed")
                else:
                    self.assertIn("Error (validation_failed):", out.getvalue())

    def test_discover_success_socket_error_and_interrupt_in_both_formats(self):
        import json
        from kobra_lan.discovery import DiscoveryError

        sample_result = {
            "protocol": "ssdp",
            "search_target": "ac:3dprinter:fdm",
            "timeout_seconds": 3,
            "interface": "192.0.2.5",
            "hardware_discovery_validated": True,
            "unauthenticated_lan_advertisement": True,
            "firmware_verified": False,
            "printers": [
                {
                    "host": "192.0.2.10",
                    "port": 18910,
                    "model_id": 20030,
                    "model_name": "Anycubic Kobra X",
                    "device_name": "Anycubic Kobra X",
                    "mac": "02:00:00:00:00:01",
                    "ctrl_type": "lan",
                    "qualified_model": True,
                    "firmware_verified": False,
                    "unauthenticated": True,
                }
            ],
            "limitations": ["Same-subnet multicast only."],
        }

        for mode in ([], ["--json"]):
            out, err = io.StringIO(), io.StringIO()
            with patch("kobra_lan.cli.Registry") as registry, \
                    patch("kobra_lan.cli.discover_printers", return_value=sample_result) as discover_fn, \
                    contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                self.assertEqual(
                    main([*mode, "printer", "discover", "--timeout", "3", "--interface", "192.0.2.5"]),
                    0,
                )
            registry.assert_not_called()
            discover_fn.assert_called_once_with(timeout=3, interface="192.0.2.5")
            self.assertEqual(err.getvalue(), "")
            if mode:
                report = json.loads(out.getvalue())
                self.assertTrue(report["ok"])
                self.assertEqual(report["result"]["printers"][0]["model_id"], 20030)
                self.assertTrue(report["result"]["hardware_discovery_validated"])
                self.assertFalse(report["result"]["firmware_verified"])
            else:
                self.assertIn("192.0.2.10", out.getvalue())
                self.assertIn("Hardware discovery validated: yes", out.getvalue())
                self.assertIn("Firmware verified: no", out.getvalue())

        # Socket error -> exit 3, operation_failed
        for mode in ([], ["--json"]):
            out, err = io.StringIO(), io.StringIO()
            with patch("kobra_lan.cli.Registry") as registry, \
                    patch("kobra_lan.cli.discover_printers", side_effect=DiscoveryError("Discovery: local UDP multicast socket operation failed")), \
                    contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                self.assertEqual(main([*mode, "printer", "discover"]), 3)
            registry.assert_not_called()
            self.assertEqual(err.getvalue(), "")
            if mode:
                report = json.loads(out.getvalue())
                self.assertFalse(report["ok"])
                self.assertEqual(report["error"]["code"], "operation_failed")
            else:
                self.assertIn("Error (operation_failed):", out.getvalue())

        # KeyboardInterrupt -> exit 130, interrupted
        for mode in ([], ["--json"]):
            out, err = io.StringIO(), io.StringIO()
            with patch("kobra_lan.cli.Registry") as registry, \
                    patch("kobra_lan.cli.discover_printers", side_effect=KeyboardInterrupt()), \
                    contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                self.assertEqual(main([*mode, "printer", "discover"]), 130)
            registry.assert_not_called()
            self.assertEqual(err.getvalue(), "")
            if mode:
                report = json.loads(out.getvalue())
                self.assertFalse(report["ok"])
                self.assertEqual(report["error"]["code"], "interrupted")
            else:
                self.assertIn("Error (interrupted):", out.getvalue())

    def test_print_plan_renders_updated_hardware_start_validated_flag(self):
        import json
        fake_cfg = object()
        @contextlib.contextmanager
        def fake_access(_config, _name):
            yield fake_cfg, None

        for validated, expected_text in ((True, "Hardware start validated: yes"), (False, "Hardware start validated: no")):
            plan_result = {
                "file_sha256": "a" * 64,
                "device_digest": "b" * 64,
                "model": "Anycubic Kobra X",
                "firmware": "2.0.2.2",
                "payload": {
                    "filename": "chip.gcode",
                    "ams_settings": {"use_ams": True, "ams_box_mapping": []},
                    "task_settings": {"auto_leveling": 0, "vibration_compensation": 1, "flow_calibration": 0},
                },
                "plan_sha256": "c" * 64,
                "dry_run": True,
                "experimental": True,
                "hardware_start_validated": validated,
                "slot_mapping": [
                    {
                        "paint_index": 0,
                        "slot": 2,
                        "ams_index": 1,
                        "gcode_material_type": "PLA",
                        "gcode_color_hex": "#FF0000",
                        "slot_material_type": "PLA High Speed",
                        "slot_color_hex": "#009639",
                    }
                ],
                "multicolor": False,
                "upload_performed": False,
            }
            for mode in ([], ["--json"]):
                out, err = io.StringIO(), io.StringIO()
                with patch("kobra_lan.cli.Registry") as registry_cls, \
                        patch("kobra_lan.cli.start", return_value=plan_result), \
                        contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                    registry_cls.return_value.access.side_effect = fake_access
                    rc = main([
                        *mode, "--printer", "bench", "print", "plan", "chip.gcode",
                        "--name", "chip.gcode", "--slot-map", "0=2", "--auto-leveling", "off",
                        "--vibration-compensation", "on", "--flow-calibration", "off",
                    ])
                self.assertEqual(rc, 0)
                self.assertEqual(err.getvalue(), "")
                if mode:
                    report = json.loads(out.getvalue())
                    self.assertTrue(report["ok"])
                    self.assertIs(report["result"]["hardware_start_validated"], validated)
                else:
                    self.assertIn(expected_text, out.getvalue())


class NamedOnlySetupTests(unittest.TestCase):
    def test_no_name_pairing_fails_before_registry_or_provisioning(self):
        for mode in ([], ['--json']):
            with patch('kobra_lan.cli.Registry') as registry, \
                    patch('kobra_lan.pairing.provision') as provision, \
                    contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main([*mode, 'printer', 'pair', '--host', '192.0.2.10']), 2)
            registry.assert_not_called()
            provision.assert_not_called()

    def test_fresh_inventory_is_read_only_and_ignores_root_config(self):
        import tempfile
        from pathlib import Path
        from kobra_lan.profiles import Registry
        from kobra_lan.config import ProtocolError
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)/'private'
            registry = Registry(root)
            self.assertEqual(registry.inventory(), {'profiles': [], 'default': None})
            self.assertFalse(root.exists())
            root.mkdir(mode=0o700)
            (root/'config.json').write_text('synthetic invalid config that must never be read')
            with patch('kobra_lan.profiles.Config.load') as load:
                self.assertEqual(registry.inventory(), {'profiles': [], 'default': None})
                self.assertRaises(ProtocolError, registry.resolve)
            load.assert_not_called()
            self.assertEqual([p.name for p in root.iterdir()], ['config.json'])

    def test_old_default_strings_are_rejected_without_translation(self):
        import json
        import tempfile
        from pathlib import Path
        from kobra_lan.profiles import Registry, ProfileLocalError
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)/'private'
            root.mkdir(mode=0o700)
            registry = Registry(root)
            for default in ('legacy-fallback', 'require-explicit'):
                content = json.dumps({'version': 1, 'profiles': {}, 'default': default})
                path = root/'profiles.json'
                path.write_text(content)
                path.chmod(0o600)
                self.assertRaises(ProfileLocalError, registry.read)
                self.assertEqual(path.read_text(), content)
