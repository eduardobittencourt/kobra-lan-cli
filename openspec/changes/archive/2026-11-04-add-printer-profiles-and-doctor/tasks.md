# Tasks

## 1. Establish the implementation baseline and profile storage

- [x] 1.1 Reconcile the implementation branch with merged main containing `4c653bee74375bffa624a8652ec27c609c0d0a5d`, preserving this change and unrelated local files; verify pairing, its main spec and community package tooling exist and baseline offline checks pass without printer access.
- [x] 1.2 Add the versioned private registry and managed-profile storage in `profiles.py`, including name validation, ownership/modes, descriptor-based no-follow access and no-replace destinations; verify synthetic tests for valid/invalid names, traversal, existing files, symlinks, permissions and unknown registry versions.
- [x] 1.3 Add bounded registry locking and atomic durable updates with explicit legacy-fallback, named-default and require-explicit states; verify concurrent writer and injected write/replace/fsync failure tests preserve a complete recoverable index and never replace a profile config.
- [x] 1.4 Document managed paths, ownership and commit/recovery boundaries in `docs/pairing.md`; verify examples match fixtures and explain retained unpublished/committed material without exposing real configuration.

## 2. Resolve targets and expose local inventory/default commands

- [x] 2.1 Add global `--printer`, explicit `--config` detection and centralized resolution; verify CLI tests for selector conflicts, named override, saved default, legacy fallback, cleared default, unknown names and broken selections without fallback to another printer.
- [x] 2.2 Implement offline `printer list` and `printer info [name]` with safe local metadata, separate legacy descriptor and per-entry unavailable states; verify empty/damaged inventories, positional/global conflicts, no socket calls, no registry creation on reads and no secret output.
- [x] 2.3 Implement `printer use <name>` with local loadability validation and persistent selection; verify offline use, invalid profile preservation and that profile registration alone does not select a default.
- [x] 2.4 Integrate resolution into existing operational commands and preserve local inspect/upload dry runs; verify unchanged existing JSON/exit/config contracts, help/version without config and selection syntax validation without requiring a printer for local-only commands.
- [x] 2.5 Document selection precedence, old-config access and command examples in the pairing/usage guides and Debian man page; verify contextual help and examples against synthetic CLI cases and update the docs index if paths are introduced.

## 3. Register named pairing without changing trust guarantees

- [x] 3.1 Extend named pairing with `--name` and `--default`, validate/reserve destinations before provisioning and reuse existing trust/status/private publication; verify synthetic end-to-end pairing and rejection of unsafe/duplicate names, selectors and default-without-name before network access.
- [x] 3.2 Publish registration and optional default selection with explicit reconciliation of partial outcomes; verify injected failures before config publication, before registry commit, after registry commit and during default update preserve referenced PEMs, prior access and truthful recovery diagnostics.
- [x] 3.3 Keep unnamed pairing destinations and results compatible and add named-flow metadata; verify original pairing tests, exact fingerprint/noninteractive rules and no implicit replacement of an existing default config.
- [x] 3.4 Document named-pairing examples, explicit default opt-in and local recovery without repeating provisioning in `docs/pairing.md`; verify examples in synthetic CLI tests and record the incremental onboarding scope in `ROADMAP.md`.

## 4. Remove managed profiles safely

- [x] 4.1 Implement removal preview, stderr terminal consent and unattended `--yes` with revalidation after confirmation; verify refusal/EOF/nonterminal behavior, no network calls, legacy exclusion, positional/global conflicts and unchanged files before affirmative consent.
- [x] 4.2 Add shared operation leases for managed access and exclusive removal, then commit detachment/default clearing before ownership-limited cleanup; verify active consumers, default/nondefault removal, symlink/shared/external/unknown files, retained orphans and injected deletion failures without silent fallback.
- [x] 4.3 Preserve state paths across names and local removal/re-pairing; verify synthetic upload/start markers for the same `printer_id` still block repeats through another profile, including uncertain outcomes and explicit `--state-dir`.
- [x] 4.4 Document local deletion versus revocation, cleared-default behavior, cleanup outcomes and the unmanaged external-reference limitation; verify JSON removal receipts identify deleted/preserved files without secrets and docs do not suggest clearing operational markers.

## 5. Diagnose connections through bounded read-only stages

- [x] 5.1 Add lazy runtime dependency loading and typed MQTT failure stages while retaining existing operational error contracts; verify missing-dependency, pin mismatch, authentication/subscription rejection and timeout tests plus the original client/pairing suite.
- [x] 5.2 Implement doctor configuration/dependency, independent TCP reachability and pinned MQTT/status/compatibility stages with the shared deadline; verify synthetic healthy, HTTP-only failure, TLS change before credentials, rejected auth, stale/absent reports, unsupported/conflicting identity and busy-printer cases, with no reconnect or provisioning/control calls.
- [x] 5.3 Add the versioned doctor JSON report, skipped dependencies, safe next steps and exit precedence; verify exact stage order/status fields, mixed-failure exit 3 precedence, finite timeouts, sanitization of injected secrets/control characters and byte-for-byte preservation of config, profile metadata and operational state.
- [x] 5.4 Document doctor stage semantics, 12-second stage/60-second network limits, exit codes and remediation in the usage/pairing guides and man page; verify documented examples against synthetic reports and clarify TCP reachability versus protocol/qualification success.

## 6. Preserve independently installed behavior

- [x] 6.1 Update Python/Debian archive module allowlists and installed runtime probes for profiles/doctor; verify wheel built from sdist and the same Debian artifact expose all new commands outside the checkout using declared runtime dependencies, without packaging private data or dev tools.
- [x] 6.2 Extend synthetic non-root private fixtures with registry, managed configs and markers; verify network-disabled Debian 13/Ubuntu 24.04 install/upgrade/remove/purge preserve their bytes and permissions and never invoke live pairing/doctor.
- [x] 6.3 Update release/rollback guidance and changelog and prepare the additive minor source version under the existing policy; verify shared version validation, package metadata, help/version and documentation links without creating tags, publishing assets or switching the live executable.

## 7. Verify integrated acceptance

- [x] 7.1 Run locked Ruff, coverage-backed offline tests, shell syntax and the relevant source/wheel/Debian build/content/lifecycle gates; verify the full synthetic legacy-to-named selection/removal/re-pairing workflow preserves state identity and all supported distribution checks pass without real printer access.
- [x] 7.2 Run strict OpenSpec validation and diff/secret-scope checks, map each scenario to automated evidence and record remaining qualification limits; verify no unsupported hardware claim, live installation change, physical command, release tag or publication was introduced.

## Workflow follow-up

- Archive this change after implementation and the repository's review requirements are satisfied. Archiving `prepare-community-repository` remains separate housekeeping.
- Any hardware acceptance, live devbox migration or public release is separate work requiring its own explicit scope; update the maintained tooling guide if a later migration changes the active installation.
