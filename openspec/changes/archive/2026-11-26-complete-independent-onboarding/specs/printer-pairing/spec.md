# Spec Delta

## MODIFIED Requirements

### Requirement: Bounded provisioning exchange
Pairing SHALL use the printer's LAN provisioning exchange with timeouts and bounded responses. It SHALL reject redirects and control URLs outside HTTP on the selected host, port 18910, and `/ctrl` path. Malformed or incomplete responses SHALL prevent configuration publication. When the printer rejects `/ctrl` with firmware error code `19002` (client connection limit reached), pairing SHALL fail with a safe, stage-specific diagnostic explaining that the printer's LAN client limit was reached and directing the operator to clear stale LAN clients on the printer panel rather than repeating blind retries.

#### Scenario: Unexpected control destination
- **WHEN** the identity response points to another host, port, scheme, path, or a URL containing userinfo, query, or fragment
- **THEN** pairing refuses that endpoint without sending a control request to it

#### Scenario: Invalid credential package
- **WHEN** the provisioning response cannot be decoded, decrypted, or validated, or lacks required identity, credentials, or matching certificate/key material
- **THEN** pairing fails without publishing configuration

#### Scenario: Timeout or excessive response
- **WHEN** a provisioning request times out, exceeds the response limit, returns a redirect, or reports failure
- **THEN** pairing reports a bounded failure without following redirects or automatically replaying the provisioning POST

#### Scenario: Printer client connection limit reached (code 19002)
- **WHEN** the provisioning `POST /ctrl` response returns JSON with integer `code: 19002`
- **THEN** pairing fails with exit 2 (`validation_failed`), saves no configuration, and reports a safe diagnostic indicating that the printer's LAN client connection limit was reached (code `19002`) without echoing raw response payloads

### Requirement: Independently installable onboarding
The Python distribution and Debian package SHALL declare and provide access to pairing's runtime dependencies through their installation mechanisms. Automated validation SHALL exercise pairing and discovery help/CLI contracts with synthetic responses without contacting real printers. Public instructions SHALL explain printer-panel LAN-mode prerequisites, explicitly record unverified factory-new / post-reset initial cloud or account setup boundaries without inferring cloud-free unboxing, document discovery versus explicit IPv4 onboarding and multicast topology limits, first-use trust, separate config destinations, and qualified hardware limits.

#### Scenario: Installed package pairing
- **WHEN** the package is installed outside the checkout on a supported distribution
- **THEN** pairing and discovery help and synthetic onboarding checks run using declared dependencies without fetching dependencies at CLI runtime

#### Scenario: Automated acceptance
- **WHEN** CI or package lifecycle checks run
- **THEN** no real printer is contacted or provisioned and private user data remains preserved

## ADDED Requirements

### Requirement: Documented credential replacement, revocation, and recovery
Public pairing documentation SHALL record the firmware `2.0.2.2` credential-lifecycle boundary (stock LAN protocol provides no client-side credential revocation endpoint; `printer remove` removes local files only and revoking previously issued device credentials or clearing `code 19002` client slots requires printer-panel LAN-mode reset/toggle). Documentation SHALL provide a non-destructive recovery and replacement procedure for IP address changes, TLS pin changes, or credential rotation using a new unused profile name (`printer pair --name <new> --host <ip>` → `doctor`/`status` → `printer use <new>` → `printer remove <old>`) that preserves existing working access until verified and preserves `printer_id`-scoped receipts, attempt markers, and watch observations.

#### Scenario: Non-destructive credential or host replacement guidance
- **WHEN** an operator consults `docs/pairing.md` after a printer IP change, TLS certificate change, or client-limit (`19002`) failure
- **THEN** the documentation provides concrete recovery steps that never overwrite existing configs in place, never auto-update a mismatched TLS pin, and never instruct clearing operational attempt markers
