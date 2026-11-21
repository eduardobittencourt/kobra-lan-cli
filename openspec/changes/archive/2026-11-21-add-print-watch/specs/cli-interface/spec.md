# Spec Delta

## MODIFIED Requirements

### Requirement: Canonical command tree
The CLI SHALL expose `printer pair|list|info|use|remove`, `doctor`, `status`, `files list|info|upload`, `gcode inspect`, `print plan|start|watch`, and `completion bash|zsh|fish`. It SHALL remove flat `file`, `upload`, `inspect`, `start` and executable bare `files` without aliases or deprecation shims.

#### Scenario: Removed invocation
- **WHEN** a superseded flat command or bare operational group is invoked
- **THEN** the CLI exits 2 with contextual guidance and performs no network or state mutation

#### Scenario: Group help
- **WHEN** `files --help` or `print --help` is requested
- **THEN** help lists the group's supported operations and distinguishes observation, planning and execution

### Requirement: Consistent errors and exit classes
The CLI SHALL use exit 0 for success, 2 for argument/selection/trust/protocol validation, and 3 for configuration/dependency/I/O/network failure. Foreground interruption of `print watch` SHALL return 130. Operational argument errors with explicit global `--json` SHALL use the machine envelope without argparse usage prose on stdout. Errors SHALL occur before side effects when required execution inputs are missing or malformed.

#### Scenario: Missing execution option
- **WHEN** an execution command omits a required hash or `--execute` in JSON mode
- **THEN** it exits 2 with one sanitized JSON error and no printer access or attempt reservation

#### Scenario: Unknown command in text mode
- **WHEN** an unknown command is supplied
- **THEN** it exits 2 with safe contextual guidance without echoing arbitrary argument values

#### Scenario: Invalid watch timeout
- **WHEN** the watch timeout is malformed or outside the documented bounds
- **THEN** watch exits 2 before network access with one safe error in the selected format

#### Scenario: Interrupted watch in JSON mode
- **WHEN** the user interrupts `print watch` with global `--json`
- **THEN** it exits 130 and stdout holds one failure envelope with a safe partial result when available

### Requirement: Discoverable installed workflow
Help and English documentation SHALL show setup, target selection, diagnosis, inspection, upload, plan, start and watch examples, including global option placement and execution guards. Python and Debian packages SHALL expose the same help, formats and completion generator outside the checkout using declared dependencies.

#### Scenario: Installed acceptance
- **WHEN** clean supported installations exercise help, version, completion, local inspection, invalid commands and synthetic diagnosis
- **THEN** their output contracts and exit codes match source execution without contacting real hardware

#### Scenario: Discover watch offline
- **WHEN** installed help or shell completion is generated without a printer configuration
- **THEN** it exposes `print watch` and its timeout option without contacting a printer
