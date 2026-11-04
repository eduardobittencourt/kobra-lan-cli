## MODIFIED Requirements

### Requirement: Machine-readable profile contract
Profile commands SHALL emit readable sanitized text by default or one shared versioned JSON envelope with global `--json` on stdout and use exit 0 for success, 2 for validation/selection errors and 3 for local configuration or I/O failures. Prompts SHALL use stderr. Profile results SHALL follow the shared CLI schema; exit conventions and operational state SHALL remain unchanged.

#### Scenario: Scripted local selection and removal
- **WHEN** a script invokes `printer use` or confirmed removal
- **THEN** stdout contains the selected text result or one shared JSON envelope, stderr carries any prompts, and no secret appears in output or exceptions

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

### Requirement: No implicit destination after default removal
Removing the default SHALL persist null. Commands without a target SHALL then require explicit selection, even when other profiles or arbitrary root config files exist.

#### Scenario: Remove default with legacy config still present
- **WHEN** the selected named profile is removed
- **THEN** no target is implicitly selected and other managed profiles remain available for deliberate selection

## REMOVED Requirements

### Requirement: Legacy access compatibility
**Reason**: The sole owner explicitly rejected all legacy compatibility; fresh named setup is the only supported onboarding.
**Migration**: None. No root configuration or old default is adopted automatically.
