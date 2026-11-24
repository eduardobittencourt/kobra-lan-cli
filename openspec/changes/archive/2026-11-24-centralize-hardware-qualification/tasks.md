# Tasks

## 1. Authoritative Qualification Registry (`kobra_lan/qualification.py`)

- [x] 1.1 Create leaf stdlib-only module `kobra_lan/qualification.py` defining immutable `OnboardBoxTopology`, `StartHardwareEvidence`, `PrinterQualification`, `QUALIFIED_PRINTERS` (with `KOBRA_X` for model `20030` / `"Anycubic Kobra X"` / firmware `"2.0.2.2"`), `QUALIFIED_FIRMWARE`, `QUALIFICATION_SUMMARY`, and pure helpers (`qualification_for_model_id`, `normalize_qualified_model_id`, `is_qualified_profile_firmware`, `info_compatibility_issue`, `is_qualified_remote_model`, `matches_slicer_model_marker`, `onboard_topology`, `is_valid_onboard_slot`, `is_start_hardware_validated`, `is_control_hardware_validated`, `is_delete_hardware_validated`). Add `tests/test_qualification.py` covering immutable profile definitions, model/firmware lookup, info compatibility precedence (`outside_qualification` vs `qualification_incomplete`), onboard topology bounds, and per-operation hardware validation predicates; verify with `uv run --locked python -m unittest tests.test_qualification -v`.

## 2. Migrate Runtime Modules to `kobra_lan/qualification.py`

- [x] 2.1 Migrate identity, config, pairing, profile, and diagnostic checks in `kobra_lan/provisioning.py`, `kobra_lan/config.py`, `kobra_lan/pairing.py`, `kobra_lan/profiles.py`, and `kobra_lan/diagnostics.py` to delegate model ID, model name, firmware, and `info` compatibility checks to `kobra_lan/qualification.py` (preserving existing public exports such as `pairing.QUALIFIED_FIRMWARE`, `diagnostics.compatibility_issue`, and existing error messages). Verify with `uv run --locked python -m unittest tests.test_pairing tests.test_profiles tests.test_diagnostics -v`.
- [x] 2.2 Migrate operational and presentation modules (`kobra_lan/filaments.py`, `kobra_lan/upload.py`, `kobra_lan/start.py`, `kobra_lan/control.py`, `kobra_lan/delete_file.py`, `kobra_lan/watch.py`, `kobra_lan/cli_output.py`, and `kobra_lan/cli.py`) to use `kobra_lan/qualification.py` for slicer/remote model checks, onboard box topology bounds, `hardware_start_validated` / `hardware_control_validated` / `hardware_delete_validated` flags, and qualification summary text, preserving all CLI, JSON, and exit-code contracts. Verify with `uv run --locked python -m unittest tests.test_cli tests.test_client tests.test_filaments tests.test_start tests.test_control tests.test_delete_file tests.test_watch tests.test_jobs tests.test_completions -v`.

## 3. Compatibility Matrix Documentation & Packaging Allowlists

- [x] 3.1 Create `docs/compatibility.md` publishing the Milestone 4 compatibility matrix (models, firmwares, slicers, filament-box topology/slots, materials, preparation settings, CLI operations with `experimental` and `hardware_*_validated` status, and host platforms/distribution channels) explicitly distinguishing implemented, offline-validated, and hardware-observed evidence; link it from `docs/README.md`, `README.md`, and `ROADMAP.md`. Verify relative Markdown links and alignment with `kobra_lan/qualification.py`.
- [x] 3.2 Update packaging module and documentation allowlists in `MANIFEST.in`, `scripts/check_python.py` (`MODULES`, `DOCS`), `scripts/build_deb.py` (`MODULES`, `SOURCE_FILES`), and `scripts/check_deb.py` (`public_docs`) to include `kobra_lan/qualification.py` and `docs/compatibility.md`. Verify with `uv run --locked python -m unittest tests.test_package_dependencies tests.test_debian_docs -v`.

## 4. Full Offline Verification Gates

- [x] 4.1 Run the full offline validation suite (`uv run --locked python -m unittest discover -s tests -v`, `uv run --locked ruff check kobra_lan scripts tests`, `sh -n kobra-lan`, and `openspec validate centralize-hardware-qualification --strict`) and confirm all tests, lint checks, shell syntax checks, and strict spec validations pass with zero live printer access.

## Workflow follow-up

- Open a PR and satisfy review and CI package checks (including Python archive and Debian build/acceptance in CI).
- Archive the change with `openspec-archive-change` (syncing `hardware-qualification` to `openspec/specs/`) once implementation and review requirements are satisfied.
