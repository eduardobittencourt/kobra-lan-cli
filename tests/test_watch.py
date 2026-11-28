"""Synthetic clock, registry and MQTT fixtures for read-only print observation."""
from contextlib import contextmanager, redirect_stderr, redirect_stdout
import hashlib
import io
import json
import os
from pathlib import Path
import stat
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

    def fresh_info(self, kind, *, require_fresh, max_backward_skew_ms=0, min_timestamp=None):
        self.assertFalse(self.leased)
        self.assertEqual(kind, "info")
        self.assertTrue(require_fresh)
        self.assertEqual(max_backward_skew_ms, 5000)
        self.advance(2)
        return {"code": 200, "timestamp": 1700000000000 + self.now * 1000, "data": INFO}

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
        self.assertEqual(
            [call.kwargs["min_timestamp"] for call in self.client.query.call_args_list],
            [None, 1700000102000, 1700000109000],
        )

    def test_deadline_caps_sleep_and_prevents_another_query(self):
        received = Mock(return_value=None)
        self.client.query.side_effect = self.fresh_info
        self.assertIsNone(observe(self.registry, None, "bench", 3, received))
        self.sleep.assert_called_once_with(1)
        self.client.query.assert_called_once_with(
            "info", require_fresh=True, max_backward_skew_ms=5000, min_timestamp=None
        )
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

    def test_continuous_coherent_tracking_across_prep_printing_filament_pause_zeroing_and_idle(self):
        emitted = []
        progress = WatchProgress(on_progress=emitted.append)
        empty_last = {"state": "", "task_id": "", "filename": "", "progress": 0,
                      "curr_layer": 0, "total_layers": 0}
        temp_warm = {"curr_nozzle_temp": 220, "target_nozzle_temp": 220,
                     "curr_hotbed_temp": 60, "target_hotbed_temp": 60}
        temp_jitter = {"curr_nozzle_temp": 221, "target_nozzle_temp": 220,
                       "curr_hotbed_temp": 60, "target_hotbed_temp": 60}

        def report(state, *, pct=0, curr=0, total=0, remain=0, temp=None):
            return {
                **INFO, "state": "busy", "last_project": empty_last,
                "temp": temp or temp_warm,
                "project": {
                    "state": state, "task_id": "-1", "filename": "sample.gcode",
                    "progress": pct, "curr_layer": curr, "total_layers": total,
                    "remain_time": remain,
                },
            }

        sequence = [
            report("auto_leveling"),
            report("vibrating"),
            report("flow_calibrating"),
            report("nozzle_heating"),
            report("printing", pct=10, curr=10, total=100, remain=25),
            # Identical progress with temperature jitter only -> deduplicated on stderr.
            report("printing", pct=10, curr=10, total=100, remain=25, temp=temp_jitter),
            report("filament_cutting", pct=10, curr=10, total=100, remain=25),
            report("extfilbox_filament_unfeeding", pct=10, curr=10, total=100, remain=25),
            report("extfilbox_filament_feeding", pct=10, curr=10, total=100, remain=25),
            report("nozzle_purging", pct=10, curr=10, total=100, remain=25),
            report("printing", pct=50, curr=50, total=100, remain=12),
            report("pausing", pct=50, curr=50, total=100, remain=12),
            report("paused", pct=50, curr=50, total=100, remain=12),
            report("resuming", pct=50, curr=50, total=100, remain=12),
            report("printing", pct=99, curr=100, total=100, remain=1),
            # End-of-print layer-counter zeroing at 99% preserves high-water 100/100.
            report("printing", pct=99, curr=0, total=0, remain=1),
        ]
        for step in sequence:
            self.assertIsNone(progress.update(step))

        result = progress.update({**INFO, "state": "free", "project": None, "last_project": empty_last})
        self.assertEqual(result, {
            "outcome": "unknown", "reason": "job_disappeared",
            "phase": "printing", "progress": 99, "current_layer": 100, "total_layers": 100,
        })
        # Verify deduplication: 14 distinct progress states (temp jitter and zeroing kept same key).
        self.assertEqual(len(emitted), 14)
        self.assertIn("preparing (auto_leveling)", emitted[0])
        self.assertIn("printing 10% layer 10/100 remaining 25m nozzle 220/220C bed 60/60C", emitted[4])
        self.assertIn("paused 50% layer 50/100 remaining 12m", emitted[11])
        for line in emitted:
            self.assertNotIn("sample.gcode", line)

    def test_initial_active_calibration_filament_pause_resuming_and_stopping_states(self):
        cases = (
            ("auto_leveling", "preparing"),
            ("vibrating", "preparing"),
            ("flow_calibrating", "preparing"),
            ("filament_cutting", "preparing"),
            ("extfilbox_filament_unfeeding", "preparing"),
            ("resuming", "preparing"),
            ("paused", "paused"),
            ("pausing", "paused"),
            ("stopping", "stopping"),
        )
        for state, expected_phase in cases:
            with self.subTest(state=state):
                progress = WatchProgress()
                proj = {"state": state, "task_id": "-1", "filename": "sample.gcode",
                        "progress": 40, "curr_layer": 20, "total_layers": 100}
                self.assertIsNone(progress.update({**INFO, "state": "busy", "project": proj}))
                partial = progress.partial("deadline_expired")
                self.assertEqual(partial["phase"], expected_phase)
                if expected_phase in ("paused", "stopping"):
                    self.assertEqual(partial["progress"], 40)
                    self.assertEqual(partial["current_layer"], 20)
                    self.assertEqual(partial["total_layers"], 100)

    def test_regression_and_post_printing_start_only_calibration_stop_with_identity_unverified(self):
        cases = (
            ("progress_drop", {**PRINTING["project"], "progress": 11, "curr_layer": 8, "total_layers": 100}),
            ("layer_drop", {**PRINTING["project"], "progress": 12, "curr_layer": 7, "total_layers": 100}),
            ("total_layers_change", {**PRINTING["project"], "progress": 12, "curr_layer": 8, "total_layers": 200}),
            ("post_print_auto_leveling", {**PRINTING["project"], "state": "auto_leveling"}),
            ("post_print_vibrating", {**PRINTING["project"], "state": "vibrating"}),
            ("post_print_flow_calibrating", {**PRINTING["project"], "state": "flow_calibrating"}),
            ("post_print_z_offset", {**PRINTING["project"], "state": "z_offset_calibrating"}),
            ("post_print_freq_sweep", {**PRINTING["project"], "state": "frequency_sweeping"}),
        )
        for name, second_project in cases:
            with self.subTest(case=name):
                progress = WatchProgress()
                self.assertIsNone(progress.update(PRINTING))
                result = progress.update({**PRINTING, "project": second_project})
                self.assertEqual(result, {
                    "outcome": "unknown", "reason": "identity_unverified",
                    "phase": "printing", "progress": 12, "current_layer": 8, "total_layers": 100,
                })

    def test_missing_or_hostile_initial_filename_cannot_establish_continuity(self):
        for bad_name in (None, "", "https://example.test/?token=SECRET", "bad\x1b[31m.gcode"):
            with self.subTest(bad_name=bad_name):
                emitted = []
                progress = WatchProgress(on_progress=emitted.append)
                first = {**PRINTING, "project": {**PRINTING["project"], "filename": bad_name}}
                self.assertIsNone(progress.update(first))
                second = {**PRINTING, "project": {**PRINTING["project"], "progress": 20, "curr_layer": 20}}
                result = progress.update(second)
                self.assertEqual(result["outcome"], "unknown")
                self.assertEqual(result["reason"], "identity_unverified")
                self.assertEqual(result["progress"], 12)
                self.assertNotIn("SECRET", json.dumps(result) + "\n".join(emitted))

    def test_non_placeholder_task_id_and_unrecognized_subsequent_state(self):
        progress = WatchProgress()
        first = {**PRINTING, "project": {**PRINTING["project"], "task_id": "job_1"}}
        self.assertIsNone(progress.update(first))
        same = {**PRINTING, "project": {**PRINTING["project"], "task_id": "job_1", "progress": 20, "curr_layer": 20}}
        self.assertIsNone(progress.update(same))
        different = {**PRINTING, "project": {**PRINTING["project"], "task_id": "job_2", "progress": 25, "curr_layer": 25}}
        result = progress.update(different)
        self.assertEqual(result["reason"], "job_replaced")
        self.assertEqual(result["progress"], 20)

        progress2 = WatchProgress()
        self.assertIsNone(progress2.update(PRINTING))
        unrec = progress2.update({**PRINTING, "project": {**PRINTING["project"], "state": "unexpected_fw_state"}})
        self.assertEqual(unrec["reason"], "active_job_unverified")
        self.assertEqual(unrec["progress"], 12)

    def test_stopping_transition_preserves_progress_and_emits_no_unsafe_fields(self):
        emitted = []
        progress = WatchProgress(on_progress=emitted.append)
        hostile_temp = {
            "curr_nozzle_temp": "https://example.test/?token=PRIVATE",
            "target_nozzle_temp": 99999,
            "curr_hotbed_temp": True,
            "target_hotbed_temp": float("nan"),
        }
        self.assertIsNone(progress.update({
            **PRINTING,
            "temp": hostile_temp,
            "project": {**PRINTING["project"], "remain_time": "https://example.test/?s=SECRET"},
        }))
        self.assertIsNone(progress.update({
            **PRINTING,
            "project": {**PRINTING["project"], "state": "stopping", "progress": 0, "curr_layer": 0},
        }))
        result = progress.update({**INFO, "state": "free", "project": None})
        self.assertEqual(result, {
            "outcome": "unknown", "reason": "job_disappeared",
            "phase": "stopping", "progress": 12, "current_layer": 8, "total_layers": 100,
        })
        self.assertEqual(emitted, ["printing 12% layer 8/100", "stopping 12% layer 8/100"])
        self.assertNotIn("PRIVATE", "\n".join(emitted))
        self.assertNotIn("SECRET", "\n".join(emitted))

    def test_sparse_total_layers_rejects_inconsistent_merge_and_accepts_compatible_total(self):
        # Incompatible sparse total (total_layers=4 after curr_layer=8) leaves prior snapshot intact.
        emitted_bad = []
        progress_bad = WatchProgress(on_progress=emitted_bad.append)
        self.assertIsNone(progress_bad.update({
            **INFO, "state": "busy",
            "project": {"state": "printing", "task_id": "-1", "filename": "sample.gcode",
                        "progress": 12, "curr_layer": 8},
        }))
        stopped = progress_bad.update({
            **INFO, "state": "busy",
            "project": {"state": "printing", "task_id": "-1", "filename": "sample.gcode",
                        "progress": 12, "total_layers": 4},
        })
        self.assertEqual(stopped, {
            "outcome": "unknown", "reason": "identity_unverified",
            "phase": "printing", "progress": 12, "current_layer": 8,
        })
        self.assertEqual(emitted_bad, ["printing 12% layer 8"])

        # Compatible sparse total (total_layers=100 after curr_layer=8) is accepted.
        emitted_ok = []
        progress_ok = WatchProgress(on_progress=emitted_ok.append)
        self.assertIsNone(progress_ok.update({
            **INFO, "state": "busy",
            "project": {"state": "printing", "task_id": "-1", "filename": "sample.gcode",
                        "progress": 12, "curr_layer": 8},
        }))
        self.assertIsNone(progress_ok.update({
            **INFO, "state": "busy",
            "project": {"state": "printing", "task_id": "-1", "filename": "sample.gcode",
                        "progress": 12, "total_layers": 100},
        }))
        self.assertEqual(progress_ok.partial("deadline_expired"), {
            "outcome": "unknown", "reason": "deadline_expired",
            "phase": "printing", "progress": 12, "current_layer": 8, "total_layers": 100,
        })
        self.assertEqual(emitted_ok, ["printing 12% layer 8", "printing 12% layer 8/100"])

    def test_paused_and_stopping_adopt_coherent_advancing_counters_and_preserve_high_water_on_zero(self):
        emitted = []
        progress = WatchProgress(on_progress=emitted.append)
        self.assertIsNone(progress.update(PRINTING))
        self.assertIsNone(progress.update({
            **PRINTING,
            "project": {**PRINTING["project"], "state": "paused", "progress": 20, "curr_layer": 16, "total_layers": 100},
        }))
        self.assertEqual(progress.partial("deadline_expired"), {
            "outcome": "unknown", "reason": "deadline_expired",
            "phase": "paused", "progress": 20, "current_layer": 16, "total_layers": 100,
        })
        self.assertIsNone(progress.update({
            **PRINTING,
            "project": {**PRINTING["project"], "state": "stopping", "progress": 25, "curr_layer": 20, "total_layers": 100},
        }))
        # Zeroed stopping counters preserve the latest verified 25%, layer 20/100.
        self.assertIsNone(progress.update({
            **PRINTING,
            "project": {**PRINTING["project"], "state": "stopping", "progress": 0, "curr_layer": 0, "total_layers": 0},
        }))
        result = progress.update({**INFO, "state": "free", "project": None})
        self.assertEqual(result, {
            "outcome": "unknown", "reason": "job_disappeared",
            "phase": "stopping", "progress": 25, "current_layer": 20, "total_layers": 100,
        })
        self.assertEqual(emitted, [
            "printing 12% layer 8/100",
            "paused 20% layer 16/100",
            "stopping 25% layer 20/100",
        ])


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

    def test_fresh_query_with_skew_enforces_window_retained_and_monotonic_timestamp(self):
        client = MQTT(config())
        client.sock = Mock()
        anchor_ms = 1700000020000
        reports = iter((
            (0x30, "response", 0, "ack"),
            (0x31, "report", -100, "retained_in_window"),
            (0x30, "report", -5001, "outside_skew"),
            (0x30, "report", -2000, "equal_min_timestamp"),
            (0x30, "report", -500, "fresh_skewed"),
        ))

        def receive(deadline):
            sent = client.sock.sendall.call_args.args[0]
            query = json.loads(sent[sent.index(b"{"):])
            header, kind, offset, state = next(reports)
            if kind == "response":
                ack = {"msgid": query["msgid"], "code": 0}
                return header, string("synthetic/response") + json.dumps(ack).encode()
            report = {"msgid": "printer-msg", "type": "info",
                      "timestamp": query["timestamp"] + offset, "data": {"state": state}}
            return header, string("synthetic/info/report") + json.dumps(report).encode()

        with patch("kobra_lan.mqtt.time.time", return_value=anchor_ms / 1000.0), \
                patch.object(client, "receive", side_effect=receive):
            result = client.query(
                "info",
                require_fresh=True,
                max_backward_skew_ms=5000,
                min_timestamp=anchor_ms - 2000,
            )
        self.assertEqual(result["data"]["state"], "fresh_skewed")

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
        self.root = root
        self.state_dir = root / "state"
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

    def invoke(self, args, expected, *, use_state_dir=True, return_stderr=False):
        out, err = io.StringIO(), io.StringIO()
        argv = list(args)
        if use_state_dir and "--state-dir" not in argv:
            if argv and argv[0] == "--json":
                argv = ["--json", "--state-dir", str(self.state_dir), *argv[1:]]
            else:
                argv = ["--state-dir", str(self.state_dir), *argv]
        with redirect_stdout(out), redirect_stderr(err):
            self.assertEqual(main(argv), expected)
        if return_stderr:
            return out.getvalue(), err.getvalue()
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
                self.assertNotIn("observation_id", outcome["result"])
                self.assertNotIn("observation_recorded", outcome["result"])
                self.assertEqual(self.mqtt.call_args.args[0].printer_id, device)
        self.assertEqual(self.mqtt.call_count, len(cases))
        self.assertFalse(self.state_dir.exists())

    def test_invalid_timeout_is_safe_and_precedes_target_selection(self):
        for timeout in ("0", "-1", "259201", "1.0", "1_0", "synthetic-private"):
            for fmt in ([], ["--json"]):
                with self.subTest(timeout=timeout, fmt=fmt), patch("kobra_lan.cli.Registry") as registry:
                    rendered = self.invoke([*fmt, "print", "watch", "--timeout", timeout], 2, use_state_dir=False)
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
                patch("kobra_lan.watch.time.sleep", side_effect=sleep), \
                patch("kobra_lan.watch.time.time", side_effect=[1700000000, 1700000300]):
            rendered, err_text = self.invoke(["--json", "print", "watch", "--timeout", "1"], 0, return_stderr=True)
        self.assertEqual(err_text.strip(), "printing 12% layer 8/100")
        self.assertNotIn("sample.gcode", err_text)
        envelope = json.loads(rendered)
        self.assertEqual(len(rendered.splitlines()), 1)
        self.assertEqual(envelope["schema_version"], 1)
        self.assertTrue(envelope["ok"])
        self.assertEqual(envelope["result"]["outcome"], "unknown")
        self.assertEqual(envelope["result"]["reason"], "deadline_expired")
        self.assertEqual(envelope["result"]["current_layer"], 8)
        self.assertTrue(envelope["result"]["observation_recorded"])
        obs_id = envelope["result"]["observation_id"]
        self.assertRegex(obs_id, r"^obs-[a-f0-9]{32}$")
        self.assertNotIn("sample.gcode", rendered)
        digest = hashlib.sha256(b"SyntheticDefault").hexdigest()
        obs_dir = self.state_dir / "observations" / digest[:16]
        obs_file = obs_dir / f"{obs_id}.json"
        self.assertEqual(stat.S_IMODE(obs_dir.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(obs_file.stat().st_mode), 0o600)
        saved = json.loads(obs_file.read_text())
        self.assertEqual(saved, {
            "version": 1,
            "observation_id": obs_id,
            "device_digest": digest,
            "observed_at": 1700000000,
            "ended_at": 1700000300,
            "observed_filename": "sample.gcode",
            "client_attribution": "unattributed",
            "outcome": "unknown",
            "reason": "deadline_expired",
            "phase": "printing",
            "progress": 12,
            "current_layer": 8,
            "total_layers": 100,
        })

    def test_failures_include_safe_partial_results_in_both_formats(self):
        digest = hashlib.sha256(b"SyntheticDefault").hexdigest()
        for error, exit_code, code in (
            (ProtocolError("Synthetic protocol refusal"), 2, "validation_failed"),
            (OSError("private network detail"), 3, "operation_failed"),
            (KeyboardInterrupt(), 130, "interrupted"),
        ):
            for mode in ([], ["--json"]):
                with self.subTest(error=error, mode=mode):
                    self.client.query.side_effect = [{"data": {**PRINTING, "deviceId": "SyntheticDefault"}}, error]
                    rendered, err_text = self.invoke([*mode, "print", "watch"], exit_code, return_stderr=True)
                    self.assertEqual(err_text.strip(), "printing 12% layer 8/100")
                    self.assertNotIn("private network detail", rendered + err_text)
                    self.assertNotIn("sample.gcode", rendered + err_text)
                    if mode:
                        envelope = json.loads(rendered)
                        self.assertFalse(envelope["ok"])
                        self.assertEqual(envelope["error"]["code"], code)
                        self.assertEqual(envelope["result"]["outcome"], "unknown")
                        self.assertEqual(envelope["result"]["progress"], 12)
                        self.assertTrue(envelope["result"]["observation_recorded"])
                        obs_id = envelope["result"]["observation_id"]
                        self.assertRegex(obs_id, r"^obs-[a-f0-9]{32}$")
                        saved = json.loads((self.state_dir / "observations" / digest[:16] / f"{obs_id}.json").read_text())
                        self.assertEqual(saved["reason"], code)
                        self.assertEqual(saved["client_attribution"], "unattributed")
                        self.assertEqual(saved["observed_filename"], "sample.gcode")
                    else:
                        self.assertIn("Error (" + code + ")", rendered)
                        self.assertIn("Outcome: unknown", rendered)
                        self.assertIn("Progress: 12", rendered)
                        self.assertIn("Observation recorded: yes", rendered)
                        self.assertRegex(rendered, r"Observation id: obs-[a-f0-9]{32}")

    def test_active_job_exits_persist_sanitized_records_without_touching_existing_state(self):
        digest = hashlib.sha256(b"SyntheticDefault").hexdigest()
        upload_dir = self.state_dir / digest[:16]
        starts_dir = self.state_dir / "starts" / digest[:16]
        upload_dir.mkdir(parents=True, mode=0o700)
        starts_dir.mkdir(parents=True, mode=0o700)
        existing_files = [
            upload_dir / ("a" * 64 + ".attempt"),
            upload_dir / ("a" * 64 + ".json"),
            starts_dir / ("a" * 64 + ".attempt"),
            starts_dir / ("a" * 64 + ".json"),
        ]
        for path in existing_files:
            path.write_bytes(b'{"synthetic":true}\n')
            path.chmod(0o600)
        preserved = {
            path: (stat.S_IMODE(path.stat().st_mode), path.read_bytes())
            for path in [*existing_files, *(p for p in (self.root / "private").rglob("*") if p.is_file())]
        }
        hostile_active = {
            **PRINTING,
            "deviceId": "SyntheticDefault",
            "urls": {"fileUploadurl": "http://192.0.2.10:18910/gcode_upload?s=SYNTHETIC_TOKEN"},
            "secret": "-----BEGIN PRIVATE KEY-----synthetic",
            "project": {
                **PRINTING["project"],
                "filename": "https://example.test/?token=SYNTHETIC_SECRET",
                "raw_extra": "SYNTHETIC_RAW_TELEMETRY",
            },
        }
        cases = (
            ("job_disappeared", {**INFO, "deviceId": "SyntheticDefault", "state": "free", "project": None}),
            ("job_replaced", {**PRINTING, "deviceId": "SyntheticDefault",
                              "project": {**PRINTING["project"], "filename": "other.gcode"}}),
            ("last_project_unattributed", {
                **INFO, "deviceId": "SyntheticDefault", "state": "free", "project": None,
                "last_project": {**PRINTING["project"], "state": "finished", "progress": 100},
            }),
            ("identity_unverified", {**PRINTING, "deviceId": "SyntheticDefault",
                                     "project": {**PRINTING["project"], "progress": 2, "curr_layer": 1}}),
        )
        for reason, second_report in cases:
            with self.subTest(reason=reason):
                first_report = hostile_active if reason == "job_disappeared" else {**PRINTING, "deviceId": "SyntheticDefault"}
                self.client.query.side_effect = [{"data": first_report}, {"data": second_report}]
                rendered, err_text = self.invoke(["--json", "print", "watch"], 0, return_stderr=True)
                self.assertEqual(err_text.strip(), "printing 12% layer 8/100")
                self.assertNotIn("sample.gcode", rendered + err_text)
                self.assertNotIn("SYNTHETIC_TOKEN", rendered + err_text)
                self.assertNotIn("SYNTHETIC_SECRET", rendered + err_text)
                self.assertNotIn("SYNTHETIC_RAW_TELEMETRY", rendered + err_text)
                envelope = json.loads(rendered)
                self.assertEqual(envelope["result"]["reason"], reason)
                self.assertTrue(envelope["result"]["observation_recorded"])
                obs_id = envelope["result"]["observation_id"]
                obs_path = self.state_dir / "observations" / digest[:16] / f"{obs_id}.json"
                raw_text = obs_path.read_text()
                self.assertEqual(stat.S_IMODE(obs_path.stat().st_mode), 0o600)
                for forbidden in ("SYNTHETIC_TOKEN", "SYNTHETIC_SECRET", "SYNTHETIC_RAW_TELEMETRY", "BEGIN PRIVATE KEY"):
                    self.assertNotIn(forbidden, raw_text)
                saved = json.loads(raw_text)
                self.assertEqual(saved["client_attribution"], "unattributed")
                self.assertEqual(saved["reason"], reason)
                if reason == "job_disappeared":
                    self.assertIsNone(saved["observed_filename"])
                else:
                    self.assertEqual(saved["observed_filename"], "sample.gcode")
        after = {
            path: (stat.S_IMODE(path.stat().st_mode), path.read_bytes())
            for path in preserved
        }
        self.assertEqual(preserved, after)

    def test_idle_and_pre_observation_failures_write_nothing(self):
        cases = (
            ([{"data": {**INFO, "deviceId": "SyntheticDefault", "state": "free", "project": None}}], 0),
            ([{"data": {**PRINTING, "deviceId": "SyntheticDefault", "project": {"state": "unrecognized"}}}], 0),
            ([{"data": {**INFO, "deviceId": "SyntheticDefault", "version": "2.0.2.3"}}], 2),
            ([OSError("synthetic connect error")], 3),
            ([KeyboardInterrupt()], 130),
        )
        for responses, expected in cases:
            with self.subTest(expected=expected, responses=responses):
                self.client.query.side_effect = list(responses)
                rendered = self.invoke(["--json", "print", "watch"], expected)
                envelope = json.loads(rendered)
                if "result" in envelope:
                    self.assertNotIn("observation_id", envelope["result"])
                    self.assertNotIn("observation_recorded", envelope["result"])
                self.assertFalse(self.state_dir.exists())

    def test_unsafe_observation_directory_preserves_watch_result(self):
        digest = hashlib.sha256(b"SyntheticDefault").hexdigest()
        obs_parent = self.state_dir / "observations"
        obs_parent.mkdir(parents=True, mode=0o700)
        device_dir = obs_parent / digest[:16]
        decoy = self.root / "decoy"
        decoy.mkdir(mode=0o700)

        # Case 1: symlinked device observation directory
        os.symlink(decoy, device_dir)
        self.client.query.side_effect = [
            {"data": {**PRINTING, "deviceId": "SyntheticDefault"}},
            {"data": {**INFO, "deviceId": "SyntheticDefault", "state": "free", "project": None}},
        ]
        rendered, _ = self.invoke(["--json", "print", "watch"], 0, return_stderr=True)
        envelope = json.loads(rendered)
        self.assertTrue(envelope["ok"])
        self.assertEqual(envelope["result"]["outcome"], "unknown")
        self.assertEqual(envelope["result"]["reason"], "job_disappeared")
        self.assertFalse(envelope["result"]["observation_recorded"])
        self.assertNotIn("observation_id", envelope["result"])
        self.assertTrue(device_dir.is_symlink())
        self.assertEqual(list(decoy.iterdir()), [])
        device_dir.unlink()

        # Case 2: non-private (0755) device observation directory across normal stop and interrupt
        device_dir.mkdir(mode=0o755)
        device_dir.chmod(0o755)
        for second, expected_exit, expected_reason in (
            ({"data": {**INFO, "deviceId": "SyntheticDefault", "state": "free", "project": None}}, 0, "job_disappeared"),
            (KeyboardInterrupt(), 130, "interrupted"),
        ):
            with self.subTest(expected_exit=expected_exit):
                self.client.query.side_effect = [{"data": {**PRINTING, "deviceId": "SyntheticDefault"}}, second]
                rendered, _ = self.invoke(["--json", "print", "watch"], expected_exit, return_stderr=True)
                envelope = json.loads(rendered)
                self.assertEqual(envelope["result"]["outcome"], "unknown")
                self.assertEqual(envelope["result"]["reason"], expected_reason)
                self.assertFalse(envelope["result"]["observation_recorded"])
                self.assertNotIn("observation_id", envelope["result"])
                self.assertEqual(stat.S_IMODE(device_dir.stat().st_mode), 0o755)
                self.assertEqual(list(device_dir.iterdir()), [])

    def test_interrupt_after_initial_record_reuses_single_observation_id(self):
        digest = hashlib.sha256(b"SyntheticDefault").hexdigest()
        self.client.query.side_effect = [
            {"data": {**PRINTING, "deviceId": "SyntheticDefault"}},
            {"data": {**INFO, "deviceId": "SyntheticDefault", "state": "free", "project": None}},
        ]
        from kobra_lan import cli as cli_mod

        real_emit = cli_mod.emit
        calls = 0

        def interrupt_first_emit(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise KeyboardInterrupt()
            return real_emit(*args, **kwargs)

        with patch("kobra_lan.cli.emit", side_effect=interrupt_first_emit):
            rendered, _ = self.invoke(["--json", "print", "watch"], 130, return_stderr=True)
        envelope = json.loads(rendered)
        self.assertFalse(envelope["ok"])
        self.assertEqual(envelope["error"]["code"], "interrupted")
        self.assertTrue(envelope["result"]["observation_recorded"])
        obs_id = envelope["result"]["observation_id"]
        obs_dir = self.state_dir / "observations" / digest[:16]
        files = list(obs_dir.glob("obs-*.json"))
        self.assertEqual(files, [obs_dir / f"{obs_id}.json"])
        saved = json.loads(files[0].read_text())
        self.assertEqual(saved["observation_id"], obs_id)
        self.assertEqual(saved["reason"], "interrupted")

    def test_live_stderr_progress_and_quiet_flag_in_text_and_json_modes(self):
        digest = hashlib.sha256(b"SyntheticDefault").hexdigest()
        reports = [
            {"data": {
                **INFO, "deviceId": "SyntheticDefault", "state": "busy",
                "temp": {"curr_nozzle_temp": 140, "target_nozzle_temp": 140,
                         "curr_hotbed_temp": 60, "target_hotbed_temp": 60},
                "project": {"state": "auto_leveling", "task_id": "-1", "filename": "sample.gcode"},
            }},
            {"data": {
                **INFO, "deviceId": "SyntheticDefault", "state": "busy",
                "temp": {"curr_nozzle_temp": 220, "target_nozzle_temp": 220,
                         "curr_hotbed_temp": 60, "target_hotbed_temp": 60},
                "project": {"state": "printing", "task_id": "-1", "filename": "sample.gcode",
                            "progress": 50, "curr_layer": 50, "total_layers": 100, "remain_time": 15},
            }},
            {"data": {
                **INFO, "deviceId": "SyntheticDefault", "state": "busy",
                "temp": {"curr_nozzle_temp": 221, "target_nozzle_temp": 220,
                         "curr_hotbed_temp": 60, "target_hotbed_temp": 60},
                "project": {"state": "printing", "task_id": "-1", "filename": "sample.gcode",
                            "progress": 50, "curr_layer": 50, "total_layers": 100, "remain_time": 15},
            }},
            {"data": {
                **INFO, "deviceId": "SyntheticDefault", "state": "busy",
                "temp": {"curr_nozzle_temp": 180, "target_nozzle_temp": 0,
                         "curr_hotbed_temp": 55, "target_hotbed_temp": 0},
                "project": {"state": "stopping", "task_id": "-1", "filename": "sample.gcode",
                            "progress": 50, "curr_layer": 50, "total_layers": 100},
            }},
            {"data": {**INFO, "deviceId": "SyntheticDefault", "state": "free", "project": None}},
        ]

        for mode in ([], ["--json"]):
            for quiet in (False, True):
                with self.subTest(mode=mode, quiet=quiet):
                    self.client.query.side_effect = list(reports)
                    argv = [*mode, "print", "watch", *(["--quiet"] if quiet else [])]
                    rendered, err_text = self.invoke(argv, 0, return_stderr=True)
                    self.assertNotIn("sample.gcode", rendered + err_text)
                    if quiet:
                        self.assertEqual(err_text, "")
                    else:
                        lines = err_text.splitlines()
                        self.assertEqual(lines, [
                            "preparing (auto_leveling) nozzle 140/140C bed 60/60C",
                            "printing 50% layer 50/100 remaining 15m nozzle 220/220C bed 60/60C",
                            "stopping 50% layer 50/100 nozzle 180/0C bed 55/0C",
                        ])
                    if mode:
                        self.assertEqual(len(rendered.splitlines()), 1)
                        envelope = json.loads(rendered)
                        self.assertTrue(envelope["ok"])
                        self.assertEqual(envelope["result"]["outcome"], "unknown")
                        self.assertEqual(envelope["result"]["reason"], "job_disappeared")
                        self.assertEqual(envelope["result"]["phase"], "stopping")
                        self.assertEqual(envelope["result"]["progress"], 50)
                        self.assertEqual(envelope["result"]["current_layer"], 50)
                        self.assertEqual(envelope["result"]["total_layers"], 100)
                        obs_id = envelope["result"]["observation_id"]
                        saved = json.loads((self.state_dir / "observations" / digest[:16] / f"{obs_id}.json").read_text())
                        self.assertEqual(saved["phase"], "stopping")
                        self.assertEqual(saved["progress"], 50)
                    else:
                        self.assertIn("Outcome: unknown", rendered)
                        self.assertIn("Reason: job_disappeared", rendered)
                        self.assertIn("Phase: stopping", rendered)
                        self.assertIn("Progress: 50", rendered)
