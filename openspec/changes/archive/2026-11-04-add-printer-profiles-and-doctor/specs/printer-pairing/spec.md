# Spec Delta

## ADDED Requirements

### Requirement: Named pairing destination
`printer pair --name <name> --host <IPv4>` SHALL create a managed profile only after existing trust acceptance, pinned authentication and fresh qualified status verification. Invalid or existing names SHALL be rejected before provisioning. `--name` SHALL be incompatible with explicit `--config` and global `--printer`; omitted `--name` SHALL retain existing unnamed pairing behavior.

#### Scenario: Pair a new named printer
- **WHEN** a new valid name is provided and trust/status verification succeeds
- **THEN** a complete private compatible config is published and becomes visible in the local profile inventory without replacing existing access

#### Scenario: Invalid or duplicate name
- **WHEN** the name is unsafe, already registered or has an existing managed destination
- **THEN** pairing fails before provisioning and preserves the existing destination and all operational state

#### Scenario: Existing unnamed automation
- **WHEN** `printer pair --host` is invoked without a name, optionally with explicit `--config`
- **THEN** it retains the existing absent-destination behavior and never redirects pairing into a saved default profile

### Requirement: Optional default on successful named pairing
Named pairing SHALL accept `--default` to select the successfully registered profile. Without it, pairing SHALL preserve the prior default or explicit unselected state. `--default` without `--name` SHALL fail before network access. Default updates SHALL NOT occur before complete verified profile publication.

#### Scenario: Pair and select
- **WHEN** `printer pair --name bancada --host 192.0.2.10 --default` succeeds
- **THEN** bancada is registered and becomes the persistent default

#### Scenario: Failed pairing
- **WHEN** trust is declined, status fails or profile publication fails
- **THEN** no incomplete profile becomes selectable and the previous default remains unchanged

#### Scenario: Profile committed but default update interrupted
- **WHEN** the verified named config and registration are committed but selecting it fails
- **THEN** the command reports the committed profile and default outcome, preserves its referenced PEMs and instructs the user to inspect locally and use `printer use` rather than repeat provisioning

### Requirement: Named pairing preservation and result
Named pairing SHALL retain existing no-overwrite, private permissions, explicit trust, sanitized JSON and exit conventions. Success SHALL add profile name and default outcome to the named-flow result; unnamed results SHALL remain compatible. Reusing the same device through another name SHALL NOT reset receipt/attempt protection.

#### Scenario: Two names for one device
- **WHEN** the same qualified device is paired under another unused name
- **THEN** its original access and device-based markers remain unchanged and the new name does not authorize replay of a prior attempt

#### Scenario: No trust bypass
- **WHEN** unattended named pairing omits an exact trusted fingerprint
- **THEN** it refuses without saving or selecting a profile, even if profile removal supports `--yes`
