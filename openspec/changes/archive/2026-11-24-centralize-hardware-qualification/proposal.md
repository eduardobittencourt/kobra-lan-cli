# Proposal

## Why

Hardware qualification limits — model ID `20030`, model name `"Anycubic Kobra X"`, firmware `"2.0.2.2"`, slicer profile markers, onboard four-slot box topology (`id == -1`, slots `1..4`), and per-operation `hardware_*_validated` rules — are currently hardcoded and duplicated across ten modules in `kobra_lan/`. Centralizing these rules into one declarative qualification registry and publishing the Milestone 4 compatibility matrix eliminates drift across commands and creates a clean, auditable foundation for qualifying future firmwares, materials, slicers, platforms, and hardware profiles without weakening existing safety gates or inventing speculative protocol abstractions.

## What Changes

- Introduce a single authoritative qualification and capability module (`kobra_lan/qualification.py`) defining immutable profile definitions for qualified printer hardware (currently Kobra X model `20030` / `"Anycubic Kobra X"` / firmware `"2.0.2.2"`), slicer profile requirements (`AnycubicSlicerNext` + Kobra X model marker), onboard filament-box topology (`box_id == -1`, 4 onboard slots), canonical qualification banner text, and centralized helpers for identity/firmware compatibility and per-operation hardware validation flags (`hardware_start_validated`, `hardware_control_validated`, `hardware_delete_validated`).
- Refactor all runtime consumers (`provisioning.py`, `pairing.py`, `config.py`, `profiles.py`, `diagnostics.py`, `filaments.py`, `upload.py`, `start.py`, `control.py`, `delete_file.py`, `watch.py`, `cli_output.py`, and `cli.py`) to delegate qualification checks, topology bounds, and validation flags to `kobra_lan/qualification.py`, preserving all existing CLI commands, JSON schemas, exit codes, error classes, and Kobra X qualification boundaries without changing runtime behavior.
- Publish `docs/compatibility.md` with a structured compatibility matrix covering model, firmware, slicer, filament topology, slots, materials, preparation settings, operations, and host platforms, explicitly distinguishing *implemented*, *offline-validated*, and *hardware-observed* evidence.
- Index `docs/compatibility.md` from `docs/README.md`, `README.md`, and `ROADMAP.md`, and update packaging module/documentation allowlists (`MANIFEST.in`, `scripts/check_python.py`, `scripts/build_deb.py`, `scripts/check_deb.py`) so `kobra_lan/qualification.py` and `docs/compatibility.md` are shipped and link-verified in Python and Debian packages.
- Add dedicated offline unit tests (`tests/test_qualification.py`) verifying single-source consistency, immutable profile invariants, per-operation hardware validation boundaries, and zero regressions across existing tests.

## Capabilities

### New Capabilities

- `hardware-qualification`: Single authoritative hardware qualification registry and published compatibility matrix that enforce consistent model, firmware, slicer, filament-topology, and per-operation hardware-evidence boundaries across all CLI operations and packages.

### Modified Capabilities

_(None — all existing CLI interfaces, JSON envelopes, exit codes, and Kobra X model 20030 / firmware 2.0.2.2 qualification boundaries are preserved unchanged.)_

## Impact

- **Code**: New module `kobra_lan/qualification.py`; refactors in `kobra_lan/provisioning.py`, `kobra_lan/pairing.py`, `kobra_lan/config.py`, `kobra_lan/profiles.py`, `kobra_lan/diagnostics.py`, `kobra_lan/filaments.py`, `kobra_lan/upload.py`, `kobra_lan/start.py`, `kobra_lan/control.py`, `kobra_lan/delete_file.py`, `kobra_lan/watch.py`, `kobra_lan/cli_output.py`, and `kobra_lan/cli.py`.
- **Tests**: New `tests/test_qualification.py` plus verification of existing offline unit tests (including `tests/test_package_dependencies.py` and `tests/test_debian_docs.py`).
- **Packaging & allowlists**: Update module allowlists in `scripts/check_python.py` and `scripts/build_deb.py`, and documentation allowlists in `MANIFEST.in`, `scripts/check_python.py`, `scripts/build_deb.py`, and `scripts/check_deb.py`.
- **Documentation**: New `docs/compatibility.md`; updated index/roadmap links in `docs/README.md`, `README.md`, and `ROADMAP.md`.
- **Compatibility & scope boundaries**: Zero breaking CLI, JSON, state, or qualification changes. Does **not** introduce speculative protocol adapters for unobserved printer models, external ACE support, or `--allow-unqualified` bypass flags.
