# Spec Delta

## Purpose

Let users manage named local printer connections and select a predictable target while preserving legacy access, private material and device-based operational safeguards.

## ADDED Requirements

### Requirement: Offline local inventory
`printer list` SHALL list registered profile names, saved addresses, known model identity and default status without network access. An empty inventory SHALL succeed. Missing or invalid profile files SHALL be identified locally without hiding healthy entries or claiming live reachability.

#### Scenario: Printers are offline
- **WHEN** registered printers are unreachable and the user runs `printer list`
- **THEN** the command returns the local inventory without opening sockets or reporting cached information as live status

#### Scenario: Empty or partially damaged inventory
- **WHEN** no named profiles exist or one registered config is missing
- **THEN** the command returns an empty list or marks the affected entry unavailable while retaining other entries

### Requirement: Local profile inspection
`printer info [name]` SHALL show the selected profile's name, address, saved identity, accepted TLS fingerprint, default status and configuration source without network access. Saved firmware, if available, SHALL be labeled as last observed. It SHALL NOT expose credentials, private key contents, certificate bodies or raw configuration.

#### Scenario: Inspect an offline profile
- **WHEN** the user runs `printer info bancada` while that printer is off
- **THEN** saved safe metadata is returned with no live-state claim and no network access

#### Scenario: Omitted name
- **WHEN** `printer info` has no positional name
- **THEN** it uses the same target selection rules as `status`

### Requirement: Deterministic target selection
Explicit `--config` and `--printer` SHALL be mutually exclusive. An explicit selector SHALL override the saved default, which SHALL override legacy fallback when fallback is enabled. Unknown, broken or unavailable selections SHALL fail without trying another printer. A positional profile name combined with a global selector SHALL be rejected before side effects.

#### Scenario: Temporary override
- **WHEN** bancada is default and `--printer oficina status` is invoked
- **THEN** only oficina is contacted and the saved default remains bancada

#### Scenario: Conflicting selectors
- **WHEN** `--config` and `--printer` are supplied together, or `printer info bancada` is combined with a global selector
- **THEN** the invocation fails with exit 2 before network or filesystem mutation

#### Scenario: Broken selected target
- **WHEN** an explicit profile or saved default has a missing config or cannot connect
- **THEN** the command fails for that target without falling back to legacy or another profile

### Requirement: Persistent local default
`printer use <name>` SHALL persist an existing registered profile as the default without contacting a printer. It SHALL validate that the local profile is loadable before changing the default. Failure SHALL preserve the previous selection. Registering a profile SHALL NOT implicitly select it.

#### Scenario: Select an offline printer
- **WHEN** oficina has a valid local config but is powered off and `printer use oficina` runs
- **THEN** it becomes the persistent default without network access

#### Scenario: Invalid profile
- **WHEN** the requested profile is unknown or locally invalid
- **THEN** the command fails without modifying the saved default

### Requirement: Legacy access compatibility
Existing `~/.config/kobra-lan/config.json` and explicit `--config` invocations SHALL remain usable without new pairing, rewriting credentials, or moving private files. Before a named default is selected, unqualified operations SHALL retain legacy selection. Local inspection SHALL identify legacy access separately from managed named profiles.

#### Scenario: Existing installation
- **WHEN** the profile registry does not exist and the old config exists
- **THEN** existing unqualified commands use the old config and list/info can describe that access without creating a registry

#### Scenario: Explicit legacy selection after adopting profiles
- **WHEN** a named default exists and the user supplies `--config` pointing to the old config
- **THEN** the old config is used and the named default is unchanged

### Requirement: Confirmed local removal
`printer remove <name>` SHALL describe local files to remove and require affirmative terminal confirmation or explicit `--yes`. Refusal, EOF or noninteractive invocation without `--yes` SHALL leave files unchanged. Removal SHALL NOT contact the printer, revoke credentials or delete operational history. Unmanaged legacy configs SHALL NOT be removable through this command.

#### Scenario: Unattended refusal
- **WHEN** removal runs without a terminal or `--yes`
- **THEN** it fails without hanging or deleting any profile data

#### Scenario: Confirmed removal
- **WHEN** the user confirms the displayed managed profile removal
- **THEN** its registration and exclusively owned managed files are removed, preserved files are reported, and the result states that device credentials were not revoked

### Requirement: No implicit destination after default removal
Removing the selected default SHALL persist an explicit unselected state. Subsequent target-dependent commands without an explicit selector SHALL fail with instructions to select a profile or config, even if legacy access or other profiles exist. Removing a nondefault profile SHALL preserve the selected default.

#### Scenario: Remove default with legacy config still present
- **WHEN** bancada is default, legacy config exists and bancada is removed
- **THEN** `status` refuses implicit selection until `printer use` is invoked, while explicit `--config` or `--printer` remains usable

### Requirement: Private crash-safe profile management
Profile storage SHALL use user-owned private directories and files, reject unsafe names and symlink destinations, prevent replacement of existing profiles and serialize conflicting local mutations. Interrupted writes SHALL leave a complete registry or a recoverable failure. Removal SHALL retain shared, external or uncertain-ownership files and SHALL NOT invalidate an operation already using the selected profile.

#### Scenario: Unsafe destination or concurrent writers
- **WHEN** a profile name escapes its storage root, a destination is a symlink or two writers contend for the same name
- **THEN** invalid operations fail before provisioning and only one complete profile can become registered without replacing existing data

#### Scenario: Interrupted removal or shared files
- **WHEN** deletion encounters shared PEMs, uncertain ownership, an active profile user or a filesystem failure
- **THEN** shared/uncertain material and active access are preserved, the command reports the outcome, and no partial state silently selects another target

### Requirement: Preserve device-based duplicate protection
Profile names and default changes SHALL NOT change receipt or attempt identities. Existing `--state-dir` behavior and device-based state paths SHALL remain compatible. Removal and re-pairing SHALL preserve operational markers, including uncertain outcomes.

#### Scenario: Same device through another profile
- **WHEN** the same printer is accessed through two profiles or re-paired after local profile removal
- **THEN** the same existing device/file attempt markers still block a duplicate upload or start

### Requirement: Machine-readable profile contract
New profile commands SHALL emit one sanitized JSON result on stdout and use exit 0 for success, 2 for validation/selection errors and 3 for local configuration or I/O failures. Prompts SHALL use stderr. Existing operational JSON schemas and exit conventions SHALL remain unchanged.

#### Scenario: Scripted local selection and removal
- **WHEN** a script invokes `printer use` or confirmed removal
- **THEN** stdout contains one JSON result, stderr carries any prompts, and no secret appears in output or exceptions
