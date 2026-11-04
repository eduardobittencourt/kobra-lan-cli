"""Offline checks for the public command tree and presentation boundary."""
import contextlib
import io
import unittest
from unittest.mock import patch

from kobra_lan.cli import ArgumentFailure, build_parser, main


class CommandTreeTests(unittest.TestCase):
    def test_every_leaf_has_help_without_operations(self):
        leaves = [("printer", c) for c in ("pair", "list", "info", "use", "remove")]
        leaves += [("files", c) for c in ("list", "info", "upload")]
        leaves += [("gcode", "inspect"), ("print", "plan"), ("print", "start")]
        leaves += [(c,) for c in ("status", "doctor", "completion")]
        for leaf in leaves:
            with self.subTest(leaf=leaf), patch("kobra_lan.cli.Registry") as registry:
                with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as exit:
                    main([*leaf, "--help"])
                self.assertEqual(exit.exception.code, 0)
                registry.assert_not_called()

    def test_removed_commands_and_missing_groups_fail_before_access(self):
        for argv in (["file", "x"], ["upload", "x"], ["inspect", "x"], ["start", "x"],
                     ["files"], ["printer"], ["gcode"], ["print"],
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
        for argv in (["files", "upload", "a.gcode", "--sha256", "0" * 64, "--exec"],
                     ["files", "upload", "a.gcode", "--execute", "--sha", "0" * 64]):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(ArgumentFailure):
                build_parser().parse_args(argv)


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
        cases = [[secret], ["files", secret], ["printer", "pair"],
                 ["files", "upload", secret],
                 ["files", "upload", secret, "--execute", "--sha256", secret],
                 ["print", "start", secret, "--name", "a.gcode", "--slot", "1",
                  "--auto-leveling", "on", "--vibration-compensation", "off",
                  "--flow-calibration", "off", "--execute", "--plan-sha256", secret]]
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

    def test_missing_execution_controls_direct_to_review_commands(self):
        for argv, guidance in ((['files', 'upload', 'a.gcode'], 'gcode inspect'),
                               (['print', 'start', 'a.gcode'], 'print plan')):
            out = io.StringIO()
            with patch('kobra_lan.cli.Registry') as registry, contextlib.redirect_stdout(out):
                self.assertEqual(main(argv), 2)
            registry.assert_not_called()
            self.assertIn(guidance, out.getvalue())


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
