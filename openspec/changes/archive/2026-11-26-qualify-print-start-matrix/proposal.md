# Proposal

## Why

After completing Milestone 1 (`feat/complete-independent-onboarding`) and retiring the non-printing Milestone 3 gaps (`files delete` local-state preservation and camera post-reboot cold-start in PR #30), the only remaining actionable Milestone 3 items on stock Kobra X model `20030` / firmware `2.0.2.2` are expanding live `print start` hardware qualification beyond `PLA High Speed` single-filament (`0 -> 1|2|4`) and 4-color contiguous 1:1 (`0..3 -> 1..4`) with `auto-leveling on` and vibration/flow calibration off. Closing these remaining print-start matrix cases in one coordinated hardware qualification session lets us complete Milestone 3 cleanly while preserving conservative, evidence-backed qualification boundaries for any untested materials or firmware-limited behaviors.

## What Changes

- Plan and execute an operator-authorized live Kobra X (`20030` / firmware `2.0.2.2`) qualification session using tiny `AnycubicSlicerNext`-sliced test prints and an isolated `--state-dir` (preserving all existing profiles, credentials, and production state markers) covering:
  - Single-filament onboard slot 3 (`0=3`) in `PLA High Speed` with baseline preparation flags (`auto-leveling on`, `vibration-compensation off`, `flow-calibration off`), completing single-filament coverage across all four onboard slots (`1..4`).
  - Alternative preparation-flag combinations on Kobra X: `auto-leveling off`, `vibration-compensation on`, and `flow-calibration on` (observing real printer preparation phases and physical completion).
  - Non-identity multicolor and non-zero `paint_index` mappings:
    - 2-color subset with cross-remapping (`paint_index != ams_index`, e.g., `0=2, 1=1`),
    - Sparse non-contiguous `paint_index` mapping (e.g., `0=1, 2=4`),
    - Single-filament non-zero `paint_index` mapping (e.g., `2=3` with `T2` only),
    - Shared physical slot mapping (e.g., `0=1, 1=1`), verifying whether firmware `2.0.2.2` prints cleanly without anomalous filament changes or requires a CLI guard/refusal.
  - Optional additional loaded materials (e.g., standard `PLA`, `PETG`, `TPU`) if physically available and authorized by the operator during the session; untested materials remain explicitly unqualified (`hardware_start_validated: false`).
- Update `kobra_lan/qualification.py` (`StartHardwareEvidence` and `is_start_hardware_validated`) strictly after live physical confirmation to reflect only the exact slot-mapping classes, preparation-flag combinations, and materials actually observed on Kobra X `20030` / firmware `2.0.2.2` (and add a guard in `kobra_lan/start.py` only if live testing uncovers a firmware failure or incompatibility, such as on shared slots).
- Update offline unit tests (`tests/test_qualification.py`, `tests/test_start.py`, `tests/test_cli.py`), `docs/compatibility.md`, `docs/usage.md`, `README.md`, `ROADMAP.md`, and `CHANGELOG.md` (`Unreleased`) with sanitized validation evidence and Milestone 3 completion status (retaining documented firmware `2.0.2.2` limits for `task_id`/`last_project` and `files download`, and deferring untested materials and external ACE units to Milestone 4).

Out of scope:
- New CLI commands, options, or breaking JSON/state contract changes.
- External ACE / ACE Pro units, other Anycubic printer models, other firmware versions, or non-Next slicers.
- Unobserved materials, unobserved preparation combinations, or weakening existing safety/trust/marker invariants.

## Capabilities

### New Capabilities
<!-- None: this change expands live hardware qualification evidence for existing print-start and qualification capabilities. -->

### Modified Capabilities
- `hardware-qualification`: Update centralized `hardware_start_validated` rules and `docs/compatibility.md` to reflect the newly hardware-observed Kobra X `20030` / `2.0.2.2` slot-mapping classes, preparation-flag combinations, and tested materials, while continuing to report `hardware_start_validated: false` for any unobserved material, preparation combination, firmware, or model.
- `reviewed-job-submission`: Update the `Evidence stays qualified` requirement (and any firmware-discovered mapping guard if shared slots or another pattern fails on stock firmware `2.0.2.2`) to match the newly observed `print plan` / `print start` hardware evidence.

## Impact

- **Code**: `kobra_lan/qualification.py` (update `StartHardwareEvidence` / `is_start_hardware_validated` strictly from observed live evidence); `kobra_lan/start.py` only if live testing reveals a firmware-rejected pattern requiring a refusal guard.
- **Tests**: `tests/test_qualification.py`, `tests/test_start.py`, `tests/test_cli.py` (and `tests/test_jobs.py` if receipt assertions touch `hardware_start_validated`).
- **Documentation & Specs**: `docs/compatibility.md`, `docs/usage.md`, `README.md`, `ROADMAP.md`, `CHANGELOG.md`, and delta specs under `openspec/changes/qualify-print-start-matrix/specs/`.
- **Hardware / Safety**: Requires an operator-authorized, schedule-agreed live printing session on Kobra X (`20030` / `2.0.2.2`) using tiny disposable test chips, an isolated `--state-dir` under `~/research/kobra-lan-cli/qualify-print-start-matrix/`, explicit reviewed upload/plan/start hashes per run, and zero modification of existing profiles, credentials, or production attempt markers.
