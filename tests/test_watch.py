"""Synthetic clock, registry and MQTT fixtures for read-only print observation."""
from contextlib import contextmanager, redirect_stderr, redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, Mock, patch

from kobra_lan.cli import main
from kobra_lan.config import ProtocolError
from kobra_lan.mqtt import MQTT, MQTTFailure, MQTTIOFailure, string
from kobra_lan.profiles import Registry
from kobra_lan.watch import WatchProgress, observe
from test_client import config
from test_diagnostics import INFO
from test_profiles import fixture


PRINTING = {
    **INFO, "state": "busy",
    "project": {"state": "printing", "task_id": "-1", "filename": "sample.gcode",
                "progress": 12, "curr_layer": 8, "total_layers": 100},
}


def transport_config():
    cfg = config()
    cfg.mqtt_port = 9883
    cfg.client_cert = "synthetic-cert"
    cfg.client_key = "synthetic-key"
    cfg.tls_sha256 = "0" * 64
    cfg.mqtt_username = "synthetic-user"
    cfg.mqtt_password = "synthetic-password"
    return cfg


class ObserveTests(unittest.TestCase):
    def setUp(self):
        self.now = 100
        self.cfg = config()
        self.cfg.printer_id = INFO["deviceId"]
        self.leased = False
        self.client = Mock(spec=MQTT)
        self.setup_connection = Mock(side_effect=self.connect)
        self.close_connection = Mock()
        self.mqtt = self.enterContext(patch("kobra_lan.watch.MQTT", side_effect=self.session))
        self.enterContext(patch("kobra_lan.watch.time.monotonic", side_effect=lambda: self.now))
        self.sleep = self.enterContext(patch("kobra_lan.watch.time.sleep", side_effect=self.advance))
        self.registry = Mock(access=Mock(side_effect=self.access))

    def advance(self, seconds):
        self.now += seconds

    @contextmanager
    def access(self, config, name):
        self.leased = True
        try:
            yield self.cfg, {}
        finally:
            self.leased = False

    def connect(self):
        self.assertTrue(self.leased)
        return self.client

    @contextmanager
    def session(self, cfg, *, deadline):
        client = self.setup_connection()
        try:
            yield client
        finally:
            self.close_connection()

    def fresh_info(self, kind, *, require_fresh):
        self.assertFalse(self.leased)
        self.assertEqual(kind, "info")
        self.assertTrue(require_fresh)
        self.advance(2)
        return {"code": 200, "data": INFO}

    def test_one_session_and_no_catch_up_after_a_slow_query(self):
        received = Mock(side_effect=[None, None, "stop"])
        self.client.query.side_effect = self.fresh_info
        self.assertEqual(observe(self.registry, None, "bench", 20, received), "stop")
        self.registry.access.assert_called_once_with(None, "bench")
        self.mqtt.assert_called_once_with(self.cfg, deadline=120)
        self.close_connection.assert_called_once()
        self.assertEqual(self.now, 116)
        self.assertEqual([call.args for call in self.sleep.call_args_list], [(5,), (5,)])
        self.assertEqual([call.args for call in received.call_args_list], [(INFO,)] * 3)
        self.assertEqual([call.args for call in self.client.method_calls], [("info",)] * 3)

    def test_deadline_caps_sleep_and_prevents_another_query(self):
        received = Mock(return_value=None)
        self.client.query.side_effect = self.fresh_info
        self.assertIsNone(observe(self.registry, None, "bench", 3, received))
        self.sleep.assert_called_once_with(1)
        self.client.query.assert_called_once_with("info", require_fresh=True)
        received.assert_called_once_with(INFO)

    def test_setup_and_query_timeout_at_deadline_but_not_before_it(self):
        for stage in ("tls_pin", "status"):
            action = self.setup_connection if stage == "tls_pin" else self.client.query
            for budget, expiry in ((5, True), (30, False)):
                def expire(*args, **kwargs):
                    self.advance(5 if expiry else 12)
                    raise MQTTFailure(stage, "timeout", "Synthetic timeout", 3)
                self.now = 100
                action.side_effect = expire
                with self.subTest(stage=stage, deadline_expired=expiry):
                    received = Mock()
                    if expiry:
                        self.assertIsNone(observe(self.registry, None, None, budget, received))
                    else:
                        with self.assertRaises(MQTTFailure):
                            observe(self.registry, None, None, budget, received)
                    received.assert_not_called()
                    self.assertFalse(self.leased)
            action.side_effect = self.connect if stage == "tls_pin" else None

    def test_interruption_and_qualification_refusal_close_the_session(self):
        for report, error in ((KeyboardInterrupt(), KeyboardInterrupt),
                              ({"data": {**INFO, "version": "2.0.2.3"}}, ProtocolError)):
            with self.subTest(error=error):
                self.client.query.side_effect = [report]
                received = Mock()
                with self.assertRaises(error):
                    observe(self.registry, None, None, 30, received)
                self.close_connection.assert_called_once()
                received.assert_not_called()
                self.close_connection.reset_mock()

    def test_read_only_session_preserves_saved_configuration_and_state(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = Registry(root / "profiles-private")
            with registry.lock():
                fixture(registry.reserve("bench"))
                registry.register("bench", "2.0.2.2")
            marker = root / "synthetic.attempt"
            marker.write_bytes(b"synthetic reservation")
            before = {path: (path.stat().st_mode, path.read_bytes())
                      for path in root.rglob("*") if path.is_file()}
            self.setup_connection.side_effect = None
            self.setup_connection.return_value = self.client
            self.client.query.side_effect = self.fresh_info
            self.assertEqual(observe(registry, None, "bench", 30, lambda _: "stop"), "stop")
            after = {path: (path.stat().st_mode, path.read_bytes())
                     for path in root.rglob("*") if path.is_file()}
            self.assertEqual(before, after)


class WatchProgressTests(unittest.TestCase):
    def test_idle_start_ignores_the_last_project(self):
        progress = WatchProgress()
        info = {**INFO, "state": "free", "project": None,
                "last_project": {**PRINTING["project"], "state": "finished", "progress": 100}}
        self.assertEqual(progress.update(info), {"outcome": "no_active_job", "reason": "idle"})
        self.assertIsNone(progress.partial("interrupted"))

    def test_changed_terminal_candidate_with_placeholder_cannot_be_attributed(self):
        for status in ("finished", "canceled", "failed"):
            with self.subTest(status=status):
                progress = WatchProgress()
                self.assertIsNone(progress.update(PRINTING))
                candidate = {**PRINTING["project"], "state": status, "progress": 100, "curr_layer": 100}
                result = progress.update({**INFO, "state": "free", "last_project": candidate})
                self.assertEqual(result["outcome"], "unknown")
                self.assertEqual(result["reason"], "last_project_unattributed")
                self.assertEqual(result["current_layer"], 8)
                self.assertEqual(result["progress"], 12)

    def test_full_progress_with_idle_and_unchanged_last_project_is_unknown(self):
        progress = WatchProgress()
        active = {**PRINTING["project"], "progress": 100}
        previous = {**active, "state": "finished"}
        self.assertIsNone(progress.update({**PRINTING, "project": active, "last_project": previous}))
        result = progress.update({**INFO, "state": "free", "last_project": {**previous, "unknown": ["sensitive"]}})
        self.assertEqual(result["outcome"], "unknown")
        self.assertEqual(result["reason"], "job_disappeared")
        self.assertEqual(result["progress"], 100)

    def test_observed_idle_transition_with_empty_last_project_is_unattributed(self):
        progress = WatchProgress()
        empty_last = {"state": "", "task_id": "", "filename": "", "progress": 0,
                      "curr_layer": 0, "total_layers": 0}
        final_active = {**PRINTING["project"], "progress": 99, "curr_layer": 685, "total_layers": 685}
        self.assertIsNone(progress.update({**PRINTING, "project": final_active, "last_project": empty_last}))
        result = progress.update({**INFO, "state": "free", "project": None, "last_project": empty_last})
        self.assertEqual(result, {"outcome": "unknown", "reason": "job_disappeared", "phase": "printing",
                                  "progress": 99, "current_layer": 685, "total_layers": 685})

    def test_replacement_cannot_supply_progress_even_with_the_same_filename(self):
        for filename, reason in (("sample.gcode", "identity_unverified"), ("different.gcode", "job_replaced")):
            with self.subTest(filename=filename):
                progress = WatchProgress()
                self.assertIsNone(progress.update(PRINTING))
                replacement = {**PRINTING["project"], "filename": filename, "task_id": "-1",
                               "progress": 2, "curr_layer": 1}
                result = progress.update({**PRINTING, "project": replacement})
                self.assertEqual(result["outcome"], "unknown")
                self.assertEqual(result["reason"], reason)
                self.assertEqual(result["progress"], 12)

    def test_preparation_and_hostile_fields_leave_only_verified_partials(self):
        for phase, expected in (("nozzle_heating", "preparing"), ("printing", "printing")):
            with self.subTest(phase=phase):
                progress = WatchProgress()
                project = {"state": phase, "progress": {"token": "private"},
                           "curr_layer": "\x1b[31mprivate", "total_layers": True,
                           "filename": "https://example.test/?token=private", "task_id": ["private"]}
                self.assertIsNone(progress.update({**PRINTING, "project": project}))
                self.assertEqual(progress.partial("interrupted"),
                                 {"outcome": "unknown", "reason": "interrupted", "phase": expected})


class WatchTransportTests(unittest.TestCase):
    def test_fresh_query_ignores_both_correlated_stale_and_retained_reports(self):
        client = MQTT(config())
        client.sock = Mock()
        reports = iter(((0x30, -1, "stale"), (0x31, 0, "retained"), (0x30, 0, "fresh")))

        def receive(deadline):
            sent = client.sock.sendall.call_args.args[0]
            query = json.loads(sent[sent.index(b"{"):])
            header, offset, state = next(reports)
            report = {"msgid": query["msgid"], "type": "info",
                      "timestamp": query["timestamp"] + offset, "data": {"state": state}}
            return header, string("synthetic/info/report") + json.dumps(report).encode()

        with patch.object(client, "receive", side_effect=receive):
            self.assertEqual(client.query("info", require_fresh=True)["data"]["state"], "fresh")

    def test_real_transport_caps_tls_setup_and_refuses_pin_before_auth(self):
        cfg = transport_config()
        registry = MagicMock()
        registry.access.return_value.__enter__.return_value = cfg, {}
        with patch("kobra_lan.mqtt.time.monotonic", return_value=100), \
                patch("kobra_lan.mqtt.ssl.SSLContext") as context, \
                patch("kobra_lan.mqtt.socket.create_connection") as connect:
            tls = context.return_value.wrap_socket.return_value
            tls.getpeercert.return_value = b"synthetic untrusted cert"
            with self.assertRaises(MQTTFailure) as error:
                observe(registry, None, "bench", 2, Mock())
        self.assertEqual(error.exception.code, "pin_mismatch")
        connect.assert_called_once_with((cfg.host, cfg.mqtt_port), 2)
        connect.return_value.settimeout.assert_called_once_with(2)
        tls.sendall.assert_not_called()
        tls.close.assert_called_once()

    def test_transport_socket_timeout_during_setup(self):
        cfg = transport_config()
        registry = MagicMock()
        registry.access.return_value.__enter__.return_value = cfg, {}
        now = 100

        def timeout(address, seconds):
            nonlocal now
            now += seconds
            raise TimeoutError

        with patch("kobra_lan.mqtt.time.monotonic", side_effect=lambda: now), \
                patch("kobra_lan.mqtt.ssl.SSLContext"), \
                patch("kobra_lan.mqtt.socket.create_connection", side_effect=timeout):
            self.assertIsNone(observe(registry, None, "bench", 2, Mock()))
            with self.assertRaises(MQTTIOFailure):
                observe(registry, None, "bench", 30, Mock())
        self.assertEqual(now, 114)


    def test_real_transport_peer_eof_is_a_connection_error_without_reconnect(self):
        cfg = transport_config()
        cert = b"synthetic trusted cert"
        cfg.tls_sha256 = hashlib.sha256(cert).hexdigest()
        registry = MagicMock()
        registry.access.return_value.__enter__.return_value = cfg, {}
        with patch("kobra_lan.mqtt.ssl.SSLContext") as context, \
                patch("kobra_lan.mqtt.socket.create_connection") as connect:
            tls = context.return_value.wrap_socket.return_value
            tls.getpeercert.return_value = cert
            tls.recv.side_effect = [b"\x20", b"\x02", b"\x00\x00",
                                    b"\x90", b"\x03", b"\x00\x01\x00", b""]
            received = Mock()
            with self.assertRaises(ConnectionError):
                observe(registry, None, "bench", 30, received)
        connect.assert_called_once()
        received.assert_not_called()
        self.assertEqual([call.args[0][0] for call in tls.sendall.call_args_list], [0x10, 0x82, 0x30, 0xe0])
        query = tls.sendall.call_args_list[2].args[0]
        self.assertIn(b'"type":"info","action":"query"', query)
        tls.close.assert_called_once()

class WatchCliTests(unittest.TestCase):
    def setUp(self):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.registry = Registry(root / "private")
        with self.registry.lock():
            for name, device in (("default", "SyntheticDefault"), ("bench", "SyntheticBench")):
                fixture(self.registry.reserve(name), device=device)
                self.registry.register(name, "2.0.2.2")
        self.registry.select("default")
        self.explicit = root / "explicit.json"
        fixture(self.explicit, device="SyntheticExplicit")
        self.enterContext(patch("kobra_lan.cli.Registry", return_value=self.registry))
        self.client = Mock(spec=MQTT)
        self.session = MagicMock()
        self.session.__enter__.return_value = self.client
        self.mqtt = self.enterContext(patch("kobra_lan.watch.MQTT", return_value=self.session))
        self.enterContext(patch("kobra_lan.watch.time.sleep"))

    def invoke(self, args, expected):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            self.assertEqual(main(args), expected)
        self.assertEqual(err.getvalue(), "")
        return out.getvalue()

    def test_default_named_and_config_targets(self):
        cases = (
            ([], "SyntheticDefault"),
            (["--printer", "bench"], "SyntheticBench"),
            (["--config", str(self.explicit)], "SyntheticExplicit"),
        )
        for flags, device in cases:
            with self.subTest(flags=flags):
                self.client.query.return_value = {"data": {**INFO, "deviceId": device, "state": "free"}}
                outcome = json.loads(self.invoke(["--json", *flags, "print", "watch"], 0))
                self.assertEqual(outcome["result"]["outcome"], "no_active_job")
                self.assertEqual(self.mqtt.call_args.args[0].printer_id, device)
        self.assertEqual(self.mqtt.call_count, len(cases))

    def test_invalid_timeout_is_safe_and_precedes_target_selection(self):
        for timeout in ("0", "-1", "259201", "1.0", "1_0", "synthetic-private"):
            for fmt in ([], ["--json"]):
                with self.subTest(timeout=timeout, fmt=fmt), patch("kobra_lan.cli.Registry") as registry:
                    rendered = self.invoke([*fmt, "print", "watch", "--timeout", timeout], 2)
                    registry.assert_not_called()
                    self.assertNotIn("synthetic-private", rendered)
                    if fmt:
                        self.assertEqual(json.loads(rendered)["error"]["code"], "invalid_arguments")
        self.mqtt.assert_not_called()

    def test_deadline_keeps_verified_progress_in_single_json_document(self):
        now = 100

        def sleep(seconds):
            nonlocal now
            now += seconds

        self.client.query.return_value = {"data": {**PRINTING, "deviceId": "SyntheticDefault"}}
        with patch("kobra_lan.watch.time.monotonic", side_effect=lambda: now), \
                patch("kobra_lan.watch.time.sleep", side_effect=sleep):
            rendered = self.invoke(["--json", "print", "watch", "--timeout", "1"], 0)
        envelope = json.loads(rendered)
        self.assertEqual(len(rendered.splitlines()), 1)
        self.assertEqual(envelope["schema_version"], 1)
        self.assertTrue(envelope["ok"])
        self.assertEqual(envelope["result"]["outcome"], "unknown")
        self.assertEqual(envelope["result"]["reason"], "deadline_expired")
        self.assertEqual(envelope["result"]["current_layer"], 8)

    def test_failures_include_safe_partial_results_in_both_formats(self):
        for error, exit_code, code in (
            (ProtocolError("Synthetic protocol refusal"), 2, "validation_failed"),
            (OSError("private network detail"), 3, "operation_failed"),
            (KeyboardInterrupt(), 130, "interrupted"),
        ):
            for mode in ([], ["--json"]):
                with self.subTest(error=error, mode=mode):
                    self.client.query.side_effect = [{"data": {**PRINTING, "deviceId": "SyntheticDefault"}}, error]
                    rendered = self.invoke([*mode, "print", "watch"], exit_code)
                    self.assertNotIn("private network detail", rendered)
                    self.assertNotIn("sample.gcode", rendered)
                    if mode:
                        envelope = json.loads(rendered)
                        self.assertFalse(envelope["ok"])
                        self.assertEqual(envelope["error"]["code"], code)
                        self.assertEqual(envelope["result"]["outcome"], "unknown")
                        self.assertEqual(envelope["result"]["progress"], 12)
                    else:
                        self.assertIn("Error (" + code + ")", rendered)
                        self.assertIn("Outcome: unknown", rendered)
                        self.assertIn("Progress: 12", rendered)
