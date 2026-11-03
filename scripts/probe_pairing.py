"""Exercise an installed command with synthetic provisioning; never open sockets.

Run with the installed application's Python outside the checkout. This script is
validation tooling, not included in the application package.
"""
import argparse
from contextlib import redirect_stdout, redirect_stderr
from datetime import datetime, timedelta, timezone
import base64
import hashlib
import io
import json
from pathlib import Path
import runpy
import sys
import tempfile
from unittest.mock import Mock, patch

from cryptography import x509
from cryptography.hazmat.primitives import hashes, padding, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


def main():
    """Exercise the installed entry point with synthetic credentials and all real sockets blocked."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--command', required=True, type=Path)
    args = parser.parse_args()
    import kobra_lan
    from kobra_lan.config import Config
    assert {'site-packages', 'dist-packages'} & set(Path(kobra_lan.__file__).resolve().parts), 'Must use installed modules'
    key = rsa.generate_private_key(public_exponent=65537,key_size=2048)
    name = x509.Name([x509.NameAttribute(x509.NameOID.COMMON_NAME,'Synthetic installed probe')])
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(1).not_valid_before(now).not_valid_after(now+timedelta(days=1)).sign(key,hashes.SHA256()))
    token = '0123456789abcdefFEDCBA9876543210'; iv = b'0123456789abcdef'
    pin = hashlib.sha256(b'synthetic server certificate').hexdigest()
    credentials = {'deviceId':'Synthetic01','modelId':20030,'username':'offline-user','password':'offline-password',
                   'devicecrt':cert.public_bytes(serialization.Encoding.PEM).decode(),
                   'devicepk':key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()).decode()}
    padder = padding.PKCS7(128).padder(); padded = padder.update(json.dumps(credentials).encode())+padder.finalize()
    enc = Cipher(algorithms.AES(token[16:32].encode()),modes.CBC(iv)).encryptor()
    cipher = base64.b64encode(enc.update(padded)+enc.finalize()).decode()
    connection = Mock()
    connection.getresponse.side_effect = [
        Mock(status=200,read=Mock(return_value=json.dumps({'token':token,'ctrlInfoUrl':'http://192.0.2.10:18910/ctrl'}).encode())),
        Mock(status=200,read=Mock(return_value=json.dumps({'code':200,'data':{'token':iv.decode(),'info':cipher}}).encode())),
        Mock(status=200,read=Mock(return_value=b'{"modelId":20030}'))]
    info = {'model':'Anycubic Kobra X','version':'2.0.2.2','state':'free'}
    class ReadOnlyMQTT:
        def __init__(self, config): self.config = config
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def query(self,kind):
            """Permit only the read-only info query in the installed-command probe."""
            assert kind=='info'
            return {'code':200,'data':info}
    def invoke(argv):
        """Capture one installed command and reject failure, stderr or leaked synthetic credentials."""
        stdout,stderr = io.StringIO(),io.StringIO()
        with patch.object(sys,'argv',[str(args.command),*argv]), redirect_stdout(stdout), redirect_stderr(stderr):
            try: runpy.run_path(str(args.command),run_name='__main__')
            except SystemExit as exit: assert exit.code==0, (exit.code,stdout.getvalue())
        result = json.loads(stdout.getvalue()); assert result['ok']; assert not stderr.getvalue()
        assert 'offline-password' not in stdout.getvalue()
        return result['result']
    with tempfile.TemporaryDirectory(prefix='pairing-probe-',dir=Path.cwd()) as temporary:
        destination = Path(temporary)/'private/config.json'
        with patch('socket.create_connection',side_effect=AssertionError('No real network permitted')) as network, \
             patch('kobra_lan.provisioning.http.client.HTTPConnection',return_value=connection), \
             patch('kobra_lan.pairing.observe_fingerprint',return_value=pin), \
             patch('kobra_lan.pairing.MQTT',ReadOnlyMQTT), patch('kobra_lan.printer.MQTT',ReadOnlyMQTT):
            result = invoke(['--config',str(destination),'printer','pair','--host','192.0.2.10','--trust-sha256',pin])
            assert result['tls_sha256']==pin and result['model_id']==20030
            assert Config.load(destination).mqtt_password=='offline-password'
            assert invoke(['--config',str(destination),'status'])['info']['state']=='free'
            network.assert_not_called()
    print('Installed synthetic pairing and ordinary status verified; no printer access')


if __name__=='__main__': main()
