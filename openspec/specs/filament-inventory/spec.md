# filament-inventory Specification

## Purpose

Provide read-only visibility into the qualified Kobra X onboard four-slot filament box so operators and agents can inspect loaded materials, colors, and slot availability before planning single- or multi-color prints.

## Requirements

### Requirement: Read-only onboard filament slot inventory
`slots list` SHALL resolve the selected printer via `--printer`, `--config`, or the saved named default and open at most one pinned MQTT session without writing local state, modifying credentials or reservations, or publishing mutating printer commands. Over that session it SHALL verify a fresh `info` report for Kobra X model `20030` / firmware `2.0.2.2` without requiring idle state, then issue a read-only `multiColorBox / getInfo` query.

#### Scenario: Inspect slots on an idle or printing qualified printer
- **WHEN** `slots list` targets a qualified Kobra X (`Anycubic Kobra X`, firmware `2.0.2.2`) that is idle or actively printing and reports the onboard four-slot box (`id == -1`, four unique slot indices `0..3`)
- **THEN** the CLI exits 0, returns one sanitized inventory result in text or root `--json` format, leaves all local state untouched, and succeeds whether the printer is idle or busy

#### Scenario: Unqualified model, firmware, or external box topology
- **WHEN** fresh `info` reports an unqualified model or firmware, or `multiColorBox / getInfo` reports missing, malformed, multi-box, or non-onboard (`id != -1`) box data, or a slot list that does not cover indices `0..3` uniquely
- **THEN** `slots list` fails with exit 2 (`validation_failed`) without fabricating slot metadata or falling back to other endpoints

#### Scenario: Network or TLS pin failure
- **WHEN** the saved configuration is unusable, the TLS pin fails, or MQTT communication times out or disconnects
- **THEN** `slots list` exits 2 for trust/authentication/protocol failure or exit 3 for configuration/network failure without retrying automatically or mutating state

### Requirement: Structured and sanitized onboard slot presentation
`slots list` SHALL report the onboard box summary (`box_id: -1`, `box_kind: "onboard"`, `slot_count: 4`, `loaded_count`) and four `slots` ordered by `ams_index` `0..3` (`slot` `1..4`). Each slot SHALL include `slot`, `ams_index`, integer `status`, `status_label` (`"loaded"`, `"empty"`, or `"other"`), `available_for_start`, and nullable `material_type`, `color_rgb`, and `color_hex`. Raw unknown telemetry fields, URLs, and credentials SHALL be excluded.

#### Scenario: Mixed loaded and empty onboard slots
- **WHEN** onboard slots contain loaded spools (`status == 5`, non-empty printable material, valid 3- or 4-channel RGB/RGBA color in `0..255`) alongside empty slots (`status == 0` with empty or absent material/color)
- **THEN** `slots list` reports slots `1..4` in order, marks loaded slots `status_label: "loaded"` and `available_for_start: true` with 3-int `color_rgb` and `#RRGGBB` `color_hex`, marks empty slots `status_label: "empty"` and `available_for_start: false` with null material/color fields, and reports accurate `loaded_count`

#### Scenario: Unrecognized slot status code or incomplete loaded metadata
- **WHEN** an onboard slot reports an integer status code other than `0` or `5`, or reports `status == 5` without both a non-empty material and valid color
- **THEN** `slots list` preserves the raw integer `status`, uses `status_label: "other"` for unrecognized codes, sets `available_for_start: false`, and avoids claiming the slot is ready for print start

#### Scenario: Equivalent text and JSON presentation
- **WHEN** identical synthetic slot inventory responses are rendered in default text mode and root `--json` mode
- **THEN** both expose the same slot numbering, material, color, availability, and qualification metadata without additional network requests
