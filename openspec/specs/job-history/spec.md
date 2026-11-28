# job-history Specification

## Purpose

Expose offline, read-only local job history (`jobs list` and `jobs info`) backed by start receipts/markers, upload provenance, and persisted watch observations while accurately representing incomplete records, unattributed other-client observations, and unclassified terminal outcomes.

## Requirements

### Requirement: Offline device-scoped job listing
`jobs list [--kind all|start|observation] [--limit N]` SHALL resolve the selected printer via shared selectors and `--state-dir` without network access or state writes. `--kind` SHALL default to `all`; `--limit` SHALL accept integers `1..500` (default `50`), exiting 2 before target selection on invalid values. Results SHALL be ordered newest first with summary counts and identical output across profiles for the same device.

#### Scenario: Empty state on a configured printer
- **WHEN** `jobs list` runs for a configured target whose device has no start or observation directories under `--state-dir`
- **THEN** it exits 0 with an empty `jobs` list, zero counts, explicit local-only coverage metadata, no network access, and no directories created

#### Scenario: Filtered and bounded listing
- **WHEN** a device has both CLI start attempts and persisted watch observations and `jobs list --kind observation --limit 1` runs
- **THEN** only observation records are considered, at most one newest record is returned, and `total_count`, `returned_count`, and `truncated` reflect the filtered set accurately

#### Scenario: Shared device history across profiles
- **WHEN** two named profiles or an explicit `--config` reference the same `printer_id` with the same `--state-dir`
- **THEN** `jobs list` returns the same local attempt IDs, chains, and observations for each selector

#### Scenario: Invalid filter or limit
- **WHEN** `--kind` is unsupported or `--limit` is malformed or outside `1..500` in text or JSON mode
- **THEN** the CLI exits 2 before target selection with one safe error and does not echo arbitrary input values

### Requirement: Detailed local job inspection

`jobs info <record-id>` SHALL inspect one start attempt, watch observation, or unreadable start-state reference offline without state writes, exiting 2 on malformed, unknown, or cross-device IDs. Start details SHALL include chain links, hashes, settings (including `slot_mapping`), status, reprint eligibility, upload provenance, issues, and matching observations, omitting `record_format`. Observation validation SHALL accept `preparing`, `printing`, `paused`, and `stopping`.

#### Scenario: Inspect an eligible start attempt with reprint chain
- **WHEN** `jobs info <attempt-id>` inspects a canonical start attempt that has verified upload provenance, `start_observed_active`, and a successor reprint
- **THEN** it exits 0, omits `record_format`, and reports the attempt's `attempt_id`, `next_attempt_id`, correlated upload provenance with `remote_byte_hash_verified: false`, `terminal_outcome: "unknown"`, and indicates the attempt is already superseded for reprint

#### Scenario: Inspect a persisted watch observation
- **WHEN** `jobs info <observation-id>` inspects an observation saved by `print watch`
- **THEN** it exits 0 and reports `client_attribution: "unattributed"`, the validated `observed_filename` if present, timestamps, outcome, reason, and last verified progress without claiming which client started the job

#### Scenario: Inspect a persisted watch observation in paused or stopping phase
- **WHEN** `jobs list` or `jobs info <observation-id>` inspects a valid observation saved by `print watch` whose recorded `phase` is `paused` or `stopping`
- **THEN** it exits 0, marks the record `completeness: "complete"`, reports `client_attribution: "unattributed"`, timestamps, outcome, reason, phase, and last verified progress without altering stored files

#### Scenario: Malformed or cross-device record ID
- **WHEN** `jobs info` receives a malformed ID or a valid ID recorded under a different device
- **THEN** it exits 2 with a safe error without echoing unsafe input and performs no state writes

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

### Requirement: Honest attribution, qualification, and coverage boundaries
History output SHALL distinguish CLI start attempts (`client_attribution: "cli"`) from watch observations (`client_attribution: "unattributed"`), include local-only coverage metadata (no direct firmware `2.0.2.2` LAN history; other-client actions absent unless watched; start receipts never prove completion or quality), and label filename matches as unattributed. Both text and `--json` SHALL follow the shared envelope and exclude credentials, raw telemetry, token URLs, and terminal controls.

#### Scenario: Watched job started by another client
- **WHEN** `print watch` observed an active print started outside the CLI and `jobs list` runs afterward
- **THEN** `jobs list` includes the saved observation with `client_attribution: "unattributed"` and coverage metadata explaining that unwatched other-client runs are not recorded locally

#### Scenario: Same filename watched after a CLI start
- **WHEN** a CLI start attempt and a later watch observation share the same filename
- **THEN** `jobs info <attempt-id>` lists the observation under unattributed filename matches and keeps the start attempt's `terminal_outcome` as `unknown`

### Requirement: Private read-only storage safety
History reads SHALL walk state directories without following symlinks and require existing device directories (`<state-dir>/<device>`, `starts/<device>`, `observations/<device>`) to be user-owned mode `0700`. A symlinked or non-private device directory SHALL fail with exit 3 without following symlinks or changing permissions. Individual symlinked, non-private, or oversized record files inside a valid directory SHALL NOT be read and SHALL be reported as incomplete unreadable entries.

#### Scenario: Symlinked or permissive starts directory
- **WHEN** `<state-dir>/starts/<device>` is a symlink or has mode `0755`
- **THEN** `jobs list` and `jobs info` exit 3 with a safe `operation_failed` error without following the symlink or altering permissions

#### Scenario: Non-private individual receipt file inside a valid directory
- **WHEN** one receipt file inside a private `0700` device directory has mode `0644` or is a symlink
- **THEN** `jobs list` refuses to read that file, marks its record incomplete with an unreadable issue code, preserves permissions, and still lists valid sibling records

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
