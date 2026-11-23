# Proposal

## Why

The Kobra X firmware `2.0.2.2` exposes no attributable completed-run history over LAN, leaving owners without a unified way to review past print starts, check which local attempt ID is eligible for `--reprint-from`, inspect incomplete or uncertain reservations, or retain records of active jobs watched from other clients. Now that durable per-attempt start identities and read-only `print watch` exist, exposing local job history backed by receipts and persisted observations completes the local visibility layer for Milestone 3 without fabricating printer-side history.

## What Changes

- Add offline, read-only `jobs list` and `jobs info <record-id>` commands scoped to the selected printer and `--state-dir`, emitting the shared text and root `--json` version-1 envelope with no network access and no state writes.
- Reconstruct CLI start attempt history in place from existing legacy and current start markers/receipts and correlate verified upload provenance, accurately surfacing reprint chains, local reprint eligibility, incomplete or unreadable records, and unclassified terminal outcomes.
- Persist sanitized local watch observation records in a separate private area under `--state-dir` whenever `print watch` observes an active job, leaving printer settings, credentials, profiles, upload receipts, start receipts, and attempt markers untouched.
- Represent watched jobs (including prints initiated by other clients) as unattributed local observation records in `jobs list` and `jobs info`, and explicitly report local-only coverage boundaries.
- Expose `jobs list` and `jobs info` in installed help, offline bash/zsh/fish shell completion, and English documentation (`README.md`, `docs/usage.md`, `ROADMAP.md`, and `debian/kobra-lan.1`).

## Capabilities

### New Capabilities
- `job-history`: Offline inspection of local printer job history (`jobs list` and `jobs info`) backed by start receipts/markers, upload provenance, and persisted watch observations, with explicit representation of incomplete records, unattributed other-client observations, and unclassified terminal outcomes.

### Modified Capabilities
- `print-observation`: Persist a sanitized private local observation record under `--state-dir` when `print watch` observes an active job (including jobs started by other clients), while continuing to issue only read-only printer queries and leaving profiles, credentials, upload/start receipts, and attempt markers untouched.
- `cli-interface`: Add `jobs list|info` to the canonical command tree, offline shell completions, installed help, and documentation.

## Impact

- New history module under `kobra_lan/` (e.g., `kobra_lan/jobs.py`), updates to `kobra_lan/watch.py`, `kobra_lan/cli.py`, and shared read-only state helpers in `kobra_lan/start.py`.
- Adds private per-device observation storage under `<state-dir>/observations/<device-prefix>/` written only after `print watch` observes an active job; existing profile, upload, and start state schemas and permissions remain unchanged.
- Updates offline tests (`tests/test_cli.py`, `tests/test_watch.py`, `tests/test_completions.py`, and new `tests/test_jobs.py`), installed docs (`README.md`, `docs/usage.md`, `ROADMAP.md`, `debian/kobra-lan.1`), and package/acceptance verification for the updated CLI interface.
- Direct LAN history queries, cloud history integration, manual marker recovery, and print lifecycle controls (`pause`/`resume`/`cancel`) remain out of scope.
