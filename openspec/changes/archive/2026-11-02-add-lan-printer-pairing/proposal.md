# Proposal

## Why

The CLI can authenticate to a configured printer, but a new installation still requires credentials and certificates obtained elsewhere. Live tests on a Kobra X model 20030 / firmware 2.0.2.2 demonstrated that its LAN HTTP API supplies everything needed for direct onboarding, including the client certificate and key.

## What Changes

- Add `kobra-lan printer pair --host <IPv4>` for a printer already in LAN mode, honoring the existing global `--config` destination.
- Obtain device identity, MQTT credentials, and client certificate/key directly through the local `/info` and signed `/ctrl` handshake, with bounded HTTP requests and validated responses.
- Establish explicit trust on first use: display the observed server certificate fingerprint and request confirmation interactively, or require an exact `--trust-sha256` fingerprint for unattended use. Preserve certificate pinning on subsequent connections.
- Authenticate and query status before committing private configuration and PEM files. Limit initial qualification to model 20030 / firmware 2.0.2.2.
- Refuse an existing configuration destination without overwriting it; permit isolated setup through an alternative `--config` path. Preserve current commands, configuration format, and operational attempt markers.
- Add sanitized pairing diagnostics, synthetic offline tests, installation dependency coverage, and public onboarding instructions.

Discovery, named profiles, configuration replacement, credential revocation/rotation, firmware reset recovery, and printer controls are outside this change. Pairing does not upload files, start prints, heat, or move the printer.

## Capabilities

### New Capabilities

- `printer-pairing`: Provision LAN access from an explicit printer address, establish initial server trust, verify read-only connectivity, and safely persist compatible private configuration.

### Modified Capabilities

None. The existing `release-distribution` requirements remain applicable; the new runtime dependency must be included in the current packaging and acceptance paths.

## Impact

- Python: extend `kobra_lan/cli.py`, add provisioning/persistence helpers, and reuse `config.py` and the pinned MQTT connection in `mqtt.py`.
- Dependencies: add `cryptography` for AES-CBC and PEM/key validation; declare Python and Debian dependencies and adjust offline CI/build environments.
- Storage: create user-owned configuration and PEM files under the selected configuration directory, without changing upload/start state.
- Documentation: update README setup instructions, roadmap onboarding status, provenance references, release dependency/compatibility notes, and the validation record without publishing device identifiers or secrets.
- Hardware: protocol feasibility was observed on one printer, including an isolated in-memory first-use test. First-use trust remains a user decision; HTTP provisioning does not authenticate the device against an active network attacker.
