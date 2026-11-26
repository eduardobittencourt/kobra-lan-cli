# printer-discovery Specification

## Purpose

Provide strictly read-only LAN printer discovery over Anycubic's validated SSDP multicast search protocol so new owners can locate LAN-enabled printers on the same subnet without auto-pairing, touching credentials, or bypassing explicit first-use trust.

## Requirements

### Requirement: Strictly read-only SSDP multicast discovery
The CLI SHALL provide `printer discover` to locate LAN-enabled Anycubic FDM printers using UDP multicast SSDP `M-SEARCH` to `239.255.255.250:1900` with `ST: ac:3dprinter:fdm`, `Man: "ssdp:discover"`, and `MX: 5`. Discovery SHALL be strictly read-only: it SHALL NOT contact HTTP port `18910`, MQTT port `9883`, or any external service, SHALL NOT read or modify profiles, credentials, or operational state, and SHALL reject global `--config` and `--printer` selectors with exit 2 before opening sockets.

#### Scenario: Qualified Kobra X responds on the local subnet
- **WHEN** `printer discover` runs and receives a valid `HTTP/1.1 200 OK` SSDP reply for `ST: ac:3dprinter:fdm` with `ctrlType=lan` and `modelId=20030` matching the UDP sender IPv4 address
- **THEN** the CLI exits 0 and reports the printer with `host`, `port: 18910`, `model_id: 20030`, `model_name`, `device_name`, normalized `mac`, `ctrl_type: "lan"`, `qualified_model: true`, `firmware_verified: false`, and `unauthenticated: true` without contacting port `18910` or creating local files

#### Scenario: No printers respond within timeout
- **WHEN** `printer discover` completes its bounded listen window without receiving any valid LAN printer advertisements
- **THEN** the CLI exits 0 with an empty `printers` list and retains topology limitations guidance directing the user to explicit `printer pair --name NAME --host IPv4`

#### Scenario: Global target selector rejected before network access
- **WHEN** `printer discover` is invoked with global `--config` or `--printer`
- **THEN** the CLI exits 2 (`validation_failed`) before opening any socket

### Requirement: Bounded discovery options and interface selection
`printer discover` SHALL accept optional `--timeout <seconds>` (whole integer from `1` to `15`, default `5`) and optional `--interface <IPv4>` (canonical bare IPv4 local bind address). Malformed or out-of-range option values SHALL fail with exit 2 (`invalid_arguments`) before opening sockets and without echoing raw argument values. Foreground interruption (`SIGINT`) SHALL exit `130` with a safe diagnostic.

#### Scenario: Invalid timeout or interface value
- **WHEN** `--timeout 0`, `--timeout 99`, or `--interface not-an-ip` is supplied in text or JSON mode
- **THEN** the CLI exits 2 (`invalid_arguments`) before opening any socket and emits one safe error in the selected format

#### Scenario: Explicit local interface binding
- **WHEN** `--interface 192.0.2.10` is supplied on a multi-homed host
- **THEN** discovery binds its UDP search socket to `192.0.2.10` instead of probing all local interfaces

#### Scenario: Interrupted discovery in JSON mode
- **WHEN** the operator interrupts `printer discover` with `SIGINT` while global `--json` is enabled
- **THEN** the CLI exits 130 with one safe JSON error envelope (`code: "interrupted"`)

### Requirement: Strict advertisement validation, deduplication, and sanitization
Discovery SHALL validate every UDP reply before including it: responses SHALL have status `200`, matching `ST: ac:3dprinter:fdm`, and a `LOCATION` URL using scheme `http`, port `18910`, path `/info`, and a host and `ip` query parameter that both exactly match the UDP packet's source IPv4 address. Malformed, non-LAN (`ctrlType != "lan"`), non-matching-ST, or cross-host/spoofed advertisements SHALL be ignored safely without failing the scan. Output SHALL deduplicate repeated replies deterministically by `(host, mac)`, sort by IPv4 address, sanitize all text fields, and NEVER expose raw `LOCATION` URLs, tokens, or `cn` cloud-binding codes.

#### Scenario: Cross-host or spoofed LOCATION advertisement is ignored
- **WHEN** a UDP reply from `192.0.2.20` advertises `LOCATION: http://192.0.2.99:18910/info?...&ip=192.0.2.99` or a non-`18910` port or non-`/info` path
- **THEN** discovery ignores that spoofed reply without crashing or contacting the advertised address

#### Scenario: Cloud-only or unrelated SSDP reply is ignored
- **WHEN** a UDP reply advertises `ctrlType=cloud`, a non-`ac:3dprinter:fdm` `ST`, or malformed bytes
- **THEN** discovery ignores the reply and continues collecting valid LAN replies until timeout

#### Scenario: Cloud binding code and raw LOCATION URL are omitted
- **WHEN** a valid reply contains `cn=XXXX-XXXX-XXXX-XXXX` and a full `LOCATION` URL
- **THEN** neither text nor JSON output contains the `cn` value or the raw `LOCATION` URL

### Requirement: Explicit unauthenticated and topology-limit disclosures
Discovery results SHALL explicitly state that SSDP advertisements are unauthenticated LAN broadcasts, that firmware version is NOT verified by discovery (`firmware_verified: false`), and that pairing still requires explicit `printer pair --name NAME --host IPv4` with explicit TLS fingerprint consent. Results SHALL disclose same-subnet multicast limitations (routed VLANs, client isolation, VPNs, or firewalls blocking UDP 1900 require explicit IPv4 pairing) and report `hardware_discovery_validated` from centralized qualification rules.

#### Scenario: Unqualified printer model discovered on LAN
- **WHEN** a valid LAN SSDP advertisement reports an unqualified `modelId` (for example `20025`)
- **THEN** discovery still lists the candidate with `qualified_model: false` and `firmware_verified: false` so the operator sees why pairing will reject it without implying support
