"""Bounded LAN bootstrap. HTTP provisioning does not authenticate the printer.

Protocol reference: stribor/anycubic_kobrax 34955343bf5fe71c0490f87682776d4b8053c43f.
No upstream application modules are imported.
"""
import base64
import hashlib
import http.client
import ipaddress
import json
import secrets
import string
import time
import uuid
from dataclasses import dataclass, field
from urllib.parse import urlencode, urlsplit

from cryptography import x509
from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.primitives import padding, serialization
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from .config import ProtocolError

MAX_RESPONSE = 1024 * 1024


def validate_host(host):
    """Require a canonical bare IPv4 address before opening any connection."""
    try:
        if str(ipaddress.IPv4Address(host)) != host:
            raise ValueError
    except (ValueError, TypeError):
        raise ProtocolError("Identity: supply a bare IPv4 address") from None


def request_json(host, method, target):
    """Perform one bounded HTTP request without proxy lookup, redirects or replay."""
    conn = http.client.HTTPConnection(host, 18910, timeout=10)
    try:
        conn.request(method, target)
        response = conn.getresponse()
        raw = response.read(MAX_RESPONSE + 1)
        if response.status != 200 or len(raw) > MAX_RESPONSE:
            raise ProtocolError("Provisioning: HTTP status or response size rejected")
        try:
            result = json.loads(raw)
        except (ValueError, RecursionError):
            raise ProtocolError("Provisioning: invalid JSON response") from None
        if not isinstance(result, dict):
            raise ProtocolError("Provisioning: expected an object response")
        return result
    except (OSError, http.client.HTTPException):
        raise OSError("Provisioning: network exchange failed; no automatic retry") from None
    finally:
        conn.close()


def required(data, name):
    """Read a required nonblank string without exposing response values in errors."""
    value = data.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ProtocolError("Response validation: missing required field")
    return value


def identity(host):
    """Validate printer identity and constrain the control endpoint to the selected host."""
    validate_host(host)
    result = request_json(host, "GET", "/info")
    if "code" in result:
        if type(result["code"]) is not int or result["code"] != 200 or not isinstance(result.get("data"), dict):
            raise ProtocolError("Identity: unsuccessful response")
        result = result["data"]
    token = required(result, "token")
    if len(token) < 32:
        raise ProtocolError("Identity: invalid provisioning token")
    endpoint = required(result, "ctrlInfoUrl")
    try:
        parsed = urlsplit(endpoint)
        safe = (parsed.scheme == "http" and parsed.hostname == host and parsed.port == 18910
                and parsed.path == "/ctrl" and parsed.netloc == f"{host}:18910"
                and not parsed.query and not parsed.fragment and "?" not in endpoint
                and "#" not in endpoint and not any(ord(c) <= 32 or ord(c) == 127 for c in endpoint))
    except ValueError:
        safe = False
    if not safe:
        raise ProtocolError("Identity: unsafe control endpoint")
    return token


def signed_parameters(token):
    """Build the firmware-defined timestamp, nonce, UUID and MD5 signature."""
    ts = str(int(time.time() * 1000))
    nonce = "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(6))
    inner = hashlib.md5(token[:16].encode(), usedforsecurity=False).hexdigest()
    sign = hashlib.md5((inner + ts + nonce).encode(), usedforsecurity=False).hexdigest()
    return {"ts": ts, "nonce": nonce, "sign": sign, "did": uuid.uuid4().hex.upper()}


def exchange(host):
    """Fetch identity and send exactly one signed credential request."""
    token = identity(host)
    response = request_json(host, "POST", "/ctrl?" + urlencode(signed_parameters(token)))
    if type(response.get("code")) is not int or response["code"] != 200 or not isinstance(response.get("data"), dict):
        raise ProtocolError("Provisioning: credential request rejected")
    return token, response["data"]


@dataclass(repr=False)
class Bundle:
    device_id: str
    model_id: int
    username: str = field(repr=False)
    password: str = field(repr=False)
    certificate: str = field(repr=False)
    private_key: str = field(repr=False)


def model_id(data):
    """Normalize the two firmware field spellings while rejecting unqualified models."""
    values = [data[k] for k in ("modelId", "modeId") if k in data]
    if not values or any(type(v) not in (str, int) or str(v) != "20030" for v in values):
        raise ProtocolError("Response validation: only model 20030 is qualified")
    return 20030


def decrypt_object(token, data):
    """Decode the firmware CBC bundle with strict padding and JSON validation."""
    try:
        encoded = required(data, "info")
        iv = required(data, "token").encode("utf-8")
        key = token[16:32].encode("utf-8")
        if len(key) != 16 or len(iv) != 16 or len(encoded) > MAX_RESPONSE:
            raise ValueError
        ciphertext = base64.b64decode(encoded, validate=True)
        # Printer-mandated decrypt-only wire format, not a new encryption scheme.
        # CBC gives no authenticity; see docs/pairing-security-review.md.
        decryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
        padded = decryptor.update(ciphertext) + decryptor.finalize()
        unpadder = padding.PKCS7(128).unpadder()
        plain = unpadder.update(padded) + unpadder.finalize()
        result = json.loads(plain)
        if not isinstance(result, dict):
            raise ValueError
        return result
    except ProtocolError:
        raise
    except (ValueError, TypeError, RecursionError):
        raise ProtocolError("Response validation: invalid encrypted credential object") from None


def decode_bundle(token, data):
    """Validate decrypted identity, credentials and matching certificate/key material."""
    try:
        result = decrypt_object(token, data)
        device_id = required(result, "deviceId")
        if not device_id.isalnum():
            raise ValueError
        model = model_id(result)
        username, password = required(result, "username"), required(result, "password")
        certificate, private_key = required(result, "devicecrt"), required(result, "devicepk")
        cert = x509.load_pem_x509_certificate(certificate.encode())
        pk = serialization.load_pem_private_key(private_key.encode(), password=None)
        def public_bytes(obj):
            """Serialize a canonical public key for certificate/private-key comparison."""
            return obj.public_key().public_bytes(serialization.Encoding.DER,
                                                serialization.PublicFormat.SubjectPublicKeyInfo)
        if public_bytes(cert) != public_bytes(pk):
            raise ValueError
        return Bundle(device_id, model, username, password, certificate, private_key)
    except ProtocolError:
        raise
    except (ValueError, TypeError, RecursionError, UnsupportedAlgorithm):
        raise ProtocolError("Response validation: invalid encrypted credentials or certificate/key") from None


def provision(host):
    """Obtain a validated in-memory credential bundle without persisting secrets."""
    token, data = exchange(host)
    return decode_bundle(token, data)
