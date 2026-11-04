## MODIFIED Requirements

### Requirement: Sanitized machine-readable results
Pairing SHALL use the shared CLI text default and opt-in versioned JSON envelope, retaining exit conventions: 0 success, 2 protocol/validation/trust errors, and 3 local configuration or network failures. Human trust prompts SHALL use stderr. Diagnostics SHALL distinguish failure stages without exposing passwords, tokens, private keys, certificate bodies, tokenized URLs, or raw provisioning responses.

#### Scenario: Successful pairing result
- **WHEN** pairing succeeds
- **THEN** stdout contains a readable success result by default or one success JSON envelope with `--json`, including the config path, model, firmware, and accepted fingerprint, without credential values

#### Scenario: Sanitized failure
- **WHEN** provisioning, trust, authentication, compatibility, or persistence fails
- **THEN** stdout contains a safe failure result in the selected format, using the shared error envelope with `--json`, and a nonzero exit status with a safe stage-specific diagnostic

### Requirement: Named pairing preservation and result
Named pairing SHALL retain existing no-overwrite, private permissions, explicit trust, sanitized shared text/opt-in JSON output and exit conventions. Success SHALL add profile name and default outcome to the named-flow result; unnamed pairing SHALL be rejected before provisioning. Reusing the same device through another name SHALL NOT reset receipt/attempt protection.

#### Scenario: Two names for one device
- **WHEN** the same qualified device is paired under another unused name
- **THEN** its original access and device-based markers remain unchanged and the new name does not authorize replay of a prior attempt

#### Scenario: No trust bypass
- **WHEN** unattended named pairing omits an exact trusted fingerprint
- **THEN** it refuses without saving or selecting a profile, even if profile removal supports `--yes`

### Requirement: Explicit address onboarding
The CLI SHALL provide `printer pair --name <name> --host <IPv4>` to obtain credentials directly from an already LAN-enabled printer without another integration. `--name` SHALL be required; global `--config` and `--printer` SHALL be rejected for pairing.

#### Scenario: Fresh installation
- **WHEN** a new name and bare IPv4 address are supplied with explicit initial trust
- **THEN** pairing verifies the supported target and publishes a private named profile

#### Scenario: Missing name or conflicting selector
- **WHEN** pairing omits --name or supplies a global target selector
- **THEN** it exits 2 before provisioning, config publication or local storage creation

#### Scenario: Invalid address
- **WHEN** the supplied host is not a bare IPv4 address
- **THEN** named pairing fails before network access with a safe address diagnostic

### Requirement: Named pairing destination
Every CLI pairing SHALL create a managed named profile only after trust acceptance, pinned authentication and fresh qualified status. Invalid or existing names SHALL fail before provisioning. There SHALL be no unnamed destination, automatic root-config lookup or compatibility migration.

#### Scenario: Invalid or duplicate name
- **WHEN** the requested name is already registered or its managed destination exists
- **THEN** pairing refuses before network access without replacing private files

#### Scenario: Pair a new named printer
- **WHEN** a new valid name is provided and trust/status verification succeeds
- **THEN** a complete private config is published and listed without replacing other managed access

#### Scenario: Existing unnamed automation
- **WHEN** printer pair is invoked without --name, with or without --config
- **THEN** it fails before provisioning; no compatibility path or migration is provided

### Requirement: Preserve existing access and operational state
Pairing SHALL refuse existing managed destinations and concurrent replacement, and preserve all other managed profiles and device-based receipts and attempt markers. A new unused name SHALL be required for an independent pairing.

#### Scenario: Already configured installation
- **WHEN** a requested named destination already exists, including a symlink
- **THEN** pairing fails before provisioning and directs the owner to inspect that profile or choose another unused name

#### Scenario: Concurrent destination creation
- **WHEN** another writer creates the managed destination before publication
- **THEN** pairing refuses replacement, preserves the complete existing file and reports the local outcome

#### Scenario: Separate setup
- **WHEN** the owner pairs using another unused --name
- **THEN** a separate managed destination is used without changing other profiles or device markers
