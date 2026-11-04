# printer-profiles Specification

## Purpose

Let users manage named local printer connections and select a predictable target while preserving private material and device-based operational safeguards.

## Requirements

### Requirement: Offline local inventory
Inventory SHALL contain only registered profiles and the saved named default or null. It SHALL return an empty profiles array successfully on a fresh setup, with no legacy section or root-config discovery.

#### Scenario: Fresh inventory
- **WHEN** no named profiles exist
- **THEN** list succeeds locally with profiles empty and default null, without creating storage

#### Scenario: Printers are offline
- **WHEN** registered printers are unreachable and printer list runs
- **THEN** the local inventory is returned without sockets or a live-reachability claim

#### Scenario: Empty or partially damaged inventory
- **WHEN** no profiles exist or a registered config is damaged
- **THEN** inventory is empty or marks only the affected profile unavailable

### Requirement: Local profile inspection
`printer info [name]` SHALL show the selected profile's name, address, saved identity, accepted TLS fingerprint, default status and configuration source without network access. Saved firmware, if available, SHALL be labeled as last observed. It SHALL NOT expose credentials, private key contents, certificate bodies or raw configuration.

#### Scenario: Inspect an offline profile
- **WHEN** the user runs `printer info bancada` while that printer is off
- **THEN** saved safe metadata is returned with no live-state claim and no network access

#### Scenario: Omitted name
- **WHEN** `printer info` has no positional name
- **THEN** it uses the same target selection rules as `status`

### Requirement: Deterministic target selection
Explicit --config and --printer SHALL be mutually exclusive and override a saved named default. With no named default or explicit selector, target-dependent commands SHALL fail with selection guidance. Root config files SHALL never be loaded automatically; old default strings SHALL be rejected without migration. Broken targets SHALL fail without trying another target.

#### Scenario: Empty setup with stray root config
- **WHEN** the registry is absent or has a null default, even if a root config.json exists
- **THEN** status refuses selection without network or state writes

#### Scenario: Explicit access
- **WHEN** --printer or --config selects a valid target
- **THEN** only that target is used and the saved default remains unchanged

#### Scenario: Temporary override
- **WHEN** bancada is default and --printer oficina status is invoked
- **THEN** only oficina is contacted and the default remains bancada

#### Scenario: Conflicting selectors
- **WHEN** --config and --printer are combined, or printer info NAME has a global selector
- **THEN** the invocation fails with exit 2 before network or filesystem mutation

#### Scenario: Broken selected target
- **WHEN** an explicit target or saved named default is missing or unavailable
- **THEN** the command fails without trying any other profile or root config

### Requirement: Persistent local default
`printer use <name>` SHALL persist an existing registered profile as the default without contacting a printer. It SHALL validate that the local profile is loadable before changing the default. Failure SHALL preserve the previous selection. Registering a profile SHALL NOT implicitly select it.

#### Scenario: Select an offline printer
- **WHEN** oficina has a valid local config but is powered off and `printer use oficina` runs
- **THEN** it becomes the persistent default without network access

#### Scenario: Invalid profile
- **WHEN** the requested profile is unknown or locally invalid
- **THEN** the command fails without modifying the saved default

### Requirement: Confirmed local removal
`printer remove <name>` SHALL describe local files to remove and require affirmative terminal confirmation or explicit `--yes`. Refusal, EOF or noninteractive invocation without `--yes` SHALL leave files unchanged. Removal SHALL NOT contact the printer, revoke credentials or delete operational history. Unmanaged legacy configs SHALL NOT be removable through this command.

#### Scenario: Unattended refusal
- **WHEN** removal runs without a terminal or `--yes`
- **THEN** it fails without hanging or deleting any profile data

#### Scenario: Confirmed removal
- **WHEN** the user confirms the displayed managed profile removal
- **THEN** its registration and exclusively owned managed files are removed, preserved files are reported, and the result states that device credentials were not revoked

### Requirement: No implicit destination after default removal
Removing the default SHALL persist null. Commands without a target SHALL then require explicit selection, even when other profiles or arbitrary root config files exist.

#### Scenario: Remove default with legacy config still present
- **WHEN** the selected named profile is removed
- **THEN** no target is implicitly selected and other managed profiles remain available for deliberate selection

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
Profile commands SHALL emit readable sanitized text by default or one shared versioned JSON envelope with global `--json` on stdout and use exit 0 for success, 2 for validation/selection errors and 3 for local configuration or I/O failures. Prompts SHALL use stderr. Profile results SHALL follow the shared CLI schema; exit conventions and operational state SHALL remain unchanged.

#### Scenario: Scripted local selection and removal
- **WHEN** a script invokes `printer use` or confirmed removal
- **THEN** stdout contains the selected text result or one shared JSON envelope, stderr carries any prompts, and no secret appears in output or exceptions
