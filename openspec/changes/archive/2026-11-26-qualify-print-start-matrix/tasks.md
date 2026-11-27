# Tasks

## 1. Prepare disposable test G-code fixtures and isolated state directory

- [x] 1.1 Coordinate explicit operator authorization, schedule, and available loaded filament materials on Kobra X (`20030` / firmware `2.0.2.2`), verify idle state and loaded onboard slots with read-only `./kobra-lan --json doctor`, `./kobra-lan --json status`, and `./kobra-lan --json slots list`, and create a `0700` isolated workspace under `<isolated-workspace>/` (preserving all production profiles and `--state-dir` markers); verify JSON outputs record qualified idle state and loaded slots.
- [x] 1.2 Generate tiny (~1–2 g) single-color, 2-color (`paint_index` `[0, 1]`), sparse 2-color (`[0, 2]`), and non-zero single-filament (`[2]`) Kobra X test chips sliced with `AnycubicSlicerNext` CLI under `<isolated-workspace>/`, and verify each file offline with `./kobra-lan --json gcode inspect <file>` confirming valid `; paint_info =`, `tool_indices`, and `sha256` before any upload.

## 2. Live Kobra X single-filament slot 3 and preparation-flag qualification

- [x] 2.1 Execute Run A (single-filament onboard slot 3: `--slot-map 0=3`, `PLA High Speed`, `--auto-leveling on --vibration-compensation off --flow-calibration off`) via reviewed `files upload`, `print plan`, `print start --execute`, and `status`/`print watch` using the isolated `--state-dir`; confirm `start_observed_active` and operator-confirmed physical print completion from slot 3, saving sanitized JSON logs under `<isolated-workspace>/`.
- [x] 2.2 Execute Runs B, C, and D (`--slot-map 0=1`, `PLA High Speed`) covering alternative preparation-flag tuples `(auto=off, vib=off, flow=off)`, `(auto=off, vib=on, flow=off)`, and `(auto=off, vib=off, flow=on)` via reviewed `print plan` / `print start --execute`; confirm observed preparation phases, `start_observed_active`, and operator-confirmed physical completion for each run, saving sanitized logs.

## 3. Live Kobra X non-identity multicolor, sparse, non-zero, shared-slot, and optional material qualification

- [x] 3.1 Execute Run E (2-color cross-remapped subset: `--slot-map 0=2 --slot-map 1=1`, `PLA High Speed`, baseline prep flags) and Run F (2-color sparse indices: `--slot-map 0=1 --slot-map 2=3`, `PLA High Speed`, baseline prep flags; adapted from `2=4` because slot 4 held `PETG` for Run I); confirm `start_observed_active` and operator-confirmed physical color/slot fidelity on both chips.
- [x] 3.2 Execute Run G (single-filament non-zero `paint_index`: `--slot-map 2=3`, `PLA High Speed`, baseline prep flags) and Run H (shared physical slot: `--slot-map 0=1 --slot-map 1=1`, `PLA High Speed`, baseline prep flags); confirm `start_observed_active` and operator-confirmed physical behavior on both chips (recording any firmware rejection or anomalous tool-change behavior on Run H instead of promoting it).
- [x] 3.3 If the operator has additional non-`PLA High Speed` materials available and authorized (Run I), execute one tiny reviewed print per extra material with matching Next-sliced G-code and record sanitized results; otherwise explicitly document that non-`PLA High Speed` materials remain untested (`hardware_start_validated: false`). Clean up disposable uploaded test `.gcode` files on the idle printer with `files delete --execute` if requested by the operator.

## 4. Update centralized qualification rules, tests, and documentation

- [x] 4.1 Update `StartHardwareEvidence` and `is_start_hardware_validated` in `kobra_lan/qualification.py` strictly to match the exact slot-mapping classes, preparation-flag tuples, and materials confirmed in Groups 2–3 (and add a targeted refusal guard in `kobra_lan/start.py` only if live testing uncovered a firmware-rejected pattern such as shared slots), and update `tests/test_qualification.py`, `tests/test_start.py`, and `tests/test_cli.py`; verify with `uv run --locked python -m unittest tests.test_qualification tests.test_start tests.test_cli -v`.
- [x] 4.2 Record sanitized live hardware evidence and updated qualification boundaries across `docs/usage.md`, `docs/compatibility.md`, `README.md`, `ROADMAP.md` (marking Milestone 3 complete with explicit firmware `2.0.2.2` and untested-material boundaries), and `CHANGELOG.md` (`Unreleased`); verify documentation consistency and relative Markdown link checks via unit tests.

## 5. Final offline validation gates

- [x] 5.1 Run `uv run --locked python -m unittest discover -s tests -v && uv run --locked ruff check kobra_lan scripts tests && sh -n kobra-lan`, confirming every test and lint gate passes with zero failures.
- [x] 5.2 Run `openspec validate qualify-print-start-matrix` and inspect `git status` and `git diff` to verify zero real configs, PEMs, tokens, or private state files were staged or modified.

## Workflow follow-up

- Sync delta specs and archive `qualify-print-start-matrix` after review requirements are satisfied.
- Open a PR (targeting `feat/complete-independent-onboarding` until PR #31 merges, or `main` after PR #31 merges) with sanitized hardware evidence and verify CI checks pass.
