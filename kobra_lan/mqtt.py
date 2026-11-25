"""Bounded synchronous MQTT 3.1.1 subset. No reconnect or replay of commands.

Protocol reference: KX-Bridge f0ce700fbcc9b3aed54f1a142b4e0318bc11638e.
This implementation contains no imported Bridge modules.
"""
import hashlib
import hmac
import json
import re
import socket
import ssl
import struct
import time
import uuid

from .config import ProtocolError, validate_filename

MAX_PACKET = 4 * 1024 * 1024
BASE = "anycubic/anycubicCloud/v1"
CONTROL_ACTIONS = frozenset({"pause", "resume", "stop"})
TASKID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
VIDEO_CAPTURE_REJECTED = "Video capture command was rejected; do not retry automatically"


def validate_delete_filename(value):
    filename = validate_filename(value)
    if not filename.strip("."):
        raise ProtocolError("Filename must contain a character other than a dot")
    return filename


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


class MQTTFailure(ProtocolError):
    """Typed diagnostic category retaining the operational ProtocolError contract."""
    def __init__(self, stage, code, message, exit_code=2):
        super().__init__(message)
        self.stage, self.code, self.exit_code = stage, code, exit_code


class MQTTIOFailure(OSError):
    def __init__(self, stage, *, timed_out=False):
        super().__init__("MQTT network operation failed; no automatic retry")
        self.stage = stage
        self.timed_out = timed_out


class MQTTClosed(MQTTFailure):
    """Peer closed the transport before the next packet was complete."""


def mqtt_failure_exit_code(error):
    if isinstance(error, (MQTTClosed, OSError)):
        return 3
    if isinstance(error, MQTTFailure) and (error.exit_code == 3 or error.code == "timeout"):
        return 3
    return 2


class MQTT:
    def __init__(self, config, timeout=12, deadline=None, observer=None):
        self.config = config
        self.timeout = timeout
        self.sock = None
        self.deadline = deadline
        self.observer = observer
        self.stage = 'status'
        self.stage_deadline = None

    def begin_stage(self, stage):
        self.stage = stage
        self.stage_deadline = self.limit()

    def limit(self):
        end = time.monotonic() + self.timeout
        return min(end, self.deadline) if self.deadline is not None else end

    def remaining(self):
        remaining = (self.stage_deadline or self.limit()) - time.monotonic()
        if remaining <= 0:
            raise self._timeout()
        return remaining

    def _timeout(self):
        return MQTTFailure(self.stage, 'timeout', 'MQTT response timeout (command was not retried)', 3)

    def passed(self, stage):
        if self.observer is not None:
            self.observer(stage)

    def __enter__(self):
        cfg = self.config
        raw = None
        self.begin_stage('tls_pin')
        try:
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            # Pin DER before MQTT credentials. No CA/hostname substitution.
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            ctx.load_cert_chain(cfg.client_cert, cfg.client_key)
            raw = socket.create_connection((cfg.host, cfg.mqtt_port), self.remaining())
            raw.settimeout(self.remaining())
            self.sock = ctx.wrap_socket(raw, server_hostname=cfg.host)
            digest = hashlib.sha256(self.sock.getpeercert(binary_form=True)).hexdigest()
            if not hmac.compare_digest(digest, cfg.tls_sha256.lower()):
                raise MQTTFailure('tls_pin', 'pin_mismatch', 'Printer TLS fingerprint changed; credentials were not sent')
            self.passed('tls_pin')
            self.begin_stage('mqtt_auth')
            self.sock.settimeout(self.remaining())
            client_id = 'kobra-lan-' + uuid.uuid4().hex[:16]
            connect = b'\x00\x04MQTT\x04\xc2\x00\x3c'
            connect += string(client_id) + string(cfg.mqtt_username) + string(cfg.mqtt_password)
            self.sock.sendall(packet(0x10, connect))
            header, body = self.receive(self.stage_deadline)
            if header != 0x20 or body != b'\x00\x00':
                raise MQTTFailure('mqtt_auth', 'authentication_rejected', 'MQTT authentication rejected')
            topic = f'{BASE}/printer/+/{cfg.type_id}/{cfg.printer_id}/#'
            self.sock.settimeout(self.remaining())
            self.sock.sendall(packet(0x82, b'\x00\x01' + string(topic) + b'\x00'))
            while True:
                header, body = self.receive(self.stage_deadline)
                if header == 0x90:
                    if body != b'\x00\x01\x00':
                        raise MQTTFailure('mqtt_auth', 'subscription_rejected', 'MQTT subscription rejected')
                    break
            self.passed('mqtt_auth')
            self.stage = 'status'
            self.stage_deadline = None
            return self
        except BaseException as error:
            self._abort(error, raw)
            raise

    def _abort(self, error, raw):
        """Close transport before translating an operational failure."""
        if self.sock:
            self.sock.close()
        elif raw is not None:
            raw.close()
        if isinstance(error, OSError):
            raise MQTTIOFailure(self.stage, timed_out=isinstance(error, TimeoutError)) from None
        if isinstance(error, ProtocolError) and not isinstance(error, MQTTFailure):
            raise MQTTFailure(self.stage, 'protocol_rejected', str(error)) from None

    def __exit__(self, *args):
        if self.sock:
            try:
                if self.deadline is None:
                    self.sock.sendall(b"\xe0\x00")
                elif (left := self.deadline - time.monotonic()) > 0:
                    self.sock.settimeout(min(self.timeout, left))
                    self.sock.sendall(b"\xe0\x00")
            except OSError:
                pass
            finally:
                self.sock.close()

    def _read(self, size, deadline):
        result = bytearray()
        while len(result) < size:
            left = deadline - time.monotonic()
            if left <= 0:
                raise self._timeout()
            self.sock.settimeout(left)
            part = self.sock.recv(size - len(result))
            if not part:
                raise MQTTClosed(self.stage, 'protocol_rejected', 'MQTT connection closed')
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

    def query(self, kind, action="query", data=None, *, require_fresh=False):
        # Keep this public method strictly read-only.
        allowed = {("info", "query"), ("print", "query"), ("status", "query"),
                   ("peripherie", "query"), ("multiColorBox", "getInfo"),
                   ("file", "fileDetails"), ("file", "listLocal")}
        if (kind, action) not in allowed:
            raise ProtocolError("Unqualified MQTT command")
        self.begin_stage('status')
        msgid = str(uuid.uuid4())
        sent_timestamp = int(time.time() * 1000)
        payload = {"type": kind, "action": action, "msgid": msgid,
                   "timestamp": sent_timestamp, "data": data}
        topic = f"{BASE}/slicer/printer/{self.config.type_id}/{self.config.printer_id}/{kind}"
        self.sock.settimeout(self.remaining())
        self.sock.sendall(packet(0x30, string(topic) + json.dumps(payload, separators=(",", ":")).encode()))
        deadline = self.stage_deadline
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
                if len(pid) != 2:
                    raise ProtocolError("Malformed MQTT packet identifier")
                offset += 2
                self.sock.settimeout(self.remaining())
                self.sock.sendall(packet(0x40, pid))
            if require_fresh and header & 1:
                continue
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
                correlated = result.get("msgid") == msgid
                if correlated and not require_fresh:
                    return result
                stamp = result.get("timestamp")
                if ((correlated or acknowledged) and type(stamp) in (int, float)
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

    def control_once(self, action, taskid="-1"):
        """One MQTT print control publish, one correlated ACK wait; never reconnect/replay.

        Allowed actions are strictly pause, resume, and stop. ACK means accepted by the
        broker/device, not proof of physical state transition.
        """
        if action not in CONTROL_ACTIONS:
            raise ProtocolError("Unqualified MQTT print control action")
        if not isinstance(taskid, str) or TASKID_RE.fullmatch(taskid) is None:
            raise ProtocolError("Invalid print control taskid")
        self.begin_stage('control')
        msgid = str(uuid.uuid4())
        message = {
            "type": "print",
            "action": action,
            "msgid": msgid,
            "timestamp": int(time.time() * 1000),
            "data": {"taskid": taskid},
        }
        topic = f"{BASE}/slicer/printer/{self.config.type_id}/{self.config.printer_id}/print"
        self.sock.settimeout(self.remaining())
        self.sock.sendall(packet(0x30, string(topic) + json.dumps(message, separators=(",", ":")).encode()))
        deadline = self.stage_deadline
        while True:
            header, body = self.receive(deadline)
            if header >> 4 != 3:
                continue
            response_topic, data = self._publish_fields(header, body)
            try:
                response = json.loads(data)
            except (ValueError, UnicodeDecodeError):
                if response_topic.endswith("/response"):
                    raise ProtocolError("Malformed MQTT control response") from None
                continue
            if not isinstance(response, dict):
                if response_topic.endswith("/response"):
                    raise ProtocolError("Malformed MQTT control response")
                continue
            if response_topic.endswith("/response") and response.get("msgid") == msgid:
                code = response.get("code")
                if type(code) is not int or code != 0:
                    raise ProtocolError("Print control was rejected; do not retry automatically")
                return {"code": 0, "msgid": msgid}

    def _publish_fields(self, header, body):
        if len(body) < 2:
            raise ProtocolError("Malformed MQTT publish")
        length = struct.unpack("!H", body[:2])[0]
        offset = 2 + length
        if offset > len(body):
            raise ProtocolError("Malformed MQTT topic")
        try:
            topic = body[2:offset].decode()
        except UnicodeDecodeError:
            raise ProtocolError("Malformed MQTT topic") from None
        qos = (header >> 1) & 3
        if qos not in (0, 1):
            raise ProtocolError("Unsupported MQTT QoS")
        if qos == 1:
            pid = body[offset:offset + 2]
            if len(pid) != 2:
                raise ProtocolError("Malformed MQTT packet identifier")
            offset += 2
            self.sock.settimeout(self.remaining())
            self.sock.sendall(packet(0x40, pid))
        return topic, body[offset:]

    def delete_file_once(self, filename, *, on_ack=None, on_report=None):
        """Send one storage deletion request and wait for both ACK and report."""
        filename = validate_delete_filename(filename)
        self.begin_stage("file_delete")
        msgid = str(uuid.uuid4())
        sent_timestamp = int(time.time() * 1000)
        message = {
            "type": "file",
            "action": "deleteBatch",
            "msgid": msgid,
            "timestamp": sent_timestamp,
            "data": {"root": "local", "files": [{"path": "/", "filename": filename}]},
        }
        topic = f"{BASE}/slicer/printer/{self.config.type_id}/{self.config.printer_id}/file"
        self.sock.settimeout(self.remaining())
        self.sock.sendall(packet(0x30, string(topic) + json.dumps(message, separators=(",", ":")).encode()))
        ack = report = None
        while ack is None or report is None:
            header, body = self.receive(self.stage_deadline)
            if header >> 4 != 3:
                continue
            response_topic, data = self._publish_fields(header, body)
            if header & 1:
                continue
            is_ack = response_topic.endswith("/response")
            if not is_ack and not response_topic.endswith("/file/report"):
                continue
            try:
                result = json.loads(data)
            except (ValueError, RecursionError):
                raise ProtocolError("Malformed MQTT file deletion response") from None
            if not isinstance(result, dict):
                raise ProtocolError("Malformed MQTT file deletion response")
            correlated = result.get("msgid") == msgid
            if is_ack:
                if not correlated:
                    continue
                code = result.get("code")
                if type(code) is not int or code != 0:
                    raise ProtocolError("File deletion was rejected; do not retry automatically")
                if ack is None:
                    ack = {"code": 0, "msgid": msgid}
                    if on_ack is not None:
                        on_ack(ack)
                continue
            if result.get("type") != "file" or result.get("action") != "deleteBatch":
                continue
            stamp = result.get("timestamp")
            fresh = (type(stamp) in (int, float)
                     and sent_timestamp <= stamp <= int(time.time() * 1000) + 5000)
            if not correlated and not (ack is not None and fresh):
                continue
            code = result.get("code", 0)
            if result.get("state") != "success" or type(code) is not int or code not in (0, 200):
                raise ProtocolError("File deletion was rejected; do not retry automatically")
            report = {"action": "deleteBatch", "state": "success"}
            if "code" in result:
                report["code"] = code
            if on_report is not None:
                on_report(report)
        return {"ack": ack, "report": report}

    def _receive_video_packet(self):
        header, body = self.receive(self.stage_deadline)
        if header >> 4 != 3:
            return None
        response_topic, data = self._publish_fields(header, body)
        if header & 1:
            return None
        is_ack = response_topic.endswith("/response")
        if not is_ack and not response_topic.endswith("/video/report"):
            return None
        try:
            result = json.loads(data)
        except (ValueError, RecursionError):
            raise ProtocolError("Malformed MQTT video response") from None
        if not isinstance(result, dict):
            raise ProtocolError("Malformed MQTT video response")
        return is_ack, result

    def _consume_video_ack(self, result, msgid, ack):
        if result.get("msgid") != msgid:
            return ack
        code = result.get("code")
        if type(code) is not int or code != 0:
            raise ProtocolError(VIDEO_CAPTURE_REJECTED)
        return ack or {"code": 0, "msgid": msgid}

    def _consume_video_report(
        self, result, action, terminal_state, intermediate_states, states, ack, msgid, sent_timestamp
    ):
        if result.get("type") != "video" or result.get("action") != action:
            return None
        correlated = result.get("msgid") == msgid
        stamp = result.get("timestamp")
        fresh = (
            type(stamp) in (int, float)
            and sent_timestamp <= stamp <= int(time.time() * 1000) + 5000
        )
        if not correlated and not (ack is not None and fresh):
            return None
        code = result.get("code", 0)
        state = result.get("state")
        if type(code) is not int or code not in (0, 200):
            raise ProtocolError(VIDEO_CAPTURE_REJECTED)
        if state in intermediate_states:
            states.append(state)
            return None
        if state != terminal_state:
            raise ProtocolError(VIDEO_CAPTURE_REJECTED)
        states.append(state)
        report = {"action": action, "state": terminal_state, "states": states}
        if "code" in result:
            report["code"] = code
        return report

    def _video_capture_once(self, action, terminal_state, intermediate_states=frozenset()):
        self.begin_stage("camera")
        msgid = str(uuid.uuid4())
        sent_timestamp = int(time.time() * 1000)
        message = {
            "type": "video",
            "action": action,
            "msgid": msgid,
            "timestamp": sent_timestamp,
            "data": None,
        }
        topic = f"{BASE}/slicer/printer/{self.config.type_id}/{self.config.printer_id}/video"
        self.sock.settimeout(self.remaining())
        self.sock.sendall(packet(0x30, string(topic) + json.dumps(message, separators=(",", ":")).encode()))
        ack = report = None
        states = []
        while ack is None or report is None:
            received = self._receive_video_packet()
            if received is None:
                continue
            is_ack, result = received
            if is_ack:
                ack = self._consume_video_ack(result, msgid, ack)
            else:
                report = self._consume_video_report(
                    result, action, terminal_state, intermediate_states, states, ack, msgid, sent_timestamp
                )
        return {"ack": ack, "report": report}

    def start_video_capture_once(self):
        """Send one video/startCapture request and wait for ACK and pushStarted."""
        return self._video_capture_once(
            "startCapture",
            "pushStarted",
            intermediate_states=frozenset({"initSuccess", "joinSuccess"}),
        )

    def stop_video_capture_once(self):
        """Send one video/stopCapture request and wait for ACK and pushStopped."""
        return self._video_capture_once("stopCapture", "pushStopped")
