# Spec Delta

## MODIFIED Requirements

### Requirement: Canonical command tree
The CLI SHALL expose `printer pair|list|info|use|remove`, `doctor`, `status`, `files list|info|upload`, `gcode inspect`, `print plan|start|watch|pause|resume|cancel`, `jobs list|info`, and `completion bash|zsh|fish`. It SHALL remove flat `file`, `upload`, `inspect`, `start` and executable bare `files` without aliases or deprecation shims.

#### Scenario: Removed invocation
- **WHEN** a superseded flat command or bare operational group is invoked
- **THEN** the CLI exits 2 with contextual guidance and performs no network or state mutation

#### Scenario: Group help
- **WHEN** `files --help`, `print --help`, or `jobs --help` is requested
- **THEN** help lists the group's supported operations and distinguishes local history inspection, network observation, planning, and execution controls

### Requirement: Discoverable installed workflow
Help and English documentation SHALL show setup, target selection, diagnosis, inspection, upload, plan, start, watch, pause/resume/cancel lifecycle controls, and local job history examples, including global option placement and execution guards. Python and Debian packages SHALL expose the same help, formats and completion generator outside the checkout using declared dependencies.

#### Scenario: Installed acceptance
- **WHEN** clean supported installations exercise help, version, completion, local inspection, invalid commands and synthetic diagnosis
- **THEN** their output contracts and exit codes match source execution without contacting real hardware

#### Scenario: Discover watch offline
- **WHEN** installed help or shell completion is generated without a printer configuration
- **THEN** it exposes `print watch` and its timeout option without contacting a printer

## ADDED Requirements

### Requirement: Discover print lifecycle controls
Installed help and English documentation SHALL expose `print pause`, `print resume`, and `print cancel` with `--execute` and optional `--filename`, stating experimental qualification and non-replay uncertainty guidance. Offline bash, zsh, and fish completion SHALL expose `pause`, `resume`, `cancel`, `--execute`, and `--filename` under `print` without configuration, state writes, or printer access.

#### Scenario: Discover lifecycle controls offline on clean installation
- **WHEN** `print --help`, `print pause --help`, `print resume --help`, `print cancel --help`, or `completion bash|zsh|fish` runs without a printer configuration or state directory
- **THEN** help and generated completions expose `pause`, `resume`, `cancel`, `--execute`, and `--filename` with no network access and no state writes
