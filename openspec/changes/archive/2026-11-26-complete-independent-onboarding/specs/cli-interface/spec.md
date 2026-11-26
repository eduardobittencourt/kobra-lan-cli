# Spec Delta

## MODIFIED Requirements

### Requirement: Canonical command tree
The CLI SHALL expose `printer discover|pair|list|info|use|remove`, `doctor`, `status`, `slots list`, `camera status|snapshot|pipe`, `files list|info|upload|delete`, `gcode inspect`, `print plan|start|watch|pause|resume|cancel`, `jobs list|info`, and `completion bash|zsh|fish`. It SHALL remove flat `file`, `upload`, `inspect`, `start` and executable bare `files` without aliases or deprecation shims. Bare `slots`, bare `camera`, and bare `printer` without a subcommand SHALL fail with exit 2 and contextual help.

#### Scenario: Removed invocation
- **WHEN** a superseded flat command or bare operational group (including bare `printer`, bare `slots`, or bare `camera`) is invoked
- **THEN** the CLI exits 2 with contextual guidance and performs no network or state mutation

#### Scenario: Group help
- **WHEN** `printer --help`, `files --help`, `slots --help`, `camera --help`, `print --help`, or `jobs --help` is requested
- **THEN** help lists the group's supported operations and distinguishes read-only discovery/inspection, pairing, snapshot/stream capture (including optional `startCapture`/`stopCapture` fallback and `--no-start-capture`), local history inspection, network observation, planning, and execution controls (including explicit `--execute` storage deletion under `files`)

### Requirement: Consistent errors and exit classes
The CLI SHALL use exit 0 for success (and `camera pipe` downstream pipe closure), 2 for argument/selection/trust/protocol validation, 3 for configuration/dependency/I/O/network failure, and 130 for foreground interruption of `printer discover`, `print watch`, or `camera pipe`. Operational argument errors with global `--json` SHALL use the machine envelope without argparse usage prose on stdout, and SHALL fail before side effects.

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

#### Scenario: Interrupted discovery in JSON mode
- **WHEN** the user interrupts `printer discover` with global `--json`
- **THEN** it exits 130 and stdout holds one failure envelope (`code: "interrupted"`)

#### Scenario: Missing ffmpeg dependency on camera snapshot
- **WHEN** `camera snapshot --output frame.jpg` runs without `ffmpeg` available on `PATH` in text or JSON mode
- **THEN** the CLI exits 3 (`operation_failed`) before network access with one safe error in the selected format

### Requirement: Discoverable installed workflow
Help and English documentation SHALL show LAN discovery, setup, target selection, diagnosis, filament slot inventory, camera inspection/snapshot/piping, inspection, upload, stored-file deletion, plan, start, watch, pause/resume/cancel lifecycle controls, and local job history examples, including global option placement and execution guards. Python and Debian packages SHALL expose the same help, formats and completion generator outside the checkout using declared dependencies.

#### Scenario: Installed acceptance
- **WHEN** clean supported installations exercise help, version, completion, local inspection, invalid commands and synthetic diagnosis
- **THEN** their output contracts and exit codes match source execution without contacting real hardware

#### Scenario: Discover watch offline
- **WHEN** installed help or shell completion is generated without a printer configuration
- **THEN** it exposes `print watch` and its timeout option without contacting a printer

## ADDED Requirements

### Requirement: Discover LAN printer discovery
Installed help and English documentation SHALL expose `printer discover` with optional `--timeout` and `--interface`, stating that discovery is strictly read-only over same-subnet SSDP multicast (`ac:3dprinter:fdm`), unauthenticated, does not verify firmware, and never pairs automatically. Offline bash, zsh, and fish completion SHALL expose `discover`, `--timeout`, and `--interface` under `printer` without configuration, state writes, or network access.

#### Scenario: Discover printer discover offline on clean installation
- **WHEN** `printer --help`, `printer discover --help`, or `completion bash|zsh|fish` runs without a printer configuration or state directory
- **THEN** help and generated completions expose `discover`, `--timeout`, and `--interface` under `printer` with no network access and no state writes
