# cli-interface Specification

## Purpose

Provide a discoverable CLI for people and automation with deliberate commands, predictable presentation and installed shell assistance.

## Requirements

### Requirement: Canonical command tree
The CLI SHALL expose `printer pair|list|info|use|remove`, `doctor`, `status`, `slots list`, `files list|info|upload`, `gcode inspect`, `print plan|start|watch|pause|resume|cancel`, `jobs list|info`, and `completion bash|zsh|fish`. It SHALL remove flat `file`, `upload`, `inspect`, `start` and executable bare `files` without aliases or deprecation shims. Bare `slots` without a subcommand SHALL fail with exit 2 and contextual help.

#### Scenario: Removed invocation
- **WHEN** a superseded flat command or bare operational group (including bare `slots`) is invoked
- **THEN** the CLI exits 2 with contextual guidance and performs no network or state mutation

#### Scenario: Group help
- **WHEN** `files --help`, `slots --help`, `print --help`, or `jobs --help` is requested
- **THEN** help lists the group's supported operations and distinguishes read-only inventory, local history inspection, network observation, planning, and execution controls

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
Help and English documentation SHALL show setup, target selection, diagnosis, filament slot inventory, inspection, upload, plan, start, watch, pause/resume/cancel lifecycle controls, and local job history examples, including global option placement and execution guards. Python and Debian packages SHALL expose the same help, formats and completion generator outside the checkout using declared dependencies.

#### Scenario: Installed acceptance
- **WHEN** clean supported installations exercise help, version, completion, local inspection, invalid commands and synthetic diagnosis
- **THEN** their output contracts and exit codes match source execution without contacting real hardware

#### Scenario: Discover watch offline
- **WHEN** installed help or shell completion is generated without a printer configuration
- **THEN** it exposes `print watch` and its timeout option without contacting a printer

### Requirement: Discover intentional reprint workflow
Installed help and documentation SHALL show `--reprint-from` on `print plan` and `print start`, explain where to find the prior local attempt reference and show how to review and explicitly execute a reprint. Offline bash, zsh and fish completion SHALL offer the flag on both commands.

#### Scenario: Installed CLI without printer configuration
- **WHEN** help is requested for `print plan` or `print start`, or shell completion is generated on a clean installation
- **THEN** the relevant help and completions expose the flag without network access or state writes

#### Scenario: Invalid predecessor reference
- **WHEN** `--reprint-from` is supplied with a malformed value in text or JSON mode
- **THEN** the CLI exits 2 before printer access or reservation and emits a safe error in the selected format

### Requirement: Discover local job history workflow
Installed help and documentation SHALL show `jobs list` (`--kind`, `--limit`) and `jobs info <record-id>`, explain local-only coverage and unattributed watch observations, and note how to locate `attempt_id` for `--reprint-from`. Offline bash, zsh, and fish completion SHALL expose `jobs`, `list`, `info`, `--kind` choices, and `--limit` without reading state or contacting a printer.

#### Scenario: Discover jobs offline on clean installation
- **WHEN** `jobs --help`, `jobs list --help`, `jobs info --help`, or shell completion is requested without a printer configuration or state directory
- **THEN** the help and completion scripts expose `jobs list`, `jobs info`, `--kind` choices (`all`, `start`, `observation`), and `--limit` without network access or state writes

### Requirement: Discover print lifecycle controls
Installed help and English documentation SHALL expose `print pause`, `print resume`, and `print cancel` with `--execute` and optional `--filename`, stating experimental qualification and non-replay uncertainty guidance. Offline bash, zsh, and fish completion SHALL expose `pause`, `resume`, `cancel`, `--execute`, and `--filename` under `print` without configuration, state writes, or printer access.

#### Scenario: Discover lifecycle controls offline on clean installation
- **WHEN** `print --help`, `print pause --help`, `print resume --help`, `print cancel --help`, or `completion bash|zsh|fish` runs without a printer configuration or state directory
- **THEN** help and generated completions expose `pause`, `resume`, `cancel`, `--execute`, and `--filename` with no network access and no state writes

### Requirement: Discover filament slot inventory
Installed help and English documentation SHALL expose `slots list` as a read-only command for the qualified Kobra X onboard four-slot box, and SHALL document the multicolor filament/color fields reported by offline `gcode inspect`. Offline bash, zsh, and fish completion SHALL expose `slots` and `list` without configuration, state writes, or printer access.

#### Scenario: Discover slots offline on clean installation
- **WHEN** `slots --help`, `slots list --help`, or `completion bash|zsh|fish` runs without a printer configuration or state directory
- **THEN** help and generated completions expose `slots` and `list` with no network access and no state writes
