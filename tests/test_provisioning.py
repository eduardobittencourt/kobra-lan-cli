"""Synthetic bootstrap tests: no printer addresses or credentials."""
import hashlib
import json
import socket
import unittest
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlsplit

from kobra_lan.config import ProtocolError
from kobra_lan import provisioning as p

HOST = '192.0.2.10'
TOKEN = '0123456789abcdefFEDCBA9876543210'
INFO = {'token': TOKEN, 'ctrlInfoUrl': f'http://{HOST}:18910/ctrl'}


class HTTPTests(unittest.TestCase):
    def connection(self, responses):
        conn = Mock()
        conn.getresponse.side_effect = [Mock(status=status, read=Mock(return_value=raw)) for status, raw in responses]
        return conn

    def test_bare_and_wrapped_exchange(self):
        for info in (INFO, {'code': 200, 'data': INFO}):
            conn = self.connection([(200, json.dumps(info).encode()), (200, b'{"code":200,"data":{}}')])
            with patch.object(p.http.client, 'HTTPConnection', return_value=conn) as factory:
                self.assertEqual(p.exchange(HOST), (TOKEN, {}))
            factory.assert_called_with(HOST, 18910, timeout=10)
            self.assertEqual(conn.request.call_args_list[0].args, ('GET', '/info'))
            method, target = conn.request.call_args_list[1].args
            self.assertEqual(method, 'POST')
            self.assertEqual(urlsplit(target).path, '/ctrl')
            params = parse_qs(urlsplit(target).query)
            self.assertEqual(set(params), {'ts', 'nonce', 'sign', 'did'})
            self.assertRegex(params['nonce'][0], r'^[A-Za-z0-9]{6}$')
            self.assertRegex(params['did'][0], r'^[A-F0-9]{12}4[A-F0-9]{3}[89AB][A-F0-9]{15}$')
            expected = hashlib.md5((hashlib.md5(TOKEN[:16].encode()).hexdigest() + params['ts'][0] + params['nonce'][0]).encode()).hexdigest()
            self.assertEqual(params['sign'], [expected])
            self.assertEqual(conn.close.call_count, 2)

    def test_signature_known_answer(self):
        with patch.object(p.time, 'time', return_value=1700000000), patch.object(p.secrets, 'choice', side_effect=list('aB3xY9')):
            result = p.signed_parameters(TOKEN)
        # Literal generated independently with OpenSSL MD5.
        self.assertEqual(result['ts'], '1700000000000')
        self.assertEqual(result['nonce'], 'aB3xY9')
        self.assertEqual(result['sign'], 'fb0d0bbd9676bf1e8311653cac6d9a73')

    def test_unsafe_endpoints_never_post(self):
        urls = ['https://192.0.2.10:18910/ctrl', 'http://192.0.2.11:18910/ctrl',
                'http://192.0.2.10:80/ctrl', 'http://192.0.2.10:18910/info',
                'http://u@192.0.2.10:18910/ctrl', INFO['ctrlInfoUrl']+'?x=1',
                INFO['ctrlInfoUrl']+'#x', INFO['ctrlInfoUrl']+'?', INFO['ctrlInfoUrl']+'#',
                'http://192.0.2.10:bad/ctrl', INFO['ctrlInfoUrl']+'\n']
        for url in urls:
            with self.subTest(url=url), patch.object(p, 'request_json', return_value={**INFO, 'ctrlInfoUrl': url}) as request:
                self.assertRaises(ProtocolError, p.exchange, HOST)
                request.assert_called_once_with(HOST, 'GET', '/info')

    def test_invalid_hosts_before_network(self):
        for host in ('localhost', 'http://192.0.2.10', '::1', '192.0.2.010', '192.0.2.10:18910'):
            with patch.object(p, 'request_json') as request:
                self.assertRaises(ProtocolError, p.exchange, host)
            request.assert_not_called()

    def test_bad_responses(self):
        for status, raw in [(301,b'{}'), (500,b'{}'), (200,b'x'*(p.MAX_RESPONSE+1)),
                            (200,b'bad'), (200,b'[]'), (200,b'\xff')]:
            conn = self.connection([(status,raw)])
            with patch.object(p.http.client, 'HTTPConnection', return_value=conn):
                self.assertRaises(ProtocolError, p.request_json, HOST, 'GET', '/info')
            conn.request.assert_called_once()
            conn.close.assert_called_once()
        for result in ({'code':500,'data':INFO}, {'token':'short','ctrlInfoUrl':INFO['ctrlInfoUrl']}, {'code':200,'data':[]}, {}):
            with patch.object(p, 'request_json', return_value=result):
                self.assertRaises(ProtocolError, p.exchange, HOST)
        for result in ({'code':201,'data':{}}, {'code':200,'data':[]}, {}):
            with patch.object(p, 'request_json', side_effect=[INFO, result]):
                self.assertRaises(ProtocolError, p.exchange, HOST)

    def test_timeout_never_replayed(self):
        conn = Mock(); conn.getresponse.side_effect = socket.timeout('sensitive')
        with patch.object(p.http.client, 'HTTPConnection', return_value=conn):
            self.assertRaisesRegex(OSError, 'Provisioning: network', p.request_json, HOST, 'POST', '/ctrl?secret')
        conn.request.assert_called_once(); conn.close.assert_called_once()

from datetime import datetime, timedelta, timezone
from cryptography import x509
from cryptography.hazmat.primitives import hashes, padding, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
import base64


def synthetic_bundle():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(x509.NameOID.COMMON_NAME, 'Synthetic offline test')])
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(1).not_valid_before(now).not_valid_after(now+timedelta(days=1)).sign(key, hashes.SHA256()))
    return {'deviceId':'Synthetic01','modelId':20030,'username':'synthetic-user','password':'synthetic-password',
            'devicecrt':cert.public_bytes(serialization.Encoding.PEM).decode(),
            'devicepk':key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,
                                        serialization.NoEncryption()).decode()}


def encrypt(data=None, plain=None):
    if plain is None: plain = json.dumps(data).encode()
    padder = padding.PKCS7(128).padder(); padded = padder.update(plain)+padder.finalize()
    enc = Cipher(algorithms.AES(TOKEN[16:32].encode()),modes.CBC(b'0123456789abcdef')).encryptor()
    return {'token':'0123456789abcdef','info':base64.b64encode(enc.update(padded)+enc.finalize()).decode()}


class CryptoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.bundle = synthetic_bundle()

    def test_independent_aes_known_answer(self):
        # Generated by openssl enc -aes-128-cbc (not this implementation).
        vector = {'token':'0123456789abcdef','info':'bDJ5vzkl3qg9eqVRd0wT1x+pYXT+GBR43kTW6JLg0Ik='}
        self.assertEqual(p.decrypt_object(TOKEN,vector), {'test':'AES-CBC known answer'})

    def test_bundle_and_both_spellings(self):
        for field in ('modelId','modeId'):
            data = dict(self.bundle); del data['modelId']; data[field] = '20030'
            result = p.decode_bundle(TOKEN, encrypt(data))
            self.assertEqual(result.device_id,'Synthetic01')
            self.assertEqual(result.model_id,20030)
            self.assertNotIn('synthetic-password',repr(result))
            self.assertNotIn('PRIVATE KEY',repr(result))

    def test_invalid_crypto_encoding_padding_json(self):
        invalid = [{}, {'info':'%%%', 'token':'0123456789abcdef'},
                   {'info':'AAAA', 'token':'0123456789abcdef'},
                   {'info':base64.b64encode(b'\0'*16).decode(),'token':'0123456789abcdef'},
                   {'info':'AAAA','token':'short'}, encrypt(plain=b'bad'), encrypt(plain=b'[]'),
                   encrypt(plain=b'\xff')]
        for data in invalid:
            with self.subTest(data=data):
                self.assertRaises(ProtocolError, p.decode_bundle, TOKEN, data)
        self.assertRaises(ProtocolError, p.decode_bundle, 'x' * 16 + 'é' * 16, encrypt(self.bundle))

    def test_missing_fields_and_unsupported_models(self):
        for field in self.bundle:
            for value in (None, '', [], 1):
                data = {**self.bundle, field:value}
                with self.subTest(field=field, value=value):
                    self.assertRaises(ProtocolError, p.decode_bundle, TOKEN, encrypt(data))
        for model in ('9999',True,20031,20030.0):
            self.assertRaises(ProtocolError, p.decode_bundle, TOKEN, encrypt({**self.bundle, 'modelId': model}))
        self.assertRaises(ProtocolError, p.decode_bundle, TOKEN, encrypt({**self.bundle, 'modeId': 9999}))
        self.assertRaises(ProtocolError, p.decode_bundle, TOKEN, encrypt({**self.bundle, 'deviceId': 'bad/id'}))

    def test_invalid_or_mismatched_pems(self):
        other = synthetic_bundle()
        for changes in ({'devicepk':other['devicepk']},{'devicecrt':'bad'},{'devicepk':'bad'}):
            self.assertRaises(ProtocolError, p.decode_bundle, TOKEN, encrypt({**self.bundle, **changes}))
