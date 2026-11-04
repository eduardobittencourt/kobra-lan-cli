"""Synthetic homes, registry failure injection and offline target selection."""
from contextlib import redirect_stdout
from dataclasses import asdict
import io
import json
import multiprocessing
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from kobra_lan.config import Config, ProtocolError
from kobra_lan.profiles import Registry, ProfileLocalError, validate_name


def fixture(path, device='Synthetic01'):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    stage = path.parent / ('.pair-' + 'a' * 32)
    stage.mkdir(mode=0o700, exist_ok=True)
    for name in ('client.crt', 'client.key'):
        (stage / name).write_text('synthetic-' + name)
        (stage / name).chmod(0o600)
    cfg = Config('192.0.2.10', 20030, device, 'secret-user', 'secret-password',
                 str(stage / 'client.crt'), str(stage / 'client.key'), 'a' * 64)
    path.write_text(json.dumps(asdict(cfg))); path.chmod(0o600)
    return cfg


def hold_lock(root, ready, release):
    with Registry(root).lock():
        ready.set(); release.wait(5)


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / 'private'
        self.registry = Registry(self.root)

    def add_profile(self, name='bancada'):
        with self.registry.lock():
            path = self.registry.reserve(name)
            cfg = fixture(path)
            self.registry.register(name, '2.0.2.2')
        return cfg

    def test_names_and_read_only_empty(self):
        for name in ('a', 'bancada-2', 'a' * 48):
            self.assertEqual(validate_name(name), name)
        for name in ('', 'A', '../a', '/a', 'a/b', 'a b', 'a\n', 'a' * 49, '2a'):
            self.assertRaises(ProtocolError, validate_name, name)
        self.assertEqual(self.registry.inventory()['profiles'], [])
        self.assertFalse(self.root.exists())

    def test_managed_modes_existing_and_symlinks(self):
        self.add_profile()
        self.assertEqual(self.registry.load('bancada').printer_id, 'Synthetic01')
        for path in (self.root, self.root/'profiles', self.registry.path('bancada').parent):
            self.assertEqual(path.stat().st_mode & 0o777, 0o700)
        self.assertEqual((self.root/'profiles.json').stat().st_mode & 0o777, 0o600)
        with self.registry.lock():
            self.assertRaises(ProtocolError, self.registry.reserve, 'bancada')
            (self.root/'profiles'/'alias').symlink_to(self.registry.path('bancada').parent)
            self.assertRaises(ProtocolError, self.registry.reserve, 'alias')
        path = self.registry.path('bancada'); path.chmod(0o644)
        self.assertRaises(ProfileLocalError, self.registry.load, 'bancada')
        path.chmod(0o600); raw = path.read_bytes(); path.unlink()
        target = self.root/'outside'; target.write_bytes(raw); target.chmod(0o600)
        path.symlink_to(target)
        self.assertRaises(OSError, self.registry.load, 'bancada')

    def test_unknown_version_and_unsafe_registry(self):
        self.add_profile()
        index = self.root/'profiles.json'
        original = index.read_bytes()
        for content in ({'version': 2}, {'version': 1, 'profiles': {'../bad': {}}, 'default': None}):
            index.write_text(json.dumps(content))
            self.assertRaises(ProfileLocalError, self.registry.read)
            with self.registry.lock():
                self.assertRaises(ProfileLocalError, self.registry.write, self.registry.empty())
            self.assertEqual(json.loads(index.read_text()), content)
        index.write_bytes(original); index.chmod(0o644)
        self.assertRaises(ProfileLocalError, self.registry.read)
        index.unlink(); index.symlink_to(self.registry.path('bancada'))
        self.assertRaises(OSError, self.registry.read)

    def test_default_states_and_failures(self):
        self.add_profile()
        self.assertIsNone(self.registry.read()['default'])
        self.registry.select('bancada')
        self.assertEqual(self.registry.resolve()[1]['name'], 'bancada')
        self.assertEqual(self.registry.resolve(config=(self.root/'explicit.json'))[0], (self.root/'explicit.json'))
        self.assertRaises(ProtocolError, self.registry.resolve, (self.root/'explicit.json'), 'bancada')
        self.assertRaises(ProtocolError, self.registry.resolve, name='unknown')
        self.registry.path('bancada').unlink()
        self.assertRaises(OSError, self.registry.select, 'bancada')
        self.assertEqual(self.registry.read()['default'], {'name': 'bancada'})
        with self.registry.lock():
            data = self.registry.read(); data['default'] = None; self.registry.write(data)
        self.assertRaises(ProtocolError, self.registry.resolve)

    def test_atomic_failures_never_replace_config(self):
        self.add_profile(); before = self.registry.path('bancada').read_bytes()
        old = self.registry.read(); new = {**old, 'default': {'name': 'bancada'}}
        for operation in ('replace', 'fsync'):
            with self.registry.lock(), patch('kobra_lan.profiles.os.'+operation, side_effect=OSError('secret')):
                self.assertRaises(OSError, self.registry.write, new)
            self.assertEqual(self.registry.read(), old)
        real_fsync = os.fsync
        calls = 0
        def fail_after_replace(fd):
            nonlocal calls
            calls += 1
            if calls == 2: raise OSError('injected after commit')
            return real_fsync(fd)
        with self.registry.lock(), patch('kobra_lan.profiles.os.fsync', side_effect=fail_after_replace):
            self.assertRaises(OSError, self.registry.write, new)
        self.assertEqual(self.registry.read(), new)
        self.assertEqual(self.registry.path('bancada').read_bytes(), before)
        self.assertEqual(list(self.root.glob('.profiles-*')), [])

    def test_bounded_concurrent_writers_and_shared_leases(self):
        self.add_profile()
        ready, release = multiprocessing.Event(), multiprocessing.Event()
        process = multiprocessing.Process(target=hold_lock, args=(self.root, ready, release))
        process.start()
        try:
            self.assertTrue(ready.wait(3))
            with self.assertRaisesRegex(ProfileLocalError, 'busy'):
                with self.registry.lock(timeout=0.03): pass
        finally:
            release.set(); process.join(3)
        with self.registry.access(name='bancada'):
            with self.assertRaisesRegex(ProfileLocalError, 'busy'):
                with self.registry.lock(timeout=0.03): pass
        with self.registry.lock(timeout=0): pass

    def test_unavailable_inventory_and_no_secrets(self):
        self.add_profile('bancada'); self.add_profile('oficina')
        self.registry.path('bancada').unlink()
        inventory = self.registry.inventory()
        self.assertEqual([p['available'] for p in inventory['profiles']], [False, True])
        self.assertNotIn('secret-', json.dumps(inventory))
        self.assertNotIn('client.key', json.dumps(inventory))


class CLITests(StorageTests):
    def invoke(self, *args):
        from kobra_lan.cli import main
        stdout = io.StringIO()
        with patch('kobra_lan.cli.Registry', return_value=self.registry), redirect_stdout(stdout), \
                patch('socket.create_connection', side_effect=AssertionError('network forbidden')):
            code = main(["--json", *args])
        return code, json.loads(stdout.getvalue())

    def test_local_commands_and_selector_conflicts(self):
        self.add_profile()
        self.assertEqual(self.invoke('printer', 'list')[0], 0)
        self.assertEqual(self.invoke('printer', 'info', 'bancada')[1]['result']['host'], '192.0.2.10')
        self.assertEqual(self.invoke('printer', 'use', 'bancada')[0], 0)
        self.assertEqual(self.invoke('printer', 'info')[1]['result']['name'], 'bancada')
        for args in (('--printer','bancada','--config','unused','status'),
                     ('--printer','bancada','printer','info','bancada'),
                     ('--config','unused','printer','list'),
                     ('--printer','bancada','printer','use','bancada')):
            self.assertEqual(self.invoke(*args)[0], 2)
        self.assertEqual(self.invoke('--printer','unknown','status')[0], 2)
        self.registry.path('bancada').unlink()
        self.assertEqual(self.invoke('--printer', 'bancada', 'status')[0], 3)

    def test_selection_override_and_local_inspection(self):
        from kobra_lan.cli import main
        from test_client import GCODE
        self.add_profile('bancada'); self.add_profile('oficina')
        other = self.registry.load('oficina'); other.host = '192.0.2.11'
        path = self.registry.path('oficina'); path.write_text(json.dumps(asdict(other)))
        fixture((self.root/'explicit.json'), 'Explicit01')
        self.assertEqual(self.invoke('printer', 'info')[0], 2)
        self.registry.select('bancada')
        self.assertEqual(self.invoke('--printer','oficina','printer','info')[1]['result']['host'], '192.0.2.11')
        self.assertEqual(self.invoke('--config',str((self.root/'explicit.json')),'printer','info')[1]['result']['printer_id'], 'Explicit01')
        stdout = io.StringIO()
        with patch('kobra_lan.cli.Registry', return_value=self.registry), redirect_stdout(stdout), \
                patch('kobra_lan.cli.snapshot', side_effect=lambda cfg: {'host': cfg.host}):
            self.assertEqual(main(['--json','--printer','oficina','status']), 0)
        self.assertEqual(json.loads(stdout.getvalue())['result']['host'], '192.0.2.11')
        self.assertEqual(self.registry.read()['default'], {'name': 'bancada'})
        self.registry.path('bancada').unlink()
        self.assertEqual(self.invoke('status')[0], 3)
        local = self.root/'input.gcode'; local.write_bytes(GCODE)
        self.assertEqual(self.invoke('--printer','unknown','gcode','inspect',str(local))[0], 0)
        self.assertEqual(self.invoke('--printer','../invalid','gcode','inspect',str(local))[0], 2)

    def test_formats_never_confirm_local_removal(self):
        from kobra_lan.cli import main
        self.add_profile()
        path = self.registry.path('bancada')
        before = (path.read_bytes(), path.stat().st_mode)
        for mode in ([], ['--json']):
            with patch('kobra_lan.cli.Registry', return_value=self.registry), \
                    patch('sys.stdin', io.StringIO()), redirect_stdout(io.StringIO()):
                self.assertEqual(main([*mode, 'printer', 'remove', 'bancada']), 2)
            self.assertEqual((path.read_bytes(), path.stat().st_mode), before)
            self.assertIn('bancada', self.registry.read()['profiles'])

    def test_files_routes_share_named_and_explicit_selection(self):
        self.add_profile('bancada')
        fixture((self.root/'explicit.json'), 'Explicit01')
        for selectors, identity in ((['--printer', 'bancada'], 'Synthetic01'),
                                    (['--config', str((self.root/'explicit.json'))], 'Explicit01')):
            with patch('kobra_lan.cli.MQTT') as mqtt, \
                    patch('kobra_lan.cli.list_files', return_value=[]), \
                    patch('kobra_lan.cli.file_details', return_value={'filename': 'test.gcode'}):
                self.assertEqual(self.invoke(*selectors, 'files', 'list')[0], 0)
                self.assertEqual(mqtt.call_args.args[0].printer_id, identity)
                self.assertEqual(self.invoke(*selectors, 'files', 'info', 'test.gcode')[0], 0)
                self.assertEqual(mqtt.call_args.args[0].printer_id, identity)
        self.registry.select('bancada')
        with patch('kobra_lan.cli.MQTT') as mqtt, patch('kobra_lan.cli.list_files', return_value=[]):
            self.assertEqual(self.invoke('files', 'list')[0], 0)
            self.assertEqual(mqtt.call_args.args[0].printer_id, 'Synthetic01')

    def test_named_pairing_real_publication_and_default(self):
        from types import SimpleNamespace
        bundle = SimpleNamespace(model_id=20030, device_id='Synthetic01', username='secret-user',
                                 password='secret-password', certificate='synthetic cert', private_key='synthetic key')
        with patch('kobra_lan.pairing.provision', return_value=bundle), \
                patch('kobra_lan.pairing.observe_fingerprint', return_value='a'*64), \
                patch('kobra_lan.pairing.verify_status', return_value={'firmware':'2.0.2.2','state':'printing'}):
            code, report = self.invoke('printer','pair','--name','bancada','--host','192.0.2.10','--trust-sha256','a'*64)
            self.assertEqual(code,0); self.assertFalse(report['result']['default'])
            self.assertIsNone(self.registry.read()['default'])
            self.assertEqual(self.invoke('printer','pair','--name','oficina','--host','192.0.2.10','--trust-sha256','a'*64,'--default')[0],0)
        self.assertEqual(self.registry.read()['default'], {'name':'oficina'})
        self.assertEqual(self.registry.load('bancada').printer_id, self.registry.load('oficina').printer_id)
        for args in (('printer','pair','--name','../bad','--host','192.0.2.10'),
                     ('printer','pair','--name','bancada','--host','192.0.2.10'),
                     ('printer','pair','--default','--host','192.0.2.10'),
                     ('--config','unused','printer','pair','--name','third','--host','192.0.2.10'),
                     ('--printer','bancada','printer','pair','--host','192.0.2.10')):
            with patch('kobra_lan.pairing.provision') as provision:
                self.assertEqual(self.invoke(*args)[0],2); provision.assert_not_called()
        self.assertEqual(self.invoke('printer','pair','--name','untrusted','--host','192.0.2.10','--trust-sha256','invalid')[0],2)

    def test_partial_named_publication_and_default_reconciliation(self):
        def publish(path, host, expected):
            fixture(path)
            return {'firmware':'2.0.2.2'}
        # Before config publication: no entry or selected default.
        with patch('kobra_lan.pairing.pair', side_effect=OSError('secret failure')):
            self.assertRaises(OSError,self.registry.pair,'before','192.0.2.10','a'*64)
        self.assertEqual(self.registry.read()['profiles'],{})
        # After config publication, before registry commit: orphan remains intact.
        with patch('kobra_lan.pairing.pair', side_effect=publish), patch.object(self.registry,'write',side_effect=OSError('secret')):
            self.assertRaisesRegex(ProfileLocalError,'unregistered',self.registry.pair,'orphan','192.0.2.10','a'*64)
        self.assertEqual(Config.load(self.registry.path('orphan')).mqtt_password,'secret-password')
        code,report=self.invoke('--config',str(self.registry.path('orphan')),'printer','info')
        self.assertEqual(code,0); self.assertEqual(report['result']['source'],'explicit-config')
        self.assertEqual(report['result']['printer_id'],'Synthetic01')
        self.assertNotIn('orphan',self.registry.read()['profiles'])
        real_write = self.registry.write
        def commit_then_fail(data):
            real_write(data); raise OSError('secret')
        with patch('kobra_lan.pairing.pair',side_effect=publish), patch.object(self.registry,'write',side_effect=commit_then_fail):
            self.assertRaisesRegex(ProfileLocalError,'registered',self.registry.pair,'committed','192.0.2.10','a'*64)
        self.assertEqual(self.registry.load('committed').printer_id,'Synthetic01')
        calls = 0
        def fail_default(data):
            nonlocal calls
            calls += 1
            if calls == 2: raise OSError('secret')
            real_write(data)
        with patch('kobra_lan.pairing.pair',side_effect=publish), patch.object(self.registry,'write',side_effect=fail_default):
            self.assertRaisesRegex(ProfileLocalError,'default unchanged',self.registry.pair,'registered','192.0.2.10','a'*64,True)
        self.assertIsNone(self.registry.read()['default'])
        self.registry.select('registered')
        self.assertEqual(self.registry.read()['default'],{'name':'registered'})

    def test_removal_consent_revalidation_and_receipt(self):
        self.add_profile(); self.registry.select('bancada')
        before = {str(p): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        for answer, terminal in (('yes\n',False), ('no\n',True), ('',True), ('yes'+' '*32,True)):
            stdin = io.StringIO(answer); stdin.isatty = lambda: terminal
            self.assertRaises(ProtocolError,self.registry.remove,'bancada',False,stdin,io.StringIO())
            self.assertEqual({str(p):p.read_bytes() for p in self.root.rglob('*') if p.is_file()},before)
        stdin = io.StringIO('yes\n'); stdin.isatty = lambda: True
        stderr = io.StringIO()
        result = self.registry.remove('bancada',stdin=stdin,stderr=stderr)
        self.assertTrue(result['registration_removed']); self.assertFalse(result['cleanup_failed'])
        self.assertEqual(len(result['deleted_files']),3); self.assertEqual(result['preserved_files'],[])
        self.assertIn('local_removal_preview',stderr.getvalue())
        self.assertNotIn('secret-',json.dumps(result))
        self.assertIsNone(self.registry.read()['default'])
        self.assertRaises(ProtocolError,self.registry.resolve)
        self.assertFalse(self.registry.path('bancada').parent.exists())
        self.assertEqual(self.invoke('printer','remove','bancada','--yes')[0],2)

    def test_removal_shared_symlink_unknown_and_io_failure(self):
        cfg = self.add_profile(); self.add_profile('oficina')
        self.registry.select('oficina')
        # Retained profile and other managed references preserve known shared PEMs.
        other = self.registry.load('oficina'); other.client_cert = cfg.client_cert
        self.registry.path('oficina').write_text(json.dumps(asdict(other)))
        root = self.registry.path('bancada').parent
        (root/'unknown.txt').write_text('keep')
        key = Path(cfg.client_key); key.unlink(); key.symlink_to('/does-not-exist')
        result = self.registry.remove('bancada',yes=True)
        self.assertIn(cfg.client_cert,result['preserved_files']); self.assertIn(cfg.client_key,result['preserved_files'])
        self.assertTrue((root/'unknown.txt').exists()); self.assertTrue(key.is_symlink())
        self.assertEqual(self.registry.read()['default'],{'name':'oficina'})
        self.assertEqual(self.registry.load('oficina').client_cert,cfg.client_cert)
        self.add_profile('failed')
        real_unlink = os.unlink
        def injected(path, **kwargs):
            if path == 'client.key': raise OSError('secret-key')
            return real_unlink(path, **kwargs)
        with patch('kobra_lan.profiles.os.unlink',side_effect=injected):
            result = self.registry.remove('failed',yes=True)
        self.assertTrue(result['cleanup_failed']); self.assertNotIn('failed',self.registry.read()['profiles'])
        self.assertTrue(any('client.key' in f for f in result['preserved_files']))

    def test_removal_active_lease_and_metadata_change(self):
        self.add_profile()
        with self.registry.access(config=self.registry.path('bancada')):
            self.assertRaisesRegex(ProfileLocalError,'busy',self.registry.remove,'bancada',True)
        self.assertIn('bancada',self.registry.read()['profiles'])
        stdin = io.StringIO('yes\n'); stdin.isatty = lambda: True
        def confirm(size):
            self.registry.select('bancada'); return 'yes\n'
        stdin.readline = confirm
        self.assertRaisesRegex(ProtocolError,'changed',self.registry.remove,'bancada',False,stdin,io.StringIO())
        self.assertTrue(self.registry.path('bancada').exists())

    def test_same_device_markers_survive_other_name_and_repair(self):
        import hashlib
        from test_client import GCODE
        from test_start import Client, GCODE as START_GCODE
        from kobra_lan.start import build_plan
        from kobra_lan.upload import describe, atomic_json
        cfg = self.add_profile(); self.add_profile('oficina')
        gcode = self.root/'input.gcode'; gcode.write_bytes(GCODE)
        sha = hashlib.sha256(GCODE).hexdigest()
        state = self.root/'custom-state'; device = hashlib.sha256(cfg.printer_id.encode()).hexdigest()[:16]
        directory = state/device; directory.mkdir(parents=True)
        (directory/(sha+'.attempt')).write_text('uncertain upload')
        args = ['--state-dir',str(state),'files','upload',str(gcode),'--execute','--sha256',sha]
        self.assertEqual(self.invoke('--printer','bancada',*args)[0],2)
        self.assertEqual(self.invoke('--printer','oficina',*args)[0],2)
        self.registry.remove('bancada',yes=True); self.add_profile('bancada')
        self.assertEqual(self.invoke('--printer','bancada',*args)[0],2)
        self.assertEqual((directory/(sha+'.attempt')).read_text(),'uncertain upload')
        # A prior uncertain start remains blocked through both names as well.
        gcode.write_bytes(START_GCODE)
        _, manifest = describe(gcode,'test.gcode')
        atomic_json(directory/(manifest['sha256']+'.json'),{**manifest,'status':'uploaded_verified_by_listing_and_metadata'})
        starts = state/'starts'/device; starts.mkdir(parents=True)
        (starts/(manifest['sha256']+'.attempt')).write_text('uncertain start')
        plan = build_plan(cfg,Client(cfg),gcode,'test.gcode',1,True,False,False)
        args = ['--state-dir',str(state),'print','start',str(gcode),'--name','test.gcode','--slot','1',
                '--auto-leveling','on','--vibration-compensation','off','--flow-calibration','off',
                '--execute','--plan-sha256',plan['plan_sha256']]
        tracked = [self.registry.path('bancada'), self.registry.path('oficina'),
                   directory/(manifest['sha256']+'.json'), directory/(sha+'.attempt'),
                   starts/(manifest['sha256']+'.attempt')]
        baseline = [(p.read_bytes(), p.stat().st_mode) for p in tracked]
        with patch('kobra_lan.start.MQTT',Client):
            for name in ('bancada','oficina'):
                code, result = self.invoke('--printer',name,*args)
                self.assertEqual(code,2,result)
        self.assertEqual((starts/(manifest['sha256']+'.attempt')).read_text(),'uncertain start')
        self.assertEqual([(p.read_bytes(), p.stat().st_mode) for p in tracked], baseline)
        self.assertEqual(Client.starts, 0)

    def test_removal_commit_failure_reports_retained_files_and_actual_state(self):
        self.add_profile(); self.registry.select('bancada')
        real_write = self.registry.write
        def after_commit(data):
            real_write(data); raise OSError('injected fsync after commit')
        with patch.object(self.registry,'write',side_effect=after_commit):
            code,report = self.invoke('printer','remove','bancada','--yes')
        self.assertEqual(code,3); self.assertTrue(report['result']['registration_removed'])
        self.assertEqual(report['result']['deleted_files'],[])
        self.assertTrue(self.registry.path('bancada').exists())
        self.assertIsNone(self.registry.read()['default'])

    def test_write_failure_and_managed_parent_permissions(self):
        self.add_profile()
        before=self.registry.read()
        with self.registry.lock(), patch('kobra_lan.profiles.json.dump',side_effect=OSError('injected write')):
            self.assertRaises(OSError,self.registry.write,{**before,'default':{'name':'bancada'}})
        self.assertEqual(self.registry.read(),before)
        self.assertEqual(list(self.root.glob('.profiles-*')),[])
        (self.root/'profiles').chmod(0o755)
        self.assertRaises(ProfileLocalError,self.registry.load,'bancada')

    def test_damaged_config_types_do_not_hide_healthy_entries(self):
        self.add_profile('bancada'); self.add_profile('oficina')
        path=self.registry.path('bancada'); raw=json.loads(path.read_text())
        for change in ({'printer_id':42},{'mqtt_password':[]},{'mqtt_port':float('inf')},{'http_port':0}):
            path.write_text(json.dumps({**raw,**change}))
            code,report=self.invoke('printer','list')
            self.assertEqual(code,0)
            self.assertEqual([p['available'] for p in report['result']['profiles']],[False,True])

    def test_cleanup_revalidates_name_and_entire_manifest_before_any_deletion(self):
        self.add_profile()
        entry=self.registry.read()['profiles']['bancada']
        original={str(p):p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        with patch('kobra_lan.profiles.open_directory',side_effect=AssertionError('must reject before filesystem access')):
            for name in ('../outside', '/outside', 'bancada/../../outside', '..', '', 'Bancada'):
                self.assertRaises(ProtocolError,self.registry._cleanup,name,entry,set(),False)
            for filename in ('../outside', '/outside', '.pair-'+'a'*32+'/../../outside'):
                invalid={**entry,'owned_files':['config.json',filename]}
                self.assertRaises(ProtocolError,self.registry._cleanup,'bancada',invalid,set(),False)
        self.assertEqual({str(p):p.read_bytes() for p in self.root.rglob('*') if p.is_file()},original)

    def test_symlinked_managed_root_is_rejected(self):
        actual=Path(self.temporary.name)/'actual'
        fixture(actual/'config.json')
        self.root.symlink_to(actual,target_is_directory=True)
        self.assertEqual(self.invoke('printer','info')[0],3)
        self.assertEqual(self.invoke('printer','list')[0],3)
        self.assertEqual(self.invoke('--config',str(actual/'config.json'),'printer','info')[0],3)
        self.assertFalse((actual/'.profiles.lock').exists())
        self.assertFalse((actual/'profiles.json').exists())

    def test_first_adoption_acquires_a_lease_before_loading_a_managed_selection(self):
        original_resolve=self.registry.resolve
        def adopt(config=None,name=None):
            self.add_profile()
            self.registry.select('bancada')
            return original_resolve(config,name)
        with patch.object(self.registry,'resolve',side_effect=adopt):
            with self.registry.access() as (cfg,source):
                self.assertEqual(source['name'],'bancada')
                with self.assertRaisesRegex(ProfileLocalError,'busy'):
                    with self.registry.lock(timeout=0): pass
