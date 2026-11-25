"""Direct, bounded, token-redacted Kobra X LAN camera status, snapshot, and FLV piping."""
import hashlib
import http.client
import os
from pathlib import Path
import re
import shutil
import socket
import struct
import subprocess
import tempfile
import time
from urllib.parse import urlsplit

from .config import ProtocolError
from .mqtt import MQTT, MQTTClosed, MQTTFailure, MQTTIOFailure
from .printer import payload_data
from .qualification import info_compatibility_issue, is_camera_hardware_validated

CAMERA_STREAM_PORT = 18088
CAMERA_STREAM_PROTOCOL = "http-flv"
STREAM_PATH_RE = re.compile(r"^/live/[A-Za-z0-9_.-]{1,128}$")

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
        raise ProtocolError("Printer announced an invalid or unsafe camera stream URL")
    try:
        parsed = urlsplit(url)
    except ValueError:
        raise ProtocolError("Printer announced an invalid or unsafe camera stream URL") from None
    valid = (
        parsed.scheme == "http"
        and parsed.username is None
        and parsed.password is None
        and parsed.hostname == host
        and parsed.port == expected_port
        and parsed.netloc == f"{host}:{expected_port}"
        and not parsed.query
        and not parsed.fragment
        and STREAM_PATH_RE.fullmatch(parsed.path) is not None
        and ".." not in parsed.path.split("/")
    )
    if not valid:
        raise ProtocolError("Printer announced an invalid or unsafe camera stream URL")
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
    conn = http.client.HTTPConnection(host, port, timeout=timeout)
    try:
        conn.request("GET", path)
        response = conn.getresponse()
        if response.status not in (200, 206):
            conn.close()
            return None, None, b""
        first_chunk = _read_flv_prefix(conn, response, deadline)
        if len(first_chunk) < len(FLV_MAGIC) or not first_chunk.startswith(FLV_MAGIC):
            conn.close()
            return None, None, b""
        return conn, response, first_chunk
    except (OSError, http.client.HTTPException):
        conn.close()
        return None, None, b""


def _best_effort_stop_capture(config):
    """Send one bounded video/stopCapture without raising cleanup failures."""
    try:
        with MQTT(config, timeout=STOP_CAPTURE_TIMEOUT) as client:
            client.stop_video_capture_once()
        return True
    except (ProtocolError, OSError, MQTTFailure, MQTTIOFailure):
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

            client.start_video_capture_once()
            start_capture_used = True

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


def validate_snapshot_output(output_path, *, overwrite=False):
    """Validate snapshot output path and format before target lookup or network access."""
    if not isinstance(output_path, (str, Path)) or not str(output_path).strip():
        raise CameraArgumentError("Snapshot --output must be a file path ending in .jpg, .jpeg, or .png")
    dest = Path(output_path)
    if dest.exists() and dest.is_dir() and not dest.is_symlink():
        raise CameraArgumentError("Snapshot --output must be a file path, not a directory")
    image_format = SUPPORTED_SNAPSHOT_FORMATS.get(dest.suffix.lower())
    if image_format is None:
        raise CameraArgumentError("Snapshot --output must end in .jpg, .jpeg, or .png")
    parent = dest.parent if str(dest.parent) else Path(".")
    if not parent.is_dir():
        raise ProtocolError("Snapshot output parent directory does not exist")
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


def parse_image_dimensions(data, image_format):
    """Validate magic bytes and parse (width, height) from PNG or JPEG bytes in pure Python."""
    if not isinstance(data, (bytes, bytearray)) or not data or len(data) > MAX_IMAGE_BYTES:
        return None
    if image_format == "png":
        if len(data) < 24 or data[:8] != PNG_MAGIC or data[12:16] != b"IHDR":
            return None
        width, height = struct.unpack("!II", data[16:24])
        return (width, height) if width > 0 and height > 0 else None
    if image_format == "jpeg":
        if len(data) < 4 or data[:3] != JPEG_MAGIC:
            return None
        index = 2
        length = len(data)
        while index < length:
            while index < length and data[index] == 0xFF:
                index += 1
            if index >= length:
                break
            marker = data[index]
            index += 1
            if marker in (0xD9, 0xDA):
                break
            if marker == 0x01 or 0xD0 <= marker <= 0xD7:
                continue
            if index + 2 > length:
                break
            seg_len = struct.unpack("!H", data[index:index + 2])[0]
            if seg_len < 2 or index + seg_len > length:
                break
            if marker in JPEG_SOF_MARKERS:
                if seg_len < 7:
                    return None
                height, width = struct.unpack("!HH", data[index + 3:index + 7])
                return (width, height) if width > 0 and height > 0 else None
            index += seg_len
    return None


def _decode_snapshot_with_ffmpeg(ffmpeg_bin, conn, response, first_chunk, tmp_path, deadline):
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
        "-y",
        str(tmp_path),
    ]
    try:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
    except OSError:
        raise CameraOperationError("Failed to start external ffmpeg process") from None

    streamed = 0
    try:
        try:
            proc.stdin.write(first_chunk)
            proc.stdin.flush()
            streamed += len(first_chunk)
            while streamed < MAX_SNAPSHOT_STREAM_BYTES and proc.poll() is None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                _set_response_timeout(conn, response, min(0.5, remaining))
                try:
                    chunk = response.read1(min(CHUNK_SIZE, MAX_SNAPSHOT_STREAM_BYTES - streamed))
                except (TimeoutError, socket.timeout):
                    continue
                except (OSError, http.client.HTTPException):
                    break
                if not chunk:
                    break
                proc.stdin.write(chunk)
                proc.stdin.flush()
                streamed += len(chunk)
        except (BrokenPipeError, OSError):
            pass
        finally:
            try:
                proc.stdin.close()
            except OSError:
                pass

        remaining = max(0.1, deadline - time.monotonic())
        try:
            proc.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            raise CameraOperationError("Timed out decoding camera snapshot") from None
        finally:
            if proc.stderr is not None:
                try:
                    proc.stderr.read(4096)
                except OSError:
                    pass
                finally:
                    proc.stderr.close()

        if proc.returncode != 0:
            raise CameraOperationError("ffmpeg failed to decode a frame from the camera stream")
    except BaseException:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
        raise


def _publish_snapshot_file(tmp_path, dest, *, overwrite):
    if overwrite:
        os.replace(tmp_path, dest)
        return
    try:
        os.link(tmp_path, dest)
    except FileExistsError:
        raise ProtocolError("Snapshot output path already exists; pass --overwrite to replace it") from None
    os.unlink(tmp_path)


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
    deadline = time.monotonic() + timeout
    conn, response, first_chunk, firmware, capture_mode, start_capture_used = _acquire_camera_stream(
        config, allow_start_capture=allow_start_capture, deadline=deadline
    )
    stop_capture_sent = False
    tmp_path = None
    try:
        parent = dest.parent if str(dest.parent) else Path(".")
        fd, raw_tmp = tempfile.mkstemp(
            dir=parent,
            prefix=".kobra-lan-snapshot-",
            suffix=dest.suffix.lower(),
        )
        os.close(fd)
        tmp_path = Path(raw_tmp)

        _decode_snapshot_with_ffmpeg(ffmpeg_bin, conn, response, first_chunk, tmp_path, deadline)

        try:
            size = tmp_path.stat().st_size
            if size <= 0 or size > MAX_IMAGE_BYTES:
                raise CameraOperationError("Decoded camera snapshot was empty or exceeded size limit")
            image_bytes = tmp_path.read_bytes()
        except OSError:
            raise CameraOperationError("Decoded camera snapshot could not be read") from None

        dimensions = parse_image_dimensions(image_bytes, image_format)
        if dimensions is None:
            raise CameraOperationError("Decoded camera snapshot was not a valid image")
        width, height = dimensions
        digest = hashlib.sha256(image_bytes).hexdigest()

        _publish_snapshot_file(tmp_path, dest, overwrite=overwrite)
        tmp_path = None
    finally:
        conn.close()
        if tmp_path is not None:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass
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


def _write_pipe_chunk(output_stream, chunk, max_bytes, written):
    if max_bytes is not None:
        remaining_bytes = max_bytes - written
        if remaining_bytes <= 0:
            return 0
        chunk = chunk[:remaining_bytes]
    if not chunk:
        return 0
    output_stream.write(chunk)
    output_stream.flush()
    return len(chunk)


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
    bytes_written = 0
    broken_pipe = False
    try:
        try:
            bytes_written += _write_pipe_chunk(output_stream, first_chunk, max_bytes, bytes_written)
            while max_bytes is None or bytes_written < max_bytes:
                if deadline is not None:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        break
                    _set_response_timeout(conn, response, remaining)
                else:
                    _set_response_timeout(conn, response, None)
                to_read = CHUNK_SIZE
                if max_bytes is not None:
                    to_read = min(to_read, max_bytes - bytes_written)
                try:
                    chunk = response.read1(to_read)
                except (TimeoutError, socket.timeout):
                    if deadline is not None and time.monotonic() >= deadline:
                        break
                    raise CameraOperationError("Camera stream timed out") from None
                except (OSError, http.client.HTTPException):
                    raise CameraOperationError("Camera stream connection failed") from None
                if not chunk:
                    break
                bytes_written += _write_pipe_chunk(output_stream, chunk, max_bytes, bytes_written)
        except BrokenPipeError:
            broken_pipe = True
    finally:
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
