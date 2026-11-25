"""Direct, bounded, token-redacted Kobra X LAN camera status, snapshot, and FLV piping."""
import hashlib
import http.client
import io
import os
from pathlib import Path
import re
import select
import shutil
import socket
import struct
import subprocess
import time
from urllib.parse import urlsplit
import uuid
import zlib

from .config import ProtocolError
from .mqtt import MQTT, MQTTClosed
from .printer import payload_data
from .qualification import info_compatibility_issue, is_camera_hardware_validated

CAMERA_STREAM_PORT = 18088
CAMERA_STREAM_PROTOCOL = "http-flv"
STREAM_PATH_RE = re.compile(r"^/live/[A-Za-z0-9_.-]{1,128}$")
UNSAFE_STREAM_URL_MSG = "Printer announced an invalid or unsafe camera stream URL"

DEFAULT_SNAPSHOT_TIMEOUT = 15
MAX_SNAPSHOT_TIMEOUT = 60
MAX_PIPE_TIMEOUT = 86400
MAX_PIPE_BYTES = 10 * 1024 * 1024 * 1024
MAX_SNAPSHOT_STREAM_BYTES = 8 * 1024 * 1024
MAX_IMAGE_BYTES = 32 * 1024 * 1024
CHUNK_SIZE = 16384
DEFAULT_CONNECT_TIMEOUT = 10
STOP_CAPTURE_TIMEOUT = 5

FLV_MAGIC = b"FLV"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
JPEG_MAGIC = b"\xff\xd8\xff"
SUPPORTED_SNAPSHOT_FORMATS = {
    ".jpg": "jpeg",
    ".jpeg": "jpeg",
    ".png": "png",
}
JPEG_SOF_MARKERS = frozenset({
    0xC0, 0xC1, 0xC2, 0xC3,
    0xC5, 0xC6, 0xC7,
    0xC9, 0xCA, 0xCB,
    0xCD, 0xCE, 0xCF,
})


class CameraArgumentError(ProtocolError):
    """Invalid caller-supplied camera option or output path (exit 2 / invalid_arguments)."""


class CameraOperationError(ProtocolError):
    """Camera dependency, stream, or decode operational failure (exit 3 / operation_failed)."""

    def __init__(self, message):
        super().__init__(message)
        self.exit_code = 3


class _PartialBrokenPipe(BrokenPipeError):
    """BrokenPipeError carrying the partial byte count transferred before closure."""

    def __init__(self, bytes_written):
        super().__init__("Broken pipe")
        self.bytes_written = bytes_written


class _DeadlineSocket:
    """Socket wrapper enforcing an absolute monotonic deadline across multi-read HTTP calls."""

    def __init__(self, raw_sock, deadline):
        self._sock = raw_sock
        self._deadline = deadline
        self._nonblocking = False
        self._io_refs = 0
        self._closed = False

    def _apply_deadline(self):
        if self._nonblocking or self._deadline is None:
            return
        remaining = self._deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("HTTP deadline exceeded")
        self._sock.settimeout(remaining)

    def recv(self, bufsize, flags=0):
        self._apply_deadline()
        return self._sock.recv(bufsize, flags)

    def recv_into(self, buffer, nbytes=0, flags=0):
        self._apply_deadline()
        return self._sock.recv_into(buffer, nbytes, flags)

    def sendall(self, data, flags=0):
        self._apply_deadline()
        return self._sock.sendall(data, flags)

    def send(self, data, flags=0):
        self._apply_deadline()
        return self._sock.send(data, flags)

    def makefile(self, mode="r", buffering=None):
        raw = socket.SocketIO(self, mode)
        self._io_refs += 1
        if buffering is None or buffering < 0:
            buffering = io.DEFAULT_BUFFER_SIZE
        if buffering == 0:
            return raw
        return io.BufferedReader(raw, buffering)

    def _decref_socketios(self):
        if self._io_refs > 0:
            self._io_refs -= 1
        if self._closed and self._io_refs <= 0:
            self._sock.close()

    def fileno(self):
        return self._sock.fileno()

    def gettimeout(self):
        return self._sock.gettimeout()

    def settimeout(self, value):
        self._nonblocking = value is not None and value <= 0
        self._sock.settimeout(value)

    def setblocking(self, flag):
        self._nonblocking = not flag
        self._sock.setblocking(flag)

    def close(self):
        self._closed = True
        if self._io_refs <= 0:
            self._sock.close()

    def __getattr__(self, name):
        return getattr(self._sock, name)


class _DeadlineHTTPConnection(http.client.HTTPConnection):
    """HTTPConnection enforcing an absolute deadline across connect, headers, and body reads."""

    def __init__(self, host, port, *, timeout, deadline=None):
        super().__init__(host, port, timeout=timeout)
        self._deadline = deadline

    def connect(self):
        if self._deadline is not None:
            remaining = self._deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("HTTP connect deadline exceeded")
            self.timeout = min(self.timeout, remaining)
        super().connect()
        if self._deadline is not None and self.sock is not None:
            self.sock = _DeadlineSocket(self.sock, self._deadline)


def validate_stream_url(host, url, *, port=None):
    """Validate an announced local HTTP-FLV stream URL and return only its path.

    Accepts only plain HTTP targeting the exact paired IPv4 host and port with
    a bounded /live/<token> path and no userinfo, query, fragment, traversal,
    or control characters. Never includes the URL or token in error messages.
    """
    expected_port = CAMERA_STREAM_PORT if port is None else port
    if not isinstance(url, str) or not url:
        raise ProtocolError("Printer did not announce a valid local camera stream URL")
    if "?" in url or "#" in url or any(ord(c) <= 32 or ord(c) == 127 for c in url):
        raise ProtocolError(UNSAFE_STREAM_URL_MSG)
    try:
        parsed = urlsplit(url)
        parsed_port = parsed.port
    except ValueError:
        raise ProtocolError(UNSAFE_STREAM_URL_MSG) from None
    valid = (
        parsed.scheme == "http"
        and parsed.username is None
        and parsed.password is None
        and parsed.hostname == host
        and parsed_port == expected_port
        and parsed.netloc == f"{host}:{expected_port}"
        and not parsed.query
        and not parsed.fragment
        and STREAM_PATH_RE.fullmatch(parsed.path) is not None
        and ".." not in parsed.path.split("/")
    )
    if not valid:
        raise ProtocolError(UNSAFE_STREAM_URL_MSG)
    return parsed.path


def _extract_announced_stream_path(host, info):
    urls = info.get("urls")
    raw_url = urls.get("rtspUrl") if isinstance(urls, dict) else None
    if not isinstance(raw_url, str) or not raw_url:
        return None
    try:
        return validate_stream_url(host, raw_url)
    except ProtocolError:
        return None


def _parse_camera_present(peripherie):
    camera_flag = peripherie.get("camera")
    if type(camera_flag) is not int or camera_flag not in (0, 1):
        raise ProtocolError("Unsupported printer peripheral camera schema")
    return camera_flag == 1


def _parse_timelapse_supported(info):
    features = info.get("features")
    if isinstance(features, dict) and type(features.get("camera_timelapse_support")) is bool:
        return features["camera_timelapse_support"]
    return None


def _query_qualified_camera_state(client, config):
    info = payload_data(client.query("info", require_fresh=True))
    if info_compatibility_issue(config.type_id, config.printer_id, info) is not None:
        raise ProtocolError("Fresh status could not establish qualified Kobra X identity and firmware")
    peripherie = payload_data(client.query("peripherie", "query", require_fresh=True))
    camera_present = _parse_camera_present(peripherie)
    return info, camera_present


def camera_status(config):
    """Read-only camera inspection over one pinned MQTT session; never touches port 18088."""
    try:
        with MQTT(config) as client:
            info, camera_present = _query_qualified_camera_state(client, config)
    except MQTTClosed as error:
        raise ConnectionError("MQTT connection closed") from error
    stream_path = _extract_announced_stream_path(config.host, info)
    stream_announced = stream_path is not None
    return {
        "device_digest": hashlib.sha256(config.printer_id.encode()).hexdigest(),
        "model": info["model"],
        "firmware": info["version"],
        "printer_state": info["state"],
        "camera_present": camera_present,
        "timelapse_supported": _parse_timelapse_supported(info),
        "stream_url_announced": stream_announced,
        "stream_protocol": CAMERA_STREAM_PROTOCOL if stream_announced else None,
        "stream_port": CAMERA_STREAM_PORT if stream_announced else None,
        "experimental": True,
        "hardware_camera_validated": is_camera_hardware_validated(config.type_id, info["version"]),
    }


def _set_response_timeout(conn, response, timeout):
    sock = getattr(getattr(response.fp, "raw", None), "_sock", None) or conn.sock
    if sock is not None:
        try:
            sock.settimeout(timeout)
        except OSError:
            pass


def _read_flv_prefix(conn, response, deadline):
    buf = bytearray()
    while len(buf) < len(FLV_MAGIC):
        if deadline is not None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return b""
            _set_response_timeout(conn, response, remaining)
        chunk = response.read1(CHUNK_SIZE)
        if not chunk:
            break
        buf.extend(chunk)
    return bytes(buf)


def _open_flv_http(host, port, path, *, deadline=None):
    timeout = DEFAULT_CONNECT_TIMEOUT
    if deadline is not None:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return None, None, b""
        timeout = min(timeout, remaining)
    conn = _DeadlineHTTPConnection(host, port, timeout=timeout, deadline=deadline)
    response = None
    try:
        conn.request("GET", path)
        response = conn.getresponse()
        if response.status not in (200, 206):
            response.close()
            conn.close()
            return None, None, b""
        first_chunk = _read_flv_prefix(conn, response, deadline)
        if len(first_chunk) < len(FLV_MAGIC) or not first_chunk.startswith(FLV_MAGIC):
            response.close()
            conn.close()
            return None, None, b""
        return conn, response, first_chunk
    except (OSError, http.client.HTTPException):
        if response is not None:
            response.close()
        conn.close()
        return None, None, b""


def _best_effort_stop_capture(config):
    """Send one bounded video/stopCapture without raising cleanup failures."""
    try:
        with MQTT(config, timeout=STOP_CAPTURE_TIMEOUT) as client:
            client.stop_video_capture_once()
        return True
    except (ProtocolError, OSError):
        return False


def _acquire_camera_stream(config, *, allow_start_capture=True, deadline=None):
    """Discover and open a validated local HTTP-FLV stream using read-only-first access.

    Returns (conn, response, first_chunk, firmware, capture_mode, start_capture_used).
    If fallback startCapture was sent and a subsequent step fails, sends best-effort
    stopCapture before re-raising.
    """
    start_capture_used = False
    try:
        mqtt_deadline = deadline
        with MQTT(config, deadline=mqtt_deadline) as client:
            info, camera_present = _query_qualified_camera_state(client, config)
            if not camera_present:
                raise ProtocolError("Printer reports no camera attached")
            urls = info.get("urls")
            raw_url = urls.get("rtspUrl") if isinstance(urls, dict) else None
            stream_path = validate_stream_url(config.host, raw_url)
            firmware = info["version"]

            conn, response, first_chunk = _open_flv_http(
                config.host, CAMERA_STREAM_PORT, stream_path, deadline=deadline
            )
            if conn is not None:
                return conn, response, first_chunk, firmware, "direct", False

            if not allow_start_capture:
                raise CameraOperationError(
                    "Camera stream unavailable over direct read and --no-start-capture was specified"
                )

            if deadline is not None and time.monotonic() >= deadline:
                raise CameraOperationError("Camera stream timed out before fallback capture could start")

            start_capture_used = True
            client.start_video_capture_once()

            refreshed_info = payload_data(client.query("info", require_fresh=True))
            if info_compatibility_issue(config.type_id, config.printer_id, refreshed_info) is not None:
                raise ProtocolError("Fresh status could not establish qualified Kobra X identity and firmware")
            refreshed_urls = refreshed_info.get("urls")
            refreshed_raw = refreshed_urls.get("rtspUrl") if isinstance(refreshed_urls, dict) else None
            stream_path = validate_stream_url(config.host, refreshed_raw)
            firmware = refreshed_info["version"]

        conn, response, first_chunk = _open_flv_http(
            config.host, CAMERA_STREAM_PORT, stream_path, deadline=deadline
        )
        if conn is None:
            raise CameraOperationError("Camera stream unavailable after starting capture")
        return conn, response, first_chunk, firmware, "start_capture", True
    except MQTTClosed as error:
        if start_capture_used:
            _best_effort_stop_capture(config)
        raise ConnectionError("MQTT connection closed") from error
    except BaseException:
        if start_capture_used:
            _best_effort_stop_capture(config)
        raise


def _resolve_snapshot_target(output_path):
    """Validate and resolve snapshot parent directory and single safe filename."""
    if not isinstance(output_path, (str, Path)) or not str(output_path).strip():
        raise CameraArgumentError("Snapshot --output must be a file path ending in .jpg, .jpeg, or .png")
    dest = Path(output_path)
    if dest.exists() and dest.is_dir() and not dest.is_symlink():
        raise CameraArgumentError("Snapshot --output must be a file path, not a directory")
    image_format = SUPPORTED_SNAPSHOT_FORMATS.get(dest.suffix.lower())
    if image_format is None:
        raise CameraArgumentError("Snapshot --output must end in .jpg, .jpeg, or .png")
    name = dest.name
    if (
        not name
        or name in (".", "..")
        or os.path.basename(name) != name
        or "/" in name
        or "\\" in name
        or "\x00" in name
    ):
        raise CameraArgumentError("Snapshot --output must end in .jpg, .jpeg, or .png")
    parent = dest.parent if str(dest.parent) else Path(".")
    if not parent.is_dir():
        raise ProtocolError("Snapshot output parent directory does not exist")
    parent_real = os.path.realpath(parent)
    resolved_candidate = os.path.abspath(os.path.join(parent_real, name))
    parent_prefix = parent_real if parent_real == os.sep else parent_real + os.sep
    if not resolved_candidate.startswith(parent_prefix):
        raise CameraArgumentError("Snapshot --output resolves outside its parent directory")
    return dest, parent_real, name, image_format


def validate_snapshot_output(output_path, *, overwrite=False):
    """Validate snapshot output path and format before target lookup or network access."""
    dest, _parent_real, _name, image_format = _resolve_snapshot_target(output_path)
    if not overwrite and os.path.lexists(dest):
        raise ProtocolError("Snapshot output path already exists; pass --overwrite to replace it")
    return dest, image_format


def validate_snapshot_request(output_path, *, timeout=DEFAULT_SNAPSHOT_TIMEOUT, overwrite=False):
    """Run all pre-network snapshot checks: arguments, destination safety, and ffmpeg presence."""
    if type(timeout) is not int or not (1 <= timeout <= MAX_SNAPSHOT_TIMEOUT):
        raise CameraArgumentError(
            f"Snapshot --timeout accepts whole seconds from 1 to {MAX_SNAPSHOT_TIMEOUT}"
        )
    dest, image_format = validate_snapshot_output(output_path, overwrite=overwrite)
    ffmpeg_bin = shutil.which("ffmpeg")
    if ffmpeg_bin is None:
        raise CameraOperationError(
            "Camera snapshot requires external ffmpeg on PATH; install ffmpeg or use kobra-lan camera pipe"
        )
    return dest, image_format, ffmpeg_bin


def _read_png_chunk(data, pos):
    if pos + 12 > len(data):
        return None
    chunk_len = struct.unpack("!I", data[pos:pos + 4])[0]
    end = pos + 12 + chunk_len
    if end > len(data):
        return None
    chunk_type = data[pos + 4:pos + 8]
    payload = data[pos + 8:pos + 8 + chunk_len]
    expected_crc = struct.unpack("!I", data[pos + 8 + chunk_len:end])[0]
    if (zlib.crc32(chunk_type + payload) & 0xFFFFFFFF) != expected_crc:
        return None
    return chunk_type, payload, end


def _has_valid_png_chunks(data, pos):
    seen_idat = False
    while pos < len(data):
        chunk = _read_png_chunk(data, pos)
        if chunk is None:
            return False
        chunk_type, payload, pos = chunk
        if chunk_type == b"IDAT":
            seen_idat = True
        elif chunk_type == b"IEND":
            return seen_idat and not payload
    return False


def _parse_png_dimensions(data):
    if len(data) < 33 or data[:8] != PNG_MAGIC:
        return None
    first = _read_png_chunk(data, 8)
    if first is None or first[0] != b"IHDR" or len(first[1]) != 13:
        return None
    width, height = struct.unpack("!II", first[1][:8])
    if width <= 0 or height <= 0:
        return None
    return (width, height) if _has_valid_png_chunks(data, first[2]) else None


def _next_jpeg_marker(data, index):
    length = len(data)
    while index < length and data[index] == 0xFF:
        index += 1
    if index >= length:
        return None, length
    return data[index], index + 1


def _read_jpeg_segment(data, index):
    length = len(data)
    if index + 2 > length:
        return None
    seg_len = struct.unpack("!H", data[index:index + 2])[0]
    if seg_len < 2 or index + seg_len > length:
        return None
    return seg_len


def _extract_sof_dimensions(data, index, seg_len):
    if seg_len < 7:
        return None
    height, width = struct.unpack("!HH", data[index + 3:index + 7])
    return (width, height) if width > 0 and height > 0 else None


def _is_standalone_jpeg_marker(marker):
    return marker == 0x01 or 0xD0 <= marker <= 0xD7


def _has_jpeg_eoi_after_sos(data, index):
    seg_len = _read_jpeg_segment(data, index)
    if seg_len is None:
        return False
    scan_start = index + seg_len
    return b"\xff\xd9" in data[scan_start:]


def _finish_jpeg_sos(data, index, dims):
    if dims is None or not _has_jpeg_eoi_after_sos(data, index):
        return None
    return dims


def _parse_jpeg_dimensions(data):
    if len(data) < 4 or data[:3] != JPEG_MAGIC:
        return None
    index = 2
    length = len(data)
    dims = None
    while index < length:
        marker, index = _next_jpeg_marker(data, index)
        if marker in (None, 0xD9):
            return None
        if marker == 0xDA:
            return _finish_jpeg_sos(data, index, dims)
        if _is_standalone_jpeg_marker(marker):
            continue
        seg_len = _read_jpeg_segment(data, index)
        if seg_len is None:
            return None
        if marker in JPEG_SOF_MARKERS and dims is None:
            dims = _extract_sof_dimensions(data, index, seg_len)
        index += seg_len
    return None


def parse_image_dimensions(data, image_format):
    """Validate magic bytes and parse (width, height) from PNG or JPEG bytes in pure Python."""
    if not isinstance(data, (bytes, bytearray)) or not data or len(data) > MAX_IMAGE_BYTES:
        return None
    if image_format == "png":
        return _parse_png_dimensions(data)
    if image_format == "jpeg":
        return _parse_jpeg_dimensions(data)
    return None


def _response_socket(conn, response):
    return getattr(getattr(response.fp, "raw", None), "_sock", None) or conn.sock


def _response_has_buffered_data(response, sock):
    """Return True if response.fp already holds buffered payload bytes without blocking."""
    fp = getattr(response, "fp", None)
    peek = getattr(fp, "peek", None)
    if peek is None:
        return False
    prev_timeout = sock.gettimeout()
    sock.setblocking(False)
    try:
        buffered = peek(4) if getattr(response, "chunked", False) else peek(1)
        if getattr(response, "chunked", False):
            return bool(buffered.lstrip(b"\r\n"))
        return bool(buffered)
    except (OSError, ValueError):
        return False
    finally:
        try:
            sock.settimeout(prev_timeout)
        except OSError:
            pass


def _wait_socket_readable(conn, response, deadline, *, proc=None):
    """Poll socket readability without triggering SocketIO timeout corruption."""
    sock = _response_socket(conn, response)
    if sock is None:
        return True
    if _response_has_buffered_data(response, sock):
        return True
    while True:
        if proc is not None and proc.poll() is not None:
            return False
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False
        ready, _, _ = select.select([sock], [], [], min(0.2, remaining))
        if ready:
            return True


def _wait_fd_writable(fd, deadline, proc):
    """Wait one bounded slice for fd writability; return 'ready', 'retry', or 'stop'."""
    if proc is not None and proc.poll() is not None:
        return "stop"
    remaining = None if deadline is None else (deadline - time.monotonic())
    if remaining is not None and remaining <= 0:
        return "stop"
    wait_s = 0.2 if remaining is None else min(0.2, remaining)
    _, writable, _ = select.select([], [fd], [], wait_s)
    return "ready" if writable else "retry"


def _write_fd_with_deadline(fd, data, deadline, *, proc=None):
    """Write bytes to a POSIX fd before deadline; return (bytes_written, completed)."""
    view = memoryview(data)
    total_written = 0
    was_blocking = os.get_blocking(fd)
    os.set_blocking(fd, False)
    try:
        while view:
            state = _wait_fd_writable(fd, deadline, proc)
            if state == "stop":
                return total_written, False
            if state == "retry":
                continue
            try:
                written = os.write(fd, view)
            except BlockingIOError:
                continue
            except BrokenPipeError:
                raise _PartialBrokenPipe(total_written) from None
            if written <= 0:
                return total_written, False
            total_written += written
            view = view[written:]
        return total_written, True
    finally:
        try:
            os.set_blocking(fd, was_blocking)
        except OSError:
            pass


def _feed_flv_to_ffmpeg(proc, conn, response, first_chunk, deadline):
    streamed = 0
    stdin_fd = proc.stdin.fileno()
    try:
        written, ok = _write_fd_with_deadline(stdin_fd, first_chunk, deadline, proc=proc)
        streamed += written
        if not ok:
            return
        while streamed < MAX_SNAPSHOT_STREAM_BYTES and proc.poll() is None:
            if not _wait_socket_readable(conn, response, deadline, proc=proc):
                break
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            _set_response_timeout(conn, response, remaining)
            try:
                chunk = response.read1(min(CHUNK_SIZE, MAX_SNAPSHOT_STREAM_BYTES - streamed))
            except (OSError, http.client.HTTPException):
                break
            if not chunk:
                break
            written, ok = _write_fd_with_deadline(stdin_fd, chunk, deadline, proc=proc)
            streamed += written
            if not ok:
                break
    except OSError:
        pass
    finally:
        try:
            proc.stdin.close()
        except OSError:
            pass


def _finish_ffmpeg(proc, deadline):
    remaining = max(0.1, deadline - time.monotonic())
    try:
        proc.wait(timeout=remaining)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        raise CameraOperationError("Timed out decoding camera snapshot") from None
    if proc.returncode != 0:
        raise CameraOperationError("ffmpeg failed to decode a frame from the camera stream")


def _decode_snapshot_with_ffmpeg(ffmpeg_bin, image_format, conn, response, first_chunk, out_fd, deadline):
    codec = "png" if image_format == "png" else "mjpeg"
    cmd = [
        ffmpeg_bin,
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "flv",
        "-i",
        "pipe:0",
        "-frames:v",
        "1",
        "-c:v",
        codec,
        "-f",
        "image2pipe",
        "pipe:1",
    ]
    try:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=out_fd,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        raise CameraOperationError("Failed to start external ffmpeg process") from None

    try:
        _feed_flv_to_ffmpeg(proc, conn, response, first_chunk, deadline)
        _finish_ffmpeg(proc, deadline)
    except BaseException:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
        raise


def _read_snapshot_fd(tmp_fd):
    size = os.fstat(tmp_fd).st_size
    if size <= 0 or size > MAX_IMAGE_BYTES:
        raise CameraOperationError("Decoded camera snapshot was empty or exceeded size limit")
    os.lseek(tmp_fd, 0, os.SEEK_SET)
    chunks = []
    remaining = MAX_IMAGE_BYTES + 1
    while remaining > 0:
        part = os.read(tmp_fd, min(65536, remaining))
        if not part:
            break
        chunks.append(part)
        remaining -= len(part)
    image_bytes = b"".join(chunks)
    if not image_bytes or len(image_bytes) > MAX_IMAGE_BYTES:
        raise CameraOperationError("Decoded camera snapshot was empty or exceeded size limit")
    return image_bytes


def _publish_snapshot_at(parent_fd, tmp_name, dest_name, *, overwrite):
    if overwrite:
        os.replace(tmp_name, dest_name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
        return
    try:
        os.link(tmp_name, dest_name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
    except FileExistsError:
        raise ProtocolError("Snapshot output path already exists; pass --overwrite to replace it") from None
    os.unlink(tmp_name, dir_fd=parent_fd)


def camera_snapshot(
    config,
    output_path,
    *,
    timeout=DEFAULT_SNAPSHOT_TIMEOUT,
    overwrite=False,
    allow_start_capture=True,
):
    """Capture one JPEG or PNG frame via stdin-piped ffmpeg and atomic file publication."""
    dest, image_format, ffmpeg_bin = validate_snapshot_request(
        output_path, timeout=timeout, overwrite=overwrite
    )
    _, parent_real, dest_name, _ = _resolve_snapshot_target(output_path)
    deadline = time.monotonic() + timeout
    conn, response, first_chunk, firmware, capture_mode, start_capture_used = _acquire_camera_stream(
        config, allow_start_capture=allow_start_capture, deadline=deadline
    )
    stop_capture_sent = False
    tmp_name = None
    tmp_fd = None
    parent_fd = None
    try:
        parent_fd = os.open(parent_real, os.O_RDONLY | os.O_DIRECTORY)
        candidate = f".kobra-lan-snapshot-{uuid.uuid4().hex}{dest.suffix.lower()}"
        tmp_fd = os.open(
            candidate,
            os.O_CREAT | os.O_EXCL | os.O_RDWR | os.O_NOFOLLOW,
            0o600,
            dir_fd=parent_fd,
        )
        tmp_name = candidate

        _decode_snapshot_with_ffmpeg(
            ffmpeg_bin, image_format, conn, response, first_chunk, tmp_fd, deadline
        )

        try:
            image_bytes = _read_snapshot_fd(tmp_fd)
        except OSError:
            raise CameraOperationError("Decoded camera snapshot could not be read") from None

        dimensions = parse_image_dimensions(image_bytes, image_format)
        if dimensions is None:
            raise CameraOperationError("Decoded camera snapshot was not a valid image")
        width, height = dimensions
        digest = hashlib.sha256(image_bytes).hexdigest()

        os.close(tmp_fd)
        tmp_fd = None
        _publish_snapshot_at(parent_fd, tmp_name, dest_name, overwrite=overwrite)
        tmp_name = None
    finally:
        response.close()
        conn.close()
        if tmp_fd is not None:
            os.close(tmp_fd)
        if tmp_name is not None and parent_fd is not None:
            try:
                os.unlink(tmp_name, dir_fd=parent_fd)
            except OSError:
                pass
        if parent_fd is not None:
            os.close(parent_fd)
        if start_capture_used:
            stop_capture_sent = _best_effort_stop_capture(config)

    return {
        "output_path": str(dest),
        "format": image_format,
        "bytes": len(image_bytes),
        "sha256": digest,
        "width": width,
        "height": height,
        "capture_mode": capture_mode,
        "start_capture_used": start_capture_used,
        "stop_capture_sent": stop_capture_sent,
        "experimental": True,
        "hardware_camera_validated": is_camera_hardware_validated(config.type_id, firmware),
    }


def validate_pipe_options(*, timeout=None, max_bytes=None):
    """Validate optional camera pipe timeout and max-bytes bounds before network access."""
    if timeout is not None and (type(timeout) is not int or not (1 <= timeout <= MAX_PIPE_TIMEOUT)):
        raise CameraArgumentError(
            f"Pipe --timeout accepts whole seconds from 1 to {MAX_PIPE_TIMEOUT}"
        )
    if max_bytes is not None and (type(max_bytes) is not int or not (1 <= max_bytes <= MAX_PIPE_BYTES)):
        raise CameraArgumentError(
            f"Pipe --max-bytes accepts whole bytes from 1 to {MAX_PIPE_BYTES}"
        )


def _stream_fileno(output_stream):
    fileno = getattr(output_stream, "fileno", None)
    if fileno is None:
        return None
    try:
        fd = fileno()
    except (OSError, ValueError):
        return None
    return fd if isinstance(fd, int) and fd >= 0 else None


def _write_stream_all(output_stream, chunk):
    view = memoryview(chunk)
    total = 0
    try:
        while view:
            written = output_stream.write(view)
            if type(written) is not int or written <= 0 or written > len(view):
                raise CameraOperationError("Camera pipe output stream made no progress")
            total += written
            view = view[written:]
        output_stream.flush()
    except BrokenPipeError:
        raise _PartialBrokenPipe(total) from None
    return total, True


def _write_pipe_chunk(output_stream, chunk, max_bytes, written, *, deadline=None):
    if max_bytes is not None:
        remaining_bytes = max_bytes - written
        if remaining_bytes <= 0:
            return 0, True
        chunk = chunk[:remaining_bytes]
    if not chunk:
        return 0, True
    fd = _stream_fileno(output_stream)
    if fd is not None:
        return _write_fd_with_deadline(fd, chunk, deadline)
    return _write_stream_all(output_stream, chunk)


def _read_next_pipe_chunk(conn, response, deadline, to_read):
    if deadline is not None:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return b""
        _set_response_timeout(conn, response, remaining)
    else:
        _set_response_timeout(conn, response, None)
    try:
        return response.read1(to_read)
    except TimeoutError:
        if deadline is not None and time.monotonic() >= deadline:
            return b""
        raise CameraOperationError("Camera stream timed out") from None
    except (OSError, http.client.HTTPException):
        raise CameraOperationError("Camera stream connection failed") from None


def _stream_flv_to_output(conn, response, first_chunk, output_stream, deadline, max_bytes):
    bytes_written = 0
    try:
        count, ok = _write_pipe_chunk(output_stream, first_chunk, max_bytes, bytes_written, deadline=deadline)
        bytes_written += count
        if not ok:
            return bytes_written, False
        while max_bytes is None or bytes_written < max_bytes:
            to_read = CHUNK_SIZE if max_bytes is None else min(CHUNK_SIZE, max_bytes - bytes_written)
            chunk = _read_next_pipe_chunk(conn, response, deadline, to_read)
            if not chunk:
                break
            count, ok = _write_pipe_chunk(output_stream, chunk, max_bytes, bytes_written, deadline=deadline)
            bytes_written += count
            if not ok:
                break
        return bytes_written, False
    except _PartialBrokenPipe as error:
        return bytes_written + error.bytes_written, True
    except BrokenPipeError:
        return bytes_written, True


def camera_pipe(
    config,
    output_stream,
    *,
    timeout=None,
    max_bytes=None,
    allow_start_capture=True,
):
    """Stream raw validated HTTP-FLV bytes directly to output_stream without ffmpeg."""
    validate_pipe_options(timeout=timeout, max_bytes=max_bytes)
    deadline = (time.monotonic() + timeout) if timeout is not None else None
    conn, response, first_chunk, firmware, capture_mode, start_capture_used = _acquire_camera_stream(
        config, allow_start_capture=allow_start_capture, deadline=deadline
    )
    stop_capture_sent = False
    try:
        bytes_written, broken_pipe = _stream_flv_to_output(
            conn, response, first_chunk, output_stream, deadline, max_bytes
        )
    finally:
        response.close()
        conn.close()
        if start_capture_used:
            stop_capture_sent = _best_effort_stop_capture(config)

    return {
        "bytes_written": bytes_written,
        "capture_mode": capture_mode,
        "start_capture_used": start_capture_used,
        "stop_capture_sent": stop_capture_sent,
        "broken_pipe": broken_pipe,
        "hardware_camera_validated": is_camera_hardware_validated(config.type_id, firmware),
    }
