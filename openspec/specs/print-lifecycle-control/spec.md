# print-lifecycle-control Specification

## Purpose

Execute guarded, single-shot pause, resume, and cancel actions against an active print on a qualified Kobra X over a pinned MQTT session while enforcing fresh state preconditions, bounded post-action verification, and non-replaying uncertainty reporting.

## Requirements

### Requirement: Explicit execution guard and optional active-job binding
`print pause`, `print resume`, and `print cancel` SHALL require `--execute` and SHALL fail with exit 2 before printer access or state locking when `--execute` is omitted rather than performing an implicit dry run. Each command SHALL accept an optional `--filename <remote-name>` validated as a safe printable filename before printer access; if supplied and different from the fresh active project filename, the CLI SHALL exit 2 without publishing.

#### Scenario: Missing execute flag
- **WHEN** `print pause`, `print resume`, or `print cancel` runs without `--execute` in text or JSON mode
- **THEN** the CLI exits 2 with `invalid_arguments`, emits safe guidance without echoing untrusted input, and performs no printer access or state locking

#### Scenario: Malformed filename guard
- **WHEN** `--filename` contains path separators, URL schemes, control characters, or empty text
- **THEN** the CLI exits 2 before target selection or printer access without echoing unsafe input

#### Scenario: Active filename mismatch
- **WHEN** `--filename` is supplied and differs from the fresh active project filename reported by the printer
- **THEN** the CLI exits 2 with `validation_failed`, publishes no control command, and leaves local state unchanged

### Requirement: Fresh qualification and strict state preconditions

Before publishing, the CLI SHALL verify a fresh `info` report over one pinned MQTT session for Kobra X model `20030` / firmware `2.0.2.2` and consistent optional identifiers. `pause` SHALL require `printing`; `resume` SHALL require `paused`; `cancel` SHALL require `printing`, a recognized firmware `2.0.2.2` preparation or filament-change phase, or `paused`. Idle, already-reached, transitional, or unrecognized states SHALL exit 2 without publishing.

#### Scenario: Pause refused when not printing
- **WHEN** `print pause --execute` runs while the printer is idle, already `paused`, `pausing`, or in a preparation phase
- **THEN** the CLI exits 2 with `validation_failed` and publishes no MQTT control command

#### Scenario: Resume refused when not paused
- **WHEN** `print resume --execute` runs while the printer is idle, already `printing`, `resuming`, or in a preparation phase
- **THEN** the CLI exits 2 with `validation_failed` and publishes no MQTT control command

#### Scenario: Cancel allowed from active printing, preparation, or paused
- **WHEN** `print cancel --execute` runs while the fresh active job is `printing`, in a recognized firmware `2.0.2.2` preparation phase, or `paused`
- **THEN** pre-flight validation succeeds and the CLI proceeds to publish one `stop` command

#### Scenario: Cancel allowed during calibration or filament-change preparation
- **WHEN** `print cancel --execute` runs while the fresh active job is in `auto_leveling`, `vibrating`, `flow_calibrating`, `filament_cutting`, or `extfilbox_filament_unfeeding`
- **THEN** pre-flight validation succeeds and the CLI proceeds to publish one `stop` command

#### Scenario: Control refused on idle, transitional, or unqualified target
- **WHEN** `print cancel --execute` encounters idle, `stopping`, an unrecognized project state, a TLS pin mismatch, or unqualified firmware
- **THEN** the CLI exits 2 without publishing any control command
- **AND** a pin mismatch prevents transmission of MQTT credentials

### Requirement: Single-shot MQTT control publish without replay
Each lifecycle command SHALL publish at most one MQTT `print` action (`pause`, `resume`, or `stop` for cancel) carrying the validated active `task_id` or `"-1"` placeholder through a dedicated control path separate from read-only queries. It SHALL wait for one correlated `/response` acknowledgement on the same session and SHALL never reconnect, retry, or replay the command on rejection, timeout, disconnect, or malformed response.

#### Scenario: Valid control publishes once with correlated ACK
- **WHEN** pre-flight checks pass for `pause`, `resume`, or `cancel`
- **THEN** the CLI publishes exactly one MQTT `print` packet with the corresponding action and validated `taskid` and waits for its correlated `/response` ACK with `code == 0`

#### Scenario: Rejected or dropped control command is never replayed
- **WHEN** the correlated `/response` returns a non-zero code or the session times out, closes, or returns a malformed packet after publish
- **THEN** the CLI does not retry or reconnect and reports an error instructing the operator to inspect `status` rather than resend blindly

### Requirement: Bounded post-action verification and honest outcome reporting
After a correlated ACK, the CLI SHALL poll fresh `info` on the same session without treating ACK as proof of state change. It SHALL report `control_observed_paused`, `control_observed_resumed`, `control_observed_stopped`, `control_acknowledged_not_confirmed`, or `control_uncertain_no_retry`, plus `experimental: true` and `hardware_control_validated: true` on the qualified Kobra X model `20030` / firmware `2.0.2.2` target.

#### Scenario: Confirmed pause, resume, or cancel transition
- **WHEN** bounded fresh polling observes `paused` after `pause`, `printing` or a recognized preparation phase after `resume`, or idle/`stoped`/`canceled` after `cancel`
- **THEN** the command exits 0 with the corresponding `control_observed_*` status, sanitized `before` and `after` snapshots, `experimental: true`, and `hardware_control_validated: true`

#### Scenario: Acknowledged without observed transition
- **WHEN** ACK succeeds and bounded polling completes without error while the printer remains in its prior or transitional state
- **THEN** the command exits 0 with `control_acknowledged_not_confirmed`, sanitized `before` and `after` snapshots, and no automatic retry

#### Scenario: Post-publish communication or protocol failure
- **WHEN** a timeout, disconnect, or protocol error occurs during ACK wait or post-action polling
- **THEN** the CLI exits with the failure's exit class (2 for protocol failure, 3 for I/O or timeout), includes `control_uncertain_no_retry` and available safe partial evidence in `result`, and performs no retry

### Requirement: Device concurrency safety and local state preservation
Executing `print pause`, `print resume`, or `print cancel` SHALL acquire the shared per-device exclusive lease under `--state-dir` across pre-flight inspection, publish, and bounded observation, verifying directory binding before publish without following symlinks or altering permissions. Lifecycle controls SHALL NOT create, modify, or delete profiles, upload receipts, start receipts, `.attempt` markers, or watch observations.

#### Scenario: Concurrent device operation refused
- **WHEN** another CLI upload, start, or lifecycle control holds the per-device lease under `--state-dir`
- **THEN** the control command fails before printer access without waiting, retrying, or publishing a command

#### Scenario: Existing local state remains untouched
- **WHEN** `print pause`, `print resume`, or `print cancel` succeeds or becomes uncertain
- **THEN** existing profiles, upload receipts, start receipts, `.attempt` markers, and watch observations remain byte-for-byte unchanged with original permissions

#### Scenario: Unsafe or replaced state directory refused
- **WHEN** the device state directory is a symlink, has non-private permissions, or is replaced before publish
- **THEN** the CLI refuses before sending any MQTT command without following symlinks or changing permissions
