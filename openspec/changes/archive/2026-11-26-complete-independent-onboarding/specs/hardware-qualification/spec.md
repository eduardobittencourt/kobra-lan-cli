# Spec Delta

## MODIFIED Requirements

### Requirement: Authoritative hardware qualification definitions
The CLI SHALL derive qualified printer identity, firmware versions, slicer profile markers, and onboard filament-box topology from one authoritative qualification definition across discovery, provisioning, pairing, configuration loading, profile indexing, diagnostics, status, slot listing, camera access, upload, planning, start, lifecycle controls, and stored-file deletion. Unqualified targets SHALL remain rejected with existing exit codes and safe errors (while read-only `printer discover` marks unqualified models explicitly as `qualified_model: false`).

#### Scenario: Qualified target passes every operation consistently
- **WHEN** synthetic discovery, provisioning, pairing, diagnostics, slots, camera status/snapshot/pipe, upload, print plan, print start, print control, and file deletion run against Kobra X model `20030` reporting `"Anycubic Kobra X"` and firmware `"2.0.2.2"` with the onboard four-slot box (`id: -1`, indices `0..3`)
- **THEN** every operation accepts or qualifies the target using the same centralized qualification rules without weakening existing safety or trust checks

#### Scenario: Unqualified model, firmware, or topology fails consistently
- **WHEN** a synthetic response reports an unqualified model ID, model name, firmware version, slicer profile marker, or non-onboard filament box topology
- **THEN** provisioning, config loading, profile validation, diagnostics, and operational commands (including `camera status|snapshot|pipe`) reject the target with exit 2 (`validation_failed` or compatibility failure) without mutating printer or local state, and `printer discover` labels the candidate `qualified_model: false`

### Requirement: Centralized per-operation hardware validation flags
The CLI SHALL compute `hardware_discovery_validated`, `hardware_start_validated`, `hardware_control_validated`, `hardware_delete_validated`, and `hardware_camera_validated` from centralized hardware-evidence rules tied to qualified model and firmware records rather than scattered literals. Observed evidence boundaries SHALL remain conservative and never infer validation for unobserved slots, materials, preparations, multicolor starts, or unverified camera/discovery CLI workflows.

#### Scenario: Discovery hardware validation reflects recorded evidence
- **WHEN** `printer discover` builds its result using centralized qualification rules for Kobra X model `20030` / firmware `2.0.2.2`
- **THEN** `is_discovery_hardware_validated(20030, "2.0.2.2")` returns `True` (and `False` for unqualified models or firmwares) and `printer discover` reports `hardware_discovery_validated: true` backed by live Kobra X SSDP evidence

#### Scenario: Start hardware validation matches observed evidence only
- **WHEN** `print plan` or `print start` evaluates a `PLA High Speed` job with `auto_leveling: on`, `vibration_compensation: off`, and `flow_calibration: off` using either single-filament `paint_index: 0` on onboard slot `1`, `2`, or `4` or the observed 4-color contiguous 1:1 mapping `0=1, 1=2, 2=3, 3=4` versus single-filament slot `3`, another material, another preparation setting, a non-zero single `paint_index`, or any other multicolor mapping (2/3-color subset, cross-remapped `paint_index != ams_index`, sparse indices, or shared physical slot)
- **THEN** only the observed single-filament and 4-color contiguous 1:1 cases report `hardware_start_validated: true`, and every unobserved combination reports `hardware_start_validated: false`

#### Scenario: Control and delete hardware validation reflect recorded evidence
- **WHEN** guarded `print pause|resume|cancel` and `files delete` build results on the qualified Kobra X model `20030` / firmware `2.0.2.2` target (versus an unqualified model or firmware)
- **THEN** lifecycle controls report `hardware_control_validated: true` and stored-file deletion reports `hardware_delete_validated: true` from the centralized qualification profile on `20030` / `2.0.2.2`, and both report `false` for unqualified models or firmwares

#### Scenario: Camera hardware validation reflects recorded evidence
- **WHEN** `camera status` or `camera snapshot` builds results on the qualified Kobra X model `20030` / firmware `2.0.2.2` target
- **THEN** camera operations report `hardware_camera_validated: true` from the centralized qualification profile (and `false` for unqualified models or firmwares)

### Requirement: Published and packaged compatibility matrix
The project SHALL maintain `docs/compatibility.md` documenting supported and unqualified models, firmwares, slicers, filament-box topologies, slots, materials, preparation settings, operations (including `printer discover`, `camera status`, `camera snapshot`, and `camera pipe`), and host platforms. The matrix SHALL explicitly distinguish implemented, offline-validated, and hardware-observed status, SHALL be indexed from project documentation, and SHALL be shipped and link-checked in Python and Debian packages.

#### Scenario: Compatibility matrix distinguishes evidence tiers
- **WHEN** an operator reads `docs/compatibility.md`
- **THEN** every row (including `printer discover` and camera commands) separates implementation status, offline test coverage, and live hardware evidence without inferring support for unobserved printers, firmwares, materials, or external ACE units

#### Scenario: New module and documentation stay synchronized with packaging allowlists
- **WHEN** Python sdist/wheel and Debian package allowlist checks inspect the repository and built archives
- **THEN** the qualification, discovery, and camera modules and `docs/compatibility.md` are included in the allowlists and all relative Markdown links resolve within shipped documentation
