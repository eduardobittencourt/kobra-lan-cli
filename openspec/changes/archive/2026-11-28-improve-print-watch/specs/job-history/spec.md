## MODIFIED Requirements

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
