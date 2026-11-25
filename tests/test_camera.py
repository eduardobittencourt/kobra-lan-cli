"""Offline unit tests for Kobra X camera status, snapshot, and raw FLV piping."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import os
from pathlib import Path
import stat
import struct
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zlib

from kobra_lan import camera
from kobra_lan.config import ProtocolError

SECRET_TOKEN = "T0kEnS3cR3t99"
SYNTHETIC_FLV = b"FLV\x01\x01\x00\x00\x00\x09\x00\x00\x00\x00" + (b"\x09\x00\x00\x04\x00\x00\x00\x00\x00\x00\x00\x17\x00\x00\x00" * 16)


def _png_chunk(chunk_type, payload):
    crc = zlib.crc32(chunk_type + payload) & 0xFFFFFFFF
    return struct.pack("!I", len(payload)) + chunk_type + payload + struct.pack("!I", crc)


def make_minimal_png(width=640, height=360):
    ihdr_data = struct.pack("!IIBBBBB", width, height, 8, 2, 0, 0, 0)
    idat_data = zlib.compress(b"\x00\x00\x00\x00")
    return (
        camera.PNG_MAGIC
        + _png_chunk(b"IHDR", ihdr_data)
        + _png_chunk(b"IDAT", idat_data)
        + _png_chunk(b"IEND", b"")
    )


def make_minimal_jpeg(width=1280, height=720):
    app0 = b"\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    sof0_payload = struct.pack("!BHHB", 8, height, width, 3) + b"\x01\x22\x00\x02\x11\x01\x03\x11\x01"
    sof0 = b"\xff\xc0" + struct.pack("!H", len(sof0_payload) + 2) + sof0_payload
    sos_payload = b"\x03\x01\x00\x02\x11\x03\x11\x00\x3f\x00"
    sos = b"\xff\xda" + struct.pack("!H", len(sos_payload) + 2) + sos_payload + b"\x00"
    eoi = b"\xff\xd9"
    return b"\xff\xd8" + app0 + sof0 + sos + eoi


def make_config(host="127.0.0.1"):
    return SimpleNamespace(
        host=host,
        http_port=18910,
        mqtt_port=9883,
        printer_id="SyntheticDevice01",
        type_id=20030,
    )


def make_info(
    *,
    host="127.0.0.1",
    port=18088,
    token=SECRET_TOKEN,
    rtsp_url=None,
    include_url=True,
    model="Anycubic Kobra X",
    version="2.0.2.2",
    state="free",
    timelapse=True,
):
    urls = {}
    if include_url:
        urls["rtspUrl"] = rtsp_url if rtsp_url is not None else f"http://{host}:{port}/live/{token}"
    features = {}
    if timelapse is not None:
        features["camera_timelapse_support"] = timelapse
    return {
        "model": model,
        "version": version,
        "state": state,
        "deviceId": "SyntheticDevice01",
        "modelId": 20030,
        "urls": urls,
        "features": features,
    }


class FakeCameraMQTT:
    info_reports = []
    peripherie_data = {"camera": 1, "multiColorBox": 1, "udisk": 0}
    calls = []
    start_hook = None
    stop_hook = None
    sessions = 0

    def __init__(self, config, timeout=12, deadline=None, observer=None):
        self.config = config
        self.timeout = timeout
        self.deadline = deadline
        FakeCameraMQTT.sessions += 1

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def query(self, kind, action="query", data=None, *, require_fresh=False):
        FakeCameraMQTT.calls.append(("query", kind, action, require_fresh))
        if kind == "info":
            report = (
                FakeCameraMQTT.info_reports.pop(0)
                if len(FakeCameraMQTT.info_reports) > 1
                else FakeCameraMQTT.info_reports[0]
            )
            return {"code": 200, "data": report}
        if kind == "peripherie" and action == "query":
            return {"code": 200, "data": FakeCameraMQTT.peripherie_data}
        raise AssertionError(f"Unexpected query {(kind, action)}")

    def start_video_capture_once(self):
        FakeCameraMQTT.calls.append(("start_video_capture_once",))
        if FakeCameraMQTT.start_hook is not None:
            FakeCameraMQTT.start_hook()
        return {"ack": {"code": 0, "msgid": "m1"}, "report": {"action": "startCapture", "state": "pushStarted"}}

    def stop_video_capture_once(self):
        FakeCameraMQTT.calls.append(("stop_video_capture_once",))
        if FakeCameraMQTT.stop_hook is not None:
            FakeCameraMQTT.stop_hook()
        return {"ack": {"code": 0, "msgid": "m2"}, "report": {"action": "stopCapture", "state": "pushStopped"}}


class LoopbackFLVServer:
    def __init__(self):
        self.status = 206
        self.payload = SYNTHETIC_FLV
        self.requests = []
        self.chunks = None
        self.delay_per_chunk = 0.0
        self.fail_until_started = False
        self.started = False
        server_ref = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                server_ref.requests.append(self.path)
                if server_ref.fail_until_started and not server_ref.started:
                    self.send_response(404)
                    self.end_headers()
                    return
                self.send_response(server_ref.status)
                self.send_header("Content-Type", "video/x-flv")
                self.end_headers()
                chunks = server_ref.chunks if server_ref.chunks is not None else [server_ref.payload]
                try:
                    for chunk in chunks:
                        if server_ref.delay_per_chunk:
                            time.sleep(server_ref.delay_per_chunk)
                        self.wfile.write(chunk)
                        self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError, OSError):
                    pass

            def log_message(self, format, *args):
                pass

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.httpd.server_port
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=2)


def write_fake_ffmpeg(directory: Path, mode="ok", argv_log: Path | None = None, require_bytes: bytes | None = None):
    script = directory / "ffmpeg"
    jpeg_hex = make_minimal_jpeg(1280, 720).hex()
    png_hex = make_minimal_png(640, 360).hex()
    log_path = repr(str(argv_log)) if argv_log is not None else "None"
    req_hex = repr(require_bytes.hex()) if require_bytes is not None else "None"
    script.write_text(
        f"#!{sys.executable}\n"
        "import json, pathlib, sys, time\n"
        f"log_path = {log_path}\n"
        "if log_path is not None:\n"
        "    pathlib.Path(log_path).write_text(json.dumps(sys.argv))\n"
        f"mode = {mode!r}\n"
        "if mode == 'sleep':\n"
        "    time.sleep(5)\n"
        "    raise SystemExit(0)\n"
        f"req_hex = {req_hex}\n"
        "if req_hex is not None:\n"
        "    req = bytes.fromhex(req_hex)\n"
        "    buf = bytearray()\n"
        "    while req not in buf:\n"
        "        part = sys.stdin.buffer.read1(4096)\n"
        "        if not part:\n"
        "            break\n"
        "        buf.extend(part)\n"
        "    data = bytes(buf)\n"
        "    if req not in data:\n"
        "        sys.stderr.write('missing required marker\\n')\n"
        "        raise SystemExit(3)\n"
        "else:\n"
        "    data = sys.stdin.buffer.read(4096)\n"
        "if mode == 'fail':\n"
        "    sys.stderr.write('synthetic decode error\\n')\n"
        "    raise SystemExit(1)\n"
        "if mode == 'empty':\n"
        "    raise SystemExit(0)\n"
        "if mode == 'corrupt':\n"
        "    sys.stdout.buffer.write(b'NOT_AN_IMAGE_AT_ALL')\n"
        "    raise SystemExit(0)\n"
        "if not data.startswith(b'FLV'):\n"
        "    sys.stderr.write('missing FLV on stdin\\n')\n"
        "    raise SystemExit(2)\n"
        f"payload = bytes.fromhex({png_hex!r}) if 'png' in sys.argv else bytes.fromhex({jpeg_hex!r})\n"
        "sys.stdout.buffer.write(payload)\n"
    )
    script.chmod(script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return script


class CameraURLValidationAndStatusTests(unittest.TestCase):
    def setUp(self):
        FakeCameraMQTT.calls = []
        FakeCameraMQTT.sessions = 0
        FakeCameraMQTT.peripherie_data = {"camera": 1}
        FakeCameraMQTT.start_hook = None
        FakeCameraMQTT.stop_hook = None

    def test_validate_stream_url_accepts_exact_local_flv_and_rejects_hostile_urls(self):
        valid = f"http://127.0.0.1:18088/live/{SECRET_TOKEN}"
        self.assertEqual(camera.validate_stream_url("127.0.0.1", valid), f"/live/{SECRET_TOKEN}")

        bad_urls = (
            "",
            None,
            f"https://127.0.0.1:18088/live/{SECRET_TOKEN}",
            f"http://192.168.1.99:18088/live/{SECRET_TOKEN}",
            f"http://127.0.0.1:18910/live/{SECRET_TOKEN}",
            f"http://127.0.0.1:bad/live/{SECRET_TOKEN}",
            f"http://127.0.0.1:99999/live/{SECRET_TOKEN}",
            f"http://127.0.0.1/live/{SECRET_TOKEN}",
            f"http://user:pass@127.0.0.1:18088/live/{SECRET_TOKEN}",
            f"http://127.0.0.1:18088/live/{SECRET_TOKEN}?extra=1",
            f"http://127.0.0.1:18088/live/{SECRET_TOKEN}#frag",
            "http://127.0.0.1:18088/live/..",
            "http://127.0.0.1:18088/live/a/b",
            "http://127.0.0.1:18088/flv",
            f"http://127.0.0.1:18088/live/{SECRET_TOKEN}\r\nX-Injected: 1",
            f"http://127.0.0.1:18088/live/{'a' * 129}",
        )
        for url in bad_urls:
            with self.subTest(url=url):
                with self.assertRaises(ProtocolError) as caught:
                    camera.validate_stream_url("127.0.0.1", url)
                self.assertNotIn(SECRET_TOKEN, str(caught.exception))

    def test_camera_status_reports_present_announced_redacted_over_one_mqtt_session(self):
        FakeCameraMQTT.info_reports = [make_info()]
        with patch("kobra_lan.camera.MQTT", FakeCameraMQTT), \
                patch("kobra_lan.camera.http.client.HTTPConnection") as http_conn:
            result = camera.camera_status(make_config())
        http_conn.assert_not_called()
        self.assertEqual(FakeCameraMQTT.sessions, 1)
        self.assertEqual(
            FakeCameraMQTT.calls,
            [("query", "info", "query", True), ("query", "peripherie", "query", True)],
        )
        self.assertTrue(result["camera_present"])
        self.assertTrue(result["timelapse_supported"])
        self.assertTrue(result["stream_url_announced"])
        self.assertEqual(result["stream_protocol"], "http-flv")
        self.assertEqual(result["stream_port"], 18088)
        self.assertEqual(result["printer_state"], "free")
        self.assertTrue(result["experimental"])
        self.assertTrue(result["hardware_camera_validated"])
        self.assertNotIn(SECRET_TOKEN, str(result))
        self.assertNotIn("rtspUrl", str(result))

    def test_camera_status_handles_absent_camera_and_hostile_or_missing_url(self):
        cases = (
            ("absent_no_url", {"camera": 0}, make_info(include_url=False, timelapse=False), False, False),
            ("hostile_url", {"camera": 1}, make_info(rtsp_url=f"http://10.0.0.2:18088/live/{SECRET_TOKEN}"), True, False),
            ("wrong_scheme", {"camera": 1}, make_info(rtsp_url=f"https://127.0.0.1:18088/live/{SECRET_TOKEN}"), True, False),
        )
        for name, peripherie, info, expect_camera, expect_url in cases:
            with self.subTest(case=name):
                FakeCameraMQTT.calls = []
                FakeCameraMQTT.peripherie_data = peripherie
                FakeCameraMQTT.info_reports = [info]
                with patch("kobra_lan.camera.MQTT", FakeCameraMQTT), \
                        patch("kobra_lan.camera.http.client.HTTPConnection") as http_conn:
                    result = camera.camera_status(make_config())
                http_conn.assert_not_called()
                self.assertEqual(result["camera_present"], expect_camera)
                self.assertEqual(result["stream_url_announced"], expect_url)
                self.assertIsNone(result["stream_protocol"])
                self.assertIsNone(result["stream_port"])
                self.assertNotIn(SECRET_TOKEN, str(result))

    def test_camera_status_rejects_unqualified_printer(self):
        FakeCameraMQTT.info_reports = [make_info(version="2.0.2.9")]
        cfg = make_config()
        with patch("kobra_lan.camera.MQTT", FakeCameraMQTT):
            with self.assertRaises(ProtocolError):
                camera.camera_status(cfg)


class CameraSnapshotAndPipeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.bin_dir = self.root / "bin"
        self.bin_dir.mkdir()
        self.server = LoopbackFLVServer()
        FakeCameraMQTT.calls = []
        FakeCameraMQTT.sessions = 0
        FakeCameraMQTT.peripherie_data = {"camera": 1}
        FakeCameraMQTT.start_hook = None
        FakeCameraMQTT.stop_hook = None
        FakeCameraMQTT.info_reports = [make_info(port=self.server.port)]

    def tearDown(self):
        self.server.close()
        self.tmp.cleanup()

    def test_snapshot_direct_success_writes_jpeg_and_png_atomically_without_token_in_argv(self):
        argv_log = self.root / "ffmpeg_argv.json"
        fake_ffmpeg = write_fake_ffmpeg(self.bin_dir, mode="ok", argv_log=argv_log)
        for ext, expected_fmt, expected_dims in (
            (".jpg", "jpeg", (1280, 720)),
            (".png", "png", (640, 360)),
        ):
            with self.subTest(ext=ext):
                FakeCameraMQTT.calls = []
                out_file = self.root / f"frame{ext}"
                with patch("kobra_lan.camera.MQTT", FakeCameraMQTT), \
                        patch("kobra_lan.camera.CAMERA_STREAM_PORT", self.server.port), \
                        patch("kobra_lan.camera.shutil.which", return_value=str(fake_ffmpeg)):
                    result = camera.camera_snapshot(make_config(), out_file, timeout=10)
                self.assertTrue(out_file.is_file())
                self.assertEqual(result["output_path"], str(out_file))
                self.assertEqual(result["format"], expected_fmt)
                actual_dims = (result["width"], result["height"])
                self.assertEqual(actual_dims, expected_dims)
                self.assertEqual(result["bytes"], out_file.stat().st_size)
                self.assertEqual(len(result["sha256"]), 64)
                self.assertEqual(result["capture_mode"], "direct")
                self.assertFalse(result["start_capture_used"])
                self.assertFalse(result["stop_capture_sent"])
                self.assertTrue(result["experimental"])
                self.assertTrue(result["hardware_camera_validated"])
                self.assertNotIn(SECRET_TOKEN, argv_log.read_text())
                self.assertNotIn(SECRET_TOKEN, str(result))
                self.assertNotIn(("start_video_capture_once",), FakeCameraMQTT.calls)
                self.assertNotIn(("stop_video_capture_once",), FakeCameraMQTT.calls)

    def test_snapshot_fallback_activates_start_capture_and_always_stops(self):
        fake_ffmpeg = write_fake_ffmpeg(self.bin_dir, mode="ok")
        self.server.fail_until_started = True
        FakeCameraMQTT.start_hook = lambda: setattr(self.server, "started", True)
        FakeCameraMQTT.info_reports = [
            make_info(port=self.server.port, token="OldToken1"),
            make_info(port=self.server.port, token=SECRET_TOKEN),
        ]
        out_file = self.root / "fallback.jpg"
        with patch("kobra_lan.camera.MQTT", FakeCameraMQTT), \
                patch("kobra_lan.camera.CAMERA_STREAM_PORT", self.server.port), \
                patch("kobra_lan.camera.shutil.which", return_value=str(fake_ffmpeg)):
            result = camera.camera_snapshot(make_config(), out_file, timeout=10)
        self.assertEqual(result["capture_mode"], "start_capture")
        self.assertTrue(result["start_capture_used"])
        self.assertTrue(result["stop_capture_sent"])
        self.assertEqual(self.server.requests, ["/live/OldToken1", f"/live/{SECRET_TOKEN}"])
        self.assertIn(("start_video_capture_once",), FakeCameraMQTT.calls)
        self.assertIn(("stop_video_capture_once",), FakeCameraMQTT.calls)

    def test_snapshot_fallback_sends_stop_capture_even_when_ffmpeg_fails(self):
        fake_ffmpeg = write_fake_ffmpeg(self.bin_dir, mode="fail")
        self.server.fail_until_started = True
        FakeCameraMQTT.start_hook = lambda: setattr(self.server, "started", True)
        FakeCameraMQTT.info_reports = [make_info(port=self.server.port), make_info(port=self.server.port)]
        out_file = self.root / "failed.jpg"
        cfg = make_config()
        with patch("kobra_lan.camera.MQTT", FakeCameraMQTT), \
                patch("kobra_lan.camera.CAMERA_STREAM_PORT", self.server.port), \
                patch("kobra_lan.camera.shutil.which", return_value=str(fake_ffmpeg)):
            with self.assertRaises(camera.CameraOperationError) as caught:
                camera.camera_snapshot(cfg, out_file, timeout=10)
        self.assertEqual(caught.exception.exit_code, 3)
        self.assertNotIn(SECRET_TOKEN, str(caught.exception))
        self.assertFalse(out_file.exists())
        self.assertEqual([p.name for p in self.root.glob(".kobra-lan-snapshot-*")], [])
        self.assertIn(("stop_video_capture_once",), FakeCameraMQTT.calls)

    def test_snapshot_no_start_capture_refuses_fallback_without_mutation(self):
        fake_ffmpeg = write_fake_ffmpeg(self.bin_dir, mode="ok")
        self.server.status = 404
        out_file = self.root / "no-fallback.jpg"
        cfg = make_config()
        with patch("kobra_lan.camera.MQTT", FakeCameraMQTT), \
                patch("kobra_lan.camera.CAMERA_STREAM_PORT", self.server.port), \
                patch("kobra_lan.camera.shutil.which", return_value=str(fake_ffmpeg)):
            with self.assertRaises(camera.CameraOperationError) as caught:
                camera.camera_snapshot(cfg, out_file, timeout=10, allow_start_capture=False)
        self.assertEqual(caught.exception.exit_code, 3)
        self.assertNotIn(("start_video_capture_once",), FakeCameraMQTT.calls)
        self.assertNotIn(("stop_video_capture_once",), FakeCameraMQTT.calls)
        self.assertFalse(out_file.exists())

    def test_snapshot_pre_network_checks_ffmpeg_existing_overwrite_and_corrupt_cleanup(self):
        out_file = self.root / "bed.jpg"
        cfg = make_config()
        # Missing ffmpeg -> exit 3, zero MQTT calls.
        with patch("kobra_lan.camera.MQTT") as mqtt_mock, \
                patch("kobra_lan.camera.shutil.which", return_value=None):
            with self.assertRaises(camera.CameraOperationError) as caught:
                camera.camera_snapshot(cfg, out_file)
            self.assertEqual(caught.exception.exit_code, 3)
            mqtt_mock.assert_not_called()

        # Existing file (and symlink) rejected without --overwrite before network.
        out_file.write_bytes(b"original")
        link_file = self.root / "link.jpg"
        link_file.symlink_to(out_file)
        for target in (out_file, link_file):
            with self.subTest(target=target.name), \
                    patch("kobra_lan.camera.MQTT") as mqtt_mock, \
                    patch("kobra_lan.camera.shutil.which", return_value="/usr/bin/ffmpeg"):
                with self.assertRaises(ProtocolError):
                    camera.camera_snapshot(cfg, target, overwrite=False)
                mqtt_mock.assert_not_called()
        self.assertEqual(out_file.read_bytes(), b"original")

        # --overwrite replaces existing file atomically.
        fake_ffmpeg = write_fake_ffmpeg(self.bin_dir, mode="ok")
        with patch("kobra_lan.camera.MQTT", FakeCameraMQTT), \
                patch("kobra_lan.camera.CAMERA_STREAM_PORT", self.server.port), \
                patch("kobra_lan.camera.shutil.which", return_value=str(fake_ffmpeg)):
            camera.camera_snapshot(cfg, out_file, overwrite=True)
        self.assertTrue(out_file.read_bytes().startswith(camera.JPEG_MAGIC))

        # Corrupt / empty decode cleans up temp files and leaves no output.
        for bad_mode in ("empty", "corrupt"):
            with self.subTest(bad_mode=bad_mode):
                bad_ffmpeg = write_fake_ffmpeg(self.bin_dir, mode=bad_mode)
                target = self.root / f"{bad_mode}.jpg"
                with patch("kobra_lan.camera.MQTT", FakeCameraMQTT), \
                        patch("kobra_lan.camera.CAMERA_STREAM_PORT", self.server.port), \
                        patch("kobra_lan.camera.shutil.which", return_value=str(bad_ffmpeg)):
                    with self.assertRaises(camera.CameraOperationError):
                        camera.camera_snapshot(cfg, target)
                self.assertFalse(target.exists())
                self.assertEqual([p.name for p in self.root.glob(".kobra-lan-snapshot-*")], [])

    def test_snapshot_rejects_bad_extensions_dirs_missing_parent_and_timeout_before_network(self):
        cfg = make_config()
        missing_parent_target = self.root / "missing-dir" / "bed.jpg"
        valid_target = self.root / "bed.jpg"
        with patch("kobra_lan.camera.MQTT") as mqtt_mock, \
                patch("kobra_lan.camera.shutil.which", return_value="/usr/bin/ffmpeg"):
            for bad_path in (self.root / "bed.bmp", self.root / "bed", self.root):
                with self.subTest(bad_path=bad_path), self.assertRaises(camera.CameraArgumentError):
                    camera.camera_snapshot(cfg, bad_path)
            with self.assertRaises(ProtocolError):
                camera.camera_snapshot(cfg, missing_parent_target)
            for bad_timeout in (0, -1, 61, True, "10"):
                with self.subTest(timeout=bad_timeout), self.assertRaises(camera.CameraArgumentError):
                    camera.camera_snapshot(cfg, valid_target, timeout=bad_timeout)
            mqtt_mock.assert_not_called()

    def test_pipe_streams_raw_flv_without_ffmpeg_and_respects_max_bytes(self):
        out = io.BytesIO()
        with patch("kobra_lan.camera.MQTT", FakeCameraMQTT), \
                patch("kobra_lan.camera.CAMERA_STREAM_PORT", self.server.port), \
                patch("kobra_lan.camera.shutil.which", return_value=None):
            result = camera.camera_pipe(make_config(), out, max_bytes=32)
        self.assertEqual(out.getvalue(), SYNTHETIC_FLV[:32])
        self.assertEqual(result["bytes_written"], 32)
        self.assertEqual(result["capture_mode"], "direct")
        self.assertFalse(result["start_capture_used"])
        self.assertFalse(result["broken_pipe"])

    def test_pipe_handles_broken_pipe_and_keyboard_interrupt_with_fallback_cleanup(self):
        # BrokenPipeError -> clean return (broken_pipe=True) and stopCapture sent.
        self.server.fail_until_started = True
        self.server.chunks = [
            SYNTHETIC_FLV[:16] + b"\x00" * camera.CHUNK_SIZE,
            b"\x00" * camera.CHUNK_SIZE,
        ]
        FakeCameraMQTT.start_hook = lambda: setattr(self.server, "started", True)
        FakeCameraMQTT.info_reports = [make_info(port=self.server.port), make_info(port=self.server.port)]

        class BrokenPipeStream:
            def __init__(self):
                self.calls = 0

            def write(self, data):
                self.calls += 1
                if self.calls >= 2:
                    raise BrokenPipeError("downstream closed")
                return len(data)

            def flush(self):
                pass

        with patch("kobra_lan.camera.MQTT", FakeCameraMQTT), \
                patch("kobra_lan.camera.CAMERA_STREAM_PORT", self.server.port):
            result = camera.camera_pipe(make_config(), BrokenPipeStream())
        self.assertTrue(result["broken_pipe"])
        self.assertTrue(result["start_capture_used"])
        self.assertTrue(result["stop_capture_sent"])
        self.assertIn(("stop_video_capture_once",), FakeCameraMQTT.calls)

        # KeyboardInterrupt -> propagates after running stopCapture cleanup.
        FakeCameraMQTT.calls = []
        self.server.started = False
        FakeCameraMQTT.info_reports = [make_info(port=self.server.port), make_info(port=self.server.port)]

        class InterruptStream:
            def write(self, data):
                raise KeyboardInterrupt()

            def flush(self):
                pass

        cfg = make_config()
        interrupt_stream = InterruptStream()
        with patch("kobra_lan.camera.MQTT", FakeCameraMQTT), \
                patch("kobra_lan.camera.CAMERA_STREAM_PORT", self.server.port):
            with self.assertRaises(KeyboardInterrupt):
                camera.camera_pipe(cfg, interrupt_stream)
        self.assertIn(("stop_video_capture_once",), FakeCameraMQTT.calls)

    def test_pipe_rejects_hostile_url_and_absent_camera_before_http(self):
        cfg = make_config()
        FakeCameraMQTT.info_reports = [make_info(rtsp_url=f"http://10.0.0.9:18088/live/{SECRET_TOKEN}")]
        sink = io.BytesIO()
        with patch("kobra_lan.camera.MQTT", FakeCameraMQTT), \
                patch("kobra_lan.camera.http.client.HTTPConnection") as http_conn:
            with self.assertRaises(ProtocolError) as caught:
                camera.camera_pipe(cfg, sink)
            http_conn.assert_not_called()
            self.assertNotIn(SECRET_TOKEN, str(caught.exception))

        FakeCameraMQTT.peripherie_data = {"camera": 0}
        FakeCameraMQTT.info_reports = [make_info(port=self.server.port)]
        sink = io.BytesIO()
        with patch("kobra_lan.camera.MQTT", FakeCameraMQTT), \
                patch("kobra_lan.camera.http.client.HTTPConnection") as http_conn:
            with self.assertRaises(ProtocolError):
                camera.camera_pipe(cfg, sink)
            http_conn.assert_not_called()

    def test_pipe_respects_timeout_and_validates_bounds(self):
        cfg = make_config()
        for kwargs in (
            {"timeout": 0},
            {"timeout": camera.MAX_PIPE_TIMEOUT + 1},
            {"timeout": True},
            {"max_bytes": 0},
            {"max_bytes": camera.MAX_PIPE_BYTES + 1},
            {"max_bytes": False},
        ):
            sink = io.BytesIO()
            with self.subTest(kwargs=kwargs), self.assertRaises(camera.CameraArgumentError):
                camera.camera_pipe(cfg, sink, **kwargs)

        self.server.chunks = [SYNTHETIC_FLV[:16]] + [b"\x00" * 16] * 20
        self.server.delay_per_chunk = 0.2
        out = io.BytesIO()
        with patch("kobra_lan.camera.MQTT", FakeCameraMQTT), \
                patch("kobra_lan.camera.CAMERA_STREAM_PORT", self.server.port):
            result = camera.camera_pipe(make_config(), out, timeout=1)
        self.assertTrue(out.getvalue().startswith(camera.FLV_MAGIC))
        self.assertGreaterEqual(result["bytes_written"], 16)
        self.assertLess(result["bytes_written"], 16 * 21)

    def test_snapshot_sends_stop_capture_when_start_capture_raises_mid_wait(self):
        fake_ffmpeg = write_fake_ffmpeg(self.bin_dir, mode="ok")
        self.server.status = 404
        FakeCameraMQTT.start_hook = lambda: (_ for _ in ()).throw(TimeoutError("wait timeout"))
        out_file = self.root / "start-timeout.jpg"
        cfg = make_config()
        with patch("kobra_lan.camera.MQTT", FakeCameraMQTT), \
                patch("kobra_lan.camera.CAMERA_STREAM_PORT", self.server.port), \
                patch("kobra_lan.camera.shutil.which", return_value=str(fake_ffmpeg)):
            with self.assertRaises(TimeoutError):
                camera.camera_snapshot(cfg, out_file, timeout=10)
        self.assertIn(("start_video_capture_once",), FakeCameraMQTT.calls)
        self.assertIn(("stop_video_capture_once",), FakeCameraMQTT.calls)

    def test_snapshot_survives_pause_longer_than_half_second_within_timeout(self):
        marker = b"DELAYED_KEYFRAME_MARKER"
        fake_ffmpeg = write_fake_ffmpeg(self.bin_dir, mode="ok", require_bytes=marker)
        self.server.chunks = [SYNTHETIC_FLV[:16], marker + SYNTHETIC_FLV[16:]]
        self.server.delay_per_chunk = 0.7
        out_file = self.root / "delayed.jpg"
        cfg = make_config()
        with patch("kobra_lan.camera.MQTT", FakeCameraMQTT), \
                patch("kobra_lan.camera.CAMERA_STREAM_PORT", self.server.port), \
                patch("kobra_lan.camera.shutil.which", return_value=str(fake_ffmpeg)):
            result = camera.camera_snapshot(cfg, out_file, timeout=5)
        self.assertEqual(result["format"], "jpeg")
        self.assertTrue(out_file.is_file())

    def test_snapshot_reads_buffered_chunked_second_chunk_without_waiting_on_select(self):
        import http.client
        import socket as _socket

        marker = b"BUFFERED_CHUNK_2"
        fake_ffmpeg = write_fake_ffmpeg(self.bin_dir, mode="ok", require_bytes=marker)
        srv_sock, cli_sock = _socket.socketpair()
        stop_event = threading.Event()

        def serve():
            c1 = b"FLV\x01\x01\x00\x00\x00\x09"
            c2 = marker
            body = (
                f"{len(c1):x}\r\n".encode() + c1 + b"\r\n"
                + f"{len(c2):x}\r\n".encode() + c2 + b"\r\n"
            )
            srv_sock.sendall(b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n" + body)
            stop_event.wait(timeout=5)
            srv_sock.close()

        thread = threading.Thread(target=serve, daemon=True)
        thread.start()
        try:
            resp = http.client.HTTPResponse(cli_sock)
            resp.begin()
            first = resp.read1(16384)
            self.assertTrue(first.startswith(camera.FLV_MAGIC))
            dummy_conn = SimpleNamespace(sock=cli_sock)
            tmp_out = self.root / "chunked.jpg"
            t0 = time.monotonic()
            with tmp_out.open("w+b") as out_fp:
                camera._decode_snapshot_with_ffmpeg(
                    str(fake_ffmpeg), "jpeg", dummy_conn, resp, first, out_fp.fileno(), time.monotonic() + 5
                )
            self.assertLess(time.monotonic() - t0, 2.0)
            self.assertTrue(tmp_out.read_bytes().startswith(camera.JPEG_MAGIC))
        finally:
            stop_event.set()
            cli_sock.close()
            thread.join(timeout=2)

    def test_snapshot_enforces_deadline_when_ffmpeg_stalls_on_stdin(self):
        fake_ffmpeg = write_fake_ffmpeg(self.bin_dir, mode="sleep")
        self.server.chunks = [SYNTHETIC_FLV[:16]] + [b"\x00" * 65536] * 20
        out_file = self.root / "stalled.jpg"
        cfg = make_config()
        t0 = time.monotonic()
        with patch("kobra_lan.camera.MQTT", FakeCameraMQTT), \
                patch("kobra_lan.camera.CAMERA_STREAM_PORT", self.server.port), \
                patch("kobra_lan.camera.shutil.which", return_value=str(fake_ffmpeg)):
            with self.assertRaises(camera.CameraOperationError):
                camera.camera_snapshot(cfg, out_file, timeout=1)
        self.assertLess(time.monotonic() - t0, 3.0)
        self.assertFalse(out_file.exists())

    def test_pipe_enforces_deadline_and_counts_partial_write_when_stdout_blocks(self):
        self.server.chunks = [SYNTHETIC_FLV[:16]] + [b"\x00" * 65536] * 32
        read_fd, write_fd = os.pipe()
        cfg = make_config()
        t0 = time.monotonic()
        drained = bytearray()
        try:
            with os.fdopen(write_fd, "wb", buffering=0) as writer, \
                    patch("kobra_lan.camera.MQTT", FakeCameraMQTT), \
                    patch("kobra_lan.camera.CAMERA_STREAM_PORT", self.server.port):
                result = camera.camera_pipe(cfg, writer, timeout=1)
            elapsed = time.monotonic() - t0
            os.set_blocking(read_fd, False)
            while True:
                try:
                    part = os.read(read_fd, 65536)
                except BlockingIOError:
                    break
                if not part:
                    break
                drained.extend(part)
        finally:
            os.close(read_fd)
        self.assertLess(elapsed, 3.0)
        self.assertGreater(len(drained), 16)
        self.assertEqual(result["bytes_written"], len(drained))

    def test_truncated_png_and_jpeg_with_valid_dimensions_are_rejected(self):
        valid_png = make_minimal_png(640, 360)
        self.assertEqual(camera.parse_image_dimensions(valid_png, "png"), (640, 360))
        # Truncated PNG retaining full valid IHDR (no IDAT/IEND).
        self.assertIsNone(camera.parse_image_dimensions(valid_png[:33], "png"))
        # PNG missing IEND.
        self.assertIsNone(camera.parse_image_dimensions(valid_png[:-12], "png"))

        valid_jpeg = make_minimal_jpeg(1280, 720)
        self.assertEqual(camera.parse_image_dimensions(valid_jpeg, "jpeg"), (1280, 720))
        # Truncated JPEG retaining SOF0 dimensions without SOS/EOI.
        sos_pos = valid_jpeg.index(b"\xff\xda")
        self.assertIsNone(camera.parse_image_dimensions(valid_jpeg[:sos_pos], "jpeg"))
        # JPEG with SOS but missing EOI.
        self.assertIsNone(camera.parse_image_dimensions(valid_jpeg[:-2], "jpeg"))

    def test_http_header_dribble_respects_absolute_deadline(self):
        import socket as _socket

        listener = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        port = listener.getsockname()[1]
        stop_event = threading.Event()

        def slow_peer():
            try:
                conn, _ = listener.accept()
                try:
                    conn.recv(4096)
                    conn.sendall(b"HTTP/1.1 200 OK\r\n")
                    for idx in range(20):
                        if stop_event.wait(timeout=0.3):
                            break
                        conn.sendall(f"X-Slow-{idx}: pad\r\n".encode())
                except OSError:
                    pass
                finally:
                    conn.close()
            finally:
                listener.close()

        thread = threading.Thread(target=slow_peer, daemon=True)
        thread.start()
        try:
            t0 = time.monotonic()
            conn, resp, first = camera._open_flv_http(
                "127.0.0.1", port, f"/live/{SECRET_TOKEN}", deadline=t0 + 1.0
            )
            elapsed = time.monotonic() - t0
            self.assertIsNone(conn)
            self.assertIsNone(resp)
            self.assertEqual(first, b"")
            self.assertLess(elapsed, 2.2)
        finally:
            stop_event.set()
            thread.join(timeout=2)

    def test_pipe_honors_short_writes_and_preserves_partial_count_on_broken_pipe(self):
        # Short-writing non-fd stream must send all bytes up to max_bytes.
        class ShortWriter:
            def __init__(self):
                self.buf = bytearray()

            def write(self, data):
                part = bytes(data[:2])
                self.buf.extend(part)
                return len(part)

            def flush(self):
                pass

        writer = ShortWriter()
        cfg = make_config()
        with patch("kobra_lan.camera.MQTT", FakeCameraMQTT), \
                patch("kobra_lan.camera.CAMERA_STREAM_PORT", self.server.port):
            result = camera.camera_pipe(cfg, writer, max_bytes=15)
        self.assertEqual(bytes(writer.buf), SYNTHETIC_FLV[:15])
        self.assertEqual(result["bytes_written"], 15)

        # Zero-progress non-fd stream must fail explicitly.
        class ZeroWriter:
            def write(self, _data):
                return 0

            def flush(self):
                pass

        zero_writer = ZeroWriter()
        with patch("kobra_lan.camera.MQTT", FakeCameraMQTT), \
                patch("kobra_lan.camera.CAMERA_STREAM_PORT", self.server.port):
            with self.assertRaises(camera.CameraOperationError):
                camera.camera_pipe(cfg, zero_writer, max_bytes=15)

        # Partial os.write followed by BrokenPipeError preserves partial count.
        write_calls = [0]

        def fake_os_write(_fd, view):
            write_calls[0] += 1
            if write_calls[0] == 1:
                return min(5, len(view))
            raise BrokenPipeError("peer closed mid-chunk")

        read_fd, write_fd = os.pipe()
        try:
            with os.fdopen(write_fd, "wb", buffering=0) as fd_writer, \
                    patch("kobra_lan.camera.os.write", side_effect=fake_os_write), \
                    patch("kobra_lan.camera.MQTT", FakeCameraMQTT), \
                    patch("kobra_lan.camera.CAMERA_STREAM_PORT", self.server.port):
                partial_result = camera.camera_pipe(cfg, fd_writer, max_bytes=32)
        finally:
            os.close(read_fd)
        self.assertTrue(partial_result["broken_pipe"])
        self.assertEqual(partial_result["bytes_written"], 5)


if __name__ == "__main__":
    unittest.main()
