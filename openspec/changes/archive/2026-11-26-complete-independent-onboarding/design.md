# Design

## Context

See `proposal.md` for motivation and Milestone 1 scope. Static reverse engineering of `AnycubicSlicerNext 1:2.0.0.6` (`/usr/lib/libssdplib.so`, `/usr/lib/libWorkbench.so`, `/usr/bin/AnycubicSlicerNext`) and a live read-only SSDP probe on Kobra X (`20030` / FW `2.0.2.2`) on 2026-11-26 established two concrete protocol realities:

1. **Discovery**: The printer responds to UDP multicast SSDP `M-SEARCH` (`239.255.255.250:1900`) only when `ST: ac:3dprinter:fdm` is sent (`ST: ssdp:all` elicits no reply). The reply carries `ST: ac:3dprinter:fdm`, `USN: uuid:fdm:<mac>`, and `LOCATION: http://<ip>:18910/info?cn=<cn>&ctrlType=lan&deviceName=...&ip=<ip>&modelId=20030&modelName=...&zone=...`. Firmware version is not included in SSDP advertisements.
2. **Credential lifecycle**: `POST /ctrl` accepts a client identifier `did` and can return `code: 19002` when the printer's client connection limit is reached (`pinter_limit_reached`). Although the decrypted `/ctrl` bundle schema contains an `accountDeleteUrl` field, `AnycubicSlicerNext` never calls it on printer deletion — removing a LAN printer only deletes local state and closes MQTT.

The CLI's core security invariants remain unchanged: zero automatic trust or pairing, TLS pin verification before MQTT credentials, private no-replace profile publication, and `printer_id`-scoped attempt protection.

## Goals / Non-Goals

**Goals:**
- Implement a small, stdlib-only `kobra_lan/discovery.py` module for `printer discover` with strict wire validation, sender-IP pinning, deterministic deduplication/sorting, and zero external dependencies.
- Surface firmware client-limit rejection (`code: 19002`) clearly in `kobra_lan/provisioning.py` without weakening error sanitization.
- Document the complete fresh-install onboarding flow, printer-panel prerequisites, unverified factory-reset boundary, multicast limitations, and safe non-destructive credential replacement/revocation/recovery workflow in `docs/pairing.md` and `docs/pairing-security-review.md`.
- Keep `kobra_lan/qualification.py`, `docs/compatibility.md`, `ROADMAP.md`, completions, and packaging allowlists synchronized.

**Non-Goals:**
- Auto-pairing from discovery results or accepting a hostname/MAC in `printer pair --host` (pairing remains explicit bare IPv4 + explicit `--name` + explicit TLS fingerprint consent).
- Active subnet scanning (TCP port sweeps across `/24` ranges) or cross-VLAN mDNS/SSDP relay workarounds.
- In-place profile overwrite, silent TLS pin replacement, or unverified client-side credential revocation calls to `accountDeleteUrl`.
- Milestone 3 print-hardware qualification (additional materials, preparation flags, or non-identity multicolor mappings).

## Decisions

### 1. New stdlib-only leaf module `kobra_lan/discovery.py`
- **Choice**: Place SSDP multicast discovery, interface enumeration, response parsing, and validation in a dedicated `kobra_lan/discovery.py` module using only Python stdlib (`ipaddress`, `select`, `socket`, `time`, `urllib.parse`, `re`).
- **Rationale**: Keeps `pairing.py` focused on provisioning/TLS trust/publication and mirrors the modular structure of `camera.py`, `filaments.py`, and `delete_file.py`. Avoids adding any third-party dependency (`netifaces`, `ifaddr`, etc.) so Debian/Python runtime dependencies remain strictly Python `>= 3.11` + `cryptography >= 41`.
- **Interface selection strategy**:
  - When `--interface IPv4` is supplied, validate it as a bare IPv4 address (reusing `validate_host` semantics) and bind a single UDP socket to `(interface, 0)` with `IP_MULTICAST_IF`.
  - When `--interface` is omitted, open a standard UDP socket (`INADDR_ANY`, ephemeral port, `IP_MULTICAST_TTL = 2`) and send two `M-SEARCH` datagrams spaced across the listen window (matching `AnycubicSlicerNext`'s `count=2`, e.g., at `t=0` and `t=min(1.0, timeout/2)`). This works portably on Linux/macOS/Windows without platform-specific `ioctl`/`getifaddrs` C bindings, while `--interface` explicitly handles multi-homed hosts where the default multicast route points elsewhere.
  - **Alternative considered**: Calling `libc.getifaddrs` via `ctypes` to enumerate every interface automatically like `libssdplib.so`. Rejected because `ctypes` struct layouts vary across architectures/OSes and introduce fragility, whereas default route multicast + explicit `--interface IPv4` is portable, auditable, and easy to unit-test with synthetic sockets.

### 2. Strict SSDP response validation & sender-IP enforcement
- **Choice**: Require `HTTP/1.1 200` (case-insensitive status line `HTTP/1.x 200`), header `ST` matching `ac:3dprinter:fdm` (case-insensitive), `LOCATION` parsing as `http://<host>:18910/info?...` with no userinfo/fragment/control chars, query `ctrlType == "lan"`, and BOTH `LOCATION` hostname and query `ip` equal to the UDP packet's source IPv4 address (`sender_ip`).
- **Rationale**: SSDP is unauthenticated UDP. Requiring `LOCATION` host and `ip` to match `sender_ip` prevents trivial cross-host redirection spoofing and ensures `printer discover` never echoes attacker-chosen arbitrary URLs or off-host destinations.
- **Sanitization**: Parse `USN` with `^uuid:fdm:((?:[0-9a-f]{2}[-:]){5}[0-9a-f]{2})$` (case-insensitive) and normalize to lowercase colon-separated MAC (or `None` if omitted/invalid). Omit `cn` (Anycubic cloud binding code) and omit raw `LOCATION` from all text/JSON output. Truncate/sanitize `model_name` and `device_name` through `safe_text`.
- **Schema**:
  ```json
  {
    "protocol": "ssdp",
    "search_target": "ac:3dprinter:fdm",
    "timeout_seconds": 5,
    "interface": null,
    "hardware_discovery_validated": true,
    "unauthenticated_lan_advertisement": true,
    "firmware_verified": false,
    "printers": [
      {
        "host": "192.0.2.10",
        "port": 18910,
        "model_id": 20030,
        "model_name": "Anycubic Kobra X",
        "device_name": "Anycubic Kobra X",
        "mac": "02:00:00:00:00:01",
        "ctrl_type": "lan",
        "qualified_model": true,
        "firmware_verified": false,
        "unauthenticated": true
      }
    ],
    "limitations": [
      "SSDP advertisements are unauthenticated LAN broadcasts and do not report firmware version; pair explicitly with kobra-lan printer pair --name NAME --host IPv4 and verify the TLS fingerprint.",
      "Multicast discovery works only within the same local network segment; routed VLANs, Wi-Fi client isolation, VPNs, or firewalls blocking UDP 1900 require explicit IPv4 pairing."
    ]
  }
  ```

### 3. Client-limit (`code: 19002`) handling and credential replacement without in-place mutation
- **Choice**: In `kobra_lan/provisioning.py:exchange()`, inspect `response.get("code")`: when `type(code) is int and code == 19002`, raise `ProtocolError("Provisioning: printer rejected credential request (client connection limit reached, code 19002); toggle LAN mode on the printer panel to clear stale clients before pairing again")`. Keep all other non-200 codes mapped to the existing safe `"Provisioning: credential request rejected"`.
- **Choice on credential replacement/revocation**: Do **not** add an in-place profile overwrite command or speculative HTTP call to `accountDeleteUrl`. Instead, document the verified protocol boundaries and the safe zero-overwrite replacement runbook in `docs/pairing.md`:
  1. Pair into a fresh unused profile name (`printer pair --name <new> --host <ip>`) with explicit TLS fingerprint acceptance.
  2. Verify with `--printer <new> doctor` and `--printer <new> status`.
  3. Switch default with `printer use <new>`.
  4. Remove the superseded local profile with `printer remove <old>`.
  5. Note explicitly that `printer_id`-scoped upload/start receipts, attempt markers, and watch observations remain intact across profile replacement and local removal, and that revoking previously issued device credentials requires resetting/toggling LAN mode on the printer panel.
- **Rationale**: Preserves the non-negotiable no-overwrite and no-auto-pin-update invariants in `AGENTS.md`, avoids guessing undocumented firmware behavior for `accountDeleteUrl`, and gives operators a crash-safe rollback path if the new pairing fails.

### 4. Centralized qualification flag
- **Choice**: Add `discovery_hardware_validated: bool = False` on `PrinterQualification` (`True` on `KOBRA_X` once live CLI `printer discover` is verified on model `20030` / firmware `2.0.2.2`) and expose `is_discovery_hardware_validated(model_id, firmware)` in `kobra_lan/qualification.py`.
- **Rationale**: Keeps all `hardware_*_validated` flags in one authoritative registry per `openspec/specs/hardware-qualification/spec.md`.

### 5. Packaging and completion sync
- **Choice**: Add `"discovery"` to `MODULES` in `scripts/build_deb.py` and `scripts/check_python.py`, extend `scripts/probe_completions.py` and `scripts/accept_deb.py` / `scripts/check_python.py` to assert `printer discover --help` and completion coverage (`discover`, `--timeout`, `--interface`) offline.

## Risks / Trade-offs

- **[Risk] Multi-homed hosts with default route on a non-LAN interface (e.g., VPN or Docker bridge) may not reach the printer with default multicast** → **Mitigation**: Provide explicit `--interface IPv4` option and clearly document the limitation and explicit `--host` fallback in both CLI output `limitations` and `docs/pairing.md`.
- **[Risk] Spoofed SSDP replies on an untrusted LAN could advertise fake printers or wrong IPs** → **Mitigation**: Enforce `LOCATION` host and `ip` == UDP `sender_ip`, strictly sanitize fields, never auto-pair, mark every record `unauthenticated: true` / `firmware_verified: false`, and document the threat model in `docs/pairing-security-review.md`.
- **[Risk] Factory-new Kobra X unboxing cloud/account requirements remain untested without destructive factory reset** → **Mitigation**: Explicitly document this unresolved boundary in `docs/pairing.md` and `ROADMAP.md` rather than inferring cloud-free unboxing from cloud-free runtime operation.
- **[Risk] `printer pair` currently generates a random `did` per invocation, which could contribute to hitting firmware error `19002` if repeated many times** → **Mitigation**: Surface `code 19002` explicitly with clear panel-side recovery steps; avoid introducing an extra unauthenticated persistent machine ID file in this change until/unless firmware `did`-slot reuse semantics are directly confirmed.

## Migration Plan

Purely additive, backward-compatible change within `0.x`:
- No existing command signatures, JSON fields, profile formats, or state directories change.
- Packaging allowlists (`scripts/build_deb.py`, `scripts/check_python.py`) are updated in the same commit as `kobra_lan/discovery.py`.
- After offline tests, lint, and shell syntax checks pass, run a strictly read-only live verification of `./kobra-lan printer discover` (text and `--json`) against the Kobra X on the local LAN to confirm end-to-end Milestone 1 evidence without modifying any profiles, credentials, or printer state.
