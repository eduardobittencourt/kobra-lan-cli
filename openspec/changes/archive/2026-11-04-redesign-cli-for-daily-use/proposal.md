# Proposal

## Why

The CLI is ready to become a coherent daily-use tool, but currently mixes flat and grouped commands and exposes JSON as its only presentation. There are no external users to migrate, so this is the right time to establish the intended interface without aliases or deprecation machinery.

## What Changes

- **BREAKING** Replace flat operations with `files list|info|upload`, `gcode inspect`, and `print plan|start`; retain `printer pair|list|info|use|remove`, `doctor`, and `status`. Remove superseded invocations outright.
- **BREAKING** Make readable English text the default and provide global `--json` for a documented versioned machine contract, including sanitized argument errors. Keep prompts/progress on stderr and exit classes 0/2/3.
- Separate inspection, upload, planning and start. `files upload` requires `--execute` and the inspected file's `--sha256`; it has no implicit dry run. `print plan` is read-only; `print start` requires `--execute` and the reviewed `--plan-sha256` and revalidates the plan before sending.
- Apply uniform target selection, contextual help, end-to-end examples and offline `completion bash|zsh|fish` generation. Format and completion must never trigger extra printer queries or bypass confirmation.
- **BREAKING** Require a named profile for every new pairing. Remove automatic root-config lookup, unnamed pairing, legacy inventory entries and legacy defaults without migration or compatibility shims. An unset default is null and requires explicit selection. Explicit `--config` remains a deliberate read/access selector, not a pairing destination.
- Keep trust and device-based duplicate protection for all operations after setup. The owner separately authorized a complete one-time local reset without backups; do not introduce a CLI reset/retry feature.
- Prepare source version 0.5.0 and update documentation and installed-package acceptance; do not publish a release.

## Capabilities

### New Capabilities

- `cli-interface`: Command hierarchy, text/JSON presentation, sanitized errors, help, offline shell completion and installed interface acceptance.
- `reviewed-job-submission`: Local inspection, explicit reviewed upload, read-only print planning and guarded start using existing immutable files and durable device-based state.

### Modified Capabilities

- `printer-pairing`: Replace JSON-only result requirements with the shared text/opt-in JSON contract, retaining every trust and persistence guarantee.
- `printer-profiles`: Replace its JSON-only output requirement with the shared presentation contract.
- `connection-diagnostics`: Provide equivalent text and JSON staged reports, retaining ordered checks, safe partial results and exit precedence. Align optional MQTT identity fields with pairing and distinguish incomplete required qualification evidence from observed conflicts.

## Impact

Touches `kobra_lan/cli.py` and presentation/parser code, adapters around `upload.py`/`start.py`, offline tests, synthetic installed probes, package module/content allowlists, completion packaging and documentation. Existing release-distribution requirements already allow a breaking minor release during 0.x; version remains sourced only from `kobra_lan.__version__`. No new runtime dependency is planned.

Out of scope: aliases, deprecation periods, discovery, credential repair/revocation, new firmware or slicer support, print watching/history/reprints, pause/resume/cancel, deletion/download, hardware operations, live installation migration, publication and archiving unrelated changes. Legacy access compatibility is intentionally removed; no existing installation needs migration.
