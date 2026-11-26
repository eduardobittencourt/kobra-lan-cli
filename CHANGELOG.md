# Changelog

## Unreleased

- Breaking: unify `print start` local state records under `starts/<device>/` so
  both root starts and reprints are stored and looked up by their deterministic
  `attempt_id` (`<attempt_id>.attempt` and `<attempt_id>.json`), and drop legacy
  file-keyed (`<file_sha256>.*`) and pre-`attempt_id` start parsing from
  `print plan`, `print start`, `jobs list|info`, and `files delete`. Preexisting
  legacy files on disk remain untouched and read-only, surfaced by `jobs list`
  and `jobs info` as `incomplete` (`unreadable-<storage-key>`).
- Breaking: remove `record_format` from `jobs info` output.
- Breaking: unify per-device mutation concurrency locking on a single
  `.device.lock` lease across `files upload`, `print start`,
  `print pause|resume|cancel`, and `files delete`; stop creating `.upload.lock`
  and `.start.lock` and remove `upload_lock()`.
- Breaking: remove `single_filament_start_compatible` from `gcode inspect`
  output.

## 0.6.0

- Experimental release for testing and feedback; the CLI and JSON automation
  interface remain under active development. Breaking changes are expected
  during 0.x and are documented per version.
- Distribute a downloadable `.deb` and `SHA256SUMS` through GitHub Releases,
  with package acceptance on Debian 13 and Ubuntu 24.04, amd64. Runtime
  dependencies remain Python >=3.11 and `cryptography>=41`; Debian adds
  optional `Suggests: ffmpeg` for `camera snapshot`. There is no hosted apt
  repository or automatic update channel.
- Breaking: replace `--slot` with repeatable `--slot-map PAINT_INDEX=SLOT` on
  `print plan` and `print start`. Expose `slot_mapping` in place of
  `selected_slot` on `print plan`, `print start`, and `jobs info`, and report
  `material_type` per mapping entry on `jobs info`. Existing receipts and
  reprint chains remain readable in place without migration.
- Add read-only `print watch` for an active job, saving sanitized local
  observations under `--state-dir` and reporting `unknown` when firmware
  telemetry cannot establish terminal outcomes (Kobra X firmware 2.0.2.2
  reports `task_id: "-1"` and empty `last_project`).
- Add reviewed intentional reprints (`--reprint-from PREVIOUS_ATTEMPT_ID` on
  `print plan` and `print start`) with durable attempt-keyed successor markers
  while preserving legacy file-keyed upload and first-start markers/receipts.
- Add offline read-only local job history (`jobs list`, `jobs info`) over local
  start receipts/markers, correlated upload provenance, and saved watch
  observations (`scope: "local_state_only"`,
  `direct_printer_history_available: false`, `terminal_outcomes_verified: false`).
- Add experimental guarded print lifecycle controls (`print pause`,
  `print resume`, `print cancel`) requiring `--execute`, optional `--filename`
  active-job guards, strict state preconditions, shared per-device locking,
  bounded post-ACK verification, and non-replaying uncertainty reporting
  (`experimental: true`, `hardware_control_validated: true` on Kobra X model
  20030 / firmware 2.0.2.2).
- Add experimental guarded stored-file deletion (`files delete <name> --execute`)
  for an idle printer with no active job, preserving local receipts, attempt
  markers, and watch observations (`experimental: true`,
  `hardware_delete_validated: false`; live wire removal and `files list`
  absence confirmed, byte-for-byte local state preservation verified offline).
- Add read-only onboard four-slot filament inventory (`slots list`),
  multicolor-aware offline `gcode inspect` (`paint_info`, `T<n>` tools,
  optional weights, `multicolor`, `single_filament_start_compatible`), and
  reviewed multicolor `print plan`/`print start --slot-map`. Live 4-color
  contiguous 1:1 `PLA High Speed` execution (`0=1, 1=2, 2=3, 3=4`) is
  hardware-validated on Kobra X model 20030 / firmware 2.0.2.2; non-identity,
  sparse, subset, shared-slot, and single-filament slot 3 starts remain
  `hardware_start_validated: false`.
- Add experimental LAN camera access (`camera status`, `camera snapshot`,
  `camera pipe`) over pinned MQTT (`info`, `peripherie`) and host-validated
  local port 18088 HTTP-FLV reads with strict token redaction, read-only-first
  acquisition with automatic single-shot `video/startCapture`/`stopCapture`
  fallback (`--no-start-capture` disables fallback), optional external `ffmpeg`
  piped over `stdin` for atomic JPEG/PNG snapshots, and zero-dependency raw FLV
  stdout piping (`experimental: true`, `hardware_camera_validated: true` on
  Kobra X model 20030 / firmware 2.0.2.2).
- Centralize hardware qualification rules in `kobra_lan/qualification.py` and
  publish the maintained compatibility matrix in `docs/compatibility.md`.
- Record the 2026-11-25 stored-file download investigation for Kobra X model
  20030 / firmware 2.0.2.2: static client inspection, public references, and
  read-only LAN probes found no HTTP or MQTT endpoint for downloading stored
  `.gcode` files (or timelapse `.mp4` videos) from printer storage, so
  `files download` is deferred unless a supported LAN endpoint is identified or
  added by future firmware.
- Preserve private profiles, credentials, receipts, attempt markers, watch
  observations, and permissions during normal operations and package upgrades.
  Never clear markers or automatically repeat uncertain actions. Hardware
  qualification remains limited to Kobra X model 20030 / firmware 2.0.2.2 and
  the recorded material, slot, preparation, and camera observations; package
  installation does not pair, upload, start a print, or migrate a live checkout
  installation.

## 0.5.0

- Experimental release for testing and feedback; the CLI and JSON automation
  interface remain under active development. Breaking changes are expected
  during 0.x and are documented per version.
- Distribute a downloadable `.deb` and `SHA256SUMS` through GitHub Releases,
  with package acceptance on Debian 13 and Ubuntu 24.04, amd64. There is no
  hosted apt repository or automatic update channel.
- Breaking: replace flat operations with `files list|info|upload`, `gcode inspect`
  and `print plan|start`, without aliases. Root options precede commands and
  cannot be abbreviated.
- Breaking: readable text is now the default. Automation uses root `--json`
  and the version-1 envelope with safe error codes and partial diagnostic data.
- Require explicit reviewed hashes and `--execute` for upload and start;
  planning stays read-only. Upload never starts printing.
- Add offline bash/zsh/fish completion generators and installed-interface probes.
- Quote local file completions correctly in Bash, including paths with spaces.
- Serialize uploads per device within shared state storage so different payloads
  cannot race the destination preflight; existing attempt markers remain intact.
- Fix doctor compatibility for qualified firmware that omits optional MQTT
  device/model IDs, aligning with pairing while retaining pinned authentication
  and rejecting supplied conflicting IDs. Distinguish missing required evidence
  from observed incompatibility in diagnostic reasons.
- Breaking: require `printer pair --name`; remove unnamed pairing, root-config
  discovery, legacy inventory and default fallback without migration. Registry
  default is null or a named selection; old string defaults are rejected.
- Preserve private config fields, receipts, permissions and device/file
  attempt identities during normal operations. Do not clear markers or repeat uncertain actions when
  updating commands. Existing qualification and experimental limits still apply.
- Printer support remains limited to Kobra X model 20030 / firmware 2.0.2.2
  and the recorded material/preparation observations. Physical print completion
  and part quality remain unassessed. Package installation does not pair, upload,
  start a print or migrate a live checkout installation.

## 0.4.0

- Add named private printer profiles, offline inventory/info, explicit target
  selection, opt-in saved defaults and consent-based local removal.
- Extend named pairing without changing initial trust, no-overwrite guarantees,
  legacy config schema or device-based upload/start reservations.
- Add bounded read-only doctor with eight ordered stages, sanitized version 1
  reports and existing exit classes. No automatic provisioning or repair.
- Preserve legacy access; removal of a saved default requires explicit selection.
  Older binaries ignore profile defaults, including cleared defaults: review
  selection and state compatibility before rollback; preserve private state.
- Extend installed Python/Debian probes and non-root lifecycle fixtures. Runtime
  dependencies and Kobra X model 20030 / firmware 2.0.2.2 qualification are unchanged.
- This prepares source only; no release, tag, publication or live migration.

## 0.3.0

- Add `printer pair --host` for direct provisioning of an already LAN-enabled
  Kobra X model 20030 / firmware 2.0.2.2, with explicit terminal consent or an
  exact `--trust-sha256` fingerprint and a read-only status check before save.
- Publish private compatible configuration atomically without overwriting an
  existing destination. Preserve existing access and upload/start markers.
- Require `cryptography>=41` in Python and `python3-cryptography (>=41)` in Debian
  packaging; carry dependencies through offline tests and installed acceptance.
- Keep existing commands, JSON, exit codes and configuration/state schemas.
  HTTP provisioning remains unauthenticated; other firmware, discovery,
  replacement, revocation and initial LAN-mode setup remain unqualified.
- This is source version preparation, not publication of a package or release.

- Prepare independent Python and Debian distributions and a gated release workflow.
- Preserve existing CLI, JSON, configuration and durable state contracts.

## 0.2.1

- Experimental direct Kobra X LAN client with offline G-code inspection, reviewed
  uploads and guarded print start. See README for the limited observed hardware
  configuration; print completion and quality remain unqualified.
- Commands, flags, JSON output, exit codes, configuration and receipt/attempt
  formats remain experimental during 0.x. This packaging setup introduces no
  state migration and does not change duplicate protection.
- This section records the existing source version; it does not claim that a
  public release or Debian package was previously published.
