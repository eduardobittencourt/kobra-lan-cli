# Design

## Context

See `proposal.md` for motivation and scope. The existing CLI loads `Config` before network operations, uses an IPv4 target, and authenticates MQTT/TLS on port 9883 with a client certificate/key and server certificate pin. Its configuration schema already contains all fields needed after pairing. MQTT checks the pin before sending username/password; this behavior must remain intact. `inspect` and upload dry runs must remain local.

Observed in this conversation on one model 20030 / firmware 2.0.2.2 printer:

- `/info` supplied a token and a same-host HTTP control URL on port 18910.
- A signed POST returned a decryptable credential bundle containing the device identity, MQTT username/password, and client PEM certificate/key.
- The returned credentials matched the pre-existing setup; both new and original credentials authenticated afterward.
- An isolated in-memory bootstrap using only the address/ports from the old setup obtained credentials and queried status with the newly observed server fingerprint. Only afterward was that fingerprint compared with the previous trusted value, and it matched.
- A deliberately incorrect pin was rejected before MQTT credentials were sent. No print, upload, heater, movement, or other control command was issued.

These are feasibility observations, not tests of the proposed command, persistence, interactive consent, reset behavior, or other firmware. Credentials and device identifiers must not become fixtures. Protocol references: [LAN credential helpers](https://github.com/stribor/anycubic_kobrax/blob/master/custom_components/anycubic_kobrax/lan_credentials.py) and [HTTP probe](https://github.com/stribor/anycubic_kobrax/blob/master/custom_components/anycubic_kobrax/lan_probe.py). Record the exact reference revision during implementation for provenance; no HA modules are runtime dependencies.

Packaging currently assumes a standard-library-only application. `scripts/check_python.py` rejects any `Requires-Dist`, enumerates application modules, and installs its wheel with `--no-deps --no-index`. `scripts/check_deb.py` reuses that module list. The network-disabled Debian/Ubuntu acceptance image currently preinstalls only Python and basic utilities.

## Goals / Non-Goals

**Goals:** Keep network parsing, trust decisions, and configuration publication separable and testable with synthetic data. Reuse the existing config contract and MQTT safeguards. Provide an unattended path that requires a specific fingerprint rather than implicit trust.

**Non-Goals:** Add a generic remote-control endpoint, change JSON defaults, migrate existing config/state, replace configured access, authenticate initial HTTP provisioning cryptographically, or infer support beyond the observed firmware.

## Decisions

### 1. Add one command without restructuring existing operations

Add `printer pair --host <IPv4> [--trust-sha256 <64-hex>]` beneath a new `printer` group. The existing global `--config` remains the destination selector and must appear before `printer`. Pairing branches before `Config.load`, because a fresh destination is expected. Bare IPv4 validation follows current runtime support; automatic discovery and hostnames can be designed separately.

Examples:

```sh
kobra-lan printer pair --host 192.0.2.10
kobra-lan --config ~/.config/kobra-lan-test/config.json printer pair \
  --host 192.0.2.10 --trust-sha256 <EXPECTED_SHA256>
```

Fail on an existing destination, including dangling symlinks, before network access. No `--force`, overwrite prompt, or replacement workflow is introduced. This avoids mixing first-use setup with access migration. A separate absent destination covers isolation without introducing named profiles.

### 2. Implement the LAN handshake with bounded synchronous HTTP

Use a new `provisioning.py` module and the standard-library HTTP client, matching the synchronous architecture. Network calls have a 10-second timeout, at most 1 MiB of response body, no redirects, no proxy/environment-derived destinations, and no automatic POST retries. Accept a bare identity object or a successful object wrapper with a `data` object; reject unexpected types and failure codes.

Protocol steps:

1. GET `http://<selected IPv4>:18910/info`; require a string token of at least 32 characters and a valid `ctrlInfoUrl`.
2. Restrict that URL to HTTP, the exact selected IPv4, port 18910, and `/ctrl`; reject userinfo, query, and fragment.
3. Generate `ts` as decimal epoch milliseconds, a six-character cryptographically random alphanumeric nonce, and `did` as an uppercase UUID4 hex string. Compute lowercase hexadecimal `sign = MD5(MD5(token[:16]) + ts + nonce)`.
4. POST `/ctrl` with `ts`, `nonce`, `sign`, and `did` as URL query parameters. Require success code 200 and an object `data`.
5. Strictly Base64-decode `data.info`; decrypt AES-128-CBC using UTF-8 bytes of `token[16:32]` and the 16-byte UTF-8 IV in `data.token`; remove PKCS#7 padding and parse a bounded JSON object.
6. Validate required nonempty string fields `deviceId`, `username`, `password`, `devicecrt`, and `devicepk`; normalize `modelId` or `modeId`. Validate the identifier against current config rules and reject unsupported model 20030 alternatives before MQTT. Parse PEMs and verify that the private key matches the certificate's public key.

MD5 and AES parameters are protocol compatibility requirements, not choices for a new security design. Use `cryptography`, with a minimum version compatible with both supported distributions (>=41), rather than a handwritten AES implementation or an external OpenSSL process with sensitive command-line arguments. Keep the decrypted bundle out of representations, exceptions, logs, and stdout.

### 3. Make first-use trust explicit and recheck it at authentication

Stage the client PEMs privately, perform a TLS handshake with that client identity, and calculate SHA-256 of the server's DER certificate. This observation sends no MQTT CONNECT packet. Display only sanitized metadata and the fingerprint. The prompt must explain that accepting the certificate trusts this first connection; the HTTP token and encrypted bundle do not establish authenticated initial trust.

If `--trust-sha256` is supplied, validate 64 hex digits before network access and require a constant-time match with the observed fingerprint. Otherwise prompt on stderr only when stdin is a terminal; accept explicit `y`/`yes`, default to refusal on empty input, and fail without prompting for noninteractive input. An invalid explicit fingerprint must never fall back to an interactive prompt. Do not introduce a general `--yes` trust bypass.

After acceptance, construct a candidate `Config` and use the existing `MQTT` connection to recheck the accepted pin before sending username/password. A changed certificate between observation and authentication therefore fails. Query only `info`; require a fresh report with the expected model and firmware 2.0.2.2 before publication. A busy status is informational: pairing does not require an idle printer or attempt to change its state.

TLS transmits the client certificate during negotiation; the pin-before-credentials promise applies specifically to MQTT username/password. The private key is not sent. Alternatives rejected: silently disabling verification for all future connections, treating the HTTP signature as device authentication, or automatically trusting changed certificates.

### 4. Publish configuration as the final durable commit

Keep persistence in a focused helper module, `pairing.py`, alongside command orchestration, or split further only if implementation warrants it. Use the selected config's parent as the private root: create a missing directory with mode 0700, or require an existing user-owned nonsymlink directory with mode 0700. Do not silently chmod a shared directory. Use directory-relative, no-follow file operations for managed artifacts to avoid symlink replacement.

Create an unpredictable, invocation-owned subdirectory with mode 0700 for PEMs and staging. Create all secret files exclusively with mode 0600. Store absolute paths to the final PEMs in the unchanged `Config` JSON schema. TLS may load the private PEMs from this directory before publication. On success the same files remain referenced; no rename of their directory is needed.

Write and fsync a complete candidate JSON file with mode 0600; fsync the PEM files and private directory before making the selected config visible. Publish the candidate atomically with no overwrite, using a same-filesystem hard link from the staged JSON into the destination, or an equivalently tested no-replace primitive. Plain `os.replace` is insufficient because it can overwrite a concurrent config. Fsync the containing directory and remove the staging JSON link after publication. Preserve the referenced PEM directory.

Before publication, handled failures or declined trust remove this invocation's staged secrets. Never delete another invocation's files. After publication, retain referenced PEMs even if final cleanup or durability reporting fails; report a safe persistence diagnostic rather than deleting material needed by a visible config. An abrupt process kill can leave a private unreferenced staging directory: document safe inspection/removal without promoting it to a valid config or touching receipts. No multi-file transaction can promise cleanup after every crash.

This arrangement ensures readers see either no config or one referencing complete files; unrelated configurations and attempt markers stay untouched. Re-pairing with replacement and revocation semantics remains a future change.

### 5. Keep existing output and failure conventions

Return one JSON document on stdout. Successful pairing reports `config_path`, `model_id`, `firmware`, `tls_sha256`, and an observed printer state. Human metadata and trust prompts go to stderr with terminal control characters escaped and bounded lengths.

Use safe stage-specific messages for identity, provisioning, response validation, trust, authentication, status qualification, and persistence. Preserve exit 2 for protocol/validation/trust refusal and exit 3 for local configuration/filesystem or network failures. An existing destination is a local configuration failure. Never embed arbitrary response bodies or URLs in errors, including HTTP exception strings. Existing command output and exit behavior remain unchanged.

### 6. Carry the dependency through the installed product

Declare `cryptography>=41` in `pyproject.toml` and the matching Debian `python3-cryptography` runtime/build requirements. Update Debian package text that currently says credentials must be provisioned separately and runtime uses only the standard library.

Update archive allowlists for the new application modules and legitimate dependency metadata (`requires.txt` in sdist metadata and `Requires-Dist` in wheels). Replace the blanket dependency rejection with exact checks for the intended declared dependency. Do not relax secret/package-content exclusions.

Update Python installation verification so required dependencies are installed through a documented build-time installer or supplied wheelhouse before offline CLI probes. For Debian acceptance, provision the declared dependency and its distro dependency closure in the disposable image while networking is available, then retain the network-disabled install/upgrade/remove/purge checks. Assert package dependency metadata; installation hooks must never run pairing. Update CI unit/build environments to install declared test/runtime requirements before offline execution.

Help, invalid-input handling, and synthetic pairing must work outside the checkout on Debian 13 and Ubuntu 24.04. Packaging must not fetch dependencies at command execution time.

## Risks / Trade-offs

- [Unauthenticated HTTP provisioning and first-observed TLS certificate] -> Explain the trust boundary and require explicit acceptance or an independently supplied exact fingerprint. TOFU protects continuity after acceptance; it cannot prove the initial network peer's identity against an active attacker.
- [Firmware-specific reverse-engineered protocol] -> Fail closed for malformed replies and unsupported model/firmware; scope initial evidence to one Kobra X and record exact reference revisions.
- [Repeated provisioning could behave differently after resets or LAN-mode changes] -> Do not claim revocation/rotation semantics. One test preserved access; replacement and resets remain out of scope.
- [Private staging needed by Python TLS APIs] -> Use private exclusive files, clean up handled failures, and document crash leftovers. No plaintext secrets in the repository or test fixtures.
- [New binary crypto dependency affects reproducible packaging] -> Use distro-supported versions, explicit metadata checks, and clean installed-package tests on both supported systems.
- [Trust confirmation was simulated by the probe] -> Test real terminal and noninteractive CLI paths with synthetic data before considering the command ready.

## Migration Plan

Ship as an additive minor feature under the project's 0.x compatibility policy; no release publication is part of implementation. Existing users keep their config and need no re-pairing. New users enable LAN mode, supply an IPv4 address, review first-use trust, and then use ordinary `status` with the saved config. Update README, ROADMAP, NOTICE, Debian man page/package description, and dependency/release notes together.

For installed-command hardware acceptance, use an alternate absent config path and the already known server fingerprint. Query status with the saved alternate config, then verify the original config still works. Do not reset the printer, toggle LAN mode, rotate/revoke credentials, upload, or issue physical controls. Preserve original receipts and markers. Record only sanitized outcomes and clearly separate preimplementation feasibility probes from implemented-command validation. The user's existing hardware-test authorization covers this scoped access test; it does not authorize starting a print.

Rollback leaves existing user data intact. An older CLI can read the unchanged generated schema, provided certificate paths remain present. Removing an isolated test config and only the PEM directory it owns does not revoke device access and must not remove operational markers.
