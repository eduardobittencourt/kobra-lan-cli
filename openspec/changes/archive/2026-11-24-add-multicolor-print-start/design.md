# Design

## Context

See [proposal.md](proposal.md) for motivation and scope.

Currently:
- `kobra_lan/filaments.py` already parses all `; paint_info = [...]` lines, `T<n>` tool indices, and `multiColorBox / getInfo` onboard four-slot box responses (`id == -1`, slots `0..3`), returning `filaments` (ordered by `paint_index`), `raw_paint_colors`, `tool_indices`, `multicolor`, and `single_filament_start_compatible`.
- `kobra_lan/start.py` (`build_plan`) accepts only a single `slot` (`1..4`), rejects any G-code with `single_filament_start_compatible == False`, constructs `payload["ams_settings"]["ams_box_mapping"]` with one hardcoded `paint_index: 0` entry, and returns scalar `selected_slot`. `PLAN_FIELDS` hashes `("file_sha256", "device_digest", "model", "firmware", "payload")`.
- `kobra_lan/cli.py` requires `--slot <1..4>` on both `print plan` and `print start`.
- `kobra_lan/jobs.py` (`_extract_slot_and_material`) inspects `payload["ams_settings"]["ams_box_mapping"]` only when `len(mapping) == 1` to populate scalar `selected_slot` and `material_type` on `jobs info` (`jobs list` uses a compact summary without slot/material fields).
- `kobra_lan/completions.py` derives bash/zsh/fish completions directly from `argparse` action metadata.
- This change is stacked on branch `feat/stored-file-deletion` (`45eb2a7`) and adds no new Python modules, keeping packaging module allowlists (`scripts/check_python.py`, `scripts/build_deb.py`) unchanged while updating installed CLI help/completion/error probes in `scripts/check_python.py` and `scripts/accept_deb.py`.

## Goals / Non-Goals

**Goals:**
- Establish one canonical, AI-ergonomic CLI flag (`--slot-map PAINT_INDEX=SLOT`) and one canonical structured output schema (`slot_mapping`) across `print plan`, `print start`, and `jobs info` without carrying duplicate legacy flags (`--slot`) or redundant scalar fields (`selected_slot`, `material_type`) during 0.x.
- Support arbitrary contiguous or non-contiguous `paint_index` sets, multi-object or multi-layer multicolor G-codes, single-filament `paint_index: 0` and non-zero `paint_index` G-codes, mixed-material G-codes (e.g., `PLA` + `PETG`), and mapping multiple `paint_index` entries onto one physical slot.
- Preserve 100% in-place compatibility with existing on-disk receipts, attempt markers, `--reprint-from` chains, and `plan_sha256` digests for `paint_index: 0` starts (which falls out naturally from `PLAN_FIELDS` and `payload.ams_settings.ams_box_mapping`).
- Keep `hardware_start_validated: false` for multicolor and non-zero `paint_index` starts until verified on live Kobra X hardware.

**Non-Goals:**
- Preserving `--slot` as a parallel alias or preserving redundant scalar `selected_slot` / `material_type` output fields.
- Changing `gcode inspect` output (keeping existing fields including `single_filament_start_compatible` untouched).
- External ACE Pro or multi-box filament units (`id != -1` or `len(boxes) != 1`).
- Automatic color-matching, heuristic slot selection, G-code modification, or mutating onboard slot metadata.

## Decisions

### 1. Single canonical repeatable `--slot-map PAINT_INDEX=SLOT` (removing `--slot`)
- **Choice:** Replace `--slot` on `print plan` and `print start` with a single required repeatable option:
  - `--slot-map PAINT_INDEX=SLOT` (`action="append"`, `required=True`, `type=slot_map_entry`, `metavar="PAINT_INDEX=SLOT"`).
- **Rationale:**
  - Because the CLI is pre-1.0 and primarily driven by AI agents, having one unambiguous canonical interface (`--slot-map 0=1` for single color, `--slot-map 0=1 --slot-map 2=4` for multicolor, `--slot-map 0=1 --slot-map 1=1` for shared spool) eliminates dual-flag branching, mutually-exclusive error cases, and legacy surface area before launch.
  - AI agents copy integer `paint_index` directly from `gcode inspect --json` to the left of `=` and integer `slot` (`1..4`) directly from `slots list --json` to the right of `=` with zero off-by-one conversion and zero JSON shell-escaping.
- **Alternatives considered:**
  - *Keep `--slot` alongside `--slot-map`*: adds a mutually exclusive argument group, dual normalization paths, and extra docs/tests just to retain a pre-1.0 shortcut.
  - *JSON string flag (`--slot-map '{"0":1}'`)*: brittle shell quoting and harder to sanitize safely.
  - *1-based extruder index (`1=1`)*: contradicts `gcode inspect`'s `paint_index` field and creates an off-by-one trap.

### 2. Strict CLI argument validation before target resolution
- **Choice:**
  - Parse each `--slot-map` token in `kobra_lan/cli.py` via `slot_map_entry`: strict ASCII regex `^([0-9]+)=([1-4])$` (rejecting signs, whitespace, non-ASCII digits, slots outside `1..4`, or arbitrary strings), returning `(int(paint_index), int(slot))`. Invalid tokens raise `argparse.ArgumentTypeError`, which `Parser.error()` turns into a sanitized `ArgumentFailure` (exit 2, `invalid_arguments`) that never echoes raw input.
  - Convert the parsed pairs into a `dict` in `main()` before `Registry()` / network access, rejecting duplicate `paint_index` keys with `ArgumentFailure` (exit 2, `invalid_arguments`) while allowing duplicate physical `slot` values.
  - Passing removed `--slot` fails cleanly in `Parser.error()` with exit 2 (`invalid_arguments`) and contextual guidance pointing to `--help`.
- **Rationale:** Preserves the project's pre-network validation and anti-echo sanitization contract (including for hostile token-bearing URLs).

### 3. Single `slot_map` path in `kobra_lan/start.py` (`build_plan` and `start`)
- **Choice:**
  - Replace the `slot` parameter on `build_plan(config, client, path, name, slot_map, auto_leveling, vibration, flow)` and `start(config, path, name, slot_map, auto_leveling, vibration, flow, state_dir, execute=False, expected_plan=None, reprint_from=None)` with `slot_map` (`dict[int, int]`).
  - Validate `slot_map` is a non-empty `dict` of `int >= 0` → `int in 1..4` (using strict `type(...) is int` so booleans are rejected).
  - Validate `paint_info_present` and verify `set(filament_info["tool_indices"]) <= declared_paint_indices` so no undeclared `T<n>` tool command can bypass mapping.
  - Require exact coverage: `set(slot_map) == declared_paint_indices` (no missing declared `paint_index` and no extra undeclared `paint_index`).
  - Allow repeated physical `slot` values across multiple `paint_index` keys.
  - Build `ams_box_mapping` and `slot_mapping` in ascending `paint_index` order (`for paint_index in sorted(slot_map):`), validating for every entry that:
    - `selected["status"] == 5` and `selected["available_for_start"]` (loaded with non-empty printable material and valid color),
    - `slot_material[0].upper() == filament["material_type"].upper()` (base material family match: `"PLA High Speed"` matches `"PLA"`, `"PETG"` never matches `"PLA"`),
    - raw slot color passes `validate_color_channels`, padding 3-channel RGB to `[R, G, B, 255]` and preserving 4-channel RGBA.
- **Rationale:**
  - Eliminates dual single/multi code paths in `start.py`.
  - Sorting by `paint_index` makes `payload` and `plan_sha256` deterministic regardless of `--slot-map` argument order.
  - For single-filament `paint_index: 0` (`--slot-map 0=N`), `payload` and `plan_sha256` remain byte-for-byte identical to the previous `--slot N` implementation, keeping existing on-disk receipts and `--reprint-from` chains valid with zero migration code.

### 4. Structured `slot_mapping` output and conservative hardware qualification
- **Choice:**
  - Keep `PLAN_FIELDS = ("file_sha256", "device_digest", "model", "firmware", "payload")` unchanged.
  - Replace `selected_slot` on `build_plan` / `start` results and persisted receipts with:
    - `multicolor`: `bool` (`len(ams_box_mapping) > 1`).
    - `slot_mapping`: ordered list by `paint_index` of `{paint_index, slot, ams_index, gcode_material_type, gcode_color_hex, slot_material_type, slot_color_hex}`.
  - Compute `hardware_start_validated`:
    - `True` ONLY when `len(slot_map) == 1`, `0 in slot_map`, `slot_map[0] in (1, 2, 4)`, `ams_box_mapping[0]["material_type"] == "PLA High Speed"`, and `auto_leveling and not vibration and not flow`.
    - `False` for all multicolor starts and all non-zero `paint_index` single-filament starts.
- **Rationale:** One uniform representation for both single- and multi-color plans/receipts, while keeping hardware qualification claims strictly honest until live Kobra X FW 2.0.2.2 testing covers multicolor.

### 5. Offline job history reconstruction (`kobra_lan/jobs.py`)
- **Choice:**
  - Replace `_extract_slot_and_material` and scalar `selected_slot` / `material_type` on start records (`jobs info`) with `_extract_slot_mapping(receipt)` returning sanitized `slot_mapping` (or `None` when absent/malformed/unreadable):
    - Reads `payload.ams_settings.ams_box_mapping` (working identically for legacy file-keyed receipts, current single-filament receipts, and new multicolor receipts without touching any file on disk).
    - Requires a non-empty list of dicts where every entry has `type(paint_index) is int and paint_index >= 0` and `type(ams_index) is int and 0 <= ams_index <= 3` with no duplicate `paint_index`.
    - Emits entries ordered by `paint_index`: `{paint_index, slot, ams_index, material_type, gcode_color_hex, slot_color_hex}` (using `_safe_short_text` for `material_type` and `normalize_color` from `kobra_lan/filaments.py` for optional hex colors).
  - Leave `jobs list`'s `_summarize` compact summary unchanged.
- **Rationale:** Removes scalar/list duplication in `jobs info` while preserving full in-place readability of existing legacy receipts on disk.

## Risks / Trade-offs

- **0.x breaking CLI/JSON change** → Document clearly in `README.md`, `ROADMAP.md`, and `docs/usage.md` (consistent with the repository's 0.x experimental policy). On-disk receipts, attempt markers, and `--reprint-from` remain fully compatible in place.
- **Unverified Kobra X FW 2.0.2.2 multicolor wire edge cases** (non-contiguous `paint_index` like `[1, 3]`, or shared `ams_index` across multiple `paint_index` entries) → Keep `hardware_start_validated: false` for multicolor and non-zero `paint_index` plans until verified in a separate live hardware session.
