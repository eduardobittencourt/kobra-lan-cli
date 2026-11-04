# reviewed-job-submission Specification

## Purpose

Let owners inspect immutable sliced files, review each submission and start a qualified stored print without losing trust or durable duplicate protection.

## Requirements

### Requirement: Local G-code inspection
`gcode inspect <file> [--name <remote-name>]` SHALL inspect the existing qualified Next-generated Kobra X plain G-code without target configuration, network or state writes. It SHALL report SHA-256, size, proposed remote filename, available slicer/layer metadata and qualification limits while preserving input bytes.

#### Scenario: Inspect before connecting
- **WHEN** a supported synthetic file is inspected without configuration
- **THEN** its reviewable manifest is returned in the selected format and its bytes remain unchanged

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
Command renaming and output formatting SHALL preserve configuration, credentials, device-based upload/start receipt paths and attempt identities, including custom `--state-dir`. Existing attempts SHALL continue blocking replay through the new command tree. This change SHALL NOT add a new-print escape hatch or remove markers.

#### Scenario: Old marker with new command
- **WHEN** a synthetic attempt from the existing state format is accessed through a renamed command or another profile for that device
- **THEN** the same duplicate protection applies and original files and permissions remain preserved

### Requirement: Evidence stays qualified
Both formats SHALL distinguish upload listing/metadata verification from remote byte-hash verification, start acknowledgement from observed activity, and activity from completion or physical quality. Qualification SHALL remain Kobra X model 20030 / firmware 2.0.2.2 and the existing narrower material/preparation evidence.

#### Scenario: Successful submission
- **WHEN** an upload is metadata-verified or a start is observed active
- **THEN** output labels that evidence accurately without claiming remote byte equality, completed printing or assessed part quality
