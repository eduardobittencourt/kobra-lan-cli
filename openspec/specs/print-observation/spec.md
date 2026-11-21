# print-observation Specification

## Purpose

Follow an active print on a qualified Kobra X through read-only telemetry and expose the degree of certainty about its outcome.

## Requirements

### Requirement: Observe one active print

`print watch` SHALL use the selected printer's pinned authenticated MQTT connection and fresh qualified reports. It SHALL observe the job active when it starts, regardless of which client started it. It SHALL issue only read-only queries and SHALL leave printer settings, credentials, profiles, receipts and attempt markers untouched.

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

### Requirement: Attribute outcomes to the observed job

Watch SHALL report `completed`, `canceled` or `failed` only when fresh firmware telemetry supplies a hardware-validated terminal signal attributable to that same print attempt. Watch SHALL stop with `unknown` when the job disappears or is replaced without attributable terminal evidence. It SHALL report only validated progress and keep physical part quality outside its result.

#### Scenario: Attributable terminal report
- **WHEN** fresh telemetry supplies a validated terminal signal for the observed attempt
- **THEN** watch exits 0 and reports the corresponding outcome and last verified progress, if any

#### Scenario: Ambiguous terminal evidence
- **WHEN** the active job disappears and telemetry only shows idle, 100 percent progress, or a last project without a reliable match to the observed attempt
- **THEN** watch exits 0 with `unknown`, the reason and any last verified progress

#### Scenario: A different attempt of the same file
- **WHEN** fresh telemetry shows a different attempt with the same filename
- **THEN** watch does not follow it or report its progress or outcome as belonging to the original attempt

### Requirement: Bound observation and preserve partial results

Watch SHALL have a finite default and accept a bounded positive observation timeout. It SHALL stop on confirmed outcome, lost attribution, deadline, communication failure or user interruption. It SHALL publish one final result using the shared presentation contract, with optional progress on stderr and no raw telemetry, tokens or credentials.

#### Scenario: Observation deadline
- **WHEN** the deadline expires while the outcome remains unconfirmed
- **THEN** watch exits 0 with outcome `unknown`, a deadline reason and any last verified progress

#### Scenario: Connection lost after observation starts
- **WHEN** the pinned connection fails after the job has been observed
- **THEN** watch exits 3 with outcome `unknown` in the partial result and preserves any last verified progress
- **AND** it does not reconnect or switch targets

#### Scenario: User stops watching
- **WHEN** the operator interrupts the foreground watcher
- **THEN** watch exits 130 with an interruption error and, once a job has been observed, outcome `unknown` and any last verified progress
- **AND** it sends no printer control command
