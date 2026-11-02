"""First-use trust, read-only verification and private no-replace publication."""
import hashlib
import hmac
import json
import os
import re
import socket
import ssl
import stat
import sys
import uuid
from dataclasses import asdict
from pathlib import Path

from .config import Config, ProtocolError
from .provisioning import provision, validate_host

from .mqtt import MQTT
from .printer import payload_data

CANDIDATE_FILE = "candidate.json"
QUALIFIED_FIRMWARE = "2.0.2.2"


def observe_fingerprint(config):
    """TLS only: client certificate exchange, no MQTT CONNECT or credentials."""
    # Observation only, not an authenticated connection: see docs/pairing-security-review.md.
    # Trust is decided explicitly, then MQTT independently rechecks the accepted pin.
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    ctx.load_cert_chain(config.client_cert, config.client_key)
    with (socket.create_connection((config.host, config.mqtt_port), 10) as raw,
          ctx.wrap_socket(raw, server_hostname=config.host) as tls):
        return hashlib.sha256(tls.getpeercert(binary_form=True)).hexdigest()


def verify_status(config):
    try:
        with MQTT(config) as client:
            info = payload_data(client.query("info"))
    except ProtocolError:
        raise ProtocolError("Authentication/status: pinned connection or fresh info query failed") from None
    if (info.get("model") != "Anycubic Kobra X" or info.get("version") != QUALIFIED_FIRMWARE
            or any(str(info[k]) != str(config.type_id) for k in ("modelId", "modeId") if k in info)
            or ("deviceId" in info and info["deviceId"] != config.printer_id)):
        raise ProtocolError("Status qualification: only matching model 20030 / firmware 2.0.2.2 is qualified")
    state = info.get("state")
    if not isinstance(state, str) or not state or len(state) > 80 or not state.isascii() or not state.isprintable():
        raise ProtocolError("Status qualification: missing or invalid printer state")
    return {"firmware": QUALIFIED_FIRMWARE, "state": state}



def validate_pin(expected):
    if expected is not None and (not isinstance(expected, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", expected)):
        raise ProtocolError("Trust: --trust-sha256 must contain exactly 64 hexadecimal digits")


def terminal_text(value):
    # JSON escaping covers C0/C1, bidi controls and other non-ASCII terminal input.
    return json.dumps(str(value)[:160], ensure_ascii=True)


def accept_trust(config, observed, expected=None, stdin=None, stderr=None):
    validate_pin(expected)
    if expected is not None:
        if not hmac.compare_digest(expected.lower(), observed):
            raise ProtocolError("Trust: server fingerprint does not match --trust-sha256")
        return
    stdin = sys.stdin if stdin is None else stdin
    stderr = sys.stderr if stderr is None else stderr
    if not stdin.isatty():
        raise ProtocolError("Trust: noninteractive pairing requires --trust-sha256")
    print(f"Host {terminal_text(config.host)}, model {config.type_id}, device {terminal_text(config.printer_id)}", file=stderr)
    print(f"Server SHA-256: {observed}", file=stderr)
    print("HTTP provisioning does not authenticate the printer. Accepting trusts this first connection.", file=stderr)
    print("Trust this fingerprint? [y/N] ", end="", file=stderr, flush=True)
    try:
        answer = stdin.readline(32)
    except (EOFError, OSError):
        answer = ""
    if len(answer) == 32 or answer.strip().lower() not in ("y", "yes"):
        raise ProtocolError("Trust: fingerprint was not explicitly accepted")



class PrivateStage:
    """Directory descriptors keep managed operations independent of symlink races."""
    def __init__(self, destination):
        self.path = Path(os.path.abspath(destination))
        self.parent_fd = self.stage_fd = None
        self.stage_name = None
        self.committed = False
        self.files = set()
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        fd = os.open('/', flags)
        try:
            for part in self.path.parent.parts[1:]:
                try:
                    next_fd = os.open(part, flags, dir_fd=fd)
                except FileNotFoundError:
                    try:
                        os.mkdir(part, 0o700, dir_fd=fd)
                        os.fsync(fd)
                    except FileExistsError:
                        pass
                    next_fd = os.open(part, flags, dir_fd=fd)
                os.close(fd)
                fd = next_fd
            self.parent_fd = fd
            fd = None
            # lexists semantics, including dangling symlinks.
            try:
                os.stat(self.path.name, dir_fd=self.parent_fd, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                raise OSError("Persistence: config exists; choose a separate absent --config destination")
            current = os.fstat(self.parent_fd)
            if current.st_uid != os.geteuid() or stat.S_IMODE(current.st_mode) != 0o700:
                raise OSError("Persistence: config parent must be user-owned with permissions 0700")
        except BaseException:
            if fd is not None:
                os.close(fd)
            self.close()
            raise

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            if self.stage_name is not None and not self.committed:
                for name in self.files:
                    os.unlink(name, dir_fd=self.stage_fd)
                os.rmdir(self.stage_name, dir_fd=self.parent_fd)
        finally:
            self.close()

    def close(self):
        for attr in ('stage_fd', 'parent_fd'):
            fd = getattr(self, attr, None)
            if fd is not None:
                os.close(fd)
                setattr(self, attr, None)

    def write_secret(self, name, content):
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=self.stage_fd)
        self.files.add(name)
        with os.fdopen(fd, 'wb') as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())

    def prepare(self, bundle, host):
        name = '.pair-' + uuid.uuid4().hex
        os.mkdir(name, 0o700, dir_fd=self.parent_fd)
        self.stage_name = name
        self.stage_fd = os.open(self.stage_name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                dir_fd=self.parent_fd)
        # Explicit modes also work with unusually restrictive umasks.
        os.fchmod(self.stage_fd, 0o700)
        self.write_secret('client.crt', bundle.certificate.encode())
        self.write_secret('client.key', bundle.private_key.encode())
        root = self.path.parent / self.stage_name
        return Config(host, bundle.model_id, bundle.device_id, bundle.username, bundle.password,
                      str(root / 'client.crt'), str(root / 'client.key'), '0' * 64)

    def publish(self, config):
        self.write_secret(CANDIDATE_FILE, json.dumps(asdict(config), ensure_ascii=True).encode())
        os.fsync(self.stage_fd)
        try:
            os.link(CANDIDATE_FILE, self.path.name, src_dir_fd=self.stage_fd,
                    dst_dir_fd=self.parent_fd, follow_symlinks=False)
        except OSError:
            # A failed/ambiguous publication must not remove PEMs if our exact
            # candidate inode is already visible at the destination.
            try:
                source = os.stat(CANDIDATE_FILE, dir_fd=self.stage_fd, follow_symlinks=False)
                target = os.stat(self.path.name, dir_fd=self.parent_fd, follow_symlinks=False)
                self.committed = (source.st_dev, source.st_ino) == (target.st_dev, target.st_ino)
            except OSError:
                pass
            raise
        # From this instruction onward cleanup must preserve referenced PEMs,
        # even if fsync or removing the extra JSON link raises.
        self.committed = True
        os.fsync(self.parent_fd)
        os.unlink(CANDIDATE_FILE, dir_fd=self.stage_fd)
        self.files.remove(CANDIDATE_FILE)
        os.fsync(self.stage_fd)



class PairingLocalError(OSError):
    """Only messages constructed here may be presented by the pairing CLI."""


def pair(destination, host, expected=None):
    validate_host(host)
    validate_pin(expected)
    failure_stage = "Persistence"
    try:
        with PrivateStage(destination) as stage:
            failure_stage = "Provisioning"
            bundle = provision(host)
            failure_stage = "Persistence"
            candidate = stage.prepare(bundle, host)
            failure_stage = "Trust observation"
            observed = observe_fingerprint(candidate)
            accept_trust(candidate, observed, expected)
            candidate.tls_sha256 = observed
            failure_stage = "Authentication/status"
            status = verify_status(candidate)
            failure_stage = "Persistence"
            stage.publish(candidate)
            return {"config_path": str(stage.path), "model_id": candidate.type_id,
                    "firmware": status["firmware"], "state": status["state"], "tls_sha256": observed}
    except OSError:
        if failure_stage == "Persistence":
            message = ("Persistence: private configuration could not be saved or finalized; "
                       "an existing config is preserved. Choose a separate absent --config path "
                       "in a user-owned 0700 directory. If a config is visible, retain its PEM files.")
        else:
            message = failure_stage + ": network operation failed; no automatic retry"
        raise PairingLocalError(message) from None
