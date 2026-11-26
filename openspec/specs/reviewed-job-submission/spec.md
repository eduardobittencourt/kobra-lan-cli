# reviewed-job-submission Specification

## Purpose

Let owners inspect immutable sliced files, review each submission and start a qualified stored print without losing trust or durable duplicate protection.

## Requirements

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

### Requirement: Deliberate reviewed upload
`files upload <file> --sha256 <hash> --execute [--name <remote-name>]` SHALL require both controls and revalidate the inspected file hash before printer access. Without them it SHALL fail instead of performing an implicit dry run. Upload SHALL retain idle/qualification checks, no overwrite, immutable bytes, device-based durable reservation and no automatic replay; it SHALL never start a print.

#### Scenario: Missing or changed review
- **WHEN** execution controls are absent, a hash is malformed or the file differs from its reviewed SHA-256
- **THEN** upload fails before printer access or reservation, with guidance to use local inspection

#### Scenario: Existing destination or attempt
- **WHEN** the remote filename exists or a matching device/file upload attempt is already reserved
- **THEN** upload refuses without replacing the remote file or repeating the POST

#### Scenario: Uncertain upload
- **WHEN** transmission or subsequent verification has an uncertain outcome
- **THEN** the durable attempt remains, the result explains uncertainty and no retry is performed

### Requirement: Serialized upload preflight
Mutating device operations sharing a device state directory SHALL hold one exclusive `.device.lock` lease (never creating `.upload.lock` or `.start.lock`) across preflight, durable reservation, execution, and verification, regardless of file hash or profile name. Contention SHALL fail before printer access without waiting, retrying, or creating an attempt. Releasing the lease SHALL NOT delete `.device.lock` or attempt markers.

#### Scenario: Concurrent payloads for one destination
- **WHEN** different reviewed payloads target the same remote filename through the same device state directory
- **THEN** only the `.device.lock` lease holder can access the printer, no `.upload.lock` or `.start.lock` file is created, and any later lease holder checks the fresh listing before considering an upload

#### Scenario: State path replaced during upload
- **WHEN** the configured state path is replaced while an upload holds its `.device.lock` device lease
- **THEN** marker checks, reservations, and receipt writes remain in the leased directory; detected replacement blocks a POST or records uncertainty after a POST without replay or writes into the replacement directory

### Requirement: Read-only print plan
`print plan` with `--name`, repeatable required `--slot-map <paint_index=slot>`, and explicit preparation flags SHALL validate the printer, local file, remote metadata, G-code filament/tool declarations, and mapped onboard slots. It SHALL report the plan hash, device, file metadata, structured `slot_mapping`, `multicolor`, preparation settings, and qualification limits without upload, start, or state writes.

#### Scenario: Review a stored file
- **WHEN** the qualified target is idle and `print plan` runs with `--slot-map 0=<1..4>` on a single-filament `paint_index: 0` G-code whose metadata and material checks pass
- **THEN** a plan is returned with `multicolor: false`, a one-entry `slot_mapping`, the canonical `ams_box_mapping` payload, and a deterministic `plan_sha256` hash unaffected by text/JSON presentation

#### Scenario: Review a stored multicolor file with --slot-map
- **WHEN** the qualified target is idle and `print plan` runs with repeatable `--slot-map PAINT_INDEX=SLOT` covering every `paint_index` declared in the G-code (contiguous or non-contiguous, such as `1` and `3`, or mixed compatible materials such as `PLA` and `PETG`)
- **THEN** a plan is returned with `multicolor: true`, `hardware_start_validated: false`, ordered `slot_mapping` and `ams_box_mapping` entries sorted by `paint_index`, and a deterministic `plan_sha256` independent of `--slot-map` argument order

#### Scenario: Incompatible plan
- **WHEN** the target is busy, firmware is unsupported, file/remote metadata do not match, a mapped slot is not loaded, or any mapped slot material family differs from its corresponding G-code `paint_index` material
- **THEN** planning fails with exit 2 (`validation_failed`) without any physical command or upload/start reservation

### Requirement: Guarded print start
`print start` SHALL require the same file/name/`--slot-map`/preparation inputs as planning plus `--execute` and `--plan-sha256`. It SHALL rebuild and match the plan (including `ams_box_mapping`), require the verified upload receipt, recheck idle state, and durably reserve before one start command. It SHALL never upload, automatically accept a changed plan, or infer completion from acknowledgement.

#### Scenario: Missing execution inputs
- **WHEN** either explicit execution control is absent or malformed
- **THEN** start fails before printer access or state mutation and directs the owner to planning

#### Scenario: Plan or provenance changed
- **WHEN** rebuilt execution-relevant content (including any mapped slot, material, or color in `ams_box_mapping`) differs from the reviewed hash or verified upload provenance is unavailable
- **THEN** start refuses without publishing a start command or creating a new attempt reservation

#### Scenario: Execute a reviewed multicolor start and intentional reprint
- **WHEN** `print start` runs with `--slot-map` matching a reviewed multicolor `plan_sha256`, `--execute`, a verified upload receipt, and fresh idle telemetry (and optionally `--reprint-from` for an eligible observed-active predecessor)
- **THEN** it durably reserves the attempt, publishes one start command carrying the full ordered `ams_box_mapping`, and records `slot_mapping`, `multicolor`, and `hardware_start_validated: false` in the start receipt

#### Scenario: Ambiguous start
- **WHEN** the start request or subsequent bounded observation is uncertain
- **THEN** its reservation remains and output distinguishes acknowledged, observed-active, and uncertain outcomes without claiming completion or replaying the command

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
- **THEN** `print plan` and `print start` do not migrate, modify, or delete those files, do not treat them as an eligible reprint predecessor, and `print start --execute` refuses without sending a start command while those files exist

### Requirement: Evidence stays qualified
Both formats SHALL distinguish upload listing/metadata verification from remote byte-hash verification, start acknowledgement from observed activity, and activity from completion or physical quality. `hardware_start_validated` SHALL reflect only the live-observed Kobra X `20030` / firmware `2.0.2.2` slot-mapping classes, materials, and preparation-flag combinations recorded in the centralized qualification registry; unobserved combinations SHALL report `hardware_start_validated: false`.

#### Scenario: Successful submission
- **WHEN** an upload is metadata-verified or a start is observed active
- **THEN** output labels that evidence accurately without claiming remote byte equality, completed printing, or assessed part quality

#### Scenario: Multicolor or non-zero paint_index qualification boundary
- **WHEN** `print plan` or `print start` runs on Kobra X `20030` / firmware `2.0.2.2` with a live-observed material, a live-observed preparation-flag tuple, and a live-observed onboard slot-mapping class (including single-filament slot `3`, cross-remapped 2-color subset, sparse `paint_index`, non-zero single `paint_index`, and shared physical slots if live-confirmed) versus an untested material, untested preparation-flag tuple, or unconfirmed mapping pattern
- **THEN** live-observed combinations report `experimental: true` and `hardware_start_validated: true`, while every unobserved combination reports `experimental: true` and `hardware_start_validated: false`

### Requirement: Local identity for each start attempt
Each durably reserved start SHALL have a deterministic local `attempt_id` independent of firmware task IDs. Both root starts and reprints SHALL be stored under `starts/<device>/<attempt_id>.attempt` and `<attempt_id>.json`, SHALL record `attempt_id` in marker and receipt, SHALL bind device, file, plan, and any reprint predecessor, and SHALL expose safe attempt references in text and JSON.

#### Scenario: Two deliberate runs share the same stored file
- **WHEN** an initial root start and its eligible reviewed reprint are reserved
- **THEN** both are stored under `<attempt_id>.attempt` and `<attempt_id>.json` with distinct durable `attempt_id` values, the second record links to the first via `previous_attempt_id`, and the upload receipt remains usable as provenance for both

#### Scenario: Result becomes uncertain after reservation
- **WHEN** the CLI can report a safe partial result for an uncertain start
- **THEN** it includes the reserved `attempt_id` and known evidence without claiming completion

### Requirement: Review an intentional reprint
`print plan --reprint-from PREVIOUS_ATTEMPT_ID` SHALL bind the review hash to the immediate predecessor for the selected device and file. Planning SHALL remain read-only and retain existing file, metadata, material and qualification checks. Ordinary planning SHALL preserve its hash semantics and expose a safe reference to the latest local attempt when available.

#### Scenario: Review context changes
- **WHEN** the reviewed predecessor, file, target or execution choices differ at execution
- **THEN** the prior reviewed hash grants no authorization to publish a start

#### Scenario: Wrong or superseded predecessor
- **WHEN** planning specifies an attempt for another device or file, or one that already has a successor
- **THEN** planning refuses and creates no reservation

### Requirement: Execute an intentional reprint once
`print start --reprint-from PREVIOUS_ATTEMPT_ID` SHALL require the matching reprint review and `--execute`, the existing verified upload receipt, and a fresh idle report immediately before reservation. It SHALL require the predecessor to have recorded observed-active start evidence and SHALL reserve at most one successor per predecessor before publishing one start command.

#### Scenario: Deliberate reprint on an idle printer
- **WHEN** the current predecessor has observed-active start evidence and the fresh plan, verified upload provenance, reviewed hash and final idle check pass
- **THEN** the CLI durably reserves a successor and publishes one start without another upload
- **AND** the prior run's terminal outcome remains unclassified by the reprint

#### Scenario: Unresolved predecessor
- **WHEN** the predecessor is reserved, interrupted, acknowledged without observed activity, otherwise uncertain or unreadable
- **THEN** reprint refuses even when fresh telemetry shows idle

#### Scenario: Replayed or competing review
- **WHEN** a predecessor already has a reserved successor or concurrent executions compete to use it, including with different plan hashes or profile names
- **THEN** at most one execution reserves a successor and publishes a start in the shared device state
- **AND** later invocations preserve the existing reservations and publish nothing for that predecessor

#### Scenario: Printer becomes busy
- **WHEN** the final read shows an active job or fails to establish fresh idle state
- **THEN** the CLI creates no successor and publishes no start

### Requirement: Explicit multicolor and non-zero paint-index slot mapping
`print plan` and `print start` SHALL require repeatable `--slot-map PAINT_INDEX=SLOT` (removing `--slot`), mapping 0-based `paint_index` to 1-based onboard slots (`1..4`). Every `T<n>` tool SHALL appear in `; paint_info =`, `--slot-map` SHALL cover all declared `paint_index` values exactly, and multiple `paint_index` entries MAY share one physical slot when materials match.

#### Scenario: Map multiple paint indices to the same physical slot
- **WHEN** a multicolor G-code declares `paint_index` `0` (`PLA`) and `1` (`PLA`) and `print plan` runs with `--slot-map 0=1 --slot-map 1=1` against a loaded `PLA High Speed` slot `1`
- **THEN** planning succeeds with two `ams_box_mapping` entries (`paint_index: 0` and `paint_index: 1`, both with `ams_index: 0`), `multicolor: true`, ordered `slot_mapping`, and `hardware_start_validated: false`

#### Scenario: Map a single-filament G-code on a non-zero paint index
- **WHEN** a single-filament G-code declares only `paint_index: 2` (`PLA`, with `T2`) and `print plan` runs with `--slot-map 2=4`
- **THEN** planning succeeds with one `ams_box_mapping` entry (`paint_index: 2`, `ams_index: 3`), `multicolor: false`, a one-entry `slot_mapping`, and `hardware_start_validated: false`

#### Scenario: Missing, extra, or undeclared tool mapping fails validation
- **WHEN** `--slot-map` omits a declared `paint_index`, specifies a `paint_index` not present in `; paint_info =`, or the G-code contains a `T<n>` command absent from `; paint_info =`
- **THEN** planning fails with exit 2 (`validation_failed`) without publishing any command or writing state

#### Scenario: External or non-onboard filament box rejected
- **WHEN** `multiColorBox / getInfo` reports multi-box or non-onboard (`id != -1`) topology during planning
- **THEN** planning fails with exit 2 (`validation_failed`) without fabricating slot mappings
