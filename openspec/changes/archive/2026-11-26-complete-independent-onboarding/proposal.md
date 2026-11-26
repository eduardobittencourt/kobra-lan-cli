# Proposal

## Why

Milestone 1 ("Independent onboarding") in `ROADMAP.md` still has three unresolved items preventing a new owner from going end-to-end from a fresh installation to a verified status query with complete, evidence-backed guidance: validated LAN discovery, researched credential replacement/revocation and recovery behavior, and documented printer-panel/app prerequisites for initial LAN-mode setup. Our 2026-11-26 static inspection of `AnycubicSlicerNext 1:2.0.0.6` (`libssdplib.so`, `libWorkbench.so`, `AnycubicSlicerNext`) and live read-only LAN SSDP probe on Kobra X model `20030` / firmware `2.0.2.2` resolved both the discovery wire protocol and stock firmware credential/revocation constraints, allowing Milestone 1 to be closed cleanly in one scoped change without conflating it with Milestone 3 print-hardware qualification.

## What Changes

- **Read-only LAN SSDP discovery (`kobra-lan printer discover`)**:
  - Add a new `kobra_lan/discovery.py` module implementing strictly read-only UDP multicast SSDP `M-SEARCH` (`239.255.255.250:1900`, `ST: ac:3dprinter:fdm`, `Man: "ssdp:discover"`, `MX: 5`, bounded `--timeout` 1..15 seconds with default 5, optional bare IPv4 `--interface`).
  - Strictly validate `HTTP/1.1 200`, `ST`, `USN`, and `LOCATION` (`http://<host>:18910/info?...`) so that `LOCATION` host and `ip` query parameter match the UDP source IPv4 address; never open HTTP `:18910` or MQTT `:9883`, never auto-pair, never bypass explicit TLS fingerprint consent, and never expose raw `LOCATION` URLs or cloud binding codes (`cn`).
  - Report sanitized structured candidate records (`host`, `port`, `model_id`, `model_name`, `device_name`, `mac`, `ctrl_type`, `qualified_model`, `firmware_verified: false`, `unauthenticated: true`) with explicit multicast/VLAN topology limitations, exit `0` on completion (including zero printers found), exit `2` on invalid arguments or global target selectors (`--config`/`--printer`), exit `3` on socket/network errors, and exit `130` on `KeyboardInterrupt`.
  - Expose `printer discover` in CLI help, error guidance, and offline `bash`/`zsh`/`fish` completions.
- **Credential limit diagnostic and replacement/revocation/recovery workflow**:
  - Update `kobra_lan/provisioning.py` to distinguish firmware error code `19002` (printer client connection limit reached, observed in `AnycubicSlicerNext` `addPrinter_vue.js`) with a safe, actionable diagnostic directing operators to clear stale LAN clients on the printer panel rather than repeating blind provisioning retries.
  - Document the 2026-11-26 credential-lifecycle investigation in `docs/pairing.md` and `docs/pairing-security-review.md`: stock Kobra X LAN clients never invoke a LAN credential-revocation endpoint on removal (`accountDeleteUrl` is unused by `AnycubicSlicerNext`), so revoking device credentials requires printer-side LAN-mode reset/toggle; document the safe zero-overwrite credential/IP/TLS-pin replacement workflow (pair new unused profile name → verify via `doctor`/`status` → `printer use <new>` → `printer remove <old>`) that preserves existing working access and `printer_id`-scoped upload/start attempt protection.
- **Complete owner onboarding guide and centralized qualification**:
  - Add a step-by-step fresh-installation onboarding walkthrough in `docs/pairing.md` covering printer-panel LAN-mode prerequisites, network/multicast limitations, explicit disclosure that factory-new/post-reset initial cloud/account setup requirements have not been tested via destructive factory reset, discovery vs explicit IPv4 pairing, first-use trust, `doctor`, and `status`.
  - Centralize discovery hardware qualification (`discovery_hardware_validated`, `is_discovery_hardware_validated`) in `kobra_lan/qualification.py` and update `docs/compatibility.md`, `docs/usage.md`, `README.md`, `ROADMAP.md`, and packaging allowlists/probes (`scripts/check_python.py`, `scripts/build_deb.py`, `scripts/accept_deb.py`, `scripts/probe_completions.py`).

## Capabilities

### New Capabilities
- `printer-discovery`: Strictly read-only SSDP multicast LAN printer discovery (`printer discover`), validating `ac:3dprinter:fdm` responses against UDP sender addresses, sanitizing output, disclosing unauthenticated/unverified-firmware and network-topology limits, and never auto-pairing or touching credentials.

### Modified Capabilities
- `printer-pairing`: Distinguish firmware client-limit rejection (`code: 19002`) during provisioning and document verified onboarding prerequisites, unverified factory-reset boundaries, and safe credential replacement/revocation/recovery procedures preserving existing access and device-based markers.
- `cli-interface`: Add `printer discover` (`--timeout`, `--interface`) to the canonical command tree, contextual help, global-selector validation, interrupt handling (exit `130`), and offline `bash`/`zsh`/`fish` completions.
- `hardware-qualification`: Track discovery hardware validation in `kobra_lan/qualification.py`, include `discovery` in packaging allowlists, and document `printer discover` and Milestone 1 evidence in `docs/compatibility.md`.

## Impact

- **Code**: New `kobra_lan/discovery.py`; updates to `kobra_lan/cli.py`, `kobra_lan/provisioning.py`, `kobra_lan/qualification.py`.
- **Tests**: New offline unit tests `tests/test_discovery.py`; updates to `tests/test_provisioning.py`, `tests/test_cli.py` / completion tests, `tests/test_qualification.py`, and packaging allowlist tests.
- **Packaging & scripts**: Add `"discovery"` to module allowlists in `scripts/build_deb.py` and `scripts/check_python.py`; extend offline CLI/completion probes in `scripts/probe_completions.py`, `scripts/check_python.py`, and `scripts/accept_deb.py`.
- **Documentation**: Updates to `docs/pairing.md`, `docs/pairing-security-review.md`, `docs/compatibility.md`, `docs/usage.md`, `README.md`, and `ROADMAP.md` (marking Milestone 1 exit evidence satisfied once live CLI discovery verification completes).
- **Dependencies**: None (stdlib `socket`, `ipaddress`, `urllib.parse`, `select` only). No breaking changes to existing CLI commands, JSON schemas, profiles, or state formats.
