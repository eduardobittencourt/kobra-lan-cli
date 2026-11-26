# Tasks

## 1. Centralized discovery qualification and provisioning client-limit diagnostic

- [x] 1.1 Add `discovery_hardware_validated: bool = False` (`True` on `KOBRA_X`) and `is_discovery_hardware_validated(model_id, firmware)` to `kobra_lan/qualification.py`, and add unit tests in `tests/test_qualification.py` covering qualified (`20030` / `2.0.2.2`) and unqualified model/firmware values; verify with `uv run --locked python -m unittest tests.test_qualification -v`.
- [x] 1.2 Update `kobra_lan/provisioning.py:exchange()` to distinguish firmware error code `19002` (printer LAN client connection limit reached) with a safe, actionable diagnostic without echoing raw payloads, and add unit tests in `tests/test_provisioning.py` covering `code: 19002` and other non-200 error codes; verify with `uv run --locked python -m unittest tests.test_provisioning -v`.

## 2. Read-only SSDP LAN discovery module

- [x] 2.1 Implement `kobra_lan/discovery.py` with stdlib-only UDP multicast `M-SEARCH` (`239.255.255.250:1900`, `ST: ac:3dprinter:fdm`, `Man: "ssdp:discover"`, `MX: 5`, bounded timeout `1..15` default `5`, optional bare IPv4 `--interface`), strict `HTTP/1.x 200` + `ST` + `LOCATION` (`http://<sender_ip>:18910/info?...` and `ip == sender_ip`) + `ctrlType == "lan"` validation, MAC normalization from `USN`, omission of `cn` and raw `LOCATION`, deterministic `(host, mac)` deduplication and IPv4 sorting, explicit `unauthenticated` / `firmware_verified: false` / `limitations` fields, and `hardware_discovery_validated` from `kobra_lan/qualification.py`; verify module import and parsing logic via unit tests in task 2.2.
- [x] 2.2 Add comprehensive offline unit tests in `tests/test_discovery.py` using synthetic sockets/datagrams covering valid qualified (`20030`) and unqualified (`20025`) replies, zero-reply timeout, duplicate replies, cross-host/spoofed `LOCATION` or `ip` mismatch rejection, non-`18910`/non-`/info`/non-`lan`/non-matching-`ST`/malformed-bytes ignoring, `cn` and raw URL redaction/omission, explicit `--interface` binding, socket error mapping (exit 3), and `KeyboardInterrupt` propagation; verify with `uv run --locked python -m unittest tests.test_discovery -v`.

## 3. CLI wiring, shell completions, and packaging allowlists

- [x] 3.1 Wire `printer discover` (`--timeout`, `--interface`) into `kobra_lan/cli.py` with contextual error guidance, strict bounded option parsing (exit 2 without echoing raw values), global `--config`/`--printer` rejection before network access, exit 3 on socket errors, and exit 130 on `KeyboardInterrupt` (both text and `--json`), and verify with `tests/test_cli.py` and completion tests (`uv run --locked python -m unittest tests.test_cli tests.test_completions -v`).
- [x] 3.2 Add `"discovery"` to module allowlists in `scripts/build_deb.py` and `scripts/check_python.py`, extend offline help/completion assertions in `scripts/probe_completions.py`, `scripts/check_python.py`, and `scripts/accept_deb.py` for `printer discover` (`--timeout`, `--interface`), and verify with `uv run --locked python -m unittest discover -s tests -v`.

## 4. Onboarding, credential-lifecycle, and compatibility documentation

- [x] 4.1 Update `docs/pairing.md` and `docs/pairing-security-review.md` with: (a) end-to-end fresh-install onboarding walkthrough (printer-panel LAN-mode prerequisites, explicit unverified factory-reset/first-boot cloud-account boundary, `printer discover` vs explicit IPv4 pairing, multicast/VLAN topology limits, first-use trust, `doctor`, `status`), (b) SSDP unauthenticated-advertisement security review boundary, and (c) the 2026-11-26 credential-lifecycle/revocation findings (`accountDeleteUrl` unused by stock client, `code 19002` client limit, and non-destructive replacement/recovery workflow preserving existing access and `printer_id`-scoped markers); verify relative Markdown links with existing doc link tests.
- [x] 4.2 Update `docs/compatibility.md`, `docs/usage.md`, `README.md`, `ROADMAP.md`, and `CHANGELOG.md` to add `printer discover` across the command tree, compatibility matrix, validation evidence, and Milestone 1 exit evidence (marking Milestone 1 complete once live CLI discovery verification in task 5.2 succeeds); verify docs consistency and link checks via unit tests.

## 5. Offline gates and read-only live discovery verification

- [x] 5.1 Run the full offline validation gates: `uv run --locked python -m unittest discover -s tests -v`, `uv run --locked ruff check kobra_lan scripts tests`, and `sh -n kobra-lan`, confirming zero failures or lint errors.
- [x] 5.2 Run a strictly read-only live verification of `./kobra-lan printer discover` and `./kobra-lan --json printer discover` against the Kobra X (`20030` / firmware `2.0.2.2`) on the local LAN (confirming exit 0, `model_id: 20030`, `qualified_model: true`, `firmware_verified: false`, `unauthenticated: true`, `hardware_discovery_validated: true`, zero raw `LOCATION`/`cn` leakage, and zero writes to profiles or state), and record sanitized evidence in `docs/usage.md`.

## Workflow follow-up

- Archive the change with `openspec archive complete-independent-onboarding` after implementation and review requirements are satisfied.
- Verify the archived specs and repository state before opening or merging the PR.
