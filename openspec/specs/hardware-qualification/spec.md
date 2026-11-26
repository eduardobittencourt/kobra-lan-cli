# hardware-qualification Specification

## Purpose

Maintain one authoritative hardware qualification definition and a published compatibility matrix so every CLI operation enforces identical model, firmware, slicer, topology, and hardware-evidence boundaries without drift.

## Requirements

### Requirement: Authoritative hardware qualification definitions
The CLI SHALL derive qualified printer identity, firmware versions, slicer profile markers, and onboard filament-box topology from one authoritative qualification definition across discovery, provisioning, pairing, configuration loading, profile indexing, diagnostics, status, slot listing, camera access, upload, planning, start, lifecycle controls, and stored-file deletion. Unqualified targets SHALL remain rejected with existing exit codes and safe errors (while read-only `printer discover` marks unqualified models explicitly as `qualified_model: false`).

#### Scenario: Qualified target passes every operation consistently
- **WHEN** synthetic discovery, provisioning, pairing, diagnostics, slots, camera status/snapshot/pipe, upload, print plan, print start, print control, and file deletion run against Kobra X model `20030` reporting `"Anycubic Kobra X"` and firmware `"2.0.2.2"` with the onboard four-slot box (`id: -1`, indices `0..3`)
- **THEN** every operation accepts or qualifies the target using the same centralized qualification rules without weakening existing safety or trust checks

#### Scenario: Unqualified model, firmware, or topology fails consistently
- **WHEN** a synthetic response reports an unqualified model ID, model name, firmware version, slicer profile marker, or non-onboard filament box topology
- **THEN** provisioning, config loading, profile validation, diagnostics, and operational commands (including `camera status|snapshot|pipe`) reject the target with exit 2 (`validation_failed` or compatibility failure) without mutating printer or local state, and `printer discover` labels the candidate `qualified_model: false`

### Requirement: Centralized per-operation hardware validation flags
The CLI SHALL compute `hardware_discovery_validated`, `hardware_start_validated`, `hardware_control_validated`, `hardware_delete_validated`, and `hardware_camera_validated` from one centralized qualification registry tied to qualified model and firmware records. Observed boundaries SHALL remain conservative and never infer validation for unobserved materials, preparation combinations, topologies, models, or firmwares.

#### Scenario: Discovery hardware validation reflects recorded evidence
- **WHEN** `printer discover` builds its result using centralized qualification rules for Kobra X model `20030` / firmware `2.0.2.2`
- **THEN** `is_discovery_hardware_validated(20030, "2.0.2.2")` returns `True` (and `False` for unqualified models or firmwares) and `printer discover` reports `hardware_discovery_validated: true` backed by live Kobra X SSDP evidence

#### Scenario: Start hardware validation matches observed evidence only
- **WHEN** `print plan` or `print start` evaluates a Kobra X `20030` / firmware `2.0.2.2` job covered by exact recorded runs or the class-level `PLA High Speed` baseline-preparation onboard slot-mapping rule backed by representative live runs (distinguishing individual untested slot permutations within those observed mapping classes from unobserved materials, unobserved preparation combinations or cross-products, unobserved mapping classes, or unqualified models/firmwares)
- **THEN** only combinations covered by recorded exact runs or those class-level representative-run rules report `hardware_start_validated: true`, and every combination with an unobserved material, unobserved preparation combination/cross-product, unobserved mapping class, or unqualified model/firmware reports `hardware_start_validated: false`

#### Scenario: Control and delete hardware validation reflect recorded evidence
- **WHEN** guarded `print pause|resume|cancel` and `files delete` build results on the qualified Kobra X model `20030` / firmware `2.0.2.2` target (versus an unqualified model or firmware)
- **THEN** lifecycle controls report `hardware_control_validated: true` and stored-file deletion reports `hardware_delete_validated: true` from the centralized qualification profile on `20030` / `2.0.2.2`, and both report `false` for unqualified models or firmwares

#### Scenario: Camera hardware validation reflects recorded evidence
- **WHEN** `camera status` or `camera snapshot` builds results on the qualified Kobra X model `20030` / firmware `2.0.2.2` target
- **THEN** camera operations report `hardware_camera_validated: true` from the centralized qualification profile (and `false` for unqualified models or firmwares)

### Requirement: Published and packaged compatibility matrix
The project SHALL maintain `docs/compatibility.md` separating implemented, offline-validated, and hardware-observed status across models, firmwares, slicers, topologies, slots, materials, preparation flags, CLI operations, and host platforms, indexed from project docs and checked in Python/Debian packaging.

#### Scenario: Compatibility matrix distinguishes evidence tiers
- **WHEN** an operator reads `docs/compatibility.md` after the Milestone 3 print-start qualification session
- **THEN** every row (including materials, slot-mapping classes, preparation flags, `printer discover`, and camera commands) separates implementation status, offline test coverage, and live hardware evidence without inferring support for untested materials, untested preparation combinations, non-Next slicers, or external ACE units

#### Scenario: New module and documentation stay synchronized with packaging allowlists
- **WHEN** Python sdist/wheel and Debian package allowlist checks inspect the repository and built archives
- **THEN** the qualification, discovery, and camera modules and `docs/compatibility.md` are included in the allowlists and all relative Markdown links resolve within shipped documentation
