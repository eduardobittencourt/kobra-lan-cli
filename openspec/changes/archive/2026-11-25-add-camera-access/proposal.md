# Proposal

## Why

Kobra LAN CLI covers pairing, diagnostics, filament inventory, file management, and the print lifecycle, but operators and automation agents remain visually blind to the printer bed and active print without falling back to a bridge, desktop app, or Home Assistant. Direct LAN testing on Kobra X (model `20030`, firmware `2.0.2.2`) confirmed that the printer exposes peripheral presence via MQTT `peripherie/query`, announces a local HTTP-FLV camera endpoint (`http://<host>:18088/live/<token>`) in MQTT `info/report`, and serves a 720p H.264 FLV stream on demand without requiring a background daemon or heavy Python dependencies.

## What Changes

- Add a `camera` command group under the canonical CLI tree with three subcommands:
  - `camera status`: strictly read-only inspection via pinned MQTT `info` and `peripherie` queries, reporting camera presence, timelapse support flag, local stream announcement status, and qualification metadata without ever exposing token-bearing URLs or opening port `18088`.
  - `camera snapshot --output <path> [--timeout SECONDS] [--overwrite] [--no-start-capture]`: captures a single JPEG or PNG frame from the printer's local HTTP-FLV stream by reading validated stream bytes in Python and piping them into an optional external `ffmpeg` binary via `stdin` (never passing the token-bearing URL in process arguments), writing the image atomically and emitting safe text or `--json` metadata.
  - `camera pipe [--timeout SECONDS] [--max-bytes BYTES] [--no-start-capture]`: streams raw validated HTTP-FLV bytes directly to `stdout` for external players or recorders (`vlc -`, `ffplay -f flv -`, `ffmpeg -f flv -i pipe:0 ...`) with zero external dependencies, rejecting `--json` with exit `2` before network access and exiting cleanly on downstream pipe close (`0`) or foreground interrupt (`130`).
- Use a read-only-first capture strategy on `camera snapshot` and `camera pipe`: attempt a direct `GET` to the strictly host- and port-validated `http://<host>:18088/live/<token>` endpoint first without mutating printer state; only if the direct read fails to produce a valid FLV stream and `--no-start-capture` is not set, send one MQTT `video/startCapture` command, retry the stream read once, and always send best-effort `video/stopCapture` in cleanup.
- Enforce strict anti-SSRF validation on announced stream URLs (plain `http`, exact paired IPv4 host, port `18088`, `/live/<alnum-token>` path, no redirects, no proxies, no userinfo/query/fragment/control characters) and ensure stream tokens never appear in stdout, stderr, JSON envelopes, logs, or subprocess command lines.
- Extend `MQTT.query()`'s strictly read-only allowlist with `("peripherie", "query")` and add dedicated single-shot `video` capture control methods (`startCapture` / `stopCapture`) separated from `query()`.
- Centralize `camera_hardware_validated` in `kobra_lan/qualification.py` (initially `false` until end-to-end live CLI verification is recorded) and document camera commands and evidence tiers in `docs/compatibility.md`.
- Keep runtime package dependencies unchanged (`python3 >= 3.11`, `cryptography >= 41`); treat `ffmpeg` as an optional external binary required only by `camera snapshot` (`Suggests: ffmpeg` in `debian/control`).
- Update contextual help, offline bash/zsh/fish completions, English documentation (`README.md`, `docs/usage.md`, `docs/compatibility.md`, `ROADMAP.md`, `debian/kobra-lan.1`), and packaging allowlists/probes.

## Capabilities

### New Capabilities
- `camera-access`: Direct, bounded, token-redacted Kobra X LAN camera status inspection, single-frame snapshot capture, and raw HTTP-FLV stdout piping over pinned MQTT discovery and strictly host-validated local port `18088` reads, with read-only-first access and optional single-shot `startCapture`/`stopCapture` fallback.

### Modified Capabilities
- `cli-interface`: Extend the canonical command tree with `camera status|snapshot|pipe`, define binary-stdout rules for `camera pipe` (rejecting `--json`, clean exit on broken pipe, exit `130` on interrupt), and add offline discoverability and shell completions for the `camera` group.
- `hardware-qualification`: Extend authoritative qualification definitions and centralized per-operation hardware-validation flags with `camera_hardware_validated` (`is_camera_hardware_validated`) and update `docs/compatibility.md` to track `camera status|snapshot|pipe` across evidence tiers.

## Impact

- Adds a new camera module (`kobra_lan/camera.py`), extends `kobra_lan/mqtt.py` with read-only `peripherie` querying and separated `video` `startCapture`/`stopCapture` helpers, adds `camera_hardware_validated` to `kobra_lan/qualification.py`, and wires `camera status|snapshot|pipe` in `kobra_lan/cli.py`.
- Keeps `pyproject.toml` and `debian/control` mandatory runtime dependencies unchanged (`cryptography>=41`); adds optional `Suggests: ffmpeg` in `debian/control`.
- Updates packaging module allowlists and offline installed-CLI checks in `scripts/check_python.py`, `scripts/build_deb.py`, and `scripts/accept_deb.py`.
- Adds offline unit tests (`tests/test_camera.py`) using synthetic MQTT transports, local loopback HTTP-FLV servers, and synthetic `ffmpeg` stubs, plus updates to `tests/test_cli.py`, `tests/test_completions.py`, `tests/test_mqtt.py`, and `tests/test_qualification.py`.
- Updates English documentation in `README.md`, `docs/usage.md`, `docs/compatibility.md`, `ROADMAP.md`, and `debian/kobra-lan.1`.
- Out of scope: background streaming daemons or web/WebRTC/HLS/MJPEG servers, exposing raw token-bearing URLs in output, printer chamber light control (`light` command group), timelapse download/management, and live post-implementation hardware qualification (recorded separately after operator-authorized live runs).
