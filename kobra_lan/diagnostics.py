"""Bounded, pinned, read-only diagnosis. Reports contain only allowlisted fields."""
from contextlib import ExitStack
import importlib
import socket
import time

from .config import ProtocolError
from .mqtt import MQTT, MQTTFailure, MQTTIOFailure
from .pairing import QUALIFIED_FIRMWARE
from .printer import payload_data
from .profiles import ProfileSelectionError

STAGES = ('configuration', 'dependencies', 'http_tcp', 'mqtt_tcp', 'tls_pin', 'mqtt_auth', 'status', 'compatibility')
STAGE_TIMEOUT = 12
NETWORK_TIMEOUT = 60
MESSAGES = {
    'configuration': 'Selected local configuration is loadable',
    'dependencies': 'Required runtime dependencies are importable',
    'http_tcp': 'Configured HTTP port accepts TCP; HTTP protocol was not tested',
    'mqtt_tcp': 'Configured MQTT port accepts TCP; authentication was not tested here',
    'tls_pin': 'Server certificate matches the saved fingerprint',
    'mqtt_auth': 'Pinned MQTT authentication and subscription succeeded',
    'status': 'A fresh correlated info report was received',
    'compatibility': 'Observed identity matches model 20030 / firmware 2.0.2.2 qualification',
}
MQTT_STAGES = ('tls_pin', 'mqtt_auth', 'status')


def check(stage, status, code, message, next_step=None):
    return {'stage': stage, 'status': status, 'code': code, 'message': message, 'next_step': next_step}


def dependencies():
    for name in ('cryptography', 'cryptography.x509', 'cryptography.hazmat.primitives.serialization'):
        importlib.import_module(name)


def compatible(cfg, info):
    state = info.get('state')
    return (info.get('model') == 'Anycubic Kobra X' and info.get('version') == QUALIFIED_FIRMWARE
            and any(k in info for k in ('modelId', 'modeId'))
            and all(str(info[k]) == str(cfg.type_id) for k in ('modelId', 'modeId') if k in info)
            and info.get('deviceId') == cfg.printer_id
            and isinstance(state, str) and 0 < len(state) <= 80 and state.isascii() and state.isprintable())


def budget(end):
    remaining = end - time.monotonic()
    if remaining <= 0:
        raise TimeoutError
    return min(STAGE_TIMEOUT, remaining)


def mqtt_failure(error):
    """Translate typed failures using only allowlisted diagnostic fields."""
    stage = error.stage if error.stage in MQTT_STAGES else 'status'
    if isinstance(error, MQTTIOFailure):
        return stage, 'network_or_tls_io_failed', 3
    known = {'pin_mismatch', 'authentication_rejected', 'subscription_rejected', 'timeout', 'protocol_rejected'}
    code = error.code if error.code in known else 'protocol_rejected'
    return stage, code, 3 if error.exit_code == 3 else 2


class DiagnosticReport:
    def __init__(self):
        self.checks = {stage: check(stage, 'skipped', 'dependency_failed', 'A required earlier check did not pass') for stage in STAGES}
        self.exits = []
        self.target = None

    def passed(self, stage):
        self.checks[stage] = check(stage, 'passed', 'ok', MESSAGES[stage])

    def failed(self, stage, code, exit_code, message, next_step):
        self.checks[stage] = check(stage, 'failed', code, message, next_step)
        self.exits.append(exit_code)

    def configuration(self, registry, stack, config, name):
        try:
            cfg, source = stack.enter_context(registry.access(config, name))
            self.target = {**source, 'host': cfg.host, 'model_id': cfg.type_id, 'printer_id': cfg.printer_id}
            self.passed('configuration')
            return cfg
        except ProfileSelectionError:
            self.failed('configuration', 'selection_or_config_invalid', 2, 'Selected target or local configuration is invalid',
                        'Inspect printer list/info and explicitly choose a valid --printer or --config; preserve existing files')
        except (ProtocolError, OSError, ValueError, TypeError, KeyError):
            self.failed('configuration', 'local_config_unavailable', 3, 'Selected local configuration cannot be loaded',
                        'Inspect local paths, ownership and private permissions; preserve existing config and PEMs')
        return None

    def runtime_dependencies(self):
        try:
            dependencies()
            self.passed('dependencies')
        except (ImportError, OSError, ValueError):
            self.failed('dependencies', 'runtime_dependency_unavailable', 3, 'Required cryptography runtime cannot be imported',
                        'Install the declared cryptography runtime using the documented Python or distribution package')

    def tcp(self, cfg, end):
        for stage, port in (('http_tcp', cfg.http_port), ('mqtt_tcp', cfg.mqtt_port)):
            try:
                with socket.create_connection((cfg.host, port), timeout=budget(end)):
                    self.passed(stage)
            except (OSError, ValueError, TypeError, OverflowError):
                self.failed(stage, 'tcp_unavailable', 3, 'Configured port did not accept a bounded TCP connection',
                            'Check the saved address, configured port, LAN mode, power and firewall; do not provision again')

    def compatibility(self, cfg, info):
        if compatible(cfg, info):
            self.passed('compatibility')
        else:
            self.failed('compatibility', 'outside_qualification', 2,
                        'Observed identity or firmware is missing, conflicting or outside qualification',
                        'Verify the target locally; only matching Kobra X model 20030 / firmware 2.0.2.2 is qualified')

    def pending_mqtt_stage(self):
        return next((stage for stage in MQTT_STAGES if self.checks[stage]['status'] != 'passed'), 'status')

    def mqtt(self, cfg, end):
        try:
            # One session, no reconnect. TLS pin is checked before MQTT CONNECT.
            with MQTT(cfg, timeout=STAGE_TIMEOUT, deadline=end, observer=self.passed) as client:
                info = payload_data(client.query('info'))
                self.passed('status')
                self.compatibility(cfg, info)
        except (MQTTFailure, MQTTIOFailure) as error:
            stage, code, exit_code = mqtt_failure(error)
            self.failed(stage, code, exit_code, 'Pinned MQTT verification failed at this stage',
                        'Inspect saved trust, certificate/key files and LAN access locally; never accept a changed pin or repeat provisioning automatically')
        except ProtocolError:
            self.failed('status', 'fresh_status_rejected', 2, 'No valid fresh correlated status could be verified',
                        'Inspect the selected target and protocol compatibility without replaying any command')
        except (OSError, ValueError, TypeError, KeyError, OverflowError):
            self.failed(self.pending_mqtt_stage(), 'network_or_local_io_failed', 3, 'Bounded verification could not complete',
                        'Check local certificate/key validity and network access; no command was retried')

    def envelope(self):
        exit_code = max(self.exits, default=0)
        result = {'version': 1, 'target': self.target, 'checks': [self.checks[s] for s in STAGES], 'healthy': exit_code == 0}
        envelope = {'ok': exit_code == 0, 'result': result}
        if exit_code:
            envelope['error'] = 'Connection diagnosis failed; inspect the ordered checks and next steps'
        return envelope, exit_code


def diagnose(registry, config=None, name=None):
    report = DiagnosticReport()
    with ExitStack() as stack:
        cfg = report.configuration(registry, stack, config, name)
        report.runtime_dependencies()
        if cfg is not None and not report.exits:
            end = time.monotonic() + NETWORK_TIMEOUT
            report.tcp(cfg, end)
            if report.checks['mqtt_tcp']['status'] == 'passed':
                report.mqtt(cfg, end)
    return report.envelope()
