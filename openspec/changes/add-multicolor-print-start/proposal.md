# Proposal

## Why

Kobra LAN CLI already supports offline multicolor G-code inspection (`gcode inspect`, reporting `paint_index`, `T<n>` tool indices, materials, and colors), byte-preserving upload (`files upload`), and read-only onboard four-slot inventory (`slots list`), but `print plan` and `print start` still accept only a single `--slot` for `paint_index: 0` files. Replacing `--slot` with a single canonical, AI-ergonomic `--slot-map PAINT_INDEX=SLOT` option and replacing scalar slot fields with `slot_mapping` completes the end-to-end multicolor and non-zero-extruder workflow on the Kobra X onboard four-slot box without accumulating duplicate legacy CLI flags or schemas during 0.x.

## What Changes

- **BREAKING**: Replace `--slot <1..4>` on `print plan` and `print start` with a single required repeatable `--slot-map PAINT_INDEX=SLOT` option that directly maps each 0-based `paint_index` from `gcode inspect` to a 1-based physical onboard slot (`1..4`) from `slots list` (for example `--slot-map 0=1` for single-filament `paint_index: 0`, `--slot-map 2=4` for single-filament non-zero `paint_index`, `--slot-map 0=1 --slot-map 2=4` for multicolor, or `--slot-map 0=1 --slot-map 1=1` to share one physical spool across multiple G-code colors).
- **BREAKING**: Replace scalar `selected_slot` (on `print plan`, `print start`, and `jobs info`) and scalar `material_type` (on `jobs info`) with structured, ordered `slot_mapping` entries as the single source of truth (alongside `multicolor` on `print plan`/`print start`).
- Allow multiple `paint_index` entries to map to the same physical slot when material families are compatible, while rejecting duplicate `paint_index` keys, missing or extra `paint_index` entries, undeclared `T<n>` tool indices, unloaded slots, or material-family mismatches.
- Emit a deterministic `paint_index`-ordered `ams_settings.ams_box_mapping` payload so `plan_sha256` is independent of `--slot-map` argument order and remains compatible with existing on-disk legacy/current start receipts and `--reprint-from` chains (`--slot-map 0=N` produces the same wire `payload` and `plan_sha256` as previous `--slot N`).
- Keep `hardware_start_validated: false` for multicolor or non-zero `paint_index` plans until verified on live Kobra X hardware; retain `hardware_start_validated: true` only for the already-observed single-filament `paint_index: 0` PLA High Speed case.
- Update offline `jobs info` to reconstruct sanitized `slot_mapping` from `payload.ams_settings.ams_box_mapping` for both legacy and new start receipts without modifying stored files, while keeping `jobs list`'s compact summary schema unchanged.
- Expose `--slot-map` (and remove `--slot`) in CLI help, offline bash/zsh/fish completion, packaging installation probes, and user documentation (`README.md`, `ROADMAP.md`, `docs/usage.md`). Leave `gcode inspect` unchanged.

## Capabilities

### New Capabilities

_(None — this change extends existing submission, CLI, and job-history capabilities.)_

### Modified Capabilities

- `reviewed-job-submission`: Replace `--slot` with repeatable required `--slot-map PAINT_INDEX=SLOT` on `print plan` and `print start` to support single-filament, non-zero `paint_index`, and multicolor G-codes (including sharing one physical slot across multiple `paint_index` entries); validate exact `paint_info`/`T<n>`/slot/material compatibility; emit deterministic `ams_box_mapping` payloads and structured `slot_mapping` + `multicolor` metadata (removing scalar `selected_slot`); preserve on-disk legacy receipt compatibility and `--reprint-from`; keep `hardware_start_validated: false` for unvalidated multicolor/non-zero plans.
- `cli-interface`: Replace `--slot` with repeatable required `--slot-map PAINT_INDEX=SLOT` on `print plan` and `print start`, reject `--slot` and malformed/duplicate `--slot-map` inputs with exit 2 (`invalid_arguments`) before target selection without echoing raw values, and expose `--slot-map` in help, docs, offline shell completion, and installed package probes.
- `job-history`: Replace scalar `selected_slot` and `material_type` on `jobs info` start records with sanitized `slot_mapping` reconstructed from `payload.ams_settings.ams_box_mapping` for legacy, single-filament, and multicolor start attempts without modifying stored files.

## Impact

- **Code**: `kobra_lan/cli.py`, `kobra_lan/start.py`, `kobra_lan/jobs.py` (no new modules; packaging module allowlists remain unchanged).
- **Tests**: Update existing `--slot` / `selected_slot` / `material_type` callers and add multicolor coverage in `tests/test_start.py`, `tests/test_cli.py`, `tests/test_profiles.py`, `tests/test_completions.py`, and `tests/test_jobs.py` (offline synthetic fixtures only; no live printer access).
- **Packaging probes**: `scripts/check_python.py`, `scripts/accept_deb.py` (help, completion, and hostile-argument sanitization probes for `--slot-map`).
- **Documentation**: `README.md`, `ROADMAP.md`, `docs/usage.md` (existing `kobra-x-slicing` skill references live `kobra-lan --help` / `docs/usage.md` and needs no edit).
- **Compatibility**: Intentional 0.x breaking CLI/JSON cleanup (`--slot` → `--slot-map`, scalar `selected_slot`/`material_type` → `slot_mapping`), while preserving 100% in-place compatibility with existing on-disk receipts, attempt markers, `plan_sha256` digests for `paint_index: 0`, and `--reprint-from` chains. External ACE units remain unqualified.
