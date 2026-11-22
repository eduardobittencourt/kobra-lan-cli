# Spec Delta

## MODIFIED Requirements

### Requirement: Canonical command tree
The CLI SHALL expose `printer pair|list|info|use|remove`, `doctor`, `status`, `files list|info|upload`, `gcode inspect`, `print plan|start|watch`, `jobs list|info`, and `completion bash|zsh|fish`. It SHALL remove flat `file`, `upload`, `inspect`, `start` and executable bare `files` without aliases or deprecation shims.

#### Scenario: Removed invocation
- **WHEN** a superseded flat command or bare operational group is invoked
- **THEN** the CLI exits 2 with contextual guidance and performs no network or state mutation

#### Scenario: Group help
- **WHEN** `files --help`, `print --help`, or `jobs --help` is requested
- **THEN** help lists the group's supported operations and distinguishes local history inspection, network observation, planning, and execution

### Requirement: Discoverable installed workflow
Help and English documentation SHALL show setup, target selection, diagnosis, inspection, upload, plan, start, watch, and local job history examples, including global option placement and execution guards. Python and Debian packages SHALL expose the same help, formats and completion generator outside the checkout using declared dependencies.

#### Scenario: Installed acceptance
- **WHEN** clean supported installations exercise help, version, completion, local inspection, invalid commands and synthetic diagnosis
- **THEN** their output contracts and exit codes match source execution without contacting real hardware

#### Scenario: Discover watch offline
- **WHEN** installed help or shell completion is generated without a printer configuration
- **THEN** it exposes `print watch` and its timeout option without contacting a printer

## ADDED Requirements

### Requirement: Discover local job history workflow
Installed help and documentation SHALL show `jobs list` (`--kind`, `--limit`) and `jobs info <record-id>`, explain local-only coverage and unattributed watch observations, and note how to locate `attempt_id` for `--reprint-from`. Offline bash, zsh, and fish completion SHALL expose `jobs`, `list`, `info`, `--kind` choices, and `--limit` without reading state or contacting a printer.

#### Scenario: Discover jobs offline on clean installation
- **WHEN** `jobs --help`, `jobs list --help`, `jobs info --help`, or shell completion is requested without a printer configuration or state directory
- **THEN** the help and completion scripts expose `jobs list`, `jobs info`, `--kind` choices (`all`, `start`, `observation`), and `--limit` without network access or state writes
