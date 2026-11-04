# printer-pairing Specification

## Purpose

Let a new CLI installation obtain access directly from an already LAN-enabled Kobra X, establish explicit initial certificate trust, and save verified private configuration without another integration.

## Requirements

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

### Requirement: Bounded provisioning exchange
Pairing SHALL use the printer's LAN provisioning exchange with timeouts and bounded responses. It SHALL reject redirects and control URLs outside HTTP on the selected host, port 18910, and `/ctrl` path. Malformed or incomplete responses SHALL prevent configuration publication.

#### Scenario: Unexpected control destination
- **WHEN** the identity response points to another host, port, scheme, path, or a URL containing userinfo, query, or fragment
- **THEN** pairing refuses that endpoint without sending a control request to it

#### Scenario: Invalid credential package
- **WHEN** the provisioning response cannot be decoded, decrypted, or validated, or lacks required identity, credentials, or matching certificate/key material
- **THEN** pairing fails without publishing configuration

#### Scenario: Timeout or excessive response
- **WHEN** a provisioning request times out, exceeds the response limit, returns a redirect, or reports failure
- **THEN** pairing reports a bounded failure without following redirects or automatically replaying the provisioning POST

### Requirement: Explicit initial server trust
Before sending MQTT username/password, pairing SHALL require explicit acceptance of the observed server certificate SHA-256 fingerprint. Interactive use SHALL show the address, model, device identity, fingerprint, and first-use trust limitation. Unattended use SHALL require an exact `--trust-sha256` fingerprint and SHALL NOT prompt.

#### Scenario: Interactive acceptance
- **WHEN** the user reviews the first-use identity and fingerprint and explicitly accepts
- **THEN** pairing uses that fingerprint to verify the subsequent MQTT authentication connection

#### Scenario: Declined or absent consent
- **WHEN** the user declines, enters an empty response, or provides no fingerprint while stdin is noninteractive
- **THEN** pairing fails without sending MQTT username/password or publishing configuration

#### Scenario: Expected fingerprint mismatch
- **WHEN** `--trust-sha256` is malformed or differs from the observed server fingerprint
- **THEN** pairing fails without sending MQTT username/password or publishing configuration

#### Scenario: Certificate changes after acceptance
- **WHEN** the server certificate changes between first observation and the authenticated connection
- **THEN** pairing rejects the connection before sending MQTT username/password and saves no configuration

### Requirement: Read-only connection verification
Pairing SHALL verify MQTT authentication and a fresh status response before publishing configuration. It SHALL initially qualify only model 20030 / firmware 2.0.2.2. Pairing SHALL NOT upload files or issue commands that start, pause, resume, cancel, heat, move, or otherwise control the printer.

#### Scenario: Verified supported printer
- **WHEN** accepted credentials authenticate and a fresh status response confirms the provisioned model and supported firmware
- **THEN** pairing becomes eligible to save configuration and reports the observed status

#### Scenario: Unsupported model or firmware
- **WHEN** the provisioned model is unsupported or the authenticated response contradicts that identity or reports unsupported firmware
- **THEN** pairing reports the qualification limit without publishing configuration

#### Scenario: Authentication or status failure
- **WHEN** authentication is rejected or a fresh valid status response is unavailable
- **THEN** pairing fails without publishing configuration or replaying commands

### Requirement: Private compatible configuration persistence
Successful pairing SHALL publish configuration loadable by existing commands, with private PEM files and config permissions `0600` under a user-owned directory with permissions `0700`. Publication SHALL be atomic and occur only after trust acceptance and status verification. Handled failures SHALL remove unpublished staged secrets and preserve files referenced by a published config.

#### Scenario: Successful save
- **WHEN** pairing completes verification and saving succeeds
- **THEN** the selected config references complete private PEM files and a subsequent ordinary `status` command can use it without another provisioning exchange

#### Scenario: Failed save
- **WHEN** a write or publication operation fails before the config becomes visible
- **THEN** no partially written configuration becomes usable and staged secret files owned by the failed invocation are removed

#### Scenario: Failure after publication
- **WHEN** final cleanup or durability confirmation fails after a complete config becomes visible
- **THEN** the CLI reports a persistence diagnostic while retaining the complete config and its referenced PEM files

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

### Requirement: Sanitized machine-readable results
Pairing SHALL use the shared CLI text default and opt-in versioned JSON envelope, retaining exit conventions: 0 success, 2 protocol/validation/trust errors, and 3 local configuration or network failures. Human trust prompts SHALL use stderr. Diagnostics SHALL distinguish failure stages without exposing passwords, tokens, private keys, certificate bodies, tokenized URLs, or raw provisioning responses.

#### Scenario: Successful pairing result
- **WHEN** pairing succeeds
- **THEN** stdout contains a readable success result by default or one success JSON envelope with `--json`, including the config path, model, firmware, and accepted fingerprint, without credential values

#### Scenario: Sanitized failure
- **WHEN** provisioning, trust, authentication, compatibility, or persistence fails
- **THEN** stdout contains a safe failure result in the selected format, using the shared error envelope with `--json`, and a nonzero exit status with a safe stage-specific diagnostic

### Requirement: Independently installable onboarding
The Python distribution and Debian package SHALL declare and provide access to pairing's runtime dependencies through their installation mechanisms. Automated validation SHALL exercise pairing with synthetic responses without contacting real printers. Public instructions SHALL explain LAN prerequisites, first-use trust, separate config destinations, and qualified hardware limits.

#### Scenario: Installed package pairing
- **WHEN** the package is installed outside the checkout on a supported distribution
- **THEN** pairing help and synthetic onboarding checks run using declared dependencies without fetching dependencies at CLI runtime

#### Scenario: Automated acceptance
- **WHEN** CI or package lifecycle checks run
- **THEN** no real printer is contacted or provisioned and private user data remains preserved

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
Named pairing SHALL retain existing no-overwrite, private permissions, explicit trust, sanitized shared text/opt-in JSON output and exit conventions. Success SHALL add profile name and default outcome to the named-flow result; unnamed pairing SHALL be rejected before provisioning. Reusing the same device through another name SHALL NOT reset receipt/attempt protection.

#### Scenario: Two names for one device
- **WHEN** the same qualified device is paired under another unused name
- **THEN** its original access and device-based markers remain unchanged and the new name does not authorize replay of a prior attempt

#### Scenario: No trust bypass
- **WHEN** unattended named pairing omits an exact trusted fingerprint
- **THEN** it refuses without saving or selecting a profile, even if profile removal supports `--yes`
