# Spec Delta: hardware-qualification

## MODIFIED Requirements

### Requirement: Centralized per-operation hardware validation flags
The CLI SHALL compute `hardware_start_validated`, `hardware_control_validated`, `hardware_delete_validated`, and `hardware_camera_validated` from centralized hardware-evidence rules tied to qualified model and firmware records rather than scattered literals. Observed evidence boundaries SHALL remain conservative and never infer validation for unobserved slots, materials, preparations, multicolor starts, or unverified camera CLI workflows.

#### Scenario: Start hardware validation matches observed evidence only
- **WHEN** `print plan` or `print start` evaluates a `PLA High Speed` job with `auto_leveling: on`, `vibration_compensation: off`, and `flow_calibration: off` using either single-filament `paint_index: 0` on onboard slot `1`, `2`, or `4` or the observed 4-color contiguous 1:1 mapping `0=1, 1=2, 2=3, 3=4` versus single-filament slot `3`, another material, another preparation setting, a non-zero single `paint_index`, or any other multicolor mapping (2/3-color subset, cross-remapped `paint_index != ams_index`, sparse indices, or shared physical slot)
- **THEN** only the observed single-filament and 4-color contiguous 1:1 cases report `hardware_start_validated: true`, and every unobserved combination reports `hardware_start_validated: false`

#### Scenario: Control and delete hardware validation reflect recorded evidence
- **WHEN** guarded `print pause|resume|cancel` and `files delete` build results on the qualified Kobra X model `20030` / firmware `2.0.2.2` target (versus an unqualified model or firmware)
- **THEN** lifecycle controls report `hardware_control_validated: true` and stored-file deletion reports `hardware_delete_validated: true` from the centralized qualification profile on `20030` / `2.0.2.2`, and both report `false` for unqualified models or firmwares

#### Scenario: Camera hardware validation reflects recorded evidence
- **WHEN** `camera status` or `camera snapshot` builds results on the qualified Kobra X model `20030` / firmware `2.0.2.2` target
- **THEN** camera operations report `hardware_camera_validated: true` from the centralized qualification profile (and `false` for unqualified models or firmwares)
