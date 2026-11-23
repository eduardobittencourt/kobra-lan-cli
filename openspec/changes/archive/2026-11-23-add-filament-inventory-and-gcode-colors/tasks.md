# Tasks

## 1. Shared Filament Parsing and Onboard Slot Inventory Module

- [x] 1.1 Create `kobra_lan/filaments.py` implementing `normalize_color`, `inspect_gcode_filaments` (all `; paint_info =` occurrences with agreement check, `T<n>` tool extraction, optional `; filament used [g]` / `; total filament used [g]`, `multicolor`, `single_filament_start_compatible`), `parse_onboard_box`, and `list_slots` (one pinned `MQTT` session checking fresh qualified `info` without requiring idle state, then querying `multiColorBox / getInfo`); verify with unit tests in `tests/test_filaments.py` covering single-color, multicolor, non-contiguous `paint_index` (`[1, 3]`, `[2]`), mixed materials (`PLA`/`PETG`), repeated/conflicting/malformed `paint_info`, absent `paint_info`, mixed loaded/empty/other slots, busy printers, unqualified firmware, external/multi-box rejection, and network/TLS errors.
- [x] 1.2 Add `"filaments"` to the module allowlists in `scripts/check_python.py` and `scripts/build_deb.py` so offline packaging allowlist checks stay in sync; verify `scripts/check_python.py` and `scripts/build_deb.py` compile cleanly with `python3 -m py_compile scripts/check_python.py scripts/build_deb.py scripts/accept_deb.py`.

## 2. Multicolor-Aware `gcode inspect` and Shared `print plan` Validation

- [x] 2.1 Wire `inspect_gcode_filaments` into `gcode inspect` in `kobra_lan/cli.py` (preserving `describe()` upload receipt schema and byte immutability) and into `build_plan` in `kobra_lan/start.py` (preserving single-filament `paint_index == 0` / `T0`-only enforcement while validating repeated `paint_info` agreement); verify with unit tests in `tests/test_client.py` and `tests/test_start.py` confirming existing `gcode inspect` fields, multicolor inspection, absent `paint_info` upload compatibility, and conflicting `paint_info` rejection.

## 3. Read-Only `slots list` CLI, Completions, Packaging Probes, and Documentation

- [x] 3.1 Add the `slots` command group with `slots list` in `kobra_lan/cli.py` (using standard `--printer`/`--config`/default selection, refusing bare `slots` with exit 2, emitting text and root `--json` schema version 1 without state writes); verify with unit tests in `tests/test_cli.py`, `tests/test_filaments.py`, and `tests/test_completions.py` covering `--help`, bare `slots` refusal, text/JSON parity, and offline bash/zsh/fish completion for `slots` and `list`.
- [x] 3.2 Update installed CLI/completion probes in `scripts/check_python.py` and `scripts/accept_deb.py` to assert `slots --help`, `slots list --help`, and offline completion entries for `slots`/`list`; verify via `uv run --locked ruff check scripts`.
- [x] 3.3 Document `slots list` and the new `gcode inspect` filament/color fields in `README.md`, `docs/usage.md`, `ROADMAP.md`, and `debian/kobra-lan.1` (clearly stating that onboard four-slot inventory is read-only and multicolor `print start` / external ACE remain unqualified); verify all documented commands and flags match `kobra-lan --help`, `kobra-lan slots --help`, and `kobra-lan gcode inspect --help`.

## 4. Integrated Offline Verification

- [x] 4.1 Run the full offline validation suite (`uv run --locked python -m unittest discover -s tests -v`, `uv run --locked ruff check kobra_lan scripts tests`, `sh -n kobra-lan`, and `openspec validate add-filament-inventory-and-gcode-colors --strict`) and confirm all checks pass without touching real hardware or private state.

## Workflow follow-up

- Optionally run an operator-authorized read-only `slots list` check against the Kobra X (`20030` / firmware `2.0.2.2`) to record hardware observation of empty vs loaded onboard slots before starting the multicolor `print plan`/`print start` change.
- Archive the change (`openspec-archive-change`) after review and merge requirements are satisfied.
