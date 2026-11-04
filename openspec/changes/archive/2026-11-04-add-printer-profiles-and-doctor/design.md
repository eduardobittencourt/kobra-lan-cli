# Design

## Context

See proposal.md for motivation and the three delta specs for the public contract. This design is necessary because selection, secret ownership, durable state and transport errors cross several modules.

The inspected merged baseline is `4c653bee74375bffa624a8652ec27c609c0d0a5d`, not this checkout's older HEAD. Its `cli.py` always supplies a default `--config` path, imports pairing eagerly and loads `Config` before network commands. `pairing.py` already stages private PEMs with directory descriptors, verifies explicit trust and publishes config without replacement. `mqtt.py` pins TLS before CONNECT, uses bounded fresh queries and exposes failures mainly as `ProtocolError`. `upload.py` and `start.py` derive state directories from a digest of `printer_id`. Package gates explicitly allowlist modules and synthetic installed probes already cover pairing.

## Goals / Non-Goals

**Goals:** Add a target-resolution layer without changing `Config` or operational state formats; separate local profile management from network diagnosis; make partial publication and removal outcomes inspectable.

**Non-Goals:** A general secret manager, automatic migration/copying of old credentials, global filesystem reference discovery, a new print-attempt model or a transport protocol rewrite. Existing qualification and physical-action safeguards apply unchanged.

## Decisions

### 1. Private registry beside unchanged configs

Add `profiles.py` for a versioned registry at `~/.config/kobra-lan/profiles.json` and managed per-profile directories at `~/.config/kobra-lan/profiles/<name>/`. Each directory contains the existing compatible `config.json` and pairing-owned `.pair-<id>/` material. Registry entries carry names, managed destinations and optional last-observed firmware metadata, never credentials. Names match `[a-z][a-z0-9-]{0,47}`; paths, whitespace, traversal and case aliases are rejected.

Use user-owned 0700 directories, 0600 files, no-follow directory operations and fsynced atomic index replacement. A private advisory lock serializes mutations; bounded/nonblocking lock acquisition returns a local diagnostic on contention. Keep the existing no-replace config publication primitive. An existing registry of an unknown version fails closed without rewriting it.

An embedded credential database was rejected because it would change the established config contract and expand the migration surface. A registry of arbitrary external paths was rejected for this first slice because removal ownership would become ambiguous.

### 2. Explicit resolution and a three-state default

Parse `--config` with an unset sentinel so explicit use can be distinguished from the legacy default. Global `--printer` and explicit `--config` conflict. A small resolver returns the chosen config plus a safe source descriptor; it never retries against another target.

The registry stores three default states: initial `legacy-fallback`, selected named profile, and `require-explicit`. Missing registry means `legacy-fallback`. Successful `printer use` selects a valid named profile; removal of the default commits `require-explicit`. A broken saved default is an error rather than legacy fallback. New named pairing without `--default` preserves the state, including on a fresh installation.

Old `~/.config/kobra-lan/config.json` remains in place. Inventory exposes it in a separate `legacy` field rather than inventing a registered name. `printer info` can inspect it via ordinary resolution or explicit `--config`; `printer use/remove` operate only on registered names. After adopting profiles, explicit `--config` remains the way to select old access without re-pairing. No import or migration command is introduced.

Commands `list/use/remove` reject global target selectors; their scope is already local/positional. `info` accepts either its positional name or ordinary global selection, never both. Profile names in the examples are illustrative, not translated identifiers.

For `inspect` and upload dry runs, validate selector syntax but retain local-only behavior: neither command requires a configured or reachable printer. Operational commands retain existing result schemas. Add selection tests at the CLI boundary instead of modifying upload/start internals.

### 3. Publication and removal have explicit commit points

Named pairing validates/reserves its destination under the registry lock before provisioning; only verified, complete configs enter the registry. Hold the exclusive lock through this bounded operation to avoid name/removal races. Existing unnamed pairing ignores the saved profile default and always uses its legacy or explicit absent destination; `--printer` is rejected for pairing. `--name` plus explicit `--config` and `--default` without `--name` are rejected.

Publish verified config first, register it second, then apply optional default selection. Failures before registration retain possibly referenced committed material but do not expose an incomplete profile. A complete unregistered config is an orphan with local inspection/cleanup guidance, never grounds to repeat provisioning or auto-adopt `candidate.json`. If registration succeeds but default selection fails, return exit 3 with the committed profile and actual default outcome so the user can run `printer use` locally. Reconcile registry contents after ambiguous write/fsync outcomes before reporting success or cleanup.

Managed config consumers hold a shared registry lease through their operation, including when an explicit config resolves inside the managed root; removal requires an exclusive lease. Revalidate metadata under the exclusive lock after confirmation. Removal commits registry detachment/default clearing before deleting exclusively managed material, so a crash cannot leave a selectable partial config. Failure after detachment reports an unregistered retained directory; repeated removal does not guess ownership or delete arbitrary files.

Deletion is limited to recorded managed config and pairing-created files within that profile tree. Check retained managed configs and the legacy config for references; preserve shared files, external PEMs, symlinks, unexpected contents and any ambiguous ownership/reference state. Arbitrary external configs cannot be exhaustively discovered: documentation must tell users that manually sharing managed paths outside the registry is unsupported and that retained files can require manual review. Removal results distinguish registration removal, deleted files and retained files; local deletion never implies device revocation.

Keeping all credential material forever was rejected because confirmed removal should clean up exclusively owned access. Blind recursive deletion was rejected because it could destroy shared or external material. Device receipt/start directories are never deletion candidates.

### 4. Doctor reuses protocol guarantees with typed stages

Add `diagnostics.py`; perform dependency checks through lazy imports so missing `cryptography` can produce a report instead of crashing the CLI at import time. Add narrowly scoped typed transport failure categories for TLS pin, authentication, subscription/protocol and timeout failures without changing their existing public operational messages or exits. Do not classify failures by parsing exception text.

Stages, in order: `configuration`, `dependencies`, `http_tcp`, `mqtt_tcp`, `tls_pin`, `mqtt_auth`, `status`, `compatibility`. HTTP is a TCP connection only: no HTTP request, `/info` provisioning or `/ctrl` POST. Use the configured ports. HTTP failure does not block MQTT. Reuse a single pinned authenticated MQTT session for a fresh `info` query; distinguish TLS/auth/status outcomes through typed stages. Qualification mirrors pairing identity checks without requiring idle state. Never serialize the raw info report, which can contain session tokens.

Each network stage has a timeout of at most 12 seconds and all network work shares a 60-second monotonic deadline. No reconnection or automatic replay. Dependencies of a failed stage become `skipped` with a reason; independent checks continue within the remaining deadline. A status query is the only application-level printer request.

Doctor emits the existing `ok` envelope with a new diagnostic `result` for both healthy and failed runs. Result schema version 1 contains `target`, ordered `checks` and `healthy`; each check contains `stage`, `status`, `code`, `message`, and `next_step` (nullable). A failed report also carries a safe top-level `error`. Exit 3 takes precedence over 2 if independent failures mix; skipped dependent checks do not add a second failure class. Parser/selector errors retain exit 2 before diagnosis. Existing commands' error envelopes remain unchanged.

### 5. Preserve installed behavior and state identity

No additional runtime dependency is needed. Extend `scripts/check_python.py` module allowlists (also consumed by Debian checks), synthetic runtime probes and Debian/Ubuntu package lifecycle fixtures. Preserve the current `--state-dir` and `printer_id` digest scheme across legacy/named access, profile removal and re-pairing. Two names for the same device must still hit the same reservation markers.

Update existing English docs, man page, roadmap and changelog in implementation. Prepare the next additive minor version according to `docs/releases.md`, without tagging or publishing. Keep help/version usable without config; no automatic doctor or migration runs during package install.

## Risks / Trade-offs

- Registry lock held during pairing can delay other local mutations -> bounded acquisition, clear contention diagnostics and no physical commands under the management path.
- Multi-file writes can be interrupted -> explicit commit points, fail-closed index validation, retained referenced secrets and synthetic failure injection.
- Manual external references cannot be proven absent -> managed ownership boundary, checks of known retained configs and conservative retention on uncertainty.
- Transport error categorization can regress existing commands -> preserve existing messages/contracts and run original pairing/client/start tests alongside stage tests.
- Default selection changes unqualified destinations by user choice -> explicit `printer use`/`--default`, safe source reporting, no fallback on failure or removal.
- This checkout predates pairing and community tooling -> implementation must first reconcile with the inspected merged baseline; do not recreate or backport those features in this change.

## Migration Plan

1. Before implementation, bring the implementation branch onto merged main while preserving these artifacts and unrelated user files. Archiving the completed community change is separate work.
2. Ship additive commands with lazy registry creation. Read-only commands and legacy operations do not write migration metadata. Users can continue using the old config unchanged.
3. Users opt into named profiles by named pairing and select a default explicitly. Document how to keep accessing the old config, inspect removal previews and recover retained orphan directories without network access.
4. For rollback, use the old executable with the unchanged legacy or an explicit complete config after checking state-format compatibility. Older binaries ignore the registry/default; explain that they cannot honor a cleared default. Keep all credentials and operational markers. Do not downgrade by deleting files.
5. Verification uses synthetic temporary homes and transports only. Any real printer validation or live devbox migration requires its own explicit authorization and applicable tooling-guide update.
