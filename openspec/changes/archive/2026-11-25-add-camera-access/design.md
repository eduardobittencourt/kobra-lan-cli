# Design

## Context

See `proposal.md` for motivation and observed Kobra X (`20030` / firmware `2.0.2.2`) LAN protocol facts.

Relevant constraints in the current codebase:
- `kobra_lan/mqtt.py` implements a bounded synchronous MQTT 3.1.1 client over pinned mTLS (`9883`) with a strictly read-only `MQTT.query()` allowlist and separated single-shot mutating methods (`start_once`, `control_once`, `delete_file_once`).
- `kobra_lan/qualification.py` is a stdlib-only leaf module that owns model/firmware qualification and centralized `hardware_*_validated` predicates.
- `kobra_lan/cli_output.py` enforces URL/credential redaction (`safe_text`) and the version-1 JSON envelope (`schema_version: 1`, `ok`, `result`, `error`, `qualification`).
- Runtime dependencies in `pyproject.toml` and `debian/control` are strictly `python3 >= 3.11` and `cryptography >= 41`, checked by `scripts/check_python.py` and `scripts/check_deb.py`.
- Live hardware observation on Kobra X `20030` / `2.0.2.2` (2026-11-25) confirmed:
  - `MQTT` `peripherie`/`query` (`slicer` topic) returns `data.camera` (`1` or `0`), `multiColorBox`, `udisk`, `mount_path`.
  - `MQTT` `info`/`query` returns `data.urls.rtspUrl` as `http://<host>:18088/live/<8-char-alnum>` and `data.features.camera_timelapse_support`.
  - Direct `GET http://<host>:18088/live/<token>` returns `HTTP 206 Partial Content`, `Content-Type: video/x-flv`, FLV v1 containing video-only H.264/AVC High@4.0 1280×720 (~10 fps), with AVC sequence header + keyframe immediately at `ts=0 ms` (~14 KB, ~0.38 s TTFB). Invalid tokens and `/flv` return `404`.
  - Direct `GET` succeeded ~2 minutes after `stopCapture` without re-issuing `startCapture`. `video/startCapture` and `video/stopCapture` also succeed on the `slicer` topic (`initSuccess` -> `joinSuccess` -> `pushStarted` / `pushStopped`).

## Goals / Non-Goals

**Goals:**
- Provide `camera status`, `camera snapshot`, and `camera pipe` in one cohesive module (`kobra_lan/camera.py`) with zero new mandatory Python/Debian dependencies.
- Keep stream tokens strictly confined inside Python memory: never emitted to stdout/stderr/JSON/exceptions and never passed in external subprocess command-line arguments.
- Default to zero printer-state mutation (direct read-only HTTP-FLV read) while gracefully handling printers that require `video/startCapture` (e.g. after reboot) via a bounded single-shot fallback that always sends best-effort `stopCapture` on exit, with `--no-start-capture` to forbid any capture mutation.
- Maintain 100% offline unit test coverage via synthetic MQTT transports, loopback HTTP-FLV servers, and synthetic `ffmpeg` executable stubs.

**Non-Goals:**
- Running a background streaming server/proxy (WebRTC, HLS, MJPEG, or HTTP relay).
- Decoding H.264 in pure Python or bundling `ffmpeg`/PyAV/OpenCV.
- Controlling the printer chamber light (`light/control`), downloading timelapses, or modifying printer settings.
- Exposing raw token-bearing stream URLs in CLI output.

## Decisions

### 1. Module architecture (`kobra_lan/camera.py` + minimal `kobra_lan/mqtt.py` additions)
- **Choice:** Create `kobra_lan/camera.py` owning URL validation, HTTP-FLV streaming, `ffmpeg` stdin piping, atomic image output, and the three high-level entrypoints (`camera_status`, `camera_snapshot`, `camera_pipe`). In `kobra_lan/mqtt.py`, add `("peripherie", "query")` to `MQTT.query()`'s strictly read-only allowlist and add separated `start_video_capture_once()` and `stop_video_capture_once()` methods (mirroring `control_once()` / `delete_file_once()`).
- **Rationale:** Preserves the strict separation between read-only queries and state-changing publishes in `mqtt.py`, keeps `camera.py` cleanly testable in isolation, and mirrors `filaments.py` / `delete_file.py` / `control.py`.
- **Alternatives considered:** Adding `startCapture` to `MQTT.query()` (rejected: violates the strict read-only invariant of `query()`). Putting camera logic in `printer.py` (rejected: `printer.py` stays lightweight for status/files).

### 2. Strict anti-SSRF stream URL validation
- **Choice:** Parse `info["urls"]["rtspUrl"]` with `urllib.parse.urlsplit` and enforce:
  - `scheme == "http"`
  - `hostname == config.host` and `port == 18088` and `netloc == f"{config.host}:18088"`
  - No `username`, `password`, `query`, `fragment`, `?`, `#`, or control chars (`ord(c) <= 32` or `127`)
  - `path` matches `^/live/[A-Za-z0-9_.-]{1,128}$` with no `..` path segment
  - HTTP fetch uses `http.client.HTTPConnection(config.host, 18088, timeout=...)` directly (never `urllib.request`, so zero proxy env lookup and zero redirect following).
- **Rationale:** Matches `kobra_lan/provisioning.py`'s `ctrlInfoUrl` hardening and prevents a compromised/spoofed MQTT report from pivoting the CLI to another LAN/loopback host or arbitrary port.

### 3. Read-only-first capture with bounded `startCapture` / `stopCapture` fallback
- **Choice:**
  1. Open one pinned `MQTT(config)` session, verify fresh `info` qualification (`info_compatibility_issue(...) is None`), query `peripherie` (`camera == 1`), and extract/validate `rtspUrl`.
  2. Attempt direct `GET` on `:18088/live/<token>` (accepting HTTP `200` or `206` and verifying `FLV` magic bytes `b"FLV"` on the first chunk).
  3. If direct `GET` fails (HTTP `404`/non-`200`/`206`, connection error, timeout, empty body, or non-FLV bytes) AND `allow_start_capture` is `True`:
     - Send one `video/startCapture` on the pinned MQTT session and wait (bounded) for `/response` ACK (`code: 0`) and `video/report` (`pushStarted`, tolerating intermediate `initSuccess`/`joinSuccess`).
     - Re-query fresh `info` to get/validate any refreshed `rtspUrl`.
     - Retry the direct `GET` once.
  4. In a `finally` block (including error, broken pipe, or `SIGINT`), if and only if this invocation sent `startCapture`, send best-effort `video/stopCapture` (using a fresh bounded timeout; swallowing cleanup transport errors so the primary result/exit code is preserved, while reporting `stop_capture_sent: bool`).
- **Rationale:** Avoids disturbing an existing viewer (slicer/HA) when `:18088` is already serving (the observed steady state on FW `2.0.2.2`), avoids unnecessary device mutations by default, still recovers automatically if a freshly booted printer requires `startCapture`, and lets strict read-only scripts pass `--no-start-capture`.
- **Alternatives considered:** Always calling `startCapture`/`stopCapture` (rejected: risks killing another active viewer on `stopCapture` and mutates printer state unnecessarily when `:18088` already streams). Never supporting `startCapture` (rejected: post-reboot cold-start behavior on FW `2.0.2.2` has not yet been ruled out).

### 4. Piping FLV into external `ffmpeg` via `stdin` (never passing URL in argv)
- **Choice:** For `camera snapshot`, locate `ffmpeg` via `shutil.which("ffmpeg")` before any network call. Spawn `ffmpeg` with:
  `["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin" (omitted since stdin is piped!), "-f", "flv", "-i", "pipe:0", "-frames:v", "1", "-f", fmt, "-y", tmp_path]`
  Specifically: `["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "flv", "-i", "pipe:0", "-frames:v", "1", "-y", str(tmp_path)]` (plus `-f mjpeg` / `-f image2` or format derived strictly from validated `.jpg`/`.jpeg`/`.png` suffix on `tmp_path` so `ffmpeg` writes exact JPEG/PNG bytes).
  Python reads bounded chunks from the `http.client` response and writes them to `proc.stdin` until `proc.poll() is not None`, `BrokenPipeError`, deadline, or byte cap (`MAX_SNAPSHOT_STREAM_BYTES`, e.g., `8 MiB`). Close `proc.stdin`, wait within remaining deadline (killing `proc` on timeout), verify exit code 0 and non-empty valid JPEG (`\xff\xd8\xff`) / PNG (`\x89PNG\r\n\x1a\n`) magic bytes, parse image dimensions (`width`, `height`) from the PNG IHDR / JPEG SOF headers in pure Python (zero Pillow dependency!), compute `sha256` and `bytes`, and atomically publish `tmp_path` to `output_path` (`os.link` + `os.unlink` when `--overwrite` is false to avoid clobber races; `os.replace` when `--overwrite` is true).
- **Rationale:**
  - Keeps `ffmpeg` completely optional (`Suggests: ffmpeg` in `debian/control`, zero change to `pyproject.toml`).
  - The token-bearing URL never enters `argv` (invisible to `ps`, `/proc`, or `ffmpeg` stderr!).
  - Pure-Python JPEG/PNG header parsing gives `width`/`height` in JSON output without requiring `ffprobe` or Pillow.
  - Atomic temp-file publication prevents partial/corrupt images on timeout or `ffmpeg` failure, and cleans up temp files on error.
- **Alternatives considered:** Passing `http://<host>:18088/live/<token>` directly to `ffmpeg -i <url>` (rejected: leaks token in process listing and bypasses Python's no-proxy/no-redirect/host-pinning controls). Requiring `ffprobe` (rejected: redundant when PNG/JPEG header parsing is ~40 lines of stdlib Python).

### 5. `camera pipe` binary stdout contract
- **Choice:** `camera pipe` writes raw FLV bytes directly to `sys.stdout.buffer` after validating the initial `b"FLV"` header bytes.
  - Reject `--json` in `cli.py` before target selection (`exit 2`, `invalid_arguments`, safe JSON error envelope).
  - Never emit text status envelopes to stdout. Errors before streaming write a safe sanitized single-line error to `sys.stderr` and exit `2`/`3`.
  - Support optional `--timeout` (`1..86400`, default none/unbounded until EOF/interrupt/broken pipe) and `--max-bytes` (`1..10737418240`, optional cap for bounded scripting/testing).
  - Handle `BrokenPipeError` cleanly (flush/suppress traceback, run `finally` cleanup, exit `0`) and `KeyboardInterrupt` cleanly (run `finally` cleanup, safe stderr message, exit `130`).
- **Rationale:** Matches standard Unix pipe ergonomics (`kobra-lan camera pipe | ffplay -f flv -`), keeps `--json` contracts unpolluted, and never hangs or leaks tracebacks when a player closes.

### 6. Centralized qualification & conservative hardware-validation flag
- **Choice:** Add `camera_hardware_validated: bool = False` to `PrinterQualification` and `is_camera_hardware_validated(model_id, firmware)` in `kobra_lan/qualification.py`. Keep it `False` initially (`KOBRA_X` has protocol-level probe observations from 2026-11-25, but end-to-end CLI execution with `camera status|snapshot|pipe` will be qualified separately once implemented and live-tested).
- **Rationale:** Follows the repository's strict evidence-tier discipline (offline tests never assert hardware validation; `docs/compatibility.md` records Implemented / Offline-validated / Hardware-observed separately).

## Risks / Trade-offs

- **[HTTP-FLV cold-start behavior after printer reboot is unverified]** → Read-only-first + automatic single-shot `startCapture`/`stopCapture` fallback handles both steady-state and cold-start printers cleanly, while `--no-start-capture` lets operators enforce strict read-only behavior.
- **[`ffmpeg` absent on minimal hosts (including current devbox)]** → `camera status` and `camera pipe` work with zero external binaries; `camera snapshot` fails cleanly before network access with exit `3` and clear installation guidance; Debian packaging adds `Suggests: ffmpeg` without bloating `Depends:`.
- **[Plaintext HTTP on port `18088` on LAN]** → Inherent to the Kobra X firmware (port `18088` is plain HTTP, unlike mTLS MQTT on `9883`). Mitigated by requiring pinned mTLS MQTT discovery first, enforcing exact paired-host/port validation with no redirects/proxies, documenting LAN trust boundaries in `docs/usage.md`, and keeping stream tokens out of all outputs and subprocess args.
- **[`camera pipe` interrupted mid-stream when `stopCapture` fallback was active]** → Always run best-effort `stopCapture` in `finally` with a short bounded socket timeout so `Ctrl+C` exits promptly while attempting to stop printer capture.
- **[Existing file clobber race on `camera snapshot`]** → Use exclusive temp creation in the destination parent directory + `os.link`/`os.unlink` when `--overwrite` is false (refusing symlinks/existing files) and `os.replace` only when `--overwrite` is true.

## Open Questions

- **Post-reboot cold start on FW `2.0.2.2`**: Immediately after power-cycling a Kobra X, does `GET :18088/live/<token>` already serve video without any prior `startCapture`, or does it require one `startCapture` after boot? (Deferrable: the read-only-first + fallback design handles both outcomes without changing specs or tasks; live testing after implementation can record the answer in `docs/compatibility.md`.)
