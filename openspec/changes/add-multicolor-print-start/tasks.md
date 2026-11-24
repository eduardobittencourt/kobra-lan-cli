# Tasks

## 1. Multicolor & Non-Zero Paint-Index Start Planning (`kobra_lan/start.py`)

- [x] 1.1 Replace single `slot` with `slot_map` (`dict[int, int]`) in `build_plan` and `start` in `kobra_lan/start.py`, enforcing exact coverage of declared `paint_info` indices and `tool_indices <= declared_paint_indices`, allowing multiple `paint_index` entries to share one physical slot, validating per-entry slot loading (`status == 5`, `available_for_start`) and base material family compatibility, emitting ascending `paint_index`-ordered `ams_box_mapping`, replacing scalar `selected_slot` with structured `slot_mapping` + `multicolor`, and keeping `hardware_start_validated` true only for the observed single-filament `paint_index: 0` case. Verify by updating existing tests and adding new unit tests in `tests/test_start.py` covering single-filament `paint_index: 0`, single-filament non-zero `paint_index`, contiguous/non-contiguous multicolor plans, shared physical slot mapping, mixed `PLA`+`PETG` mapping, order-independent `plan_sha256`, undeclared `T<n>` tools, missing/extra `paint_index`, unloaded/mismatched slots, external box rejection, and `--reprint-from` chains (including legacy on-disk receipts).

## 2. CLI Argument Parsing, Help & Offline Completions (`kobra_lan/cli.py`)

- [x] 2.1 Replace `--slot` on `print plan` and `print start` in `kobra_lan/cli.py` with repeatable required `--slot-map PAINT_INDEX=SLOT` (`action="append"`, `required=True`), adding strict ASCII parsing (`slot_map_entry`), duplicate `paint_index` rejection before target/printer access, safe `Parser.error()` guidance without echoing raw input, and forwarding the `slot_map` dict to `start()`. Verify by updating existing `--slot` CLI tests and adding unit tests in `tests/test_cli.py`, `tests/test_profiles.py`, `tests/test_start.py`, and `tests/test_completions.py` covering removed `--slot`, missing/malformed/hostile `--slot-map` inputs, duplicate keys, JSON/text error envelopes, and bash/zsh/fish completion output exposing `--slot-map` (and omitting `--slot`) on both `print plan` and `print start`.

## 3. Offline Job History Slot-Mapping Reconstruction (`kobra_lan/jobs.py`)

- [x] 3.1 Replace scalar `selected_slot` and `material_type` on start records in `kobra_lan/jobs.py` with sanitized `slot_mapping` (`paint_index`, `slot`, `ams_index`, `material_type`, `gcode_color_hex`, `slot_color_hex`) ordered by `paint_index`, reconstructed from `payload.ams_settings.ams_box_mapping` for legacy, single-filament, and multicolor receipts (`None` for unreadable/missing-mapping records) while keeping `jobs list`'s compact summary unchanged. Verify by updating existing `selected_slot`/`material_type` assertions and adding multicolor/shared-slot/mixed-material/legacy-receipt tests in `tests/test_jobs.py` without modifying stored fixture files.

## 4. Packaging Probes & Documentation

- [x] 4.1 Update installed CLI probes in `scripts/check_python.py` and `scripts/accept_deb.py` to assert `--slot-map` help, bash/zsh/fish completion exposure (and absence of `--slot`), and sanitized hostile-input exit-2 handling on `print plan` and `print start`, and update `README.md`, `ROADMAP.md`, and `docs/usage.md` to replace `--slot` examples with `--slot-map`, document the AI-friendly multicolor workflow (`gcode inspect` → `slots list` → `files upload` → `print plan --slot-map` → `print start --slot-map`), note the 0.x removal of `--slot` and scalar `selected_slot`/`material_type`, and keep `hardware_start_validated: false` limits explicit. Verify via `uv run --locked ruff check kobra_lan scripts tests` and inspection of updated docs/probe assertions.

## 5. Offline Verification Gates

- [x] 5.1 Run full offline validation suite (`uv run --locked python -m unittest discover -s tests -v`, `uv run --locked ruff check kobra_lan scripts tests`, `sh -n kobra-lan`, and `openspec validate add-multicolor-print-start --strict`) and confirm all tests, lint checks, shell syntax checks, and spec validations pass with no live printer access.

## Workflow follow-up

- Optionally qualify multicolor `print start` on live Kobra X (model 20030 / firmware 2.0.2.2) in a separate hardware session and record observed results before changing `hardware_start_validated`.
- Archive the change with `openspec-archive-change` after implementation and review requirements are satisfied.
