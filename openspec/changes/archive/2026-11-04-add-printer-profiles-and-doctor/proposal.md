# Proposal

## Why

Direct pairing now works for a qualified LAN-enabled Kobra X, but users still select configuration paths manually and receive limited connection diagnostics. Named profiles and a read-only doctor command complete the next onboarding slice without changing print controls or existing automation contracts.

## What Changes

- Add offline `printer list`, `printer info [name]`, `printer use <name>`, and confirmed `printer remove <name>` commands for named local profiles.
- Add global `--printer <name>` selection, persistent defaults, explicit-selector conflict detection, and continued access to the existing single configuration without copying credentials or pairing again.
- Extend `printer pair` with optional `--name` and `--default`; retain the existing unnamed/explicit-config flow and all trust and no-overwrite guarantees.
- Add `doctor` with bounded configuration, dependency, TCP, pinned TLS, authentication, fresh status and compatibility checks, reporting safe actionable results without repairing state.
- Preserve JSON stdout, existing commands and exit codes, config schema, receipt paths, device-based duplicate protection and private data during package lifecycle operations.
- Document default removal, profile ownership, legacy access and recovery after interrupted local writes. No silent target changes after a saved default is removed or becomes unusable.
- Exclude discovery, address editing, credential replacement/revocation, printer/app LAN activation, new physical controls, human-output mode, shell completions and release publication.

## Capabilities

### New Capabilities

- `printer-profiles`: Local profile inventory, deterministic selection, persistent defaults, legacy configuration compatibility and safe local removal.
- `connection-diagnostics`: Bounded read-only connection diagnosis with sanitized stage results and next steps.

### Modified Capabilities

- `printer-pairing`: Support named managed destinations and optional default selection while retaining unnamed and explicit-config onboarding and existing trust/persistence guarantees.

## Impact

The implementation baseline is merged `main` commit `4c653bee74375bffa624a8652ec27c609c0d0a5d`, including pairing from PR #1. The current working checkout is older (`994e170`); integrate that baseline before implementation rather than recreating pairing. This planning change does not update the checkout, archive other changes, or modify main specs.

Affected areas: `kobra_lan/cli.py`, configuration resolution, new profile/diagnostic modules, existing pairing and MQTT stage reporting, offline tests, installed-package probes and archive allowlists, Debian man page, `docs/pairing.md`, `docs/usage.md`, `docs/releases.md`, the docs index, roadmap and changelog. No new runtime dependency is expected. Python >=3.11 and the existing Linux qualification remain unchanged; no hardware access, live installation migration, tag or release is authorized by this proposal.
