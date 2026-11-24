# Design

## Context

See [proposal.md](proposal.md) for motivation and scope.

Currently, Kobra X model `20030` / `"Anycubic Kobra X"` / firmware `"2.0.2.2"` qualification constants and hardware-evidence predicates are duplicated across ten modules:
- `kobra_lan/provisioning.py` hardcodes `"20030"` / `20030` in `model_id()`.
- `kobra_lan/config.py` hardcodes `config.type_id != 20030`.
- `kobra_lan/pairing.py` defines `QUALIFIED_FIRMWARE = "2.0.2.2"` and hardcodes `"Anycubic Kobra X"` and `"model 20030 / firmware 2.0.2.2"` in `verify_status()`.
- `kobra_lan/profiles.py` hardcodes `entry.get('firmware') not in (None, '2.0.2.2')`.
- `kobra_lan/diagnostics.py` imports `QUALIFIED_FIRMWARE` from `pairing.py` while hardcoding `"Anycubic Kobra X"` and the compatibility check logic in `compatibility_issue()`.
- `kobra_lan/filaments.py` hardcodes `box_id != -1` and 4 onboard slots (`0..3`).
- `kobra_lan/upload.py` hardcodes `b"; printer_model = Anycubic Kobra X"`, `info.get("model") != "Anycubic Kobra X"`, `info.get("version") != "2.0.2.2"`, and `details.get("printer_model") != "Anycubic Kobra X"`.
- `kobra_lan/start.py` hardcodes slots `1..4`, `"Anycubic Kobra X"`, `"2.0.2.2"`, and inline `hardware_validated` logic (`slot_map.get(0) in (1, 2, 4)`, `"PLA High Speed"`, `auto_leveling and not vibration and not flow`).
- `kobra_lan/control.py` and `kobra_lan/delete_file.py` call `compatibility_issue()` (with `delete_file.py` also repeating `config.type_id != 20030`) and hardcode `hardware_control_validated: True` and `hardware_delete_validated: False`.
- `kobra_lan/cli_output.py` and `kobra_lan/cli.py` repeat the `"Kobra X model 20030 / firmware 2.0.2.2"` text.

Adding a new module and documentation file also touches packaging allowlists in `MANIFEST.in`, `scripts/check_python.py`, `scripts/build_deb.py`, and `scripts/check_deb.py` (which enforces relative link integrity across all shipped Markdown docs).

## Goals / Non-Goals

**Goals:**
- Provide one zero-dependency (stdlib-only) module `kobra_lan/qualification.py` as the single authoritative source of truth for qualified printer models, firmwares, slicer profile requirements, onboard box topology, status compatibility evaluation, and per-operation hardware validation flags.
- Eliminate scattered `"20030"`, `"2.0.2.2"`, `"Anycubic Kobra X"`, topology, and `hardware_*_validated` literals across runtime modules while keeping every CLI command, JSON field, exit code, and error message contract unchanged.
- Publish `docs/compatibility.md` as the maintained Milestone 4 compatibility matrix and keep it synced with packaging allowlists and documentation indexes.

**Non-Goals:**
- Speculative protocol adapters, plugin loaders, or wire-format abstractions for printer models or external ACE units not yet observed on real hardware.
- Adding new CLI flags (such as `--allow-unqualified`), changing existing JSON envelope schemas, or relaxing Kobra X model `20030` / firmware `2.0.2.2` enforcement.
- Expanding live hardware qualification claims (e.g., flipping `hardware_delete_validated` or multicolor `hardware_start_validated`).

## Decisions

### 1. Leaf stdlib-only module `kobra_lan/qualification.py`
- **Choice:** Place all qualification data models and pure predicate helpers in a new leaf module `kobra_lan/qualification.py` that imports only Python stdlib (`dataclasses`, `types`).
- **Rationale:** Every layer of the package — from low-level `config.py` and `provisioning.py` up to `diagnostics.py`, `start.py`, `cli_output.py`, and `cli.py` — needs qualification rules. Keeping `qualification.py` free of internal `kobra_lan` imports guarantees zero import cycles and makes it trivial to unit-test in isolation.
- **Alternatives considered:**
  - *Keep constants in `config.py` or `pairing.py`*: mixes transport/persistence concerns with hardware evidence and already caused `diagnostics.py` to import from `pairing.py` while other modules copied literals to avoid awkward imports.
  - *Load qualification from an external JSON/YAML data file*: adds package-data/path-resolution complexity and requires updating setuptools `include-package-data`, wheel checks, and Debian install rules for a small static table that benefits from Python frozen dataclasses and type safety.

### 2. Immutable declarative profile structures
- **Choice:** Represent each qualified printer with frozen dataclasses and immutable collections (`frozenset`, `tuple`, `MappingProxyType`):
  - `OnboardBoxTopology(box_id: int, box_kind: str, slot_count: int)` (currently `(-1, "onboard", 4)`).
  - `StartHardwareEvidence(slots: frozenset[int], paint_index: int, materials: frozenset[str], auto_leveling: bool, vibration_compensation: bool, flow_calibration: bool)`.
  - `PrinterQualification(model_id, model_name, short_name, firmware_versions, slicer_name, gcode_model_marker, onboard_box, start_evidence, control_hardware_validated, delete_hardware_validated)`.
  - `QUALIFIED_PRINTERS = MappingProxyType({20030: KOBRA_X})` plus `QUALIFIED_FIRMWARE = "2.0.2.2"` and `QUALIFICATION_SUMMARY` derived from the active profile.
- **Rationale:** Prevents accidental runtime mutation, cleanly supports future firmware versions (adding a version to `firmware_versions`), additional observed start combinations (appending a `StartHardwareEvidence` entry), or future qualified models (adding an entry to `QUALIFIED_PRINTERS`) without rewriting consumers.
- **Alternatives considered:**
  - *Plain module-level constants*: avoids a class definition but scatters related attributes (model ID, model name, firmwares, box slots, start evidence) with no cohesive lookup by `model_id`.

### 3. Unified compatibility & evidence helpers while preserving module contracts
- **Choice:** Expose pure helpers in `kobra_lan/qualification.py`:
  - `qualification_for_model_id(model_id)` and `normalize_qualified_model_id(values)` (for `config.py`, `provisioning.py`, `delete_file.py`).
  - `is_qualified_profile_firmware(version)` (accepting `None` or any firmware across `QUALIFIED_PRINTERS`, used by `profiles.py`).
  - `info_compatibility_issue(model_id, printer_id, info)` (returning `None`, `"qualification_incomplete"`, or `"outside_qualification"` — preserving `diagnostics.compatibility_issue(cfg, info)` as a thin wrapper and sharing exact matching semantics with `pairing.py`, `upload.py`, `start.py`, `control.py`, `delete_file.py`, `filaments.py`, and `watch.py`).
  - `is_qualified_remote_model(model_id, remote_model)` and `matches_slicer_model_marker(data)` (for `upload.py` and `start.py`).
  - `is_valid_onboard_slot(model_id, slot)` / `onboard_topology(model_id)` (for `filaments.py`, `start.py`, and CLI `--slot-map` bounds).
  - `is_start_hardware_validated(...)`, `is_control_hardware_validated(model_id, firmware)`, and `is_delete_hardware_validated(model_id, firmware)`.
- **Rationale:** Consolidates identical checks (`model`/`version`/`modelId`/`modeId`/`deviceId`/`state` validation) so every command agrees on qualification, while preserving existing public module symbols (e.g., `pairing.QUALIFIED_FIRMWARE`, `diagnostics.compatibility_issue`, `cli_output.QUALIFICATION`) and error messages so no callers or tests break.
- **Alternatives considered:**
  - *Delete `pairing.QUALIFIED_FIRMWARE` and `diagnostics.compatibility_issue`*: unnecessary churn for existing imports and tests when thin re-exports/wrappers cost two lines.

### 4. Maintained compatibility matrix in `docs/compatibility.md`
- **Choice:** Create `docs/compatibility.md` with explicit tables for:
  1. Printer models & firmware versions (implemented vs. offline-validated vs. hardware-observed)
  2. Slicers & G-code profiles
  3. Filament-box topologies & onboard slots (`1..4` vs. external ACE)
  4. Materials & print preparation combinations
  5. Operations (`pair`, `doctor`, `status`, `slots list`, `gcode inspect`, `files list|info|upload|delete`, `print plan|start|watch|pause|resume|cancel`, `jobs list|info`, `completion`) with their exact `experimental` / `hardware_*_validated` flags
  6. Host platforms & distribution channels (Debian 13 / Ubuntu 24.04 amd64 vs. unqualified macOS / Windows / other architectures)
- Link `docs/compatibility.md` from `docs/README.md`, `README.md`, and `ROADMAP.md`, and add it to `MANIFEST.in`, `scripts/check_python.py` (`DOCS`), `scripts/build_deb.py` (`SOURCE_FILES`), and `scripts/check_deb.py` (`public_docs`).
- **Rationale:** Satisfies Milestone 4's matrix deliverable with honest evidence tiers and keeps all shipped package docs link-verified by `scripts/check_deb.py` and `tests/test_debian_docs.py`.

## Risks / Trade-offs

- **Packaging allowlist drift** (`kobra_lan/qualification.py` or `docs/compatibility.md` missing from one of the build/check lists) → Explicitly update `MANIFEST.in`, `scripts/check_python.py`, `scripts/build_deb.py`, and `scripts/check_deb.py` in the same task and verify via `tests/test_package_dependencies.py` and `tests/test_debian_docs.py`.
- **Subtle behavioral drift in error wording or missing-field handling** (e.g., `pairing.verify_status` vs. `diagnostics.compatibility_issue` vs. `upload.py`/`start.py`) → Keep each caller's existing `ProtocolError` message and verify exact behavior against the full 299-test offline suite plus new dedicated `tests/test_qualification.py` unit tests.
- **Over-abstraction before second hardware model exists** → Keep `qualification.py` strictly declarative for current known dimensions without speculative transport/protocol plugin hooks.
