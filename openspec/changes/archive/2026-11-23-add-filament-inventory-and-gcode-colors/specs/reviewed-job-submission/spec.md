# Spec Delta

## MODIFIED Requirements

### Requirement: Local G-code inspection
`gcode inspect <file> [--name <remote-name>]` SHALL inspect the existing qualified Next-generated Kobra X plain G-code without target configuration, network or state writes. It SHALL report SHA-256, size, proposed remote filename, available slicer/layer metadata, filament/color metadata, and qualification limits while preserving input bytes. Files without `; paint_info =` SHALL remain inspectable and uploadable.

#### Scenario: Inspect before connecting
- **WHEN** a supported synthetic file is inspected without configuration
- **THEN** its reviewable manifest is returned in the selected format with existing hash/size/layer/slicer fields preserved, filament inspection metadata included, and its bytes unchanged

#### Scenario: Minimal G-code without paint_info remains compatible
- **WHEN** a qualified Next-generated Kobra X G-code omits `; paint_info =`
- **THEN** `gcode inspect` succeeds with `paint_info_present: false`, `filaments: []`, `filament_count: 0`, `multicolor: false` (unless multiple distinct `T<n>` tools are present), and `single_filament_start_compatible: false`, and `files upload` continues to accept the reviewed file

## ADDED Requirements

### Requirement: Multicolor G-code filament and tool inspection
Local `gcode inspect` SHALL parse all `; paint_info = [...]` lines, `T<n>` tool commands, and optional filament weight summaries, reporting `paint_info_present`, ordered `filaments` (`paint_index`, `material_type`, `color_rgb`, `color_hex`, nullable `filament_used_g`), `filament_count`, `multicolor`, sorted `tool_indices`, nullable `total_filament_used_g`, and `single_filament_start_compatible`. Repeated `; paint_info =` lines SHALL agree; malformed or conflicting declarations SHALL exit 2.

#### Scenario: Inspect single-filament G-code declaring paint_index 0
- **WHEN** a Next-generated Kobra X G-code declares one filament at `paint_index: 0` with no tool index other than `0`
- **THEN** `gcode inspect` reports `paint_info_present: true`, `filament_count: 1`, `multicolor: false`, `single_filament_start_compatible: true`, and one normalized filament entry with `color_rgb` and `color_hex`

#### Scenario: Inspect multicolor G-code with non-contiguous paint indices and repeated headers
- **WHEN** a Next-generated Kobra X G-code contains identical `; paint_info = [...]` lines in both the header and config blocks declaring multiple filaments (for example `paint_index` `1` and `3`, or mixed materials such as `PLA` and `PETG`), corresponding `T<n>` commands, and filament weight summaries
- **THEN** `gcode inspect` exits 0 without network access, reports all declared filaments ordered by `paint_index` with normalized `color_rgb`, `color_hex`, `material_type`, and per-index `filament_used_g`, reports `multicolor: true`, `tool_indices`, `total_filament_used_g`, and `single_filament_start_compatible: false`, and remains uploadable via `files upload`

#### Scenario: Inspect single-filament G-code with non-zero paint index
- **WHEN** a Next-generated Kobra X G-code declares one filament at a non-zero index (for example `paint_index: 2` with `T2`)
- **THEN** `gcode inspect` reports `filament_count: 1`, `multicolor: false`, `tool_indices: [2]`, and `single_filament_start_compatible: false`

#### Scenario: Conflicting or malformed paint_info fails validation
- **WHEN** a G-code file contains malformed `; paint_info =` JSON, invalid color/material/index fields, duplicate `paint_index` values within one declaration, or two `; paint_info =` lines with different normalized declarations
- **THEN** `gcode inspect` fails with exit 2 (`validation_failed`) without modifying the file
