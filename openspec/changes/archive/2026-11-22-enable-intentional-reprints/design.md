# Design

## Context

`start.py` uses the verified upload receipt for provenance and calls the shared reservation helper with the G-code hash. The helper creates a durable marker before the first publish. The start receipt can record reservation, acknowledgement, observed activity or uncertainty. The [hardware observations](../2026-11-21-add-print-watch/verification.md) found a firmware task ID of `-1` and an empty last-project record after an operator-confirmed finish.

## Goals / Non-Goals

**Goals:** Preserve the existing first-start workflow and duplicate protection. Support a separately reviewed second run of the same stored file and capture enough local evidence to support a future history view.

**Non-Goals:** Job history commands, terminal classification, manual recovery for unresolved starts, and changes to the firmware request or supported hardware combinations.

## Decisions

### Bind the review to one predecessor

Add `--reprint-from PREVIOUS_ATTEMPT_ID` to `print plan` and `print start`. Ordinary planning retains its current digest and returns the latest local attempt ID and available start status as separate fields. The reprint digest covers the rebuilt execution plan and the predecessor ID under a distinct review scope. Execution requires that review, the explicit predecessor and `--execute`. Choosing the predecessor makes the reviewed intent single-use even if a caller repeats it after the printer is idle again. A boolean reprint flag would leave successive invocations indistinguishable when they use the same plan.

### Keep a durable chain rooted in the existing guard

Use a deterministic local ID for the first attempt derived from the device digest and file SHA-256. Assign each successor a deterministic ID derived from its predecessor with a separate hash domain. Use the existing file-keyed marker and receipt as the root and an attempt-keyed area for new successors. Each successor stores its predecessor, file, device, review and start evidence. The chain is reconstructed from reservations. An incomplete successor registration becomes the current unresolved attempt, so recovery cannot fall back to a previously eligible predecessor. A random ID alone would need a second durable mechanism to prevent independently generated siblings.

Reuse the existing private atomic-write and directory-lease primitives where applicable. An exclusive per-device start lease in the selected state directory covers the execution-side state check, final idle query, reservation, one publish and bounded observation. Acquire it before printer access for executing starts. Check the predecessor under that lease, validate state directory identity, and persist the exclusive reservation before publishing. A conflicting lease or an unverified state directory causes refusal. Preserve evidence after interruptions and write failures, including reservations for which the process could not finish the receipt.

### Require observed activity and fresh idle for eligibility

The immediate predecessor must have matching durable state and a `start_observed_active` receipt. A reservation, a bare acknowledgement or an uncertain receipt keeps that device/file blocked, even when the printer currently reports idle. The reprint also needs verified upload provenance, a fresh review and a fresh final idle report from the pinned session. The CLI records these facts as start evidence and leaves the earlier run's terminal outcome unclassified. Requiring a firmware terminal record would make the feature unavailable on the qualified evidence. Accepting idle after an ambiguous start would let a repeated invocation resend it without evidence of activity.

### Preserve the CLI contract

Keep existing ordinary command syntax, execution-hash behavior, JSON envelope, exit classes and receipt result fields. Add safe `attempt_id` and, where relevant, `previous_attempt_id` and available start status. A partial result after reservation can include the safe reference and evidence when known. Help and completion expose the flag and omit dynamic attempt lookup. `print watch` keeps its read-only behavior and existing outcome rules.

## Risks / Trade-offs

- A power loss after reservation can leave a blocked attempt even if no publish occurred. Preserve the reservation and report the evidence available.
- Firmware telemetry lacks a reliable per-run terminal identity. A prior activity observation and a fresh idle report establish reprint eligibility while leaving completion and quality unknown.
- A directory lease coordinates cooperating CLI invocations that share the state directory. Other clients, older binaries and separate state directories have their own coordination limits.

## Migration Plan

Interpret legacy markers and receipts lazily in their original locations. Derive a stable root ID for each legacy device/file reservation. Require a matching, well-formed observed-active receipt for eligibility and refuse reprint when evidence is incomplete or inconsistent. Keep all original files and permissions and append new-format successor records only during an authorized start. A downgrade retains the legacy file guard for ordinary starts and cannot offer reprints or read the newer successors. Use matching synthetic legacy fixtures to validate both access through another profile and a custom `--state-dir`.
