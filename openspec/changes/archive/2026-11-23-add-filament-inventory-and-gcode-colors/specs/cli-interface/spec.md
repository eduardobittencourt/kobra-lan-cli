# Spec Delta

## MODIFIED Requirements

### Requirement: Canonical command tree
The CLI SHALL expose `printer pair|list|info|use|remove`, `doctor`, `status`, `slots list`, `files list|info|upload`, `gcode inspect`, `print plan|start|watch|pause|resume|cancel`, `jobs list|info`, and `completion bash|zsh|fish`. It SHALL remove flat `file`, `upload`, `inspect`, `start` and executable bare `files` without aliases or deprecation shims. Bare `slots` without a subcommand SHALL fail with exit 2 and contextual help.

#### Scenario: Removed invocation
- **WHEN** a superseded flat command or bare operational group (including bare `slots`) is invoked
- **THEN** the CLI exits 2 with contextual guidance and performs no network or state mutation

#### Scenario: Group help
- **WHEN** `files --help`, `slots --help`, `print --help`, or `jobs --help` is requested
- **THEN** help lists the group's supported operations and distinguishes read-only inventory, local history inspection, network observation, planning, and execution controls

### Requirement: Discoverable installed workflow
Help and English documentation SHALL show setup, target selection, diagnosis, filament slot inventory, inspection, upload, plan, start, watch, pause/resume/cancel lifecycle controls, and local job history examples, including global option placement and execution guards. Python and Debian packages SHALL expose the same help, formats and completion generator outside the checkout using declared dependencies.

#### Scenario: Installed acceptance
- **WHEN** clean supported installations exercise help, version, completion, local inspection, invalid commands and synthetic diagnosis
- **THEN** their output contracts and exit codes match source execution without contacting real hardware

#### Scenario: Discover watch offline
- **WHEN** installed help or shell completion is generated without a printer configuration
- **THEN** it exposes `print watch` and its timeout option without contacting a printer

## ADDED Requirements

### Requirement: Discover filament slot inventory
Installed help and English documentation SHALL expose `slots list` as a read-only command for the qualified Kobra X onboard four-slot box, and SHALL document the multicolor filament/color fields reported by offline `gcode inspect`. Offline bash, zsh, and fish completion SHALL expose `slots` and `list` without configuration, state writes, or printer access.

#### Scenario: Discover slots offline on clean installation
- **WHEN** `slots --help`, `slots list --help`, or `completion bash|zsh|fish` runs without a printer configuration or state directory
- **THEN** help and generated completions expose `slots` and `list` with no network access and no state writes
