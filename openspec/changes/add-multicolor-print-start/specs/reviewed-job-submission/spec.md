# Spec Delta

## MODIFIED Requirements

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

### Requirement: Evidence stays qualified
Both formats SHALL distinguish upload listing/metadata verification from remote byte-hash verification, start acknowledgement from observed activity, and activity from completion or physical quality. Qualification SHALL remain Kobra X model 20030 / firmware 2.0.2.2 and the existing narrower material/preparation evidence; multicolor and non-zero `paint_index` starts SHALL report `hardware_start_validated: false`.

#### Scenario: Successful submission
- **WHEN** an upload is metadata-verified or a start is observed active
- **THEN** output labels that evidence accurately without claiming remote byte equality, completed printing, or assessed part quality

#### Scenario: Multicolor or non-zero paint_index qualification boundary
- **WHEN** `print plan` or `print start` succeeds for a multicolor mapping or a single-filament G-code whose `paint_index` is not `0` (even when using PLA High Speed in slots 1, 2, or 4 with auto-leveling on and vibration/flow calibration off)
- **THEN** output reports `experimental: true` and `hardware_start_validated: false`

## ADDED Requirements

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
