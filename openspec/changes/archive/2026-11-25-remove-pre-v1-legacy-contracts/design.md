# Design

## Context

See `proposal.md` for motivation and breaking-change scope.

Today `kobra-lan` carries three pre-`v1` compatibility shims across six modules in `kobra_lan/`:
1. **Start-record storage and parsing** (`start.py`, `jobs.py`, `delete_file.py`):
   - Root starts (`previous_attempt_id is None`) currently write `<file_sha256>.attempt` and `<file_sha256>.json`, whereas reprints write `<attempt_id>.attempt` and `<attempt_id>.json`.
   - `matching_receipt()` (`start.py`), `_parse_start_candidate()` (`jobs.py`), and `_matching_start_receipt()` (`delete_file.py`) carry legacy branches for pre-`attempt_id` markers (`{"sha256", "plan_sha256"}`) and receipts lacking `attempt_id`/`previous_attempt_id`.
   - `jobs info` exposes `record_format` (`"legacy"` / `"current"` / `None`) solely to distinguish those two formats.
2. **Per-device lockfiles** (`upload.py`, `start.py`, `control.py`, `delete_file.py`):
   - `device_lock(directory, operation)` acquires `.upload.lock` or `.start.lock` in addition to `.device.lock` for `"upload"` and `"start"`, while `"control"` and `"delete"` acquire only `.device.lock`.
   - `upload_lock(directory)` remains as a thin wrapper around `device_lock(directory, "upload")`.
3. **G-code inspection metadata** (`filaments.py`):
   - `inspect_gcode_filaments()` computes and returns `single_filament_start_compatible`, a holdover from before `--slot-map` enabled multicolor and non-zero `paint_index` starts.

## Goals / Non-Goals

**Goals:**
- Establish one canonical start-record storage layout (`starts/<device>/<attempt_id>.attempt` and `.json`) and one canonical schema across `start.py`, `jobs.py`, and `delete_file.py`.
- Remove `record_format` from `jobs info` output.
- Standardize all mutating device operations (`upload`, `start`, `control`, `delete`) on `.device.lock` alone via a single `device_lock(directory)` helper.
- Remove `single_filament_start_compatible` from `inspect_gcode_filaments()` and `gcode inspect`.
- Preserve all non-destructive storage safety invariants: never migrate, overwrite, or delete unrecognized/legacy files on disk; never follow symlinks or alter directory/file permissions.

**Non-Goals:**
- Changing upload receipt keying (`<state-dir>/<device16>/<file_sha256>.attempt` and `.json` remain file-hash-keyed, because upload deduplication is strictly per device + file bytes).
- Changing `attempt_id` derivation (`json_digest(["start-root", device_digest, file_sha256])` and `json_digest(["start-successor", previous_attempt_id])`), `plan_sha256` derivation, watch observation schema (`obs-<32hex>.json`), profile registry schema (`profiles.json` v1), or CLI command/flag syntax.
- Touching firmware protocol quirk handling (`modelId`/`modeId`, `task_id`/`taskid`, `"stoped"`/`"canceled"`, `code` `0`/`200`, RGB/RGBA channels), which reflects Kobra X firmware behavior rather than CLI legacy.

## Decisions

### 1. Always key start state files by `attempt_id` (`storage_key == attempt_id`)
- **Choice**: Both `latest_attempt()` and `publish_start()` in `kobra_lan/start.py` always use `identity` (`attempt_id(device, file_sha256, previous)`) as the filename stem (`<attempt_id>.attempt` and `<attempt_id>.json`), including when `previous is None`.
- **Rationale**: Root `attempt_id` is already deterministic from `(device_digest, file_sha256)` (`json_digest(["start-root", device_digest, file_sha256])`). Using it directly eliminates the root-vs-reprint special case in `start.py`, `jobs.py`, and `delete_file.py`, making `storage_key == attempt_id` an invariant for every valid start record.
- **Alternative considered**: Keep `<file_sha256>` for root starts and only drop pre-`attempt_id` parsing. Rejected because it leaves a permanent two-keying split (`file_sha256` vs `attempt_id`) in `v1` solely for historical reasons.

### 2. Canonical start marker/receipt validation and `previous_attempt_id` representation
- **Choice**:
  - **Markers** always contain `attempt_id`, `device_digest`, `plan_sha256`, `sha256`, and `previous_attempt_id` (`None` for root, 64-hex for reprint).
  - **Receipts** always contain `attempt_id == identity`, `device_digest == device`, `file_sha256 == file_sha256`, `plan_sha256 == review_digest(receipt, previous)`, `dry_run is False`, and `payload` dict; `previous_attempt_id` remains omitted on root starts (matching `receipt.get("previous_attempt_id") == previous` so text mode does not render `Previous attempt id: unknown` via `cli_output.scalar(None)`).
  - `matching_receipt()` drops the legacy `set(marker) == {"sha256", "plan_sha256"}` branch and requires `marker.get("attempt_id") == identity` and `receipt.get("attempt_id") == identity`.
  - `_parse_start_candidate()` in `kobra_lan/jobs.py` drops the `"legacy"` branches and returns `(file_sha256, previous_attempt_id, identity, error_issue)` without `record_format`. Any record whose `attempt_id != storage_key`, whose `device_digest != device_digest`, or whose deterministic `attempt_id(device_digest, file_sha256, prev) != storage_key` is rejected as `invalid_start_identity` (or `invalid_successor_identity` when `prev` is set) and surfaced read-only as `unreadable-<storage_key>` with `completeness: "incomplete"` and `reprint_eligibility: "blocked_incomplete"`.
  - `_matching_start_receipt()` in `kobra_lan/delete_file.py` requires `key == identity and record.get("attempt_id") == identity` (no fallback default).
- **Rationale**: Keeps `print start` text output clean while enforcing strict single-format validation everywhere and never touching unrecognized files on disk.

### 3. Single `.device.lock` lease in `device_lock(directory)`
- **Choice**: Simplify `device_lock(directory)` in `kobra_lan/upload.py` to open and exclusively `flock` only `.device.lock` (`0600`, `O_NOFOLLOW`, `O_CLOEXEC`, user-owned, `st_nlink == 1`), remove `upload_lock()`, and update all callers (`upload.py`, `start.py`, `control.py`, `delete_file.py`) to call `device_lock(directory)`.
- **Rationale**: Every mutating operation already acquires `.device.lock`. Keeping `.upload.lock` and `.start.lock` only served lock compatibility with older `0.x` binaries and doubled lockfile creation/management for upload and start.
- **Alternative considered**: Retain `device_lock(directory, operation)` signature ignoring `operation`. Rejected because `operation` would become dead API surface; `ensure_directory_bound(directory, directory_fd, operation=...)` still carries operation names for contextual error messages.

### 4. Remove `single_filament_start_compatible` from `gcode inspect`
- **Choice**: Remove the calculation and JSON key `single_filament_start_compatible` from `inspect_gcode_filaments()` in `kobra_lan/filaments.py`.
- **Rationale**: `print plan` and `print start` accept any declared `paint_index` and multicolor mappings via `--slot-map`, and `gcode inspect` already exposes the exact primitives (`paint_info_present`, `filaments`, `filament_count`, `multicolor`, `tool_indices`). Keeping a single-filament-only boolean misleads callers about what the CLI supports.

## Risks / Trade-offs

- **[Preexisting local start records on disk]** → Pre-change root starts stored under `<file_sha256>.*` will no longer match `latest_attempt()` or `--reprint-from` and will appear as `unreadable-<file_sha256>` (`incomplete`) in `jobs list`/`jobs info`. Mitigation: acceptable for pre-`1.0` single-operator state; original files and permissions remain untouched and inspectable without silent deletion or migration.
- **[Concurrent runs with older `0.x` binaries]** → An older binary holding `.upload.lock` or `.start.lock` without `.device.lock` would not contend with the updated binary. Mitigation: document in `CHANGELOG.md` and `docs/usage.md` as a pre-`1.0` breaking state change; single-operator environment upgrades in place.
- **[Downstream JSON consumers reading removed fields]** → Any script checking `gcode inspect` for `single_filament_start_compatible` or `jobs info` for `record_format` will see those keys absent. Mitigation: documented explicitly under `Unreleased` breaking changes in `CHANGELOG.md` and updated across `docs/usage.md`, `docs/compatibility.md`, `debian/kobra-lan.1`, `README.md`, and `ROADMAP.md`.

## Migration Plan

No automated state migration is performed. Existing `~/.local/share/kobra-lan/uploads/` files are left untouched; any new `print start` creates `<attempt_id>.attempt` and `<attempt_id>.json`, and any new mutating command acquires only `.device.lock`. Keep preexisting files under `starts/` in place to preserve start evidence and duplicate protection; only obsolete `.upload.lock` or `.start.lock` files confirmed not to be held by any running process should be cleaned up manually if desired.
