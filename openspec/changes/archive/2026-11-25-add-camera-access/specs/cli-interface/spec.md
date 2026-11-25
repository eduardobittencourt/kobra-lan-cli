# Spec Delta: cli-interface

## MODIFIED Requirements

### Requirement: Canonical command tree
The CLI SHALL expose `printer pair|list|info|use|remove`, `doctor`, `status`, `slots list`, `camera status|snapshot|pipe`, `files list|info|upload|delete`, `gcode inspect`, `print plan|start|watch|pause|resume|cancel`, `jobs list|info`, and `completion bash|zsh|fish`. It SHALL remove flat `file`, `upload`, `inspect`, `start` and executable bare `files` without aliases or deprecation shims. Bare `slots` and bare `camera` without a subcommand SHALL fail with exit 2 and contextual help.

#### Scenario: Removed invocation
- **WHEN** a superseded flat command or bare operational group (including bare `slots` or bare `camera`) is invoked
- **THEN** the CLI exits 2 with contextual guidance and performs no network or state mutation

#### Scenario: Group help
- **WHEN** `files --help`, `slots --help`, `camera --help`, `print --help`, or `jobs --help` is requested
- **THEN** help lists the group's supported operations and distinguishes read-only inspection, snapshot/stream capture (including optional `startCapture`/`stopCapture` fallback and `--no-start-capture`), local history inspection, network observation, planning, and execution controls (including explicit `--execute` storage deletion under `files`)

### Requirement: Deterministic presentation
Operational commands SHALL emit readable English text by default and one JSON document when global `--json` is supplied before the command, EXCEPT `camera pipe`, which writes raw binary HTTP-FLV bytes to stdout and SHALL reject global `--json` with exit 2 before target selection or network access. Piping SHALL NOT change the selected format. Prompts, progress, and `camera pipe` diagnostics SHALL use stderr. Help, version and completion SHALL retain their native textual formats.

#### Scenario: Piped output
- **WHEN** `status` runs with redirected stdout, with and without `--json`
- **THEN** default output remains text and explicit JSON remains a single parseable document without progress or prompts

#### Scenario: Same operation in either format
- **WHEN** identical synthetic responses for `status`, `camera status`, or `camera snapshot` are rendered in text and JSON
- **THEN** both expose equivalent outcomes and qualification limits without extra network requests or state writes for presentation

#### Scenario: Camera pipe rejects global --json before printer access
- **WHEN** `kobra-lan --json camera pipe` is invoked
- **THEN** the CLI exits 2 (`invalid_arguments`) with one safe JSON error envelope on stdout and performs no target lookup or network access

### Requirement: Consistent errors and exit classes
The CLI SHALL use exit 0 for success (and `camera pipe` downstream pipe closure), 2 for argument/selection/trust/protocol validation, 3 for configuration/dependency/I/O/network failure, and 130 for foreground interruption of `print watch` or `camera pipe`. Operational argument errors with global `--json` SHALL use the machine envelope without argparse usage prose on stdout, and SHALL fail before side effects.

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

#### Scenario: Missing ffmpeg dependency on camera snapshot
- **WHEN** `camera snapshot --output frame.jpg` runs without `ffmpeg` available on `PATH` in text or JSON mode
- **THEN** the CLI exits 3 (`operation_failed`) before network access with one safe error in the selected format

### Requirement: Discoverable installed workflow
Help and English documentation SHALL show setup, target selection, diagnosis, filament slot inventory, camera inspection/snapshot/piping, inspection, upload, stored-file deletion, plan, start, watch, pause/resume/cancel lifecycle controls, and local job history examples, including global option placement and execution guards. Python and Debian packages SHALL expose the same help, formats and completion generator outside the checkout using declared dependencies.

#### Scenario: Installed acceptance
- **WHEN** clean supported installations exercise help, version, completion, local inspection, invalid commands and synthetic diagnosis
- **THEN** their output contracts and exit codes match source execution without contacting real hardware

#### Scenario: Discover watch offline
- **WHEN** installed help or shell completion is generated without a printer configuration
- **THEN** it exposes `print watch` and its timeout option without contacting a printer

## ADDED Requirements

### Requirement: Discover camera access
Installed help and English documentation SHALL expose `camera status`, `camera snapshot` (`--output`, `--timeout`, `--overwrite`, `--no-start-capture`), and `camera pipe` (`--timeout`, `--max-bytes`, `--no-start-capture`), noting optional external `ffmpeg` for `snapshot`, token redaction, and read-only-first capture. Offline bash, zsh, and fish completion SHALL expose `camera` subcommands and flags (with file completion for `--output`) without configuration or network access.

#### Scenario: Discover camera offline on clean installation
- **WHEN** `camera --help`, `camera status --help`, `camera snapshot --help`, `camera pipe --help`, or `completion bash|zsh|fish` runs without a printer configuration, state directory, or `ffmpeg` installed
- **THEN** help and generated completions expose `camera`, `status`, `snapshot`, `pipe`, `--output`, `--timeout`, `--overwrite`, `--max-bytes`, and `--no-start-capture` with no network access and no state writes
