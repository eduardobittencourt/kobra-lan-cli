"""Strictly read-only LAN SSDP discovery for Anycubic FDM printers.

Uses only the Python standard library to send bounded UDP multicast M-SEARCH
probes (ST: ac:3dprinter:fdm) and validate unicast responses against their UDP
sender IPv4 address. Never contacts HTTP port 18910 or MQTT port 9883, never
auto-pairs, never writes profiles or state, and never exposes raw LOCATION URLs
or cloud binding codes (cn).
"""
import ipaddress
import re
import select
import socket
import time
from urllib.parse import parse_qs, urlsplit

from .cli_output import safe_text
from .qualification import (
    KOBRA_X,
    QUALIFIED_FIRMWARE,
    is_discovery_hardware_validated,
    qualification_for_model_id,
)

SSDP_MULTICAST_HOST = "239.255.255.250"
SSDP_MULTICAST_PORT = 1900
SSDP_SEARCH_TARGET = "ac:3dprinter:fdm"
SSDP_MX = 5
SSDP_MULTICAST_TTL = 2
PRINTER_HTTP_PORT = 18910

DEFAULT_DISCOVER_TIMEOUT = 5
MAX_DISCOVER_TIMEOUT = 15
MAX_DATAGRAM_BYTES = 4096
MAX_NAME_LENGTH = 80

_STATUS_LINE_RE = re.compile(r"HTTP/1\.\d+\s+200(?:\s+.*)?", flags=re.IGNORECASE | re.ASCII)
_USN_MAC_RE = re.compile(
    r"^uuid:fdm:((?:[0-9a-f]{2}[-:]){5}[0-9a-f]{2})$",
    flags=re.IGNORECASE | re.ASCII,
)
_MODEL_ID_RE = re.compile(r"0|[1-9][0-9]*", flags=re.ASCII)
_URL_SCHEME_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9+.-]*://", flags=re.ASCII)

DISCOVERY_LIMITATIONS = (
    "SSDP advertisements are unauthenticated LAN broadcasts and do not report firmware version; "
    "pair explicitly with kobra-lan printer pair --name NAME --host IPv4 and verify the TLS fingerprint.",
    "Multicast discovery works only within the same local network segment; routed VLANs, "
    "Wi-Fi client isolation, VPNs, or firewalls blocking UDP 1900 require explicit IPv4 pairing.",
)


class DiscoveryArgumentError(ValueError):
    """Raised when discovery CLI options fail strict offline validation."""


class DiscoveryError(OSError):
    """Raised when the local UDP multicast socket operation fails."""


def validate_timeout(timeout):
    """Require a bounded whole-second listen window (1..MAX_DISCOVER_TIMEOUT)."""
    if type(timeout) is not int or not (1 <= timeout <= MAX_DISCOVER_TIMEOUT):
        raise DiscoveryArgumentError(
            f"Discovery timeout must be a whole integer from 1 to {MAX_DISCOVER_TIMEOUT} seconds"
        )
    return timeout


def validate_interface(interface):
    """Require a canonical bare IPv4 address for optional --interface binding."""
    if not isinstance(interface, str):
        raise DiscoveryArgumentError("Interface must be a bare IPv4 address")
    try:
        if str(ipaddress.IPv4Address(interface)) != interface:
            raise ValueError
    except ValueError:
        raise DiscoveryArgumentError("Interface must be a bare IPv4 address") from None
    return interface


def build_msearch_payload():
    """Construct the Anycubic FDM SSDP M-SEARCH datagram."""
    return (
        "M-SEARCH * HTTP/1.1\r\n"
        f"Host: {SSDP_MULTICAST_HOST}:{SSDP_MULTICAST_PORT}\r\n"
        f"ST: {SSDP_SEARCH_TARGET}\r\n"
        'Man: "ssdp:discover"\r\n'
        f"MX: {SSDP_MX}\r\n"
        "\r\n"
    ).encode("ascii")


def _canonical_ipv4(value):
    if not isinstance(value, str):
        return None
    try:
        if str(ipaddress.IPv4Address(value)) == value:
            return value
    except ValueError:
        return None
    return None


def _sanitize_name(value):
    if not isinstance(value, str):
        return None
    if _URL_SCHEME_RE.search(value):
        return "[redacted URL]"
    cleaned = " ".join(safe_text(value).split())
    if not cleaned:
        return None
    return cleaned[:MAX_NAME_LENGTH]


def _parse_usn_mac(usn):
    if not isinstance(usn, str):
        return None
    match = _USN_MAC_RE.fullmatch(usn.strip())
    if not match:
        return None
    return match.group(1).replace("-", ":").lower()


def _single_query_value(params, key):
    values = params.get(key)
    if not values or len(values) != 1:
        return None
    return values[0]


def parse_ssdp_response(raw_bytes, sender_ip):
    """Validate and sanitize one SSDP UDP reply against its sender IPv4 address.

    Returns a sanitized printer candidate dictionary, or None for malformed,
    unrelated, non-LAN, or spoofed cross-host advertisements.
    """
    canonical_sender = _canonical_ipv4(sender_ip)
    if canonical_sender is None:
        return None
    if not isinstance(raw_bytes, (bytes, bytearray)) or not raw_bytes or len(raw_bytes) > MAX_DATAGRAM_BYTES:
        return None
    try:
        text = bytes(raw_bytes).decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        return None

    lines = text.splitlines()
    if not lines or not _STATUS_LINE_RE.fullmatch(lines[0].strip()):
        return None

    headers = {}
    for line in lines[1:]:
        if not line.strip():
            break
        if ":" not in line:
            return None
        name, _, value = line.partition(":")
        key = name.strip().lower()
        if not key:
            return None
        headers.setdefault(key, value.strip())

    if headers.get("st", "").lower() != SSDP_SEARCH_TARGET:
        return None

    location = headers.get("location")
    if not location or "#" in location or any(ord(c) < 32 or ord(c) == 127 for c in location):
        return None

    try:
        parsed = urlsplit(location)
        port = parsed.port
    except ValueError:
        return None

    if (
        parsed.scheme != "http"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.hostname != canonical_sender
        or port != PRINTER_HTTP_PORT
        or parsed.netloc != f"{canonical_sender}:{PRINTER_HTTP_PORT}"
        or parsed.path != "/info"
        or parsed.fragment
        or not parsed.query
    ):
        return None

    params = parse_qs(parsed.query, keep_blank_values=False)
    if _single_query_value(params, "ctrlType") != "lan":
        return None
    if _single_query_value(params, "ip") != canonical_sender:
        return None

    model_id = None
    if "modelId" in params:
        raw_model_id = _single_query_value(params, "modelId")
        if raw_model_id is None or not _MODEL_ID_RE.fullmatch(raw_model_id):
            return None
        model_id = int(raw_model_id)

    model_name = _sanitize_name(_single_query_value(params, "modelName"))
    device_name = _sanitize_name(_single_query_value(params, "deviceName"))
    mac = _parse_usn_mac(headers.get("usn"))

    return {
        "host": canonical_sender,
        "port": PRINTER_HTTP_PORT,
        "model_id": model_id,
        "model_name": model_name,
        "device_name": device_name,
        "mac": mac,
        "ctrl_type": "lan",
        "qualified_model": qualification_for_model_id(model_id) is not None,
        "firmware_verified": False,
        "unauthenticated": True,
    }


def discover_printers(
    timeout=DEFAULT_DISCOVER_TIMEOUT,
    interface=None,
    *,
    socket_factory=socket.socket,
    select_fn=select.select,
    monotonic=time.monotonic,
):
    """Run one bounded read-only SSDP multicast discovery scan on the local LAN."""
    timeout = validate_timeout(timeout)
    if interface is not None:
        interface = validate_interface(interface)

    payload = build_msearch_payload()
    destination = (SSDP_MULTICAST_HOST, SSDP_MULTICAST_PORT)
    candidates = {}

    sock = None
    try:
        try:
            sock = socket_factory(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            sock.setblocking(False)
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, SSDP_MULTICAST_TTL)
            if interface is not None:
                sock.bind((interface, 0))
                sock.setsockopt(
                    socket.IPPROTO_IP,
                    socket.IP_MULTICAST_IF,
                    socket.inet_aton(interface),
                )

            start = monotonic()
            deadline = start + timeout
            second_send = start + min(1.0, timeout / 2.0)
            sent_second = False

            sock.sendto(payload, destination)

            while True:
                now = monotonic()
                if now >= deadline:
                    break
                if not sent_second and now >= second_send:
                    sock.sendto(payload, destination)
                    sent_second = True
                next_event = deadline if sent_second else min(second_send, deadline)
                wait = max(0.0, next_event - now)
                ready, _, _ = select_fn([sock], [], [], wait)
                if ready:
                    try:
                        data, addr = sock.recvfrom(MAX_DATAGRAM_BYTES)
                    except (BlockingIOError, InterruptedError):
                        continue
                    sender_ip = addr[0] if isinstance(addr, tuple) and addr else None
                    candidate = parse_ssdp_response(data, sender_ip)
                    if candidate is not None:
                        candidates.setdefault((candidate["host"], candidate["mac"]), candidate)
        except OSError:
            raise DiscoveryError("Discovery: local UDP multicast socket operation failed") from None
    finally:
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass

    printers = sorted(
        candidates.values(),
        key=lambda item: (ipaddress.IPv4Address(item["host"]), item["mac"] or ""),
    )
    return {
        "protocol": "ssdp",
        "search_target": SSDP_SEARCH_TARGET,
        "timeout_seconds": timeout,
        "interface": interface,
        "hardware_discovery_validated": is_discovery_hardware_validated(KOBRA_X.model_id, QUALIFIED_FIRMWARE),
        "unauthenticated_lan_advertisement": True,
        "firmware_verified": False,
        "printers": printers,
        "limitations": list(DISCOVERY_LIMITATIONS),
    }
