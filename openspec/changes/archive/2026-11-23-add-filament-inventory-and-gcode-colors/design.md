# Design

## Context

See [proposal.md](proposal.md) for motivation and scope.

Currently:
- `kobra_lan/mqtt.py` already allows read-only `("multiColorBox", "getInfo")` in `MQTT.query`.
- `kobra_lan/start.py` (`build_plan`) queries `multiColorBox / getInfo` and parses `; paint_info =` and `T<n>` inline, hard-rejecting any file with `len(paints) != 1`, `paint_index != 0`, or tools other than `T0`.
- `kobra_lan/upload.py` (`describe`) backs both `gcode inspect` and `files upload`, extracting only `sha256`, `md5`, `size_bytes`, `remote_filename`, `layer_count`, and `slicer_version`.
- Offline tests using real `AnycubicSlicerNext 2.0.0.6` Kobra X slicing (two separate colored objects, non-contiguous filament IDs `2,4`, single object on filament ID `3`, assembled multi-layer object, and mixed PLA/PETG) confirmed four concrete slicer behaviors:
  1. `; paint_info = [...]` is emitted **twice** per file (in `HEADER_BLOCK` near line 10 and again in the trailing config block).
  2. `paint_index` is 0-based and **can be non-contiguous** (`[1, 3]`, `[0, 2]`, or even single-filament `[2]`), matching the `T<n>` tool numbers in the G-code.
  3. Each `paint_info` entry carries `paint_index`, `material_type` (base material family, e.g., `"PLA"` or `"PETG"`), and 3-channel RGB `paint_color` (e.g., `[0, 255, 0]`).
  4. Trailing summary comments include `; filament used [g] = 0.00, 1.47, 0.00, 1.85` (0-based by extruder/paint index) and `; total filament used [g] = 3.32`.

## Goals / Non-Goals

**Goals:**
- Centralize G-code filament/color parsing and onboard `multiColorBox / getInfo` parsing/sanitization in one new module (`kobra_lan/filaments.py`) so `gcode inspect`, `slots list`, and `print plan`/`print start` share a single validated interpretation.
- Expose a clean, read-only `slots list` command that works on idle or printing qualified Kobra X printers over one pinned MQTT session without writing state.
- Enrich `gcode inspect` with accurate single- and multi-color metadata while keeping all existing fields intact and never breaking `files upload` on valid multicolor G-codes or legacy synthetic fixtures without `; paint_info =`.
- Keep packaging allowlists and installed CLI/completion probes in sync with the new module and command.

**Non-Goals:**
- Multicolor `print plan` / `print start` slot mapping (deferred to the next change once this visibility layer and hardware protocol checks are in place).
- External ACE Pro / multi-box support (`id != -1` or `len(boxes) != 1`).
- Mutating filament/slot operations (editing slot color/material, feeding/retracting).
- Adding new fields to `status` output (keeping `status` fast, single-query, and backward-compatible).

## Decisions

### 1. Dedicated `slots list` command group rather than overloading `status`
- **Choice:** Add `slots list` under a new `slots` command group in `kobra_lan/cli.py`.
- **Rationale:** Matches the canonical `<resource> list` convention (`printer list`, `files list`, `jobs list`), avoids adding a second MQTT round-trip (`multiColorBox / getInfo`) to every `status` call, keeps `status`'s JSON contract untouched, and leaves a clean namespace for future slot-scoped subcommands (e.g., `slots info` or external ACE boxes) if hardware later justifies them.
- **Alternatives considered:**
  - *Embed slots inside `status`*: adds latency and an extra failure mode to `status`, and blurs the boundary between core printer telemetry (`info`) and multicolor-box queries (`multiColorBox`).
  - *Bare top-level `slots` command*: breaks the project's resource-group convention established in `cli-interface` (which explicitly rejected bare `files`).

### 2. Dedicated `kobra_lan/filaments.py` module shared across inspect, slots, and start
- **Choice:** Create `kobra_lan/filaments.py` containing:
  - `normalize_color(color)`: validates 3- or 4-int RGB/RGBA values in `0..255` (using strict `type(x) is int`, rejecting booleans) and returns `(rgb3, hex_str)` (e.g., `[0, 255, 0]`, `"#00FF00"`).
  - `inspect_gcode_filaments(data)`: scans all `; paint_info = ...` lines, validates JSON and per-entry fields (`paint_index` int `>= 0` with no duplicates inside a declaration, non-empty printable ASCII `material_type`, valid RGB/RGBA `paint_color`), verifies that repeated `; paint_info =` lines in the file agree after sorting by `paint_index`, extracts sorted unique `T<n>` tool indices, parses optional `; filament used [g] = ...` and `; total filament used [g] = ...`, and computes `paint_info_present`, `filaments`, `filament_count`, `multicolor`, `tool_indices`, `total_filament_used_g`, and `single_filament_start_compatible`.
  - `parse_onboard_box(boxes)` / `list_slots(config)`: validates qualified fresh `info` (`Anycubic Kobra X`, firmware `2.0.2.2`), queries `multiColorBox / getInfo` over the same `MQTT` session, validates `len(boxes) == 1`, `boxes[0].get("id") == -1`, and four unique slot indices `0..3`, and returns sanitized slot inventory sorted by `ams_index`.
- **Rationale:** Eliminates duplicate `paint_info`, color, and `multiColorBox` validation logic between `upload.py`, `start.py`, and the new `slots list` command, while preparing cleanly for the next multicolor `print plan` / `print start` change.
- **Packaging impact:** Add `"filaments"` to module allowlists in `scripts/check_python.py` and `scripts/build_deb.py`, and add `slots` help/completion probes to `scripts/check_python.py` and `scripts/accept_deb.py`.

### 3. Handling `slots list` status codes and empty slots conservatively
- **Choice:** Represent each onboard slot (`slot` `1..4`, `ams_index` `0..3`) with:
  - `status`: raw integer from firmware (must be `type(status) is int`).
  - `status_label`: `"loaded"` if `status == 5`, `"empty"` if `status == 0`, else `"other"`.
  - `material_type`: sanitized printable string when non-empty, else `None`.
  - `color_rgb` / `color_hex`: normalized `[R, G, B]` and `"#RRGGBB"` when valid 3- or 4-channel RGB/RGBA data is present, else `None`.
  - `available_for_start`: `True` only when `status == 5`, `material_type` is non-empty, and `color_rgb` is valid; `False` otherwise.
  - Schema refusal: fail with `ProtocolError` (exit 2) only on structural violations (missing/duplicate slot indices `0..3`, non-int `status`, non-list non-empty `color`, or non-onboard/multi-box responses). Empty or transient slots (`status != 5`) that omit `type`/`color` or report empty values normalize cleanly to `None` with `available_for_start: False`. `start.py` continues to enforce strict `status == 5`, valid material, and valid color when planning a start.
- **Rationale:** Prevents `slots list` from crashing just because one slot is empty (`status == 0` with `type: ""` or `color: []`) or in an unobserved transient state, while never claiming an incomplete or unknown-status slot is ready for `print start`.

### 4. Backward-compatible `gcode inspect` and `files upload` behavior
- **Choice:** Keep `describe(path, remote_name)` in `kobra_lan/upload.py` returning all existing manifest keys unchanged for `files upload` receipts, and merge `inspect_gcode_filaments(data)` onto the manifest returned by `gcode inspect`. Also reuse `inspect_gcode_filaments(data)` inside `kobra_lan/start.py` (`build_plan`) so single-filament planning gains duplicate `; paint_info =` consistency checking while preserving its exact current `paint_index == 0` / `T0`-only guard.
- **Rationale:** Preserves existing upload receipt schemas byte-for-byte, keeps `files upload` working on valid single-color, multicolor, and minimal synthetic G-codes without `; paint_info =`, and avoids duplicating `paint_info` / `T<n>` parsing across `upload.py` and `start.py`.

### 5. Exact semantics of `multicolor` and `single_filament_start_compatible`
- `multicolor`: `True` when `len(filaments) > 1` or `len(tool_indices) > 1`, else `False`.
- `single_filament_start_compatible`: `True` only when `paint_info_present` is `True`, `len(filaments) == 1`, `filaments[0]["paint_index"] == 0`, and `set(tool_indices) <= {0}` (matching `start.py`'s exact current qualification guard).
- This accurately distinguishes:
  - Normal single-color (`paint_index: 0`, `T0` or no `T`): `multicolor: False`, `single_filament_start_compatible: True`.
  - Single-color on non-zero extruder (`paint_index: 2`, `T2`, as observed in `single_3`): `multicolor: False`, `single_filament_start_compatible: False`.
  - Two+ colors (layered or multi-object, contiguous or non-contiguous like `[1, 3]`): `multicolor: True`, `single_filament_start_compatible: False`.
  - Synthetic fixture without `paint_info`: `paint_info_present: False`, `filament_count: 0`, `filaments: []`, `single_filament_start_compatible: False`.

## Risks / Trade-offs

- **Unobserved firmware `multiColorBox / getInfo` empty-slot shapes** → Real firmware `2.0.2.2` might represent empty slots with `status: 0`, `type: ""`, `color: [0,0,0]` or `color: []` or omitted keys. Tolerating omitted/empty `type` and `color` when `status != 5` (normalizing to `None`) avoids brittle failures on empty slots; live read-only hardware check during or after implementation will confirm the exact empty-slot fields on Kobra X `2.0.2.2`.
- **Duplicate `; paint_info =` lines in large G-codes** → Scanning bytes with `re.finditer(rb'^; paint_info = (.*)$', data, re.M)` on files up to `MAX_FILE` (128 MiB) runs in milliseconds in C-backed regex and catches tampering or inconsistent metadata between header and footer.
- **Per-filament weight line formatting differences** → `; filament used [g] = ...` is optional in minimal or older G-codes; if absent or unparseable, `filament_used_g` and `total_filament_used_g` gracefully remain `None` rather than rejecting otherwise valid G-codes.
- **No external ACE hardware evidence** → Explicitly refusing `len(boxes) != 1` or `id != -1` with exit 2 (`validation_failed`) prevents silently misinterpreting external ACE box payloads before hardware evidence exists.
