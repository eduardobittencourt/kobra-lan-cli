import ipaddress
import json
import stat
from dataclasses import dataclass, field
from pathlib import Path


class ProtocolError(Exception):
    pass


@dataclass(repr=False)
class Config:
    host: str
    type_id: int
    printer_id: str
    mqtt_username: str = field(repr=False)
    mqtt_password: str = field(repr=False)
    client_cert: str
    client_key: str = field(repr=False)
    tls_sha256: str
    mqtt_port: int = 9883
    http_port: int = 18910

    @classmethod
    def load(cls, path: Path):
        if stat.S_IMODE(path.stat().st_mode) & 0o077:
            raise ProtocolError("Config must have permissions 0600")
        config = cls(**json.loads(path.read_text()))
        ipaddress.IPv4Address(config.host)
        if config.type_id != 20030:
            raise ProtocolError("Only Kobra X model 20030 is qualified")
        if not config.printer_id.isalnum():
            raise ProtocolError("Invalid device identity")
        if len(config.tls_sha256) != 64:
            raise ProtocolError("TLS SHA-256 pin is required")
        bytes.fromhex(config.tls_sha256)
        for filename in [config.client_cert, config.client_key]:
            if stat.S_IMODE(Path(filename).stat().st_mode) & 0o077:
                raise ProtocolError("Client certificate/key must have permissions 0600")
        return config

