"""Doctor uses synthetic transports only, including real TLS pin/auth ordering."""
from contextlib import redirect_stdout
import hashlib
import io
from itertools import combinations
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from kobra_lan import diagnostics as d
from kobra_lan.cli import main
from kobra_lan.mqtt import MQTT, MQTTFailure
from kobra_lan.profiles import Registry
from test_profiles import fixture

INFO = {'model':'Anycubic Kobra X','version':'2.0.2.2','state':'printing','deviceId':'Synthetic01','modelId':20030}


class HealthyMQTT:
    calls = []
    def __init__(self, cfg, timeout=12, deadline=None, observer=None):
        self.observer = observer
        assert timeout <= 12
        assert math.isfinite(deadline)
    def __enter__(self):
        self.observer('tls_pin'); self.observer('mqtt_auth'); return self
    def __exit__(self,*args): pass
    def query(self, kind):
        self.calls.append(kind)
        assert kind == 'info'
        return {'code':200,'data':{**INFO, 'sessionToken':'secret-report\x1b[31m'}}


class DoctorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.registry = Registry(Path(self.tmp.name)/'private')
        with self.registry.lock():
            fixture(self.registry.reserve('bancada'))
            self.registry.register('bancada','2.0.2.2')
        self.registry.select('bancada')
        HealthyMQTT.calls = []

    def run_doctor(self, client=HealthyMQTT, tcp=None):
        with patch.object(d,'MQTT',client), patch.object(d.socket,'create_connection',side_effect=tcp) as connect:
            report, code = d.diagnose(self.registry)
        for call in connect.call_args_list:
            self.assertTrue(0 < call.kwargs['timeout'] <= 12)
        return report,code

    def test_healthy_busy_report_safe_and_byte_preservation(self):
        before = {str(p):(p.read_bytes(),p.stat().st_mode) for p in self.registry.root.rglob('*') if p.is_file()}
        report,code = self.run_doctor()
        self.assertEqual(code,0); self.assertTrue(report['ok']); self.assertTrue(report['result']['healthy'])
        self.assertEqual(report['result']['version'],1)
        self.assertEqual([c['stage'] for c in report['result']['checks']],list(d.STAGES))
        for c in report['result']['checks']:
            self.assertEqual(set(c),{'stage','status','code','message','next_step'})
            self.assertEqual(c['status'],'passed')
        self.assertEqual(HealthyMQTT.calls,['info'])
        for secret in ('secret-password','secret-report','client.key','sessionToken','\x1b'):
            self.assertNotIn(secret,json.dumps(report))
        self.assertEqual(before,{str(p):(p.read_bytes(),p.stat().st_mode) for p in self.registry.root.rglob('*') if p.is_file()})

    def test_configuration_and_dependency_failures_have_no_network(self):
        self.registry.path('bancada').unlink()
        with patch.object(d.socket,'create_connection') as network, patch.object(d,'dependencies',side_effect=ImportError('secret\x1b')):
            report,code = d.diagnose(self.registry)
        network.assert_not_called(); self.assertEqual(code,3)
        self.assertEqual([c['status'] for c in report['result']['checks']],['failed','failed']+['skipped']*6)
        self.assertNotIn('secret',json.dumps(report))
        fixture(self.registry.path('bancada'))
        self.registry.path('bancada').chmod(0o644)
        with patch.object(d.socket,'create_connection') as network:
            self.assertEqual(d.diagnose(self.registry)[1],3)
        network.assert_not_called()

    def test_http_failure_does_not_block_mqtt_and_exit3_wins(self):
        def tcp(address, timeout):
            if address[1] == 18910: raise OSError('secret-network\x1b')
            return Mock(__enter__=Mock(),__exit__=Mock())
        report,code = self.run_doctor(tcp=tcp)
        self.assertEqual(code,3); self.assertEqual(report['result']['checks'][2]['status'],'failed')
        self.assertEqual(report['result']['checks'][-1]['status'],'passed')
        class Unsupported(HealthyMQTT):
            def query(self,kind): return {'code':200,'data':{**INFO,'version':'unsupported-secret\x1b'}}
        report,code = self.run_doctor(client=Unsupported,tcp=tcp)
        self.assertEqual(code,3); self.assertEqual(report['result']['checks'][-1]['code'],'outside_qualification')
        self.assertNotIn('secret',json.dumps(report))

    def test_mqtt_tcp_timeout_skips_dependents(self):
        def tcp(address, timeout):
            if address[1] == 9883: raise TimeoutError('private')
            return Mock(__enter__=Mock(),__exit__=Mock())
        with patch.object(d,'MQTT') as mqtt, patch.object(d.socket,'create_connection',side_effect=tcp):
            report,code = d.diagnose(self.registry)
        mqtt.assert_not_called(); self.assertEqual(code,3)
        self.assertEqual([c['status'] for c in report['result']['checks'][3:]],['failed']+['skipped']*4)

    def test_typed_failure_stages_and_compatibility(self):
        for stage,category,exit_code in (('tls_pin','pin_mismatch',2),('mqtt_auth','authentication_rejected',2),
                                         ('mqtt_auth','subscription_rejected',2),('status','timeout',3)):
            class Failing(HealthyMQTT):
                def __enter__(self):
                    if stage != 'tls_pin': self.observer('tls_pin')
                    if stage == 'status': self.observer('mqtt_auth'); return self
                    raise MQTTFailure(stage,category,'secret\x1b',exit_code)
                def query(self,kind): raise MQTTFailure(stage,category,'secret\x1b',exit_code)
            report,code = self.run_doctor(client=Failing)
            self.assertEqual(code,exit_code)
            self.assertEqual(next(c for c in report['result']['checks'] if c['stage']==stage)['code'],category)
            self.assertNotIn('secret',json.dumps(report))
        for changes in ({'deviceId':'Other01'},{'modelId':9},{'modeId':9},{'version':'other'},{'model':None},{'state':'\x1b'}):
            class Unsupported(HealthyMQTT):
                def query(self,kind): return {'code':200,'data':{**INFO,**changes}}
            report,code = self.run_doctor(client=Unsupported)
            self.assertEqual(code,2); self.assertEqual(report['result']['checks'][-1]['status'],'failed')

    def test_real_transport_pin_before_credentials_and_auth_rejections(self):
        cfg = self.registry.load('bancada')
        for changed, packets, stage, category in (
            (True,[], 'tls_pin','pin_mismatch'),
            (False,[(0x20,b'\x00\x05')], 'mqtt_auth','authentication_rejected'),
            (False,[(0x20,b'\x00\x00'),(0x90,b'\x00\x01\x80')], 'mqtt_auth','subscription_rejected')):
            cfg.tls_sha256 = 'a'*64 if changed else hashlib.sha256(b'synthetic-cert').hexdigest()
            ctx, tls, raw = Mock(),Mock(),Mock()
            ctx.wrap_socket.return_value=tls; tls.getpeercert.return_value=b'synthetic-cert'
            observed=[]
            with patch('kobra_lan.mqtt.ssl.SSLContext',return_value=ctx), \
                    patch('kobra_lan.mqtt.socket.create_connection',return_value=raw), \
                    patch.object(MQTT,'receive',side_effect=packets):
                client = MQTT(cfg,observer=observed.append)
                with self.assertRaises(MQTTFailure) as caught:
                    client.__enter__()
            self.assertEqual(caught.exception.stage,stage); self.assertEqual(caught.exception.code,category)
            self.assertEqual(observed, [] if changed else ['tls_pin'])
            if changed:
                tls.sendall.assert_not_called()
            else:
                tls.sendall.assert_called()
            tls.close.assert_called_once()

    def test_shared_deadline_and_no_retries(self):
        clock = {'now': 100.0}
        timeouts = []
        def tcp(address, timeout):
            timeouts.append(timeout)
            clock['now'] += 12 if len(timeouts) == 1 else 1
            return Mock(__enter__=Mock(),__exit__=Mock())
        def mqtt(cfg, **kwargs):
            self.assertEqual(kwargs['deadline'],100+total)
            self.assertEqual(clock['now'],113)
            self.assertLessEqual(kwargs['timeout'],12)
            return HealthyMQTT(cfg,**kwargs)
        # Verify the real deadline and a shortened budget that exposes cumulative accounting.
        for total,expected in ((60,[12,12]),(15,[12,3])):
            clock['now']=100
            timeouts.clear()
            with patch.object(d.time,'monotonic',side_effect=lambda: clock['now']), \
                    patch.object(d,'NETWORK_TIMEOUT',total), patch.object(d.socket,'create_connection',side_effect=tcp), \
                    patch.object(d,'MQTT',side_effect=mqtt):
                report,code = d.diagnose(self.registry)
            self.assertEqual(code,0)
            self.assertEqual(timeouts,expected)
        clock['now']=100
        def expired(address, timeout):
            self.assertEqual(timeout,12)
            clock['now']=161
            raise TimeoutError
        with patch.object(d.time,'monotonic',side_effect=lambda: clock['now']), \
                patch.object(d.socket,'create_connection',side_effect=expired) as network, \
                patch.object(d,'MQTT') as mqtt_client:
            report,code=d.diagnose(self.registry)
        self.assertEqual(code,3); self.assertEqual(network.call_count,1); mqtt_client.assert_not_called()
        self.assertEqual(report['result']['checks'][2]['status'],'failed')
        cfg = self.registry.load('bancada')
        client = MQTT(cfg,deadline=5); client.stage='status'; client.sock=Mock()
        with patch('kobra_lan.mqtt.time.monotonic',return_value=6):
            self.assertRaises(MQTTFailure,client.query,'info')
        client.sock.sendall.assert_not_called()

    def test_optional_report_identity_can_be_omitted_without_writes_or_extra_queries(self):
        before = {str(p): (p.read_bytes(), p.stat().st_mode) for p in self.registry.root.rglob('*') if p.is_file()}
        optional = ('deviceId', 'modelId', 'modeId')
        complete = {**INFO, 'modeId': INFO['modelId']}
        omissions = [()] + [absent for size in range(1, 4) for absent in combinations(optional, size)]
        for absent in omissions:
            class MissingIdentity(HealthyMQTT):
                def query(self,kind):
                    self.calls.append(kind)
                    assert kind == 'info'
                    return {'code':200,'data':{key:value for key,value in complete.items() if key not in absent}}
            for mode in ([], ['--json']):
                HealthyMQTT.calls = []
                stdout = io.StringIO()
                with patch('kobra_lan.cli.Registry', return_value=self.registry), \
                        patch.object(d, 'MQTT', MissingIdentity), patch.object(d.socket, 'create_connection'), \
                        redirect_stdout(stdout):
                    self.assertEqual(main([*mode, 'doctor']), 0)
                if mode:
                    report = json.loads(stdout.getvalue())
                    self.assertTrue(report['ok'])
                    self.assertTrue(report['result']['healthy'])
                    self.assertTrue(all(check['status'] == 'passed' for check in report['result']['checks']))
                if absent:
                    self.assertIn('optional MQTT identity fields omitted: ' + ', '.join(absent), stdout.getvalue())
                else:
                    self.assertNotIn('optional MQTT identity fields omitted', stdout.getvalue())
                self.assertEqual(HealthyMQTT.calls, ['info'])
        self.assertEqual(before, {str(p): (p.read_bytes(), p.stat().st_mode)
                                 for p in self.registry.root.rglob('*') if p.is_file()})
        alias={**INFO,'modeId':INFO['modelId']}; del alias['modelId']
        self.assertIsNone(d.compatibility_issue(self.registry.load('bancada'),alias))

    def test_missing_required_evidence_is_distinct_from_contradiction(self):
        for missing in ('model', 'version', 'state'):
            for value in ('absent', None):
                info = {key: val for key, val in INFO.items() if key != missing}
                if value is None:
                    info[missing] = None
                class Incomplete(HealthyMQTT):
                    def query(self, kind): return {'code': 200, 'data': info}
                with self.subTest(missing=missing, value=value):
                    report, code = self.run_doctor(client=Incomplete)
                    self.assertEqual(code, 2)
                    self.assertEqual(report['result']['checks'][-2]['status'], 'passed')
                    self.assertEqual(report['result']['checks'][-1]['code'], 'qualification_incomplete')

        # Optional does not mean ignored: reject conflicting/null IDs even when
        # the other optional identifiers are absent, or required evidence is missing.
        for key, value in (('deviceId', 'Other01'), ('deviceId', None), ('modelId', 9),
                           ('modelId', None), ('modeId', 9), ('modeId', None)):
            info = {k: v for k, v in INFO.items() if k not in ('deviceId', 'modelId', 'modeId', 'version')}
            info[key] = value
            class Contradictory(HealthyMQTT):
                def query(self, kind): return {'code': 200, 'data': info}
            with self.subTest(key=key, value=value):
                report, code = self.run_doctor(client=Contradictory)
                self.assertEqual(code, 2)
                self.assertEqual(report['result']['checks'][-1]['code'], 'outside_qualification')

    def test_cli_envelope_and_conflict(self):
        stdout=io.StringIO()
        with patch('kobra_lan.cli.Registry',return_value=self.registry), patch.object(d,'MQTT',HealthyMQTT), \
                patch.object(d.socket,'create_connection'), redirect_stdout(stdout):
            self.assertEqual(main(['--json','doctor']),0)
        self.assertTrue(json.loads(stdout.getvalue())['result']['healthy'])
        stdout=io.StringIO()
        with redirect_stdout(stdout), patch.object(d.socket,'create_connection') as network:
            self.assertEqual(main(['--printer','bancada','--config','unused','doctor']),2)
        network.assert_not_called()

    def test_both_cli_formats_preserve_failed_stages_and_precedence(self):
        outputs = []
        for mode in ([], ['--json']):
            stdout = io.StringIO()
            with patch('kobra_lan.cli.Registry', return_value=self.registry), \
                    patch.object(d, 'MQTT', HealthyMQTT), \
                    patch.object(d.socket, 'create_connection', side_effect=OSError('private network detail')), \
                    redirect_stdout(stdout):
                self.assertEqual(main([*mode, 'doctor']), 3)
            outputs.append(stdout.getvalue())
        report = json.loads(outputs[1])
        self.assertEqual(report['error']['code'], 'diagnostic_failed')
        self.assertFalse(report['result']['healthy'])
        for check in report['result']['checks']:
            self.assertIn(check['stage'], outputs[0])
            self.assertIn(check['status'], outputs[0])
        self.assertNotIn('private network detail', ''.join(outputs))

    def test_missing_dependency_does_not_crash_cli_import(self):
        script = '''
import builtins, sys
original = builtins.__import__
def blocked(name,*args,**kwargs):
    if name.startswith('cryptography'): raise ImportError('synthetic absent crypto')
    return original(name,*args,**kwargs)
builtins.__import__ = blocked
from kobra_lan.cli import main
sys.exit(main(['--help']))
'''
        process=subprocess.run([sys.executable,'-c',script],capture_output=True,text=True)
        self.assertEqual(process.returncode,0,process.stderr)
        self.assertIn('doctor',process.stdout)

    def test_doctor_missing_crypto_in_a_fresh_process(self):
        script = """
import sys
class AbsentCrypto:
    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith('cryptography'): raise ImportError('secret missing dependency')
sys.meta_path.insert(0, AbsentCrypto())
from kobra_lan.cli import main
sys.exit(main(['--json', '--config', '/nonexistent-synthetic/config.json', 'doctor']))
"""
        process = subprocess.run([sys.executable,'-c',script],capture_output=True,text=True)
        self.assertEqual(process.returncode,3,process.stderr)
        report=json.loads(process.stdout)
        self.assertEqual(report['result']['checks'][1]['code'],'runtime_dependency_unavailable')
        self.assertNotIn('secret',process.stdout)
