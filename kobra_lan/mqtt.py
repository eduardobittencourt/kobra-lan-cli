"""Bounded synchronous MQTT 3.1.1 subset. No reconnect or replay of commands.

Protocol reference: KX-Bridge f0ce700fbcc9b3aed54f1a142b4e0318bc11638e.
This implementation contains no imported Bridge modules.
"""
import hashlib
import hmac
import json
import socket
import ssl
import struct
import time
import uuid

from .config import ProtocolError

MAX_PACKET = 4 * 1024 * 1024
BASE = "anycubic/anycubicCloud/v1"


def string(value):
    data = value.encode()
    if len(data) > 65535:
        raise ProtocolError("MQTT string too large")
    return struct.pack("!H", len(data)) + data


def packet(header, body):
    remaining = len(body)
    result = bytearray([header])
    while True:
        byte = remaining % 128
        remaining //= 128
        result.append(byte | (128 if remaining else 0))
        if not remaining:
            break
    return bytes(result) + body


class MQTT:
    def __init__(self, config, timeout=12):
        self.config = config
        self.timeout = timeout
        self.sock = None

    def __enter__(self):
        cfg = self.config
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        # The printer uses a private certificate: pin DER before sending credentials.
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        ctx.load_cert_chain(cfg.client_cert, cfg.client_key)
        raw = socket.create_connection((cfg.host, cfg.mqtt_port), self.timeout)
        try:
            self.sock = ctx.wrap_socket(raw, server_hostname=cfg.host)
            digest = hashlib.sha256(self.sock.getpeercert(binary_form=True)).hexdigest()
            if not hmac.compare_digest(digest, cfg.tls_sha256.lower()):
                raise ProtocolError("Printer TLS fingerprint changed; credentials were not sent")
            self.sock.settimeout(self.timeout)
            client_id = "kobra-lan-" + uuid.uuid4().hex[:16]
            connect = b"\x00\x04MQTT\x04\xc2\x00\x3c"
            connect += string(client_id) + string(cfg.mqtt_username) + string(cfg.mqtt_password)
            self.sock.sendall(packet(0x10, connect))
            header, body = self.receive(time.monotonic() + self.timeout)
            if header != 0x20 or body != b"\x00\x00":
                raise ProtocolError("MQTT authentication rejected")
            topic = f"{BASE}/printer/+/{cfg.type_id}/{cfg.printer_id}/#"
            self.sock.sendall(packet(0x82, b"\x00\x01" + string(topic) + b"\x00"))
            deadline = time.monotonic() + self.timeout
            while True:
                header, body = self.receive(deadline)
                if header == 0x90:
                    if body != b"\x00\x01\x00":
                        raise ProtocolError("MQTT subscription rejected")
                    break
            return self
        except BaseException:
            if self.sock:
                self.sock.close()
            else:
                raw.close()
            raise

    def __exit__(self, *args):
        if self.sock:
            try:
                self.sock.sendall(b"\xe0\x00")
            except OSError:
                pass
            self.sock.close()

    def _read(self, size, deadline):
        result = bytearray()
        while len(result) < size:
            left = deadline - time.monotonic()
            if left <= 0:
                raise ProtocolError("MQTT response timeout (command was not retried)")
            self.sock.settimeout(left)
            part = self.sock.recv(size - len(result))
            if not part:
                raise ProtocolError("MQTT connection closed")
            result.extend(part)
        return bytes(result)

    def receive(self, deadline):
        header = self._read(1, deadline)[0]
        size = 0
        multiplier = 1
        for _ in range(4):
            byte = self._read(1, deadline)[0]
            size += (byte & 127) * multiplier
            if not byte & 128:
                if size > MAX_PACKET:
                    raise ProtocolError("MQTT packet exceeds size limit")
                return header, self._read(size, deadline)
            multiplier *= 128
        raise ProtocolError("Malformed MQTT length")

    def query(self, kind, action="query", data=None):
        # Keep this public method strictly read-only.
        allowed = {("info", "query"), ("print", "query"), ("status", "query"),
                   ("multiColorBox", "getInfo"), ("file", "fileDetails"),
                   ("file", "listLocal")}
        if (kind, action) not in allowed:
            raise ProtocolError("Unqualified MQTT command")
        msgid = str(uuid.uuid4())
        sent_timestamp = int(time.time() * 1000)
        payload = {"type": kind, "action": action, "msgid": msgid,
                   "timestamp": sent_timestamp, "data": data}
        topic = f"{BASE}/slicer/printer/{self.config.type_id}/{self.config.printer_id}/{kind}"
        self.sock.sendall(packet(0x30, string(topic) + json.dumps(payload, separators=(",", ":")).encode()))
        deadline = time.monotonic() + self.timeout
        acknowledged = False
        while True:
            header, body = self.receive(deadline)
            if header >> 4 != 3:
                continue
            if len(body) < 2:
                raise ProtocolError("Malformed MQTT publish")
            length = struct.unpack("!H", body[:2])[0]
            if length + 2 > len(body):
                raise ProtocolError("Malformed MQTT topic")
            topic = body[2:2 + length].decode()
            offset = 2 + length
            qos = (header >> 1) & 3
            if qos not in (0, 1):
                raise ProtocolError("Unsupported MQTT QoS")
            if qos == 1:
                pid = body[offset:offset + 2]
                offset += 2
                self.sock.sendall(packet(0x40, pid))
            try:
                result = json.loads(body[offset:])
            except (ValueError, UnicodeDecodeError):
                continue
            if not isinstance(result, dict):
                continue
            # FW 2.0.2.2 sends a correlated /response ACK, then a report with
            # its own msgid. Gate that report by the ACK and fresh timestamp.
            if result.get("msgid") == msgid and topic.endswith("/response"):
                if result.get("code") != 0:
                    raise ProtocolError("MQTT query rejected")
                acknowledged = True
                continue
            is_report = topic.endswith(f"/{kind}/report") and result.get("type") == kind
            if is_report and isinstance(result.get("data"), dict):
                if result.get("msgid") == msgid:
                    return result
                stamp = result.get("timestamp")
                if (acknowledged and isinstance(stamp, (int, float))
                        and sent_timestamp <= stamp <= int(time.time() * 1000) + 5000):
                    return result

    def start_once(self, payload):
        """One MQTT start publish, one correlated ACK wait; never reconnect/replay.

        Call only after the application has durably reserved this start attempt.
        ACK means accepted by the broker/device, not proof of physical printing.
        """
        msgid = str(uuid.uuid4())
        message = {"type": "print", "action": "start", "msgid": msgid,
                   "timestamp": int(time.time() * 1000), "data": payload}
        topic = f"{BASE}/slicer/printer/{self.config.type_id}/{self.config.printer_id}/print"
        self.sock.sendall(packet(0x30, string(topic) + json.dumps(message, separators=(",", ":")).encode()))
        deadline = time.monotonic() + self.timeout
        while True:
            header, body = self.receive(deadline)
            if header != 0x30 or len(body) < 2:
                continue
            size = struct.unpack("!H", body[:2])[0]
            topic = body[2:2 + size].decode()
            try:
                response = json.loads(body[2 + size:])
            except (ValueError, UnicodeDecodeError):
                continue
            if isinstance(response, dict) and topic.endswith("/response") and response.get("msgid") == msgid:
                if response.get("code") != 0:
                    raise ProtocolError("Start was rejected; do not retry automatically")
                return {"code": 0, "msgid": msgid}
