## MODIFIED Requirements

### Requirement: Explicit compatibility results
Doctor SHALL distinguish successful connectivity from qualified model/firmware support. After pinned TLS verification and MQTT authentication, the fresh MQTT info report SHALL identify `Anycubic Kobra X`, firmware `2.0.2.2` and a nonempty printable ASCII state of at most 80 characters. As in pairing, `deviceId`, `modelId` and `modeId` SHALL be optional report fields; each supplied identifier SHALL match the selected configuration. Omitted optional identifiers SHALL be disclosed without failing compatibility. Missing or null required evidence SHALL fail with `qualification_incomplete`; supplied contradictory or invalid values SHALL fail with `outside_qualification`, taking precedence over missing evidence. Doctor SHALL NOT add HTTP identity fallback, queries, trust changes or retries to compensate for missing fields. Passing diagnosis SHALL NOT expand hardware or physical-operation qualification.

#### Scenario: Qualified firmware omits optional MQTT identifiers
- **WHEN** a pinned authenticated target reports the qualified model name, firmware and valid state but omits some or all optional device/model identifiers
- **THEN** compatibility passes and the report states that optional identifiers were omitted and target trust uses pinned authentication

#### Scenario: Connected but unsupported firmware
- **WHEN** authentication and status succeed but reported firmware is outside qualification or any supplied device/model identifier contradicts the selected config
- **THEN** connection stages pass, compatibility fails with `outside_qualification` and no value is silently ignored or repaired

#### Scenario: Missing required qualification evidence
- **WHEN** authentication and fresh status succeed but required model, firmware or state evidence is absent or null and no contradictory value is present
- **THEN** connection stages pass, compatibility fails with `qualification_incomplete` and the report distinguishes incomplete evidence from confirmed incompatibility

### Requirement: Sanitized diagnostic result and exit status
Doctor SHALL emit readable text by default or one shared versioned JSON envelope with global `--json`, containing ordered stages, an overall health result and safe next steps, without raw config, credential bundles, certificate bodies or token-bearing reports. Exit 0 SHALL mean all required stages passed; exit 2 SHALL indicate validation/trust/protocol/compatibility failure; exit 3 SHALL indicate local configuration/dependency/I/O or network failure. If failures mix, exit 3 SHALL take precedence.

#### Scenario: Structured failure report
- **WHEN** any diagnostic stage fails
- **THEN** stdout still contains one report in the selected format, including the shared error envelope and partial result with `--json`, with failed and skipped stages and its nonzero exit status, without secret material or a traceback

#### Scenario: Healthy target
- **WHEN** all local, reachability, trust, authentication, status and compatibility checks pass
- **THEN** doctor exits 0 and states only that the diagnosed connection is healthy within the recorded qualification
