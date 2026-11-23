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
- **THEN** `gcode inspect` succeeds with `paint_info_present: false`, `filaments: []`, `filament_count: 0`, `multicolor: false` (unless multiple distinct `T<n>` tools are present), and `single_filament_start_compatible: false`, and `files upload` continues to accept the reviewed file

### Requirement: Multicolor G-code filament and tool inspection
Local `gcode inspect` SHALL parse all `; paint_info = [...]` lines, `T<n>` tool commands, and optional filament weight summaries, reporting `paint_info_present`, ordered `filaments` (`paint_index`, `material_type`, `color_rgb`, `color_hex`, nullable `filament_used_g`), `filament_count`, `multicolor`, sorted `tool_indices`, nullable `total_filament_used_g`, and `single_filament_start_compatible`. Repeated `; paint_info =` lines SHALL agree; malformed or conflicting declarations SHALL exit 2.

#### Scenario: Inspect single-filament G-code declaring paint_index 0
- **WHEN** a Next-generated Kobra X G-code declares one filament at `paint_index: 0` with no tool index other than `0`
- **THEN** `gcode inspect` reports `paint_info_present: true`, `filament_count: 1`, `multicolor: false`, `single_filament_start_compatible: true`, and one normalized filament entry with `color_rgb` and `color_hex`

#### Scenario: Inspect multicolor G-code with non-contiguous paint indices and repeated headers
- **WHEN** a Next-generated Kobra X G-code contains identical `; paint_info = [...]` lines in both the header and config blocks declaring multiple filaments (for example `paint_index` `1` and `3`, or mixed materials such as `PLA` and `PETG`), corresponding `T<n>` commands, and filament weight summaries
- **THEN** `gcode inspect` exits 0 without network access, reports all declared filaments ordered by `paint_index` with normalized `color_rgb`, `color_hex`, `material_type`, and per-index `filament_used_g`, reports `multicolor: true`, `tool_indices`, `total_filament_used_g`, and `single_filament_start_compatible: false`, and remains uploadable via `files upload`

#### Scenario: Inspect single-filament G-code with non-zero paint index
- **WHEN** a Next-generated Kobra X G-code declares one filament at a non-zero index (for example `paint_index: 2` with `T2`)
- **THEN** `gcode inspect` reports `filament_count: 1`, `multicolor: false`, `tool_indices: [2]`, and `single_filament_start_compatible: false`

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
Uploads sharing the same device state directory SHALL hold an exclusive device lease across destination listing, durable reservation, POST and verification, regardless of file hash or profile name. Contention SHALL fail before printer access without waiting, retrying or creating an attempt. Releasing a lease SHALL NOT delete its lock file or any attempt marker. This coordination SHALL NOT claim atomic firmware-side exclusion against other tools or state directories.

#### Scenario: Concurrent payloads for one destination
- **WHEN** different reviewed payloads target the same remote filename through the same device state directory
- **THEN** only the lease holder can access the printer, and any later lease holder checks the fresh listing before considering an upload

#### Scenario: State path replaced during upload
- **WHEN** the configured state path is replaced while an upload holds its device lease
- **THEN** marker checks, reservations and receipt writes remain in the leased directory; detected replacement blocks a POST or records uncertainty after a POST without replay or writes into the replacement directory

### Requirement: Read-only print plan
`print plan <file> --name <remote-name> --slot <1..4> --auto-leveling <on|off> --vibration-compensation <on|off> --flow-calibration <on|off>` SHALL validate the selected printer, local file, remote metadata and loaded material using the existing qualification checks. It SHALL report the reviewed plan hash, selected device, file hash/name, slot/material/color, explicit preparation settings and qualification limits without upload, start or attempt writes.

#### Scenario: Review a stored file
- **WHEN** the qualified target is idle and file, metadata and material checks pass
- **THEN** a plan is returned with all execution-relevant choices and a deterministic hash unaffected by text/JSON presentation

#### Scenario: Incompatible plan
- **WHEN** the target is busy, firmware is unsupported or file/material/remote metadata do not match
- **THEN** planning fails without any physical command or upload/start reservation

### Requirement: Guarded print start
`print start` SHALL require the same file/name/slot/preparation inputs as planning plus `--execute` and `--plan-sha256`. It SHALL rebuild and match the plan, require the existing verified upload receipt, recheck idle state and durably reserve before one start command. It SHALL never upload, automatically accept a changed plan or infer completion from acknowledgement.

#### Scenario: Missing execution inputs
- **WHEN** either explicit execution control is absent or malformed
- **THEN** start fails before printer access or state mutation and directs the owner to planning

#### Scenario: Plan or provenance changed
- **WHEN** rebuilt execution-relevant content differs from the reviewed hash or verified upload provenance is unavailable
- **THEN** start refuses without publishing a start command or creating a new attempt reservation

#### Scenario: Ambiguous start
- **WHEN** the start request or subsequent bounded observation is uncertain
- **THEN** its reservation remains and output distinguishes acknowledged, observed-active and uncertain outcomes without claiming completion or replaying the command

### Requirement: Existing device state remains authoritative
The CLI SHALL preserve configuration, credentials, existing device-based receipts, reservation paths, permissions and custom `--state-dir` behavior. A first start SHALL retain the existing device/file guard. Existing start records SHALL be interpreted in place and SHALL continue blocking ordinary start. Only the explicit reviewed reprint workflow can authorize a successor to an eligible attempt.

#### Scenario: Old marker with new command
- **WHEN** an existing-format attempt is accessed through the current command tree or another profile for the same device
- **THEN** ordinary start retains the same duplicate protection and preserves the original files and permissions

#### Scenario: Legacy attempt is eligible
- **WHEN** a legacy marker and matching receipt establish an observed-active start for the selected device and file
- **THEN** planning exposes a stable local reference and applies the same reprint checks as for newly created attempts
- **AND** a reprint preserves both legacy files and the verified upload receipt

#### Scenario: Legacy evidence is incomplete
- **WHEN** a prior marker has a missing, malformed or inconsistent receipt, or a receipt exists without its matching marker
- **THEN** both ordinary start and explicit reprint refuse to send a print command for that device and file

### Requirement: Evidence stays qualified
Both formats SHALL distinguish upload listing/metadata verification from remote byte-hash verification, start acknowledgement from observed activity, and activity from completion or physical quality. Qualification SHALL remain Kobra X model 20030 / firmware 2.0.2.2 and the existing narrower material/preparation evidence.

#### Scenario: Successful submission
- **WHEN** an upload is metadata-verified or a start is observed active
- **THEN** output labels that evidence accurately without claiming remote byte equality, completed printing or assessed part quality

### Requirement: Local identity for each start attempt
Each durably reserved start SHALL have a stable local attempt ID independent of firmware task IDs and distinct from other executions of the same file. The state SHALL associate the attempt with its device, file and plan, and record its predecessor for a reprint. Text and JSON SHALL expose safe attempt references and available start evidence.

#### Scenario: Two deliberate runs share the same stored file
- **WHEN** an initial start and its eligible reviewed reprint are reserved
- **THEN** each has its own durable attempt ID and evidence record, and the second record links to the first
- **AND** the upload receipt remains usable as provenance for both

#### Scenario: Result becomes uncertain after reservation
- **WHEN** the CLI can report a safe partial result for an uncertain start
- **THEN** it includes the reserved attempt ID and known evidence without claiming completion

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
