# cli-interface Specification

## Purpose

Provide a discoverable CLI for people and automation with deliberate commands, predictable presentation and installed shell assistance.

## Requirements

### Requirement: Canonical command tree
The CLI SHALL expose `printer pair|list|info|use|remove`, `doctor`, `status`, `files list|info|upload`, `gcode inspect`, `print plan|start`, and `completion bash|zsh|fish`. It SHALL remove flat `file`, `upload`, `inspect`, `start` and executable bare `files` without aliases or deprecation shims.

#### Scenario: Removed invocation
- **WHEN** a superseded flat command or bare operational group is invoked
- **THEN** the CLI exits 2 with contextual guidance and performs no network or state mutation

#### Scenario: Group help
- **WHEN** `files --help` or `print --help` is requested
- **THEN** help lists the group's supported operations and distinguishes observation, planning and execution

### Requirement: Deterministic presentation
Operational commands SHALL emit readable English text by default and one JSON document when global `--json` is supplied before the command. Piping SHALL NOT change the selected format. Prompts and progress SHALL use stderr. Help, version and completion SHALL retain their native textual formats.

#### Scenario: Piped output
- **WHEN** `status` runs with redirected stdout, with and without `--json`
- **THEN** default output remains text and explicit JSON remains a single parseable document without progress or prompts

#### Scenario: Same operation in either format
- **WHEN** identical synthetic responses are rendered in text and JSON
- **THEN** both expose equivalent outcomes and qualification limits without extra network requests or state writes for presentation

### Requirement: Versioned machine envelope
Operational JSON SHALL contain integer `schema_version: 1` and boolean `ok`. Success SHALL contain `result`; failure SHALL contain `error` with documented stable `code` and safe `message`, and SHALL retain a safe partial `result` when available. Output SHALL exclude secrets, raw private configuration and token-bearing URLs.

#### Scenario: Failed diagnosis with partial result
- **WHEN** a doctor stage fails in JSON mode
- **THEN** one failure envelope contains the ordered checks and health result alongside a safe error code and message

#### Scenario: Unsafe failure input
- **WHEN** parsing or execution fails on synthetic input containing a token-bearing URL or private data
- **THEN** neither output stream nor exception text exposes that sensitive input

### Requirement: Consistent errors and exit classes
The CLI SHALL use exit 0 for success, 2 for argument/selection/trust/protocol validation, and 3 for configuration/dependency/I/O/network failure. Operational argument errors with explicit global `--json` SHALL use the machine envelope without argparse usage prose on stdout. Errors SHALL occur before side effects when required execution inputs are missing or malformed.

#### Scenario: Missing execution option
- **WHEN** an execution command omits a required hash or `--execute` in JSON mode
- **THEN** it exits 2 with one sanitized JSON error and no printer access or attempt reservation

#### Scenario: Unknown command in text mode
- **WHEN** an unknown command is supplied
- **THEN** it exits 2 with safe contextual guidance without echoing arbitrary argument values

### Requirement: Uniform target and interaction rules
Target-dependent commands SHALL share explicit selectors and a saved named default, honoring --state-dir. Root options SHALL precede commands. No default SHALL require explicit selection; root configs SHALL NOT be discovered. Broken selections SHALL NOT try another target. Pairing SHALL require --name and reject selectors. Format SHALL NOT grant consent or physical authorization.

#### Scenario: Noninteractive confirmation
- **WHEN** named pairing lacks a trusted fingerprint or removal lacks `--yes` without a terminal
- **THEN** it refuses without hanging or treating JSON/text selection as consent

#### Scenario: Shared selected target
- **WHEN** status, files or print commands select the same named profile
- **THEN** they use the same access selection and device-based state without implicit destination changes

### Requirement: Offline shell completion
`completion <shell>` SHALL emit an installable script for bash, zsh or fish without config, network or state writes. Completion SHALL cover canonical commands, flags, fixed choices and local file arguments. It SHALL NOT query printers, provision access or inspect private credential contents; dynamic printer-name discovery is outside this contract.

#### Scenario: Fresh installation completion
- **WHEN** completion is generated and sourced for a supported shell without configuration
- **THEN** canonical commands and options can be completed offline without contacting any printer

### Requirement: Discoverable installed workflow
Help and English documentation SHALL show setup, target selection, diagnosis, inspection, upload, plan and start examples, including global option placement and execution guards. Python and Debian packages SHALL expose the same help, formats and completion generator outside the checkout using declared dependencies.

#### Scenario: Installed acceptance
- **WHEN** clean supported installations exercise help, version, completion, local inspection, invalid commands and synthetic diagnosis
- **THEN** their output contracts and exit codes match source execution without contacting real hardware
