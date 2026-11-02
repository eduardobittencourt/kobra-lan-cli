# Tasks

## 1. Provisioning protocol and crypto dependency

- [x] 1.1 Add `cryptography>=41` to Python metadata and install it in offline-test preparation; verify it is available in the development/test runtime and the dependency resolves on the supported distribution versions.
- [x] 1.2 Implement bounded `/info` and signed `/ctrl` exchange in `provisioning.py`, including IPv4/endpoint restrictions and no redirects or POST replay; verify synthetic HTTP tests cover bare/wrapped identity objects, exact request parameters, unsafe URLs, failed status codes, timeout, and oversized/invalid responses.
- [x] 1.3 Implement bundle decryption and identity/PEM validation; verify independent synthetic known-answer vectors cover signature construction, AES-CBC/PKCS#7 decoding, both model-field spellings, malformed encoding/padding/JSON, missing fields, unsupported models, and mismatched certificate/key material without real printer secrets.
- [x] 1.4 Record the exact upstream protocol reference revision in NOTICE and document the handshake's unauthenticated HTTP boundary in the onboarding instructions; verify the references are resolvable and no device secrets or raw captures are included.

## 2. Initial trust and status verification

- [x] 2.1 Add isolated TLS fingerprint observation using provisioned client PEMs, followed by the existing pinned MQTT connection and only an `info` query; verify mocked transport tests show no MQTT credentials during observation and no control/upload operations anywhere in pairing.
- [x] 2.2 Implement explicit interactive trust acceptance and exact `--trust-sha256` matching, with terminal-safe metadata on stderr; verify tests for explicit acceptance, refusal, empty input, EOF, noninteractive input, invalid fingerprint, mismatch, and certificate changes between observation and authentication.
- [x] 2.3 Enforce fresh status/identity and model 20030 / firmware 2.0.2.2 qualification before save; verify tests cover rejected authentication, stale/missing reports, conflicting identity, unsupported firmware, and successful verification of both free and busy states without changing state.
- [x] 2.4 Document first-use trust, externally supplied fingerprints, the distinction between client certificate exchange and MQTT credentials, and the hardware qualification limit; verify the examples agree with the implemented acceptance behavior.

## 3. Safe configuration publication

- [x] 3.1 Implement private PEM staging and config construction under the selected config directory using user ownership checks, 0700 directories, 0600 files, exclusive creation, and no-follow operations; verify permission/symlink tests and that `Config.load` can read the resulting schema.
- [x] 3.2 Implement fsynced, atomic no-overwrite config publication after trust/status verification and cleanup of invocation-owned staging material; verify injected write/fsync/publication failures, declined trust, and concurrent destination creation preserve existing data and never expose a partial config or delete PEMs referenced by a committed config.
- [x] 3.3 Refuse existing config paths before network access and support a separate absent destination; verify tests cover ordinary files, dangling symlinks, parallel attempts, preserved original PEMs, and unchanged upload/start attempt markers.
- [x] 3.4 Document generated file locations, private-directory prerequisites, refusal to replace config, and safe cleanup of an isolated setup or abandoned private staging; verify the instructions preserve original access and distinguish local cleanup from device revocation.

## 4. CLI integration and user-facing contract

- [x] 4.1 Wire `printer pair --host` and `--trust-sha256` into `cli.py` before existing-config loading, preserving global `--config`; verify parser/help tests and a synthetic end-to-end command from absent config through saved config to ordinary `status`.
- [x] 4.2 Return one JSON result with safe success metadata or stage-specific diagnostics, preserving exit codes 0/2/3 and stderr-only prompts; verify captured stdout/stderr tests for provisioning, trust, authentication, unsupported firmware, existing config, and filesystem/network failures, including injected sensitive values and terminal control characters.
- [x] 4.3 Add complete README examples for interactive first use, unattended fingerprint-pinned setup, alternate config paths, and existing-config behavior; update ROADMAP onboarding status and Debian man page, then verify help/docs consistency and that existing command examples remain valid.

## 5. Packaging the new runtime behavior

- [x] 5.1 Update `scripts/check_python.py` and package tests for new module allowlists and exact dependency metadata, including sdist `requires.txt`; provision declared dependencies before isolated installed-command checks and verify wheel/sdist installation outside the checkout without relaxing secret exclusions.
- [x] 5.2 Declare Debian crypto runtime/build dependencies and update the package description, `scripts/check_deb.py`, and CI build environment; verify the built package's dependency metadata and content allowlists, including all new application modules.
- [x] 5.3 Prepare the distro dependency closure in `scripts/acceptance.Dockerfile` and extend installed-package checks with pairing help and synthetic onboarding; verify network-disabled installation/upgrade/remove/purge acceptance on Debian 13 and Ubuntu 24.04 while seeded private files and markers remain unchanged.
- [x] 5.4 Update release/dependency documentation and changelog for the additive minor feature, removing standard-library-only claims; verify source version/tag expectations and documentation are consistent without publishing a release.

## 6. Integrated acceptance

- [x] 6.1 Run the full offline suite and existing Python/Debian package validation paths with the new dependencies; verify existing upload/start protections and local-only inspection/dry runs still pass, with no real-printer access from automated tests.
- [x] 6.2 Exercise the implemented installed command against the authorized Kobra X using a separate absent config and known fingerprint, then run ordinary status with both new and original configs; verify model/firmware/state, config permissions, original access, and unchanged operational markers, with no upload or physical controls. Keep private test material outside the repo under the prescribed project research area.
- [x] 6.3 Record sanitized implemented-command acceptance results separately from the earlier in-memory feasibility observations; verify all `printer-pairing` scenarios have automated coverage or explicit hardware evidence and run `openspec validate add-lan-printer-pairing --strict`.
