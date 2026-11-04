# Spec Delta

## Purpose

Help users identify configuration and connection failures through bounded read-only checks with actionable results that preserve credentials, trust and printer state.

## ADDED Requirements

### Requirement: Selected-target diagnosis
`doctor` SHALL use the same explicit selectors, persistent default and legacy fallback rules as operational commands. It SHALL report safe target metadata and local configuration/dependency checks even when later network checks cannot run. It SHALL NOT scan addresses or try another target.

#### Scenario: Missing config or dependency
- **WHEN** the selected config or a required runtime dependency is absent
- **THEN** doctor reports the failed local stage and a concrete next step, marks dependent checks skipped and opens no printer connection

### Requirement: Bounded staged checks
Doctor SHALL report configuration, dependencies, HTTP TCP reachability, MQTT TCP reachability, pinned TLS, MQTT authentication, fresh status and compatibility as distinct stages. Each stage SHALL be `passed`, `failed` or `skipped`, with safe reason codes and next steps. Network stages SHALL have finite timeouts and SHALL NOT automatically retry.

#### Scenario: HTTP unavailable but MQTT usable
- **WHEN** the configured HTTP port refuses connections but MQTT is reachable
- **THEN** the HTTP stage fails while independent MQTT/status checks run, and the result explains that upload/provisioning connectivity is unavailable

#### Scenario: MQTT timeout
- **WHEN** a MQTT connection attempt times out
- **THEN** doctor reports a network-stage failure within its documented timeout budget and skips dependent stages without replay or fallback

### Requirement: Pinned authenticated read-only verification
Doctor SHALL compare the server TLS fingerprint to the saved pin before sending MQTT credentials and require a fresh correlated status response. It SHALL NOT provision credentials, POST to HTTP endpoints, upload, control the printer, change trust, repair files or mutate profile and operational state.

#### Scenario: Changed certificate
- **WHEN** the observed server certificate differs from the saved pin
- **THEN** the TLS stage fails, MQTT credentials are not sent, authentication/status stages are skipped and the stored pin remains unchanged

#### Scenario: Rejected authentication or stale reports
- **WHEN** authentication is rejected or no fresh valid status response arrives
- **THEN** the appropriate authentication/status stage fails without re-pairing, accepting stale state or replaying a command

#### Scenario: Busy printer
- **WHEN** the selected printer is already printing and fresh status is available
- **THEN** doctor can succeed without requiring idle state or changing the ongoing job

### Requirement: Explicit compatibility results
Doctor SHALL distinguish successful connectivity from qualified model/firmware support. It SHALL compare observed identity with the selected config and report model 20030 / firmware 2.0.2.2 as the initial qualification. Unknown or contradictory identity SHALL NOT be reported as fully supported.

#### Scenario: Connected but unsupported firmware
- **WHEN** authentication and status succeed but firmware is outside qualification
- **THEN** connection stages pass, compatibility fails and the result identifies the qualification limit without claiming printer controls are supported

### Requirement: Sanitized diagnostic result and exit status
Doctor SHALL emit one JSON result containing ordered stages, an overall health result and safe next steps, without raw config, credential bundles, certificate bodies or token-bearing reports. Exit 0 SHALL mean all required stages passed; exit 2 SHALL indicate validation/trust/protocol/compatibility failure; exit 3 SHALL indicate local configuration/dependency/I/O or network failure. If failures mix, exit 3 SHALL take precedence.

#### Scenario: Structured failure report
- **WHEN** any diagnostic stage fails
- **THEN** stdout still contains one JSON report with failed and skipped stages and its nonzero exit status, without secret material or a traceback

#### Scenario: Healthy target
- **WHEN** all local, reachability, trust, authentication, status and compatibility checks pass
- **THEN** doctor exits 0 and states only that the diagnosed connection is healthy within the recorded qualification

### Requirement: Offline and installed diagnostic acceptance
Automated doctor verification SHALL use synthetic transports and configs without contacting a real printer. Installed-command checks SHALL exercise diagnostics outside the checkout on supported Python/Debian installations, and package lifecycle operations SHALL NOT invoke live diagnostics.

#### Scenario: Installed synthetic diagnosis
- **WHEN** an installed CLI runs synthetic healthy and failed diagnosis cases in acceptance
- **THEN** stage reports, exit codes and data preservation match source behavior without accessing real devices
