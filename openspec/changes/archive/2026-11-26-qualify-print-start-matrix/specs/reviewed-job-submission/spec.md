# Spec Delta

## MODIFIED Requirements

### Requirement: Evidence stays qualified
Both formats SHALL distinguish upload listing/metadata verification from remote byte-hash verification, start acknowledgement from observed activity, and activity from completion or physical quality. `hardware_start_validated` SHALL reflect only the live-observed Kobra X `20030` / firmware `2.0.2.2` slot-mapping classes, materials, and preparation-flag combinations recorded in the centralized qualification registry; unobserved combinations SHALL report `hardware_start_validated: false`.

#### Scenario: Successful submission
- **WHEN** an upload is metadata-verified or a start is observed active
- **THEN** output labels that evidence accurately without claiming remote byte equality, completed printing, or assessed part quality

#### Scenario: Multicolor or non-zero paint_index qualification boundary
- **WHEN** `print plan` or `print start` runs on Kobra X `20030` / firmware `2.0.2.2` with a live-observed material, a live-observed preparation-flag tuple, and a live-observed onboard slot-mapping class (including single-filament slot `3`, cross-remapped 2-color subset, sparse `paint_index`, non-zero single `paint_index`, and shared physical slots if live-confirmed) versus an untested material, untested preparation-flag tuple, or unconfirmed mapping pattern
- **THEN** live-observed combinations report `experimental: true` and `hardware_start_validated: true`, while every unobserved combination reports `experimental: true` and `hardware_start_validated: false`
