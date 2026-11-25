# Tasks

## 1. Qualification and MQTT camera protocol primitives

- [x] 1.1 Add `camera_hardware_validated: bool = False` to `PrinterQualification` and `is_camera_hardware_validated(model_id, firmware)` to `kobra_lan/qualification.py`, and add unit tests in `tests/test_qualification.py` verifying qualified vs. unqualified models/firmwares (`uv run --locked python -m unittest tests.test_qualification -v`).
- [x] 1.2 Extend `kobra_lan/mqtt.py` read-only `MQTT.query()` allowlist with `("peripherie", "query")` and add separated single-shot `start_video_capture_once()` and `stop_video_capture_once()` methods on `MQTT` (handling `/response` ACK + `video/report` `initSuccess`/`joinSuccess`/`pushStarted` and `pushStopped` without reconnects/retries), with offline synthetic-broker unit tests in `tests/test_mqtt.py` (`uv run --locked python -m unittest tests.test_mqtt -v`).

## 2. Core camera module (`kobra_lan/camera.py`)

- [x] 2.1 Implement strict local stream URL validation (`http://<host>:18088/live/<token>`, exact IPv4 host/port, no redirects/proxies/userinfo/query/fragment/control chars) and `camera_status(config)` over one pinned MQTT session (`info` + `peripherie` queries, qualification check, redacted output with zero token leakage), verified by offline unit tests in `tests/test_camera.py` covering present/absent camera, unannounced/hostile URLs, and unqualified targets (`uv run --locked python -m unittest tests.test_camera -v`).
- [x] 2.2 Implement read-only-first HTTP-FLV acquisition (`HTTP 200`/`206`, `FLV` magic verification, bounded reads) with optional single-shot `startCapture` + fresh `info` retry + guaranteed best-effort `stopCapture` cleanup (and `--no-start-capture` opt-out), verified by offline tests in `tests/test_camera.py` using local loopback HTTP-FLV servers and synthetic MQTT brokers covering direct success, `404`/empty fallback + cleanup, cleanup on error/interrupt, and `--no-start-capture` refusal (`uv run --locked python -m unittest tests.test_camera -v`).
- [x] 2.3 Implement `camera_snapshot(config, output_path, ...)` with pre-network validation (`.jpg`/`.jpeg`/`.png` extension, existing parent dir, non-existing destination unless `--overwrite`, timeout `1..60`, `ffmpeg` presence on `PATH`), `stdin`-piped `ffmpeg` execution (never passing stream URLs in argv), pure-Python JPEG/PNG magic and dimension parsing, atomic non-clobbering file publication, and sanitized result metadata, verified by offline unit tests in `tests/test_camera.py` using synthetic `ffmpeg` stubs covering success, missing `ffmpeg` (exit 3), existing-file refusal, `--overwrite`, corrupt/empty decode cleanup, and token redaction (`uv run --locked python -m unittest tests.test_camera -v`).
- [x] 2.4 Implement `camera_pipe(config, output_stream, ...)` streaming raw validated FLV bytes directly to `stdout` without requiring `ffmpeg`, enforcing optional `--timeout` (`1..86400`) and `--max-bytes` (`1..10737418240`), handling `BrokenPipeError` cleanly (exit 0) and `KeyboardInterrupt` cleanly (exit 130) with fallback `stopCapture` cleanup and stderr-only safe errors, verified by offline tests in `tests/test_camera.py` (`uv run --locked python -m unittest tests.test_camera -v`).

## 3. CLI integration, shell completions, and user documentation

- [x] 3.1 Wire `camera status|snapshot|pipe` in `kobra_lan/cli.py` (rejecting bare `camera` and `--json camera pipe` with exit 2 before target lookup, validating `--output`, `--timeout`, `--max-bytes`, `--overwrite`, `--no-start-capture`, routing `camera pipe` interrupt/broken-pipe exit codes, and keeping contextual help accurate), and add CLI + completion tests in `tests/test_cli.py` and `tests/test_completions.py` (`uv run --locked python -m unittest tests.test_cli tests.test_completions -v`).
- [x] 3.2 Update English documentation (`README.md`, `docs/usage.md`, `docs/compatibility.md`, `ROADMAP.md`, and `debian/kobra-lan.1`) to document `camera status|snapshot|pipe`, optional `ffmpeg` requirement for `snapshot`, read-only-first + `--no-start-capture` semantics, token-redaction guarantees, and compatibility matrix evidence tiers; verify all relative Markdown links resolve and `--help` output matches documented flags.

## 4. Packaging allowlists and offline validation gates

- [x] 4.1 Add `camera` to module allowlists in `scripts/check_python.py` and `scripts/build_deb.py`, add optional `Suggests: ffmpeg` to `debian/control` (preserving `Depends:`), and extend offline completion/help assertions in `scripts/probe_completions.py` and `scripts/accept_deb.py`; verify `uv run --locked python -m unittest tests.test_completions tests.test_cli -v` and static syntax checks pass.
- [x] 4.2 Run full local offline verification gates across the repository: `uv run --locked python -m unittest discover -s tests -v`, `uv run --locked ruff check kobra_lan scripts tests`, and `sh -n kobra-lan`, confirming zero failures or lint findings and verifying no real printer traffic or private state changes occur.

## Workflow follow-up

- After implementation passes all offline gates, run an operator-authorized live Kobra X verification session (`camera status`, `camera pipe`, and `camera snapshot` with `ffmpeg` installed, plus a post-reboot cold-start check if available) before flipping `camera_hardware_validated` and updating live evidence rows in `docs/compatibility.md`.
- Archive the change with `openspec archive` once review requirements and verification are satisfied.
