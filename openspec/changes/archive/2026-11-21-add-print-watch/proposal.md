# Proposal

## Why

The CLI can observe the start of a print, but its hardware evidence ends at the first layer. Milestone 3 needs a way to follow the active job to an outcome that the firmware can substantiate.

## What Changes

- Characterize the Kobra X firmware's current and last project telemetry against an operator-observed outcome. A print already in progress can supply this evidence with separately authorized observation.
- Add a read-only `kobra-lan print watch` for a job already active on the selected printer, including jobs started by another client. Bound the observation and report the last verified progress and the outcome.
- Distinguish confirmed completion, cancellation and failure when verified signals can be tied to the observed job. Report an unknown outcome when observation ends without that evidence.
- Describe the command in installed help, shell completion and the usage guide. Print controls, job history, intentional reprints and assessment of part quality stay outside this change.

## Capabilities

### New Capabilities

- `print-observation` — Read-only observation of an active print through a verified outcome or an explicit report of uncertainty.

### Modified Capabilities

- `cli-interface` — Add `print watch` to the canonical command tree and installed workflow.

## Impact

The change extends CLI routing and adds an observation path using the existing pinned MQTT transport and profile selection. It adds synthetic CLI and telemetry tests, documentation and a hardware evidence record for the qualified Kobra X model 20030 / firmware 2.0.2.2.
