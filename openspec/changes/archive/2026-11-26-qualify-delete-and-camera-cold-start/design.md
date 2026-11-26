# Design

## Context

See [proposal.md](proposal.md) for motivation and scope. On Kobra X model `20030` / firmware `2.0.2.2`:

- `kobra_lan/qualification.py` is the single source of truth for `delete_hardware_validated` and `camera_hardware_validated`. `kobra_lan/delete_file.py` and `kobra_lan/cli.py` already derive `hardware_delete_validated` dynamically from `is_delete_hardware_validated(model_id, firmware)` — no scattered literals exist in runtime code.
- `kobra_lan/camera.py` already implements read-only-first HTTP-FLV acquisition with optional single-shot `video/startCapture` + info refresh + single retry + best-effort `video/stopCapture` cleanup (`_acquire_camera_stream`).
- Hardware safety rules require explicit operator authorization and an agreed time window before operating the live printer, and forbid modifying existing private profiles/credentials or clearing production `.attempt` markers.

## Goals / Non-Goals

**Goals:**
- Capture reproducible, sanitized live hardware evidence on Kobra X `20030` / `2.0.2.2` for:
  1. `files delete --execute` byte-for-byte preservation of local receipts, `.attempt` markers, start history, watch observations, and directory/file permissions.
  2. Post-reboot cold-start camera behavior (`camera status`, direct `--no-start-capture` probe, and fallback `camera snapshot` / `camera pipe`).
- Flip `KOBRA_X.delete_hardware_validated = True` strictly *after* live byte-for-byte preservation passes, keeping `hardware_delete_validated: false` for all unqualified models/firmwares.
- Keep `kobra_lan/camera.py` untouched unless live cold-start evidence exposes a real firmware quirk, in which case address it with minimal scoped changes and offline regression tests.
- Keep tests, `docs/compatibility.md`, `docs/usage.md`, `README.md`, `ROADMAP.md`, `CHANGELOG.md`, and main OpenSpec specs synchronized.

**Non-Goals:**
- Physical printing or changing `StartHardwareEvidence` in `kobra_lan/qualification.py`.
- Touching or migrating existing production receipts/markers in `~/.local/share/kobra-lan/uploads/`.
- Running full local Debian/Python package build acceptance (handled in CI per `openspec/config.yaml` and `docs/releases.md`).

## Decisions

### 1. Evidence-gated qualification flip
`KOBRA_X.delete_hardware_validated` stays `False` until the live verification session completes and confirms byte-for-byte preservation. No code change is merged claiming `hardware_delete_validated: true` based solely on offline tests.
- *Alternative considered*: Flipping the flag preemptively and testing afterwards. Rejected because it violates the project's strict separation between offline-validated and hardware-observed evidence.

### 2. Isolated disposable `--state-dir` for live `files delete` preservation test
Run the live `files delete` verification using a dedicated private (`0700`) disposable `--state-dir` under `~/research/kobra-lan-cli/` and a dedicated small disposable Next-generated Kobra X `.gcode` file (never started on the printer):
1. Upload the disposable `.gcode` via `kobra-lan --state-dir <tmp> files upload ... --execute` so the device directory holds a real upload `.attempt` marker and `.json` receipt.
2. Seed realistic private (`0600`) canonical start (`starts/<device>/<attempt_id>.attempt` + `.json`) and watch observation (`observations/<device>/obs-<32hex>.json`) records referencing that filename inside the same disposable `--state-dir`, ensuring `jobs list` / `jobs info` reads them cleanly before deletion.
3. Record exact `(relative_path, mode, size, sha256)` for every file and directory under `--state-dir`.
4. Run `kobra-lan --json --state-dir <tmp> files delete <name> --execute`.
5. Assert:
   - Exit 0, `status == "delete_observed_removed"`, correlated ACK `code == 0`, `deleteBatch` `success`/200, and `local_state.preserved == true` with accurate matching upload/start counts.
   - Follow-up `files list` confirms `<name>` is absent from printer storage.
   - Every pre-existing file and directory under `--state-dir` has identical `(mode, size, sha256)` byte-for-byte before and after deletion (and `.device.lock` remains mode `0600`).
   - `jobs list` and `jobs info` continue reading the preserved history cleanly, and a duplicate `files upload --execute` of the same SHA-256 is refused before contacting the printer due to the preserved `.attempt` marker.
- *Alternative considered*: Deleting a file tracked in the operator's production `~/.local/share/kobra-lan/uploads/`. Rejected to avoid unnecessary risk or clutter in production state while still exercising 100% of the live MQTT delete path, per-device `.device.lock`, and local state inspection code.

### 3. Structured post-reboot cold-start camera verification sequence
Coordinate one clean printer reboot with the operator (ensuring no Anycubic app, slicer, or CLI accesses the camera first), then execute in strict order:
1. `doctor` / `status` to confirm the printer is reachable, qualified (`20030` / `2.0.2.2`), and `free`.
2. `camera status --json` (strictly read-only MQTT `info` + `peripherie`, never opens `:18088`) to record cold-boot `camera_present`, `timelapse_supported`, and `stream_url_announced`.
3. `camera pipe --max-bytes 65536 --no-start-capture` redirected to a temporary file under `~/research/kobra-lan-cli/` to observe whether port `18088` serves FLV directly on cold boot (`exit 0`, valid `FLV` magic) or requires `startCapture` (`exit 3`, no `startCapture` sent).
4. `camera snapshot --output <tmp>/cold-start.jpg` (default fallback enabled) and `camera pipe --max-bytes 65536` to verify whether `capture_mode` is `"direct"` or `"start_capture"`, confirm `start_capture_used`/`stop_capture_sent`, verify valid JPEG decoding (`1280x720`) and FLV magic, confirm zero URL/token leakage across stdout/stderr/JSON, and confirm `status` / `camera status` remain healthy afterwards.
- *Alternative considered*: Simulating cold-start only with synthetic mocks. Rejected because firmware behavior before the first `startCapture` after boot (such as whether `urls.rtspUrl` is already populated or whether `:18088` returns 404 / connection refused) can only be established on real hardware.

## Risks / Trade-offs

- [Printer reboot disrupts active household use or ongoing work] → Coordinate the reboot explicitly with the operator and confirm the printer is idle (`state == "free"`) before starting.
- [Cold-start firmware omits `urls.rtspUrl` prior to `video/startCapture` or needs longer warm-up than current timeouts] → If observed, capture sanitized MQTT/HTTP timing evidence under `~/research/kobra-lan-cli/`, adjust `_acquire_camera_stream` minimally in `kobra_lan/camera.py`, add offline regression tests in `tests/test_camera.py`, and re-verify on hardware after another cold reboot.
- [Leftover disposable `.gcode` if `files delete` fails or is uncertain] → Never replay blindly; inspect `files list` and clean up manually only after verifying printer state.
- [Accidental credential/token leakage in research notes or docs] → Store scratch outputs only in `~/research/kobra-lan-cli/` with sanitized JSON/hashes and never commit raw tokens, stream URLs, PEMs, or real configs.
