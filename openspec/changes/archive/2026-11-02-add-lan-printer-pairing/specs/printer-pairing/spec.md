# Spec Delta

## Purpose

Let a new CLI installation obtain access directly from an already LAN-enabled Kobra X, establish explicit initial certificate trust, and save verified private configuration without another integration.

## ADDED Requirements

### Requirement: Explicit address onboarding
The CLI SHALL provide `printer pair --host <IPv4>` and honor the existing global `--config` destination. Pairing SHALL obtain credentials directly from the selected LAN printer without HA, Slicer, a cloud account, or cloud requests.

#### Scenario: Fresh installation
- **WHEN** the user pairs a supported LAN-enabled printer at an explicit IPv4 address into an absent configuration destination
- **THEN** the CLI obtains its identity, MQTT credentials, and client certificate/key directly from that printer

#### Scenario: Invalid address
- **WHEN** the supplied host is not a bare IPv4 address
- **THEN** pairing fails before network access with an address validation diagnostic

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
Pairing SHALL refuse an existing configuration destination before provisioning and SHALL NOT overwrite a destination created concurrently. It SHALL preserve existing certificates, configurations, receipts, and attempt markers. An alternate absent `--config` destination SHALL permit isolated pairing without replacing current access.

#### Scenario: Already configured installation
- **WHEN** the selected config path already exists, including a symlink
- **THEN** pairing fails before network access and explains how to choose a separate destination

#### Scenario: Concurrent destination creation
- **WHEN** another process creates the selected config after the initial absence check
- **THEN** publication fails without replacing that config or its private material

#### Scenario: Separate setup
- **WHEN** pairing succeeds with a separate absent `--config` destination
- **THEN** the previous configuration and upload/start state remain unchanged

### Requirement: Sanitized machine-readable results
Pairing SHALL preserve JSON stdout and current exit conventions: 0 success, 2 protocol/validation/trust errors, and 3 local configuration or network failures. Human trust prompts SHALL use stderr. Diagnostics SHALL distinguish failure stages without exposing passwords, tokens, private keys, certificate bodies, tokenized URLs, or raw provisioning responses.

#### Scenario: Successful pairing result
- **WHEN** pairing succeeds
- **THEN** stdout contains one success JSON result with the config path, model, firmware, and accepted fingerprint, without credential values

#### Scenario: Sanitized failure
- **WHEN** provisioning, trust, authentication, compatibility, or persistence fails
- **THEN** stdout contains one error JSON result and a nonzero exit status with a safe stage-specific diagnostic

### Requirement: Independently installable onboarding
The Python distribution and Debian package SHALL declare and provide access to pairing's runtime dependencies through their installation mechanisms. Automated validation SHALL exercise pairing with synthetic responses without contacting real printers. Public instructions SHALL explain LAN prerequisites, first-use trust, separate config destinations, and qualified hardware limits.

#### Scenario: Installed package pairing
- **WHEN** the package is installed outside the checkout on a supported distribution
- **THEN** pairing help and synthetic onboarding checks run using declared dependencies without fetching dependencies at CLI runtime

#### Scenario: Automated acceptance
- **WHEN** CI or package lifecycle checks run
- **THEN** no real printer is contacted or provisioned and private user data remains preserved
