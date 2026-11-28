# print-observation Specification

## Purpose

Follow an active print on a qualified Kobra X through read-only telemetry and expose the degree of certainty about its outcome.

## Requirements

### Requirement: Observe one active print

`print watch` SHALL poll fresh qualified `info` reports over one pinned MQTT session for the active job across recognized firmware `2.0.2.2` preparation/filament-change, `printing`, pause, `resuming`, and `stopping` states. It SHALL tolerate bounded negative clock skew on correlated non-retained post-ACK reports with strictly increasing timestamps, issuing only read-only queries and writing only under `--state-dir/observations/`.

#### Scenario: Job started by another client
- **WHEN** fresh qualified telemetry reports an active job started from another client
- **THEN** watch observes that job without requiring a local upload or start receipt

#### Scenario: Active job in calibration, filament-change, pause, or stopping state
- **WHEN** fresh qualified telemetry reports an active job in `auto_leveling`, `vibrating`, `flow_calibrating`, `filament_cutting`, `extfilbox_filament_unfeeding`, `nozzle_cooling_off`, `paused`, `pausing`, `resuming`, or `stopping`
- **THEN** watch recognizes the active job, maps it to its normalized phase (`preparing`, `paused`, or `stopping`), and continues polling rather than exiting with `active_job_unverified`

#### Scenario: Small printer clock skew during a long watch
- **WHEN** a correlated, non-retained post-ACK `info` report carries a timestamp slightly behind the host send clock (within the bounded skew tolerance) and strictly greater than the previous accepted report timestamp
- **THEN** watch accepts the report and continues polling without timing out
- **AND** genuinely stale reports outside the skew window, retained reports, or non-increasing timestamps are ignored

#### Scenario: No active job
- **WHEN** the initial fresh report establishes that the printer is idle without an active job
- **THEN** watch exits 0 with outcome `no_active_job` and does not attribute a last-project record to this invocation

#### Scenario: Invalid trust or qualification
- **WHEN** the target fails pin or firmware validation
- **THEN** watch exits 2 with a safe error and no terminal print claim
- **AND** a pin mismatch prevents transmission of MQTT credentials

### Requirement: Attribute outcomes to the observed job

Watch SHALL report `completed`, `canceled`, or `failed` only on hardware-validated attributable terminal telemetry. While the active job retains a matching filename, matching non-placeholder `task_id` if present, coherent phases, and non-regressing counters, watch SHALL keep updating verified progress even with placeholder `task_id` `"-1"`. It SHALL stop with `unknown` on disappearance, replacement, unattributed `last_project`, missing filename, or regression.

#### Scenario: Continuous coherent observation across preparation, printing, filament change, pause, and idle transition
- **WHEN** fresh qualified telemetry progresses from `auto_leveling` through `printing` (with increasing `progress` and `curr_layer`), temporary `filament_cutting` / `nozzle_purging` or `paused` / `resuming` transitions, end-of-print layer-counter zeroing at `99%`, and finally `state: "free"` with empty `last_project`
- **THEN** watch continues polling across the entire run, retains the highest verified progress and layer counters without overwriting them with zero, and exits 0 with `outcome: "unknown"`, `reason: "job_disappeared"`, and the latest verified phase and scalar progress

#### Scenario: Attributable terminal report
- **WHEN** fresh telemetry supplies a validated terminal signal for the observed attempt
- **THEN** watch exits 0 and reports the corresponding outcome and last verified progress, if any

#### Scenario: Ambiguous terminal evidence
- **WHEN** the active job disappears and telemetry only shows idle, 100 percent progress, or a last project without a reliable match to the observed attempt
- **THEN** watch exits 0 with `unknown`, the reason and any last verified progress

#### Scenario: A different attempt of the same file
- **WHEN** fresh telemetry with the same filename reports regressed printing `progress`, a lower nonzero `curr_layer`, a changed nonzero `total_layers`, or a start-only calibration phase (`auto_leveling`, `z_offset_calibrating`, `vibrating`, `flow_calibrating`) after printing progress was established
- **THEN** watch stops immediately with `outcome: "unknown"` and `reason: "identity_unverified"` and preserves only the prior verified progress without adopting the replacement's counters

#### Scenario: Missing or hostile filename cannot establish continuity
- **WHEN** the initial active report lacks a valid printable filename (or supplies a hostile URL/control-character string) and a second active report arrives
- **THEN** watch stops with `outcome: "unknown"` and `reason: "identity_unverified"` without leaking the untrusted filename

### Requirement: Bound observation and preserve partial results

Watch SHALL enforce a finite default and bounded positive timeout, stopping on confirmed outcome, lost continuity, deadline, communication failure, or interruption. It SHALL emit one final result on `stdout` using the shared presentation contract. By default, while observing an active job, watch SHALL emit concise sanitized progress lines to `stderr` on scalar status changes (excluding filenames, URLs, credentials, and control characters); `--quiet` SHALL suppress `stderr` progress.

#### Scenario: Live progress on stderr with clean stdout
- **WHEN** `print watch` runs without `--quiet` in text or `--json` mode while an active job advances across preparation and printing polls
- **THEN** `stderr` receives sanitized progress updates containing only safe scalar status (without filenames, URLs, credentials, or terminal controls)
- **AND** `stdout` contains only the single final text summary or single-line JSON envelope

#### Scenario: Quiet flag suppresses stderr progress
- **WHEN** `print watch --quiet` runs in text or `--json` mode while observing an active job
- **THEN** `stderr` remains empty and `stdout` emits the normal final result

#### Scenario: Observation deadline
- **WHEN** the deadline expires while the outcome remains unconfirmed
- **THEN** watch exits 0 with outcome `unknown`, a deadline reason and the latest verified progress

#### Scenario: Connection lost after observation starts
- **WHEN** the pinned connection fails after the job has been observed
- **THEN** watch exits 3 with outcome `unknown` in the partial result and preserves the latest verified progress
- **AND** it does not reconnect or switch targets

#### Scenario: User stops watching
- **WHEN** the operator interrupts the foreground watcher
- **THEN** watch exits 130 with an interruption error and, once a job has been observed, outcome `unknown` and the latest verified progress
- **AND** it sends no printer control command

### Requirement: Persist local watch observations

After establishing a verified active phase (`preparing`, `printing`, `paused`, or `stopping`), `print watch` SHALL atomically save one private (`0600`) sanitized observation under `<state-dir>/observations/<device-prefix>/` (`0700`, no-follow) before exiting, including on deadline, error, or interrupt. It SHALL write nothing on `no_active_job` or pre-observation failure; unsafe paths or I/O errors SHALL preserve the watch result with `observation_recorded: false`.

#### Scenario: Active job observed until stop or deadline
- **WHEN** `print watch` observes an active job across one or more polls and stops due to disappearance, replacement, regression, or deadline expiration
- **THEN** it writes one private atomic observation record with `observation_id`, `device_digest`, timestamps, validated `observed_filename`, `client_attribution: "unattributed"`, outcome, reason, and the latest verified phase (`preparing`, `printing`, `paused`, or `stopping`) and scalar progress, preserves existing profiles/receipts/markers, and reports `observation_id` and `observation_recorded: true` in stdout without leaking raw telemetry

#### Scenario: Active job interrupted or disconnected after observation
- **WHEN** `print watch` observes an active job and then encounters a connection failure (exit 3) or user interruption (exit 130)
- **THEN** it persists the partial observation record with the latest verified progress under `--state-dir` and includes `observation_id` and `observation_recorded: true` in its partial result alongside the existing exit code

#### Scenario: Idle printer or pre-observation failure writes nothing
- **WHEN** `print watch` sees `no_active_job` or fails before establishing a verified active phase
- **THEN** it creates no observation directory and writes no observation file under `--state-dir`

#### Scenario: Unsafe observation directory preserves watch result
- **WHEN** `print watch` observes an active job but `--state-dir/observations/<device-prefix>` is a symlink or has non-private permissions
- **THEN** it does not follow the symlink or change permissions, keeps the watch outcome and exit status intact, and reports `observation_recorded: false` without an `observation_id`
