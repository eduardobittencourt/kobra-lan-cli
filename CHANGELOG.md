# Changelog

## Unreleased

## 0.4.0

- Add named private printer profiles, offline inventory/info, explicit target
  selection, opt-in saved defaults and consent-based local removal.
- Extend named pairing without changing initial trust, no-overwrite guarantees,
  legacy config schema or device-based upload/start reservations.
- Add bounded read-only doctor with eight ordered stages, sanitized version 1
  reports and existing exit classes. No automatic provisioning or repair.
- Preserve legacy access; removal of a saved default requires explicit selection.
  Older binaries ignore profile defaults, including cleared defaults: review
  selection and state compatibility before rollback; preserve private state.
- Extend installed Python/Debian probes and non-root lifecycle fixtures. Runtime
  dependencies and Kobra X model 20030 / firmware 2.0.2.2 qualification are unchanged.
- This prepares source only; no release, tag, publication or live migration.

## 0.3.0

- Add `printer pair --host` for direct provisioning of an already LAN-enabled
  Kobra X model 20030 / firmware 2.0.2.2, with explicit terminal consent or an
  exact `--trust-sha256` fingerprint and a read-only status check before save.
- Publish private compatible configuration atomically without overwriting an
  existing destination. Preserve existing access and upload/start markers.
- Require `cryptography>=41` in Python and `python3-cryptography (>=41)` in Debian
  packaging; carry dependencies through offline tests and installed acceptance.
- Keep existing commands, JSON, exit codes and configuration/state schemas.
  HTTP provisioning remains unauthenticated; other firmware, discovery,
  replacement, revocation and initial LAN-mode setup remain unqualified.
- This is source version preparation, not publication of a package or release.

- Prepare independent Python and Debian distributions and a gated release workflow.
- Preserve existing CLI, JSON, configuration and durable state contracts.

## 0.2.1

- Experimental direct Kobra X LAN client with offline G-code inspection, reviewed
  uploads and guarded print start. See README for the limited observed hardware
  configuration; print completion and quality remain unqualified.
- Commands, flags, JSON output, exit codes, configuration and receipt/attempt
  formats remain experimental during 0.x. This packaging setup introduces no
  state migration and does not change duplicate protection.
- This section records the existing source version; it does not claim that a
  public release or Debian package was previously published.
