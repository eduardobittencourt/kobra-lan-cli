# hardware-qualification Specification

## Purpose

Maintain one authoritative hardware qualification definition and a published compatibility matrix so every CLI operation enforces identical model, firmware, slicer, topology, and hardware-evidence boundaries without drift.

## Requirements

### Requirement: Authoritative hardware qualification definitions
The CLI SHALL derive qualified printer identity, firmware versions, slicer profile markers, and onboard filament-box topology from one authoritative qualification definition across provisioning, pairing, configuration loading, profile indexing, diagnostics, status, slot listing, upload, planning, start, lifecycle controls, and stored-file deletion. Unqualified targets SHALL remain rejected with existing exit codes and safe errors.

#### Scenario: Qualified target passes every operation consistently
- **WHEN** synthetic provisioning, pairing, diagnostics, slots, upload, print plan, print start, print control, and file deletion run against Kobra X model `20030` reporting `"Anycubic Kobra X"` and firmware `"2.0.2.2"` with the onboard four-slot box (`id: -1`, indices `0..3`)
- **THEN** every operation accepts the target using the same centralized qualification rules without weakening existing safety or trust checks

#### Scenario: Unqualified model, firmware, or topology fails consistently
- **WHEN** a synthetic response reports an unqualified model ID, model name, firmware version, slicer profile marker, or non-onboard filament box topology
- **THEN** provisioning, config loading, profile validation, diagnostics, and operational commands reject the target with exit 2 (`validation_failed` or compatibility failure) without mutating printer or local state

### Requirement: Centralized per-operation hardware validation flags
The CLI SHALL compute `hardware_start_validated`, `hardware_control_validated`, and `hardware_delete_validated` from centralized hardware-evidence rules tied to qualified model and firmware records rather than scattered literals. Observed evidence boundaries SHALL remain conservative and never infer validation for unobserved slots, materials, preparations, or multicolor starts.

#### Scenario: Start hardware validation matches observed evidence only
- **WHEN** `print plan` or `print start` evaluates a `PLA High Speed` job with `auto_leveling: on`, `vibration_compensation: off`, and `flow_calibration: off` using either single-filament `paint_index: 0` on onboard slot `1`, `2`, or `4` or the observed 4-color contiguous 1:1 mapping `0=1, 1=2, 2=3, 3=4` versus single-filament slot `3`, another material, another preparation setting, a non-zero single `paint_index`, or any other multicolor mapping (2/3-color subset, cross-remapped `paint_index != ams_index`, sparse indices, or shared physical slot)
- **THEN** only the observed single-filament and 4-color contiguous 1:1 cases report `hardware_start_validated: true`, and every unobserved combination reports `hardware_start_validated: false`

#### Scenario: Control and delete hardware validation reflect recorded evidence
- **WHEN** guarded `print pause|resume|cancel` and `files delete` build results on the qualified Kobra X model `20030` / firmware `2.0.2.2` target
- **THEN** lifecycle controls report `hardware_control_validated: true` and stored-file deletion reports `hardware_delete_validated: false` from the centralized qualification profile

### Requirement: Published and packaged compatibility matrix
The project SHALL maintain `docs/compatibility.md` documenting supported and unqualified models, firmwares, slicers, filament-box topologies, slots, materials, preparation settings, operations, and host platforms. The matrix SHALL explicitly distinguish implemented, offline-validated, and hardware-observed status, SHALL be indexed from project documentation, and SHALL be shipped and link-checked in Python and Debian packages.

#### Scenario: Compatibility matrix distinguishes evidence tiers
- **WHEN** an operator reads `docs/compatibility.md`
- **THEN** every row separates implementation status, offline test coverage, and live hardware evidence without inferring support for unobserved printers, firmwares, materials, or external ACE units

#### Scenario: New module and documentation stay synchronized with packaging allowlists
- **WHEN** Python sdist/wheel and Debian package allowlist checks inspect the repository and built archives
- **THEN** both the qualification module and `docs/compatibility.md` are included in the allowlists and all relative Markdown links resolve within shipped documentation
