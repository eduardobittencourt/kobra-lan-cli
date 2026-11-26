# Proposal

## Why

Two lightweight Milestone 3 qualification items remain open on Kobra X model `20030` / firmware `2.0.2.2` after `v0.6.0`:
1. `files delete` already has live wire-removal evidence (`deleteBatch` `success`/200 and post-delete `files list` absence from 2026-11-23), but still reports `hardware_delete_validated: false` solely because byte-for-byte preservation of local receipts, `.attempt` markers, and watch observations was verified only offline.
2. Camera operations (`camera status`, `camera snapshot`, `camera pipe`) were hardware-validated while the printer already had an active capture state, leaving post-reboot cold-start behavior without prior capture unverified on live firmware `2.0.2.2`.

Closing both items in one focused live verification session (requiring no physical printing) retires the remaining non-printing Milestone 3 hardware gaps and aligns `kobra_lan/qualification.py`, tests, specs, and docs with observed hardware behavior.

## What Changes

- Perform an operator-authorized live Kobra X (`20030` / `2.0.2.2`) verification of `files delete <name> --execute` against a controlled test file with pre-existing local state (upload receipt/marker, canonical start receipt/marker, and/or watch observation under `--state-dir`), capturing cryptographic hashes and permissions of all local state files and directories before and after deletion to establish live byte-for-byte preservation alongside remote removal.
- Once live byte-for-byte preservation is observed, promote `KOBRA_X.delete_hardware_validated` from `False` to `True` in `kobra_lan/qualification.py`, so `files delete` and `files delete --help` report `hardware_delete_validated: true` for qualified Kobra X `20030` / `2.0.2.2` while keeping `false` for unqualified models or firmwares.
- Perform an operator-authorized post-reboot cold-start camera verification on Kobra X (`20030` / `2.0.2.2`) immediately after a clean printer reboot (before any app/slicer/CLI camera capture), verifying `camera status`, direct read-only probe (`--no-start-capture`), and automatic single-shot `video/startCapture` + `video/stopCapture` fallback in `camera pipe` and `camera snapshot`, confirming clean teardown and zero URL/token leakage.
- Fix any cold-start firmware nuance uncovered during live testing (with offline regression tests), or keep camera implementation unchanged if current read-only-first + fallback behavior passes cleanly.
- Update offline unit/CLI tests, `docs/compatibility.md`, `docs/usage.md`, `README.md`, `ROADMAP.md`, and `CHANGELOG.md` (`Unreleased`) to reflect the newly recorded hardware evidence and retire both Milestone 3 roadmap items.

Out of scope:
- Expanding `hardware_start_validated` (single-filament slot 3, non-identity multicolor mappings, non-`PLA High Speed` materials, or alternative preparation flags).
- Adding new printer commands, discovery, stored-file download, or external ACE support.
- Modifying private credentials, clearing existing `.attempt` markers, or operating hardware without explicit user authorization and an agreed test window.

## Capabilities

### New Capabilities

<!-- None: this change completes hardware qualification for existing capabilities. -->

### Modified Capabilities

- `hardware-qualification`: Promote `hardware_delete_validated` to `true` on qualified Kobra X `20030` / `2.0.2.2` once live byte-for-byte local state preservation is observed, while preserving `false` for unqualified models/firmwares, and reflect both live delete and cold-start camera observations in `docs/compatibility.md`.
- `stored-file-deletion`: Update `files delete` outcome reporting from literal `hardware_delete_validated: false` to centralized `hardware_delete_validated` (`true` on qualified Kobra X `20030` / `2.0.2.2`, `false` on unqualified targets) after live local-state preservation is verified.

## Impact

- Code: `kobra_lan/qualification.py` (`KOBRA_X.delete_hardware_validated = True` only after live hardware confirmation); `kobra_lan/camera.py` only if live cold-start testing reveals a firmware edge case.
- Tests: `tests/test_qualification.py`, `tests/test_delete_file.py`, `tests/test_cli.py`, and `tests/test_camera.py` (if cold-start regression tests are added).
- Documentation & Specs: `docs/compatibility.md`, `docs/usage.md`, `README.md`, `ROADMAP.md`, `CHANGELOG.md`, and delta sync to `openspec/specs/hardware-qualification/spec.md` and `openspec/specs/stored-file-deletion/spec.md`.
- Hardware / Safety: Requires one operator-authorized live session against the real Kobra X (`20030` / `2.0.2.2`), including a coordinated printer reboot for cold-start camera verification and an isolated/disposable `--state-dir` (or read-only hash check of real local state) plus a dedicated disposable test `.gcode` file for `files delete`, with zero printing and zero modification of existing credentials or production markers.
