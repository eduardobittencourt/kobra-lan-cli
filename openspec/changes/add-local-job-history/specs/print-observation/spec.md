# Spec Delta

## MODIFIED Requirements

### Requirement: Observe one active print

`print watch` SHALL use the selected printer's pinned authenticated MQTT connection and fresh qualified reports. It SHALL observe the job active at startup, regardless of which client started it. It SHALL issue only read-only printer queries and leave printer settings, credentials, profiles, upload/start receipts, and attempt markers untouched; local observation persistence SHALL occur only in the separate observations area under `--state-dir` after an active job is observed.

#### Scenario: Job started by another client
- **WHEN** fresh qualified telemetry reports an active job started from another client
- **THEN** watch observes that job without requiring a local upload or start receipt

#### Scenario: No active job
- **WHEN** the initial fresh report establishes that the printer is idle without an active job
- **THEN** watch exits 0 with outcome `no_active_job` and does not attribute a last-project record to this invocation

#### Scenario: Invalid trust or qualification
- **WHEN** the target fails pin or firmware validation
- **THEN** watch exits 2 with a safe error and no terminal print claim
- **AND** a pin mismatch prevents transmission of MQTT credentials

## ADDED Requirements

### Requirement: Persist local watch observations

After establishing a verified active phase, `print watch` SHALL atomically write one sanitized private (`0600`) observation record under `<state-dir>/observations/<device-prefix>/` (`0700`, no-follow) before exiting, including on deadline, post-observation error, or interruption. It SHALL write nothing on `no_active_job` or pre-observation failure. If persistence fails due to unsafe paths or I/O errors, watch SHALL preserve its result and exit status and report `observation_recorded: false`.

#### Scenario: Active job observed until stop or deadline
- **WHEN** `print watch` observes an active job and stops due to lost attribution, replacement, or deadline expiration
- **THEN** it writes one private atomic observation record with `observation_id`, `device_digest`, timestamps, validated `observed_filename`, `client_attribution: "unattributed"`, outcome, reason, and verified progress, preserves existing profiles/receipts/markers, and reports `observation_id` and `observation_recorded: true` in stdout without leaking raw telemetry

#### Scenario: Active job interrupted or disconnected after observation
- **WHEN** `print watch` observes an active job and then encounters a connection failure (exit 3) or user interruption (exit 130)
- **THEN** it persists the partial observation record under `--state-dir` and includes `observation_id` and `observation_recorded: true` in its partial result alongside the existing exit code

#### Scenario: Idle printer or pre-observation failure writes nothing
- **WHEN** `print watch` sees `no_active_job` or fails before establishing a verified active phase
- **THEN** it creates no observation directory and writes no observation file under `--state-dir`

#### Scenario: Unsafe observation directory preserves watch result
- **WHEN** `print watch` observes an active job but `--state-dir/observations/<device-prefix>` is a symlink or has non-private permissions
- **THEN** it does not follow the symlink or change permissions, keeps the watch outcome and exit status intact, and reports `observation_recorded: false` without an `observation_id`
