import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from kobra_lan import pairing as p
from kobra_lan.config import Config, ProtocolError

HOST = '192.0.2.10'
PIN = hashlib.sha256(b'synthetic certificate').hexdigest()


def config():
    return Config(HOST,20030,'Synthetic01','private-user','private-password','cert.pem','key.pem',PIN)


class TransportTests(unittest.TestCase):
    def test_observation_is_tls_only(self):
        raw = Mock(); raw.__enter__ = Mock(return_value=raw); raw.__exit__ = Mock()
        tls = Mock(); tls.__enter__ = Mock(return_value=tls); tls.__exit__ = Mock()
        tls.getpeercert.return_value = b'synthetic certificate'
        ctx = Mock(); ctx.wrap_socket.return_value = tls
        with patch.object(p.ssl,'SSLContext',return_value=ctx), patch.object(p.socket,'create_connection',return_value=raw) as connect:
            self.assertEqual(p.observe_fingerprint(config()),PIN)
        connect.assert_called_once_with((HOST,9883),10)
        ctx.load_cert_chain.assert_called_once_with('cert.pem','key.pem')
        tls.sendall.assert_not_called(); raw.sendall.assert_not_called()

    def test_authenticated_verification_only_queries_info(self):
        client = Mock(); client.query.return_value = {'code':200,'data':{'state':'free','model':'Anycubic Kobra X','version':'2.0.2.2'}}
        transport = Mock(); transport.__enter__ = Mock(return_value=client); transport.__exit__ = Mock(return_value=False)
        with patch.object(p,'MQTT',return_value=transport) as mqtt:
            self.assertEqual(p.verify_status(config()),{'state':'free','firmware':'2.0.2.2'})
        mqtt.assert_called_once()
        self.assertEqual(client.method_calls,[unittest.mock.call.query('info')])


class TrustTests(unittest.TestCase):
    def test_explicit_acceptance(self):
        for answer in ('y\n','yes\n','YES\n'):
            stdin = io.StringIO(answer); stdin.isatty = lambda: True
            stderr = io.StringIO()
            p.accept_trust(config(),PIN,stdin=stdin,stderr=stderr)
            self.assertIn(PIN,stderr.getvalue())
            self.assertIn('does not authenticate',stderr.getvalue())

    def test_declined_empty_eof_noninteractive(self):
        for answer in ('n\n','\n','','sure\n', 'yes' + ' ' * 32 + 'no\n'):
            stdin = io.StringIO(answer); stdin.isatty = lambda: True
            with self.assertRaises(ProtocolError): p.accept_trust(config(),PIN,stdin=stdin,stderr=io.StringIO())
        with self.assertRaises(ProtocolError): p.accept_trust(config(),PIN,stdin=io.StringIO('yes\n'))
        stdin = Mock(); stdin.isatty.return_value = True; stdin.readline.side_effect = EOFError
        with self.assertRaises(ProtocolError): p.accept_trust(config(),PIN,stdin=stdin,stderr=io.StringIO())

    def test_exact_pin_without_prompt_or_fallback(self):
        stdin = Mock(); stderr = io.StringIO()
        p.accept_trust(config(),PIN,PIN.upper(),stdin=stdin,stderr=stderr)
        self.assertEqual(stderr.getvalue(),''); stdin.readline.assert_not_called()
        for pin in ('0'*64, 'a'*63, 'g'*64, PIN+'\n', ''):
            with self.assertRaises(ProtocolError): p.accept_trust(config(),PIN,pin,stdin=stdin,stderr=stderr)
        stdin.readline.assert_not_called()

    def test_terminal_safe_bounded_metadata(self):
        cfg = config(); cfg.printer_id = '\x1b[31m\n\u202e'+'x'*1000
        stdin = io.StringIO('y\n'); stdin.isatty = lambda: True
        stderr = io.StringIO(); p.accept_trust(cfg,PIN,stdin=stdin,stderr=stderr)
        text = stderr.getvalue()
        self.assertNotIn('\x1b',text); self.assertNotIn('\u202e',text)
        self.assertLess(len(text),600)

    def test_changed_cert_rejected_before_credentials(self):
        # Reuse the real authenticated transport: a second observation is not trust.
        from kobra_lan.mqtt import MQTT
        ctx = Mock(); tls = Mock(); tls.getpeercert.return_value = b'changed certificate'
        ctx.wrap_socket.return_value = tls
        p.accept_trust(config(),PIN,PIN)
        with patch('kobra_lan.mqtt.ssl.SSLContext',return_value=ctx), patch('kobra_lan.mqtt.socket.create_connection'):
            with self.assertRaisesRegex(ProtocolError,'fingerprint changed'):
                with MQTT(config()): pass
        tls.sendall.assert_not_called()


class QualificationTests(unittest.TestCase):
    def transport(self, data):
        client = Mock(); client.query.return_value = {'code':200,'data':data}
        transport = Mock(); transport.__enter__ = Mock(return_value=client); transport.__exit__ = Mock(return_value=False)
        return transport, client

    def test_free_and_busy_only_query(self):
        for state in ('free','busy','printing'):
            transport, client = self.transport({'model':'Anycubic Kobra X','version':'2.0.2.2','state':state})
            with patch.object(p,'MQTT',return_value=transport):
                self.assertEqual(p.verify_status(config()),{'firmware':'2.0.2.2','state':state})
            self.assertEqual(client.method_calls,[unittest.mock.call.query('info')])

    def test_conflicting_identity_firmware_missing_status(self):
        good = {'model':'Anycubic Kobra X','version':'2.0.2.2','state':'free'}
        for changes in ({'model':'other'},{'version':'3.0'},{'state':None},{'deviceId':'Other01'},
                        {'modelId':20031},{'modeId':'20031'},{'state':'\x1b[31m'}):
            transport, _ = self.transport({**good,**changes})
            with patch.object(p,'MQTT',return_value=transport), self.assertRaisesRegex(ProtocolError,'Status qualification'):
                p.verify_status(config())

    def test_authentication_and_no_fresh_report(self):
        transport, client = self.transport({})
        transport.__enter__.side_effect = ProtocolError('MQTT authentication rejected private')
        with patch.object(p,'MQTT',return_value=transport), self.assertRaisesRegex(ProtocolError,'Authentication/status'):
            p.verify_status(config())
        transport.__enter__.side_effect = None
        client.query.side_effect = ProtocolError('timeout')
        with patch.object(p,'MQTT',return_value=transport), self.assertRaisesRegex(ProtocolError,'Authentication/status'):
            p.verify_status(config())

    def test_real_query_drops_stale_then_fails_without_fresh_report(self):
        from kobra_lan.mqtt import MQTT, string
        client = MQTT(config()); client.sock = Mock()
        def receive(deadline):
            raw = client.sock.sendall.call_args.args[0]; payload = json.loads(raw[raw.index(b'{'):])
            if not getattr(client,'acked',False):
                client.acked = True
                return 0x30, string('root/response')+json.dumps({'code':0,'msgid':payload['msgid']}).encode()
            if not getattr(client,'stale',False):
                client.stale = True
                return 0x30,string('root/info/report')+json.dumps({'type':'info','msgid':'old','timestamp':payload['timestamp']-1000,'data':{}}).encode()
            raise ProtocolError('MQTT response timeout')
        with patch.object(client,'receive',side_effect=receive), self.assertRaisesRegex(ProtocolError,'timeout'):
            client.query('info')

import os
import stat
from dataclasses import asdict
from test_provisioning import synthetic_bundle
from kobra_lan.provisioning import Bundle


def bundle():
    data = synthetic_bundle()
    return Bundle(data['deviceId'],20030,data['username'],data['password'],data['devicecrt'],data['devicepk'])


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.dest = self.root/'private/config.json'
        self.bundle = bundle()

    def test_private_stage_config_contract_and_cleanup(self):
        with p.PrivateStage(self.dest) as stage:
            cfg = stage.prepare(self.bundle,HOST)
            self.assertEqual(stat.S_IMODE(self.dest.parent.stat().st_mode),0o700)
            for filename in (cfg.client_cert,cfg.client_key):
                self.assertEqual(stat.S_IMODE(Path(filename).stat().st_mode),0o600)
                self.assertEqual(Path(filename).stat().st_uid,os.geteuid())
            # Config loader compatibility independent of publication task.
            self.dest.write_text(json.dumps(asdict(cfg))); self.dest.chmod(0o600)
            self.assertEqual(Config.load(self.dest).printer_id,'Synthetic01')
            self.dest.unlink()
        self.assertEqual(list(self.dest.parent.iterdir()),[])

    def test_shared_parent_and_symlinks_refused(self):
        self.dest.parent.mkdir(mode=0o755)
        with self.assertRaises(OSError): p.PrivateStage(self.dest)
        self.assertEqual(stat.S_IMODE(self.dest.parent.stat().st_mode),0o755)
        link = self.root/'alias'; link.symlink_to(self.dest.parent)
        with self.assertRaises(OSError): p.PrivateStage(link/'config.json')
        self.dest.parent.chmod(0o700)
        with patch.object(p.os,'geteuid',return_value=os.geteuid()+1):
            with self.assertRaises(OSError): p.PrivateStage(self.dest)

    def test_exclusive_secret_creation(self):
        with p.PrivateStage(self.dest) as stage:
            cfg = stage.prepare(self.bundle,HOST)
            with self.assertRaises(FileExistsError): stage.write_secret('client.key',b'replace')
            self.assertEqual(Path(cfg.client_key).read_text(),self.bundle.private_key)
            target = self.root/'other'; target.write_text('untouched')
            os.symlink(target,'linked',dir_fd=stage.stage_fd)
            try:
                with self.assertRaises(FileExistsError): stage.write_secret('linked',b'replace')
            finally:
                os.unlink('linked',dir_fd=stage.stage_fd)
            self.assertEqual(target.read_text(),'untouched')


class PublicationTests(StorageTests):
    def test_atomic_complete_publish_and_permissions(self):
        with p.PrivateStage(self.dest) as stage:
            cfg = stage.prepare(self.bundle,HOST); cfg.tls_sha256 = PIN
            stage.publish(cfg)
        loaded = Config.load(self.dest)
        self.assertEqual(loaded.tls_sha256,PIN)
        self.assertEqual(stat.S_IMODE(self.dest.stat().st_mode),0o600)
        self.assertTrue(Path(loaded.client_key).is_file())
        self.assertEqual({f.name for f in Path(loaded.client_key).parent.iterdir()},{'client.crt','client.key'})

    def test_concurrent_config_creation_preserved(self):
        with self.assertRaises(FileExistsError):
            with p.PrivateStage(self.dest) as stage:
                cfg = stage.prepare(self.bundle,HOST)
                self.dest.write_text('concurrent config')
                stage.publish(cfg)
        self.assertEqual(self.dest.read_text(),'concurrent config')
        self.assertEqual(list(self.dest.parent.iterdir()),[self.dest])

    def test_write_fsync_link_failures_cleanup_before_commit(self):
        for operation in ('write_secret','fsync','link'):
            with self.subTest(operation=operation):
                with self.assertRaises(OSError):
                    with p.PrivateStage(self.dest) as stage:
                        cfg = stage.prepare(self.bundle,HOST)
                        target = patch.object(stage,operation,side_effect=OSError('private')) if operation=='write_secret' else patch.object(p.os,operation,side_effect=OSError('private'))
                        with target: stage.publish(cfg)
                self.assertFalse(self.dest.exists()); self.assertEqual(list(self.dest.parent.iterdir()),[])

    def test_partial_pem_failure_cleanup(self):
        real_fsync = os.fsync
        calls = 0
        def fail_second(fd):
            nonlocal calls
            calls += 1
            if calls==2: raise OSError('private')
            return real_fsync(fd)
        with patch.object(p.os,'fsync',side_effect=fail_second), self.assertRaises(OSError):
            with p.PrivateStage(self.dest) as stage: stage.prepare(self.bundle,HOST)
        self.assertEqual(list(self.dest.parent.iterdir()),[])

    def test_failures_after_commit_preserve_config_and_pems(self):
        for operation in ('fsync','unlink'):
            with self.subTest(operation=operation):
                dest = self.dest.parent/(operation+'.json')
                with self.assertRaises(OSError):
                    with p.PrivateStage(dest) as stage:
                        cfg = stage.prepare(self.bundle,HOST)
                        original = os.link
                        def link_then_fail(*args,**kwargs):
                            result = original(*args,**kwargs)
                            # Fault begins only after publication.
                            fault.start()
                            return result
                        fault = patch.object(p.os,operation,side_effect=OSError('private'))
                        try:
                            with patch.object(p.os,'link',side_effect=link_then_fail): stage.publish(cfg)
                        finally:
                            fault.stop()
                loaded = Config.load(dest)
                self.assertEqual(Path(loaded.client_key).read_text(),self.bundle.private_key)

    def test_declined_trust_cleans_up_without_authentication(self):
        with patch.object(p,'provision',return_value=self.bundle), patch.object(p,'observe_fingerprint',return_value=PIN), patch.object(p,'accept_trust',side_effect=ProtocolError('Trust: declined')), patch.object(p,'verify_status') as verify:
            with self.assertRaises(ProtocolError): p.pair(self.dest,HOST)
        verify.assert_not_called(); self.assertFalse(self.dest.exists())
        self.assertEqual(list(self.dest.parent.iterdir()),[])


class PreservationTests(StorageTests):
    def test_existing_file_and_dangling_link_before_network(self):
        self.dest.parent.mkdir(mode=0o700)
        for symlink in (False,True):
            if symlink: self.dest.symlink_to(self.root/'missing')
            else: self.dest.write_text('original')
            with patch.object(p,'provision') as provision:
                with self.assertRaises(p.PairingLocalError): p.pair(self.dest,HOST,PIN)
            provision.assert_not_called()
            if not symlink: self.assertEqual(self.dest.read_text(),'original')
            self.dest.unlink()

    def test_parallel_stages_only_one_publishes(self):
        with p.PrivateStage(self.dest) as first:
            with self.assertRaises(FileExistsError):
                with p.PrivateStage(self.dest) as second:
                    cfg1 = first.prepare(self.bundle,HOST); cfg2 = second.prepare(self.bundle,HOST)
                    first.publish(cfg1)
                    second.publish(cfg2)
            self.assertEqual(Config.load(self.dest).client_key,cfg1.client_key)
            self.assertFalse(Path(cfg2.client_key).exists())
        self.assertTrue(Path(cfg1.client_key).exists())

    def test_alternate_destination_preserves_original_and_markers(self):
        original = self.root/'original.json'; original.write_text('original config')
        pem = self.root/'original.key'; pem.write_text('original PEM')
        markers = [self.root/'upload.attempt',self.root/'start.attempt']
        for marker in markers: marker.write_text('reserved')
        paths = [original,pem,*markers]
        before = {f:(f.read_bytes(),f.stat().st_mode,f.stat().st_uid) for f in paths}
        with patch.object(p,'provision',return_value=self.bundle), patch.object(p,'observe_fingerprint',return_value=PIN), patch.object(p,'verify_status',return_value={'firmware':'2.0.2.2','state':'free'}):
            p.pair(self.dest,HOST,PIN)
        self.assertEqual(before,{f:(f.read_bytes(),f.stat().st_mode,f.stat().st_uid) for f in paths})

    def test_colliding_stage_is_not_owned_or_deleted(self):
        self.dest.parent.mkdir(mode=0o700)
        existing = self.dest.parent/('.pair-'+'0'*32); existing.mkdir(mode=0o700)
        with patch.object(p.uuid,'uuid4',return_value=Mock(hex='0'*32)), self.assertRaises(FileExistsError):
            with p.PrivateStage(self.dest) as stage: stage.prepare(self.bundle,HOST)
        self.assertTrue(existing.is_dir())

from contextlib import redirect_stdout, redirect_stderr
from kobra_lan.cli import main


class CLITests(StorageTests):
    def invoke(self, args):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr): code = main(args)
        return code, json.loads(stdout.getvalue()), stderr.getvalue()

    def test_help_and_required_options(self):
        for args in (['--help'],['printer','--help'],['printer','pair','--help']):
            stdout = io.StringIO()
            with redirect_stdout(stdout), self.assertRaises(SystemExit) as exit:
                main(args)
            self.assertEqual(exit.exception.code,0)
            self.assertIn('usage:',stdout.getvalue())
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as exit:
            main(['printer','pair'])
        self.assertEqual(exit.exception.code,2)

    def test_synthetic_pair_then_ordinary_status(self):
        with patch.object(p,'provision',return_value=self.bundle), patch.object(p,'observe_fingerprint',return_value=PIN), patch.object(p,'verify_status',return_value={'firmware':'2.0.2.2','state':'free'}):
            code, result, stderr = self.invoke(['--config',str(self.dest),'printer','pair','--host',HOST,'--trust-sha256',PIN])
        self.assertEqual(code,0); self.assertTrue(result['ok']); self.assertEqual(stderr,'')
        self.assertEqual(result['result']['tls_sha256'],PIN)
        client = Mock(); client.query.return_value = {'data':{'model':'Anycubic Kobra X','version':'2.0.2.2','state':'free'}}
        transport = Mock(); transport.__enter__ = Mock(return_value=client); transport.__exit__ = Mock(return_value=False)
        with patch('kobra_lan.printer.MQTT',return_value=transport) as mqtt, patch('kobra_lan.printer.public_info',return_value={'modelId':20030}):
            code, result, _ = self.invoke(['--config',str(self.dest),'status'])
        self.assertEqual(code,0); self.assertEqual(result['result']['info']['state'],'free')
        self.assertEqual(mqtt.call_args.args[0].mqtt_password,self.bundle.password)

    def test_invalid_host_pin_and_existing_path_before_network(self):
        with patch.object(p,'provision') as provision:
            for host,pin in [('localhost',PIN),(HOST,'bad')]:
                code, result, _ = self.invoke(['--config',str(self.dest),'printer','pair','--host',host,'--trust-sha256',pin])
                self.assertEqual(code,2); self.assertFalse(result['ok'])
            self.dest.parent.mkdir(mode=0o700); self.dest.write_text('existing')
            code, result, _ = self.invoke(['--config',str(self.dest),'printer','pair','--host',HOST,'--trust-sha256',PIN])
            self.assertEqual(code,3); self.assertIn('separate absent --config',result['error'])
        provision.assert_not_called()

from test_provisioning import encrypt, INFO, TOKEN


class DiagnosticTests(CLITests):
    def command(self, pin=PIN):
        args = ['--config',str(self.dest),'printer','pair','--host',HOST]
        return args if pin is None else args+['--trust-sha256',pin]

    def test_full_synthetic_http_to_cli_and_interactive_stderr(self):
        data = {'deviceId':self.bundle.device_id,'modelId':20030,'username':self.bundle.username,
                'password':self.bundle.password,'devicecrt':self.bundle.certificate,'devicepk':self.bundle.private_key}
        stdin = io.StringIO('yes\n'); stdin.isatty = lambda: True
        with patch('kobra_lan.provisioning.request_json',side_effect=[INFO,{'code':200,'data':encrypt(data)}]), patch.object(p,'observe_fingerprint',return_value=PIN), patch.object(p,'verify_status',return_value={'firmware':'2.0.2.2','state':'free'}), patch.object(p.sys,'stdin',stdin):
            code,result,stderr = self.invoke(self.command(None))
        self.assertEqual(code,0); self.assertIn('Trust this fingerprint?',stderr)
        self.assertNotIn('Trust this fingerprint?',json.dumps(result))
        self.assertEqual(Config.load(self.dest).mqtt_username,self.bundle.username)

    def test_sanitized_protocol_network_filesystem_and_trust_diagnostics(self):
        secret = 'SENSITIVE\x1b[31m\n'
        scenarios = [
            (patch('kobra_lan.provisioning.request_json',return_value={'token':secret,'ctrlInfoUrl':secret}),2,'Response validation'),
            (patch.object(p,'observe_fingerprint',side_effect=OSError(secret)),3,'Trust observation'),
            (patch.object(p,'observe_fingerprint',return_value='0'*64),2,'Trust'),
            (patch.object(p.PrivateStage,'publish',side_effect=OSError(secret)),3,'Persistence'),
        ]
        # Identity failure actually diagnoses a too-short token.
        scenarios[0] = (patch('kobra_lan.provisioning.request_json',return_value={'token':secret,'ctrlInfoUrl':secret}),2,'Identity')
        for override,expected,stage in scenarios:
            with self.subTest(stage=stage):
                with patch.object(p,'provision',return_value=self.bundle), patch.object(p,'observe_fingerprint',return_value=PIN), patch.object(p,'verify_status',return_value={'firmware':'2.0.2.2','state':'free'}):
                    if stage=='Identity':
                        from kobra_lan.provisioning import provision
                        with patch.object(p,'provision',side_effect=provision), override:
                            code,result,stderr = self.invoke(self.command())
                    else:
                        with override: code,result,stderr = self.invoke(self.command())
                self.assertEqual(code,expected); self.assertIn(stage,result['error'])
                self.assertNotIn('SENSITIVE',json.dumps(result)+stderr)
                self.assertFalse(self.dest.exists()); self.assertEqual(list(self.dest.parent.iterdir()),[])

    def test_authentication_and_qualification_safe_output(self):
        for data in ({'model':'Anycubic Kobra X','version':'sensitive-firmware','state':'free'}, None):
            client = Mock(); client.query.return_value = {'data':data}
            transport = Mock(); transport.__enter__ = Mock(return_value=client); transport.__exit__ = Mock(return_value=False)
            if data is None: transport.__enter__.side_effect = ProtocolError('sensitive-auth\x1b')
            with patch.object(p,'provision',return_value=self.bundle), patch.object(p,'observe_fingerprint',return_value=PIN), patch.object(p,'MQTT',return_value=transport):
                code,result,stderr = self.invoke(self.command())
            self.assertEqual(code,2); self.assertNotIn('sensitive',json.dumps(result)+stderr)
            self.assertFalse(self.dest.exists())

    def test_provisioning_network_error_safe(self):
        with patch.object(p,'provision',side_effect=OSError('sensitive tokenized URL')):
            code,result,_ = self.invoke(self.command())
        self.assertEqual(code,3); self.assertIn('Provisioning',result['error']); self.assertNotIn('sensitive',result['error'])


class TerminalTests(unittest.TestCase):
    def test_acceptance_on_real_terminal_stdin(self):
        import pty
        import subprocess
        import sys
        master, slave = pty.openpty()
        try:
            code = ('from kobra_lan.pairing import accept_trust; '
                    'from kobra_lan.config import Config; '
                    'c=Config("192.0.2.10",20030,"Synthetic01","u","p","c","k","0"*64); '
                    'accept_trust(c,"0"*64); print("accepted")')
            process = subprocess.Popen([sys.executable,'-c',code],stdin=slave,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            os.write(master,b'yes\n')
            stdout,stderr = process.communicate(timeout=10)
            self.assertEqual(process.returncode,0)
            self.assertEqual(stdout,'accepted\n'); self.assertIn('Trust this fingerprint?',stderr)
        finally:
            os.close(master); os.close(slave)


class AmbiguousPublicationTests(StorageTests):
    def test_publication_raises_after_link_preserves_referenced_pems(self):
        link = os.link
        def ambiguous(*args,**kwargs):
            link(*args,**kwargs)
            raise OSError('ambiguous publication')
        with self.assertRaises(OSError):
            with p.PrivateStage(self.dest) as stage:
                cfg = stage.prepare(self.bundle,HOST)
                with patch.object(p.os,'link',side_effect=ambiguous): stage.publish(cfg)
        loaded = Config.load(self.dest)
        self.assertTrue(Path(loaded.client_key).is_file())
