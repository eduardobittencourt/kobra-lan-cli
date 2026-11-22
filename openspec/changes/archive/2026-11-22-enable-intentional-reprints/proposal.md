# Proposal

## Why

The current print start reservation uses the printer and G-code hash, so it blocks a deliberate second run of the same stored file. The qualified firmware exposes a placeholder task ID and has supplied no attributable terminal record, so the client needs its own execution identity to support reprints safely.

## What Changes

- Give each CLI start attempt a durable local ID and retain its relationship to the stored file and reviewed plan.
- Allow an explicit reprint of a stored file after a recorded observed-active start and a fresh idle check. Bind the review to the previous attempt and consume it at most once.
- Keep ambiguous, interrupted and incomplete starts blocked, including records carried forward from the current state format. Preserve existing upload provenance and start reservations.
- Expose safe attempt references in text and JSON and document the review flow in installed help, shell completion and usage examples.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `reviewed-job-submission` gains attempt identity, deliberate reprint review and execution, and backward-compatible handling of existing reservations.
- `cli-interface` gains reprint workflow guidance in help, completion and installed documentation.

## Impact

This affects `print plan`, `print start`, private device state, and installed interface checks. Qualification remains limited to the current Kobra X evidence. See the [roadmap](../../../../ROADMAP.md) and [history investigation](../2026-11-22-investigate-printer-job-history/verification.md). Job history commands, cloud history, and printer lifecycle controls belong to separate changes.
