# Spec Delta

## MODIFIED Requirements

### Requirement: Detailed local job inspection
`jobs info <record-id>` SHALL inspect one start attempt, watch observation, or unreadable start-state reference for the selected device under `--state-dir` without network access or state writes. Malformed, unknown, or cross-device IDs SHALL exit 2. Start details SHALL include chain links, hashes, settings (including sanitized `slot_mapping`), start status, reprint eligibility, upload provenance, issues, and matching unattributed observations.

#### Scenario: Inspect an eligible start attempt with reprint chain
- **WHEN** `jobs info <attempt-id>` inspects a start attempt that has verified upload provenance, `start_observed_active`, and a successor reprint
- **THEN** it exits 0 and reports the attempt's `attempt_id`, `next_attempt_id`, correlated upload provenance with `remote_byte_hash_verified: false`, `terminal_outcome: "unknown"`, and indicates the attempt is already superseded for reprint

#### Scenario: Inspect a persisted watch observation
- **WHEN** `jobs info <observation-id>` inspects an observation saved by `print watch`
- **THEN** it exits 0 and reports `client_attribution: "unattributed"`, the validated `observed_filename` if present, timestamps, outcome, reason, and last verified progress without claiming which client started the job

#### Scenario: Malformed or cross-device record ID
- **WHEN** `jobs info` receives a malformed ID or a valid ID recorded under a different device
- **THEN** it exits 2 with a safe error without echoing unsafe input and performs no state writes

## ADDED Requirements

### Requirement: Multicolor start slot-mapping visibility
`jobs info` SHALL replace scalar `selected_slot` and `material_type` on start records with sanitized `slot_mapping` reconstructed from `payload.ams_settings.ams_box_mapping` ordered by `paint_index` (or `null` for unreadable/missing-mapping records) without modifying stored files. `jobs list` SHALL retain its compact summary shape.

#### Scenario: Inspect a multicolor start attempt with mixed materials
- **WHEN** `jobs info <attempt-id>` reads a valid multicolor start receipt mapping `paint_index` `0` to slot `1` (`PLA High Speed`) and `paint_index` `2` to slot `4` (`PETG`)
- **THEN** it exits 0 without modifying files and reports two ordered `slot_mapping` entries covering both `paint_index` values, slots, `ams_index` values, sanitized materials, and sanitized colors

#### Scenario: Inspect a multicolor start attempt sharing one physical slot
- **WHEN** `jobs info <attempt-id>` reads a valid multicolor start receipt mapping `paint_index` `0` and `1` to slot `1` (`PLA High Speed`)
- **THEN** it reports both entries ordered by `paint_index` under `slot_mapping` with `slot: 1`, `ams_index: 0`, and sanitized material/color metadata

#### Scenario: Legacy single-filament start receipt remains readable in place
- **WHEN** `jobs info <attempt-id>` reads a legacy file-keyed single-filament receipt whose `ams_box_mapping` has one entry
- **THEN** it reconstructs the one-entry `slot_mapping` from `payload.ams_settings.ams_box_mapping` and leaves the legacy files byte-for-byte unchanged
