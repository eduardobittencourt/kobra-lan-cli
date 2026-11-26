## REMOVED Requirements

### Requirement: Accurate representation of legacy, incomplete, and unreadable records
**Reason**: Pre-v1 file-keyed start-record reconstruction and the `record_format` output field are removed before v1.
**Migration**: Replaced by `Accurate representation of canonical, incomplete, and unreadable records`, which reads only canonical attempt-keyed start records and surfaces non-canonical files read-only as `incomplete` (`unreadable-<storage-key>`).

### Requirement: Multicolor start slot-mapping visibility
**Reason**: Removes the legacy file-keyed single-filament scenario while preserving canonical `slot_mapping` reconstruction for both single-filament and multicolor start receipts.
**Migration**: Replaced by `Start slot-mapping visibility`.

## ADDED Requirements

### Requirement: Accurate representation of canonical, incomplete, and unreadable records
History commands SHALL read canonical attempt-keyed start records (`<attempt_id>.attempt` and `.json`, where `storage_key == attempt_id`) in place without altering bytes or permissions. Non-canonical (including pre-v1 file-keyed), incomplete, mismatched, orphan, or unreadable records SHALL surface in `jobs list` and `jobs info` as `completeness: "incomplete"` with `unreadable-<storage-key>` when no valid canonical `attempt_id` matches `storage_key`.

#### Scenario: Pre-v1 file-keyed start files surfaced as incomplete without modification
- **WHEN** `starts/<device>` contains pre-v1 file-keyed `<file_sha256>.attempt` and `<file_sha256>.json` files lacking canonical `attempt_id` keying
- **THEN** `jobs list` and `jobs info unreadable-<file_sha256>` exit 0, report `completeness: "incomplete"`, `attempt_id: null`, `reprint_eligibility: "blocked_incomplete"`, omit `record_format`, and leave the original files and permissions byte-for-byte unchanged

#### Scenario: Incomplete and corrupt start records alongside valid records
- **WHEN** `starts/<device>` contains a valid canonical start attempt, a marker-only reservation, a receipt-only file, and a corrupt unreadable pair
- **THEN** `jobs list` exits 0, returns all four records with accurate `completeness` and `issues`, increments `incomplete_count`, and marks every incomplete record ineligible for reprint without modifying any file

#### Scenario: Unreadable observation file
- **WHEN** `observations/<device>` contains a malformed JSON observation alongside a valid observation
- **THEN** `jobs list` exits 0, surfaces the malformed file with its validated `observation_id`, `completeness: "incomplete"`, and an unreadable issue code, and still lists the valid observation

### Requirement: Start slot-mapping visibility
`jobs info` SHALL expose sanitized `slot_mapping` on start records reconstructed from `payload.ams_settings.ams_box_mapping` ordered by `paint_index` (or `null` for unreadable/missing-mapping records) without modifying stored files. `jobs list` SHALL retain its compact summary shape.

#### Scenario: Inspect a multicolor start attempt with mixed materials
- **WHEN** `jobs info <attempt-id>` reads a valid multicolor start receipt mapping `paint_index` `0` to slot `1` (`PLA High Speed`) and `paint_index` `2` to slot `4` (`PETG`)
- **THEN** it exits 0 without modifying files and reports two ordered `slot_mapping` entries covering both `paint_index` values, slots, `ams_index` values, sanitized materials, and sanitized colors

#### Scenario: Inspect a multicolor start attempt sharing one physical slot
- **WHEN** `jobs info <attempt-id>` reads a valid multicolor start receipt mapping `paint_index` `0` and `1` to slot `1` (`PLA High Speed`)
- **THEN** it reports both entries ordered by `paint_index` under `slot_mapping` with `slot: 1`, `ams_index: 0`, and sanitized material/color metadata

#### Scenario: Canonical single-filament start receipt exposes one-entry slot_mapping
- **WHEN** `jobs info <attempt-id>` reads a canonical attempt-keyed single-filament start receipt whose `ams_box_mapping` has one entry
- **THEN** it reconstructs the one-entry `slot_mapping` from `payload.ams_settings.ams_box_mapping` and leaves the stored files byte-for-byte unchanged

## MODIFIED Requirements

### Requirement: Detailed local job inspection
`jobs info <record-id>` SHALL inspect one start attempt, watch observation, or unreadable start-state reference for the selected device under `--state-dir` without network access or state writes. Malformed, unknown, or cross-device IDs SHALL exit 2. Start details SHALL include chain links, hashes, settings (including sanitized `slot_mapping`), start status, reprint eligibility, upload provenance, issues, and matching unattributed observations, and SHALL omit `record_format`.

#### Scenario: Inspect an eligible start attempt with reprint chain
- **WHEN** `jobs info <attempt-id>` inspects a canonical start attempt that has verified upload provenance, `start_observed_active`, and a successor reprint
- **THEN** it exits 0, omits `record_format`, and reports the attempt's `attempt_id`, `next_attempt_id`, correlated upload provenance with `remote_byte_hash_verified: false`, `terminal_outcome: "unknown"`, and indicates the attempt is already superseded for reprint

#### Scenario: Inspect a persisted watch observation
- **WHEN** `jobs info <observation-id>` inspects an observation saved by `print watch`
- **THEN** it exits 0 and reports `client_attribution: "unattributed"`, the validated `observed_filename` if present, timestamps, outcome, reason, and last verified progress without claiming which client started the job

#### Scenario: Malformed or cross-device record ID
- **WHEN** `jobs info` receives a malformed ID or a valid ID recorded under a different device
- **THEN** it exits 2 with a safe error without echoing unsafe input and performs no state writes
