# Proposal

## Why

`kobra-lan` is still in `0.x` with a single operator, yet it already carries three pre-`v1` backward-compatibility behaviors in its local state layout and JSON output contracts. Removing these legacy shims now ensures `1.0` starts with one clean, canonical contract per feature instead of carrying historical compatibility complexity into the first stable release.

## What Changes

- **BREAKING**: Unify `print start` local state records under `starts/<device>/` so every attempt—including root starts (`previous_attempt_id: null`) and reprints—is keyed by its deterministic `attempt_id` (`<attempt_id>.attempt` and `<attempt_id>.json`) and always carries `attempt_id`. Remove legacy file-keyed (`<file_sha256>.*`) and pre-`attempt_id` marker/receipt parsing from `print plan`, `print start`, `jobs list`, `jobs info`, and `files delete` local-state counting. Any preexisting legacy files on disk remain untouched and read-only, surfaced by `jobs list`/`jobs info` as incomplete/unreadable records (`unreadable-<storage-key>`).
- **BREAKING**: Remove `record_format` from `jobs info` output now that only one canonical start-record format exists.
- **BREAKING**: Unify per-device mutation concurrency locking to `.device.lock` only across `files upload`, `print start`, `print pause|resume|cancel`, and `files delete`. Remove creation/acquisition of legacy `.upload.lock` and `.start.lock` files and remove the `upload_lock()` wrapper.
- **BREAKING**: Remove the historical `single_filament_start_compatible` field from `gcode inspect` output (superseded by `--slot-map` multicolor and non-zero `paint_index` planning/start support).

## Capabilities

### New Capabilities

### Modified Capabilities
- `reviewed-job-submission`: Remove `single_filament_start_compatible` from `gcode inspect`, unify root and reprint start reservations/receipts on `<attempt_id>.*` without legacy file-keyed parsing, and standardize on the single `.device.lock` lease for mutating operations.
- `job-history`: Remove legacy file-keyed start-record reconstruction and the `record_format` output field; treat non-canonical or pre-`attempt_id` files on disk as read-only incomplete/unreadable entries (`unreadable-<storage-key>`) without altering bytes or permissions.

## Impact

- **Code (`kobra_lan/`)**: `start.py`, `jobs.py`, `delete_file.py`, `upload.py`, `control.py`, `filaments.py`.
- **Tests (`tests/`)**: `test_start.py`, `test_jobs.py`, `test_delete_file.py`, `test_control.py`, `test_client.py`, `test_filaments.py`.
- **Docs & packaging**: `docs/usage.md`, `docs/compatibility.md`, `debian/kobra-lan.1`, `README.md`, `ROADMAP.md`, `CHANGELOG.md`.
- **On-disk compatibility**: Preexisting legacy file-keyed start records (if any exist under `--state-dir/starts/<device>/`) will no longer be eligible for `--reprint-from` or matched as canonical start records, but will never be modified or deleted. Older `0.x` binaries that only lock `.upload.lock`/`.start.lock` will no longer share mutual exclusion with the updated binary.
