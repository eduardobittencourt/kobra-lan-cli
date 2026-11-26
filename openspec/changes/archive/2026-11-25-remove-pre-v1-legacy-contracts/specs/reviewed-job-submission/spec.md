## REMOVED Requirements

### Requirement: Existing device state remains authoritative
**Reason**: Pre-v1 file-keyed (`<file_sha256>.*`) start markers/receipts and legacy pre-`attempt_id` reprint eligibility are removed before v1.
**Migration**: Replaced by `Canonical device state remains authoritative`, which keys all start attempts by `attempt_id` and leaves any unrecognized preexisting files untouched without migration.

## ADDED Requirements

### Requirement: Canonical device state remains authoritative
The CLI SHALL preserve configuration, credentials, device-based receipts, permissions, and custom `--state-dir` behavior without automatic migration or deletion of preexisting files. Canonical start records under `starts/<device>/` SHALL be keyed by `attempt_id` for both root starts and reprints and SHALL block duplicate ordinary starts; only the reviewed reprint workflow can authorize a successor to an eligible canonical attempt.

#### Scenario: Canonical root attempt blocks duplicate ordinary start across profiles
- **WHEN** a canonical attempt-keyed root start record exists under `starts/<device>/` and ordinary `print start` runs through another profile for the same device
- **THEN** ordinary start refuses without sending a start command and preserves the existing files and permissions

#### Scenario: Incomplete or inconsistent start evidence blocks all starts
- **WHEN** a canonical root or successor attempt marker has a missing, malformed, or inconsistent receipt, or a receipt exists without its matching marker
- **THEN** both ordinary start and explicit reprint refuse to send a print command for that device and file and leave all existing files unchanged

#### Scenario: Unrecognized legacy file-keyed start files are neither migrated nor eligible
- **WHEN** `starts/<device>/` contains a pre-v1 file-keyed (`<file_sha256>.*`) marker/receipt without canonical `attempt_id` keying
- **THEN** `print plan` and `print start` do not migrate, modify, or delete those files and do not treat them as an eligible reprint predecessor

## MODIFIED Requirements

### Requirement: Local G-code inspection
`gcode inspect <file> [--name <remote-name>]` SHALL inspect the existing qualified Next-generated Kobra X plain G-code without target configuration, network or state writes. It SHALL report SHA-256, size, proposed remote filename, available slicer/layer metadata, filament/color metadata, and qualification limits while preserving input bytes. Files without `; paint_info =` SHALL remain inspectable and uploadable.

#### Scenario: Inspect before connecting
- **WHEN** a supported synthetic file is inspected without configuration
- **THEN** its reviewable manifest is returned in the selected format with existing hash/size/layer/slicer fields preserved, filament inspection metadata included, and its bytes unchanged

#### Scenario: Minimal G-code without paint_info remains compatible
- **WHEN** a qualified Next-generated Kobra X G-code omits `; paint_info =`
- **THEN** `gcode inspect` succeeds with `paint_info_present: false`, `filaments: []`, `filament_count: 0`, and `multicolor: false` (unless multiple distinct `T<n>` tools are present), omits `single_filament_start_compatible`, and `files upload` continues to accept the reviewed file

### Requirement: Multicolor G-code filament and tool inspection
Local `gcode inspect` SHALL parse all `; paint_info = [...]` lines, `T<n>` tool commands, and optional filament weights, reporting `paint_info_present`, ordered `filaments`, `filament_count`, `multicolor`, sorted `tool_indices`, and nullable `total_filament_used_g` without emitting `single_filament_start_compatible`. Repeated `; paint_info =` lines SHALL agree; malformed or conflicting declarations SHALL exit 2.

#### Scenario: Inspect single-filament G-code declaring paint_index 0
- **WHEN** a Next-generated Kobra X G-code declares one filament at `paint_index: 0` with no tool index other than `0`
- **THEN** `gcode inspect` reports `paint_info_present: true`, `filament_count: 1`, `multicolor: false`, omits `single_filament_start_compatible`, and returns one normalized filament entry with `color_rgb` and `color_hex`

#### Scenario: Inspect multicolor G-code with non-contiguous paint indices and repeated headers
- **WHEN** a Next-generated Kobra X G-code contains identical `; paint_info = [...]` lines in both the header and config blocks declaring multiple filaments (for example `paint_index` `1` and `3`, or mixed materials such as `PLA` and `PETG`), corresponding `T<n>` commands, and filament weight summaries
- **THEN** `gcode inspect` exits 0 without network access, reports all declared filaments ordered by `paint_index` with normalized `color_rgb`, `color_hex`, `material_type`, and per-index `filament_used_g`, reports `multicolor: true`, `tool_indices`, and `total_filament_used_g`, omits `single_filament_start_compatible`, and remains uploadable via `files upload`

#### Scenario: Inspect single-filament G-code with non-zero paint index
- **WHEN** a Next-generated Kobra X G-code declares one filament at a non-zero index (for example `paint_index: 2` with `T2`)
- **THEN** `gcode inspect` reports `filament_count: 1`, `multicolor: false`, and `tool_indices: [2]`, and omits `single_filament_start_compatible`

#### Scenario: Conflicting or malformed paint_info fails validation
- **WHEN** a G-code file contains malformed `; paint_info =` JSON, invalid color/material/index fields, duplicate `paint_index` values within one declaration, or two `; paint_info =` lines with different normalized declarations
- **THEN** `gcode inspect` fails with exit 2 (`validation_failed`) without modifying the file

### Requirement: Serialized upload preflight
Mutating device operations sharing a device state directory SHALL hold one exclusive `.device.lock` lease (never creating `.upload.lock` or `.start.lock`) across preflight, durable reservation, execution, and verification, regardless of file hash or profile name. Contention SHALL fail before printer access without waiting, retrying, or creating an attempt. Releasing the lease SHALL NOT delete `.device.lock` or attempt markers.

#### Scenario: Concurrent payloads for one destination
- **WHEN** different reviewed payloads target the same remote filename through the same device state directory
- **THEN** only the `.device.lock` lease holder can access the printer, no `.upload.lock` or `.start.lock` file is created, and any later lease holder checks the fresh listing before considering an upload

#### Scenario: State path replaced during upload
- **WHEN** the configured state path is replaced while an upload holds its `.device.lock` device lease
- **THEN** marker checks, reservations, and receipt writes remain in the leased directory; detected replacement blocks a POST or records uncertainty after a POST without replay or writes into the replacement directory

### Requirement: Local identity for each start attempt
Each durably reserved start SHALL have a deterministic local `attempt_id` independent of firmware task IDs. Both root starts and reprints SHALL be stored under `starts/<device>/<attempt_id>.attempt` and `<attempt_id>.json`, SHALL record `attempt_id` in marker and receipt, SHALL bind device, file, plan, and any reprint predecessor, and SHALL expose safe attempt references in text and JSON.

#### Scenario: Two deliberate runs share the same stored file
- **WHEN** an initial root start and its eligible reviewed reprint are reserved
- **THEN** both are stored under `<attempt_id>.attempt` and `<attempt_id>.json` with distinct durable `attempt_id` values, the second record links to the first via `previous_attempt_id`, and the upload receipt remains usable as provenance for both

#### Scenario: Result becomes uncertain after reservation
- **WHEN** the CLI can report a safe partial result for an uncertain start
- **THEN** it includes the reserved `attempt_id` and known evidence without claiming completion
