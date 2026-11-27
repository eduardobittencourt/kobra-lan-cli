# Design

## Context

See `proposal.md` for motivation and scope. On Kobra X model `20030` / firmware `2.0.2.2`, `kobra_lan/qualification.py` currently hard-codes two `StartHardwareEvidence` entries:
1. Single-filament `0 -> 1|2|4` in `PLA High Speed` with `(auto_leveling=True, vibration_compensation=False, flow_calibration=False)`.
2. 4-color contiguous 1:1 `0=1, 1=2, 2=3, 3=4` in `PLA High Speed` with `(auto_leveling=True, vibration_compensation=False, flow_calibration=False)`.

All other onboard slot mappings (`0=3`, non-zero single `paint_index`, 2/3-color subsets, cross-remapped `paint_index != ams_index`, sparse indices, shared physical slots), alternative preparation flags (`auto-leveling off`, `vibration-compensation on`, `flow-calibration on`), and other loaded materials currently return `hardware_start_validated: false`.

## Goals / Non-Goals

**Goals:**
- Execute a compact, low-waste, operator-authorized live qualification matrix on Kobra X (`20030` / `2.0.2.2`) using tiny `AnycubicSlicerNext` CLI-sliced chips (via the `kobra-x-slicing` workflow) and an isolated `--state-dir` under `<isolated-workspace>/`.
- Record concrete physical and telemetry evidence per run before promoting any `hardware_start_validated` predicate.
- Keep `kobra_lan/qualification.py` expressive enough to represent observed mapping classes, observed preparation-flag tuples, and observed materials cleanly without over-generalizing to untested materials, untested preparation combinations, or rejected mapping patterns.
- Close Milestone 3 in `ROADMAP.md` once the Kobra X print-start matrix is verified, while preserving explicit boundaries for untested materials, firmware `2.0.2.2` telemetry/download limits, and external ACE units.

**Non-Goals:**
- Changing existing CLI syntax, JSON envelope keys, state formats, or safety guards (unless live testing proves firmware `2.0.2.2` rejects or misbehaves on a pattern such as shared physical slots, in which case a targeted refusal guard is added).
- Printing large models or touching production `--state-dir` / `~/.config/kobra-lan` profiles.
- Qualifying materials the operator does not physically load during the session.

## Decisions

### 1. Compact live Kobra X test matrix (tiny 1–2 g chips, isolated `--state-dir`)
Each test uses a minimal geometry (e.g., 15×15×1.2 mm single-color or 20×12×1.2 mm two-color chip) sliced with `AnycubicSlicerNext` CLI for Kobra X, uploaded via `kobra-lan --state-dir <tmp> files upload`, reviewed via `print plan`, executed via `print start --execute`, verified via `status`/`print watch` and physical inspection of the finished chip, and optionally cleaned from printer storage via `files delete --execute`:

| Run | Purpose | G-code `paint_info` | `--slot-map` | Prep flags (`auto`, `vib`, `flow`) | Material |
| --- | --- | --- | --- | --- | --- |
| A | Single-filament slot 3 | `[0]` | `0=3` | `on`, `off`, `off` | `PLA High Speed` |
| B | `auto-leveling off` | `[0]` | `0=1` | `off`, `off`, `off` | `PLA High Speed` |
| C | `vibration-compensation on` | `[0]` | `0=1` | `off`, `on`, `off` | `PLA High Speed` |
| D | `flow-calibration on` | `[0]` | `0=1` | `off`, `off`, `on` | `PLA High Speed` |
| E | 2-color cross-remapped subset | `[0, 1]` | `0=2 1=1` | `on`, `off`, `off` | `PLA High Speed` |
| F | 2-color sparse indices | `[0, 2]` | `0=1 2=3` | `on`, `off`, `off` | `PLA High Speed` |
| G | Single-filament non-zero index | `[2]` | `2=3` | `on`, `off`, `off` | `PLA High Speed` |
| H | Shared physical slot | `[0, 1]` | `0=1 1=1` | `on`, `off`, `off` | `PLA High Speed` |
| I* | Optional extra material(s) | `[0]` | `0=<slot>` | `on`, `off`, `off` | Operator-supplied (e.g., `PLA`, `PETG`, `TPU`) |

*Note:* If the operator prefers fewer runs, Run B (`auto=off, vib=off, flow=off`) can optionally be combined with Run A (`0=3`), though keeping Run A on baseline `(on, off, off)` cleanly isolates slot 3 first. Run H specifically checks how firmware `2.0.2.2` handles two `paint_index` entries pointing to the same `ams_index` (clean print without superfluous color swap vs firmware error/anomaly).

### 2. Structured `StartHardwareEvidence` model in `kobra_lan/qualification.py`
- **Choice**: Extend `StartHardwareEvidence` (while keeping it a frozen stdlib dataclass) so a single evidence record can express observed slot-mapping rules cleanly without enumerating all `4^N` permutations once every wire pattern is live-verified:
  - Keep exact `slot_maps: frozenset[tuple[tuple[int, int], ...]] = frozenset()` support for exact-map evidence.
  - Add optional explicit pattern predicates on `StartHardwareEvidence` (defaulting to `False`):
    - `allow_any_distinct_onboard_slot_map: bool = False` — enabled for `KOBRA_X` **only after** Runs A, E, F, and G all complete with operator-confirmed physical colors/slots (proving all 4 onboard slots `1..4`, single/multicolor subsets, cross-remapping `paint_index != ams_index`, sparse `paint_index`, and non-zero single `paint_index`).
    - `allow_shared_onboard_slots: bool = False` — enabled for `KOBRA_X` **only if** Run H completes cleanly on hardware without anomalous filament changes or rejection.
  - Keep `materials: frozenset[str]` strictly enumerated to exact live-observed loaded slot materials (never wildcarding untested materials).
  - Keep `preparation_flags: frozenset[tuple[bool, bool, bool]]` (or one `StartHardwareEvidence` entry per exact observed `(auto_leveling, vibration_compensation, flow_calibration)` tuple) strictly enumerated to live-observed combinations.
- **Alternative considered**: Listing only the 8 literal tested `slot_map` tuples forever. Rejected because once all four onboard slots (`1..4`), non-zero indices, cross-remapping, subsets, and sparse indices are physically validated on `20030` / `2.0.2.2`, reporting `hardware_start_validated: false` for `0=4, 1=2` while `0=2, 1=1` is `true` would make the flag artificially narrow and fail to retire the Milestone 3 multicolor item; conversely, keeping `materials`, `preparation_flags`, `allow_shared_onboard_slots`, firmware, model, and onboard-only topology strictly gated preserves the conservative evidence boundary.

### 3. Handling firmware anomalies during live testing
- If any run (especially Run H shared slots, or `vibration-compensation on` / `flow-calibration on`) fails or behaves unexpectedly on firmware `2.0.2.2`:
  - Do **not** promote that case in `kobra_lan/qualification.py`.
  - Record the exact sanitized telemetry and physical outcome in `docs/usage.md` and `docs/compatibility.md`.
  - If firmware actively rejects or misbehaves on the pattern, add a targeted validation guard + offline regression tests in `kobra_lan/start.py` and `tests/test_start.py`.

## Risks / Trade-offs

- **[Risk] Shared physical slots (Run H) might trigger unexpected purge/retract or firmware rejection on FW `2.0.2.2`** → **Mitigation**: Test on a tiny 2-layer chip under live observation with `print cancel --execute` ready, keep `allow_shared_onboard_slots` gated strictly on confirmed clean behavior, and add a refusal guard if firmware misbehaves.
- **[Risk] Preparation flags (`vibration_compensation`, `flow_calibration`) add extra minutes of printer noise/movement** → **Mitigation**: Schedule the session explicitly with the operator at an agreed time when household noise/presence is comfortable, and run them on tiny 1–2 g chips.
- **[Risk] Untested filament materials remain outside `materials`** → **Mitigation**: Explicitly document tested vs untested materials in `docs/compatibility.md` and `ROADMAP.md` (Milestone 4 continues broader material coverage).

## Open Questions

- Which non-`PLA High Speed` filament materials (if any) are currently available to load on the Kobra X for optional Run I?
- When is the best time window to execute the live printing session on the Kobra X?
