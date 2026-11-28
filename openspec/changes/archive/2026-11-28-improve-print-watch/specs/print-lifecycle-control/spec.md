## MODIFIED Requirements

### Requirement: Fresh qualification and strict state preconditions

Before publishing, the CLI SHALL verify a fresh `info` report over one pinned MQTT session for Kobra X model `20030` / firmware `2.0.2.2` and consistent optional identifiers. `pause` SHALL require `printing`; `resume` SHALL require `paused`; `cancel` SHALL require `printing`, a recognized firmware `2.0.2.2` preparation or filament-change phase, or `paused`. Idle, already-reached, transitional, or unrecognized states SHALL exit 2 without publishing.

#### Scenario: Pause refused when not printing
- **WHEN** `print pause --execute` runs while the printer is idle, already `paused`, `pausing`, or in a preparation phase
- **THEN** the CLI exits 2 with `validation_failed` and publishes no MQTT control command

#### Scenario: Resume refused when not paused
- **WHEN** `print resume --execute` runs while the printer is idle, already `printing`, `resuming`, or in a preparation phase
- **THEN** the CLI exits 2 with `validation_failed` and publishes no MQTT control command

#### Scenario: Cancel allowed from active printing, preparation, or paused
- **WHEN** `print cancel --execute` runs while the fresh active job is `printing`, in a recognized firmware `2.0.2.2` preparation phase, or `paused`
- **THEN** pre-flight validation succeeds and the CLI proceeds to publish one `stop` command

#### Scenario: Cancel allowed during calibration or filament-change preparation
- **WHEN** `print cancel --execute` runs while the fresh active job is in `auto_leveling`, `vibrating`, `flow_calibrating`, `filament_cutting`, or `extfilbox_filament_unfeeding`
- **THEN** pre-flight validation succeeds and the CLI proceeds to publish one `stop` command

#### Scenario: Control refused on idle, transitional, or unqualified target
- **WHEN** `print cancel --execute` encounters idle, `stopping`, an unrecognized project state, a TLS pin mismatch, or unqualified firmware
- **THEN** the CLI exits 2 without publishing any control command
- **AND** a pin mismatch prevents transmission of MQTT credentials
