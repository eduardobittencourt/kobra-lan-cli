# Tasks

## 1. Establish the canonical parser and command routes

- [x] 1.1 Restructure `cli.py` around the approved command tree and shared root options, disabling option abbreviation; verify help/argument tests cover every leaf, missing subcommands, global-option placement and rejection of removed flat invocations before side effects.
- [x] 1.2 Route `files list|info`, `gcode inspect`, profiles, status and doctor through existing operations and selection rules; adapt affected CLI tests and verify explicit/default/unnamed selection, selector conflicts and offline local operations still behave correctly.
- [x] 1.3 Update README and contextual help with the canonical tree and local/read-only/execution boundaries; verify examples use supported signatures and contain no accidental live-action execution in automated checks.

## 2. Add shared text and JSON presentation

- [x] 2.1 Implement `cli_output.py` and one CLI result boundary with default text and explicit root `--json`, the version-1 envelope and stable error codes; verify representative success/failure/empty/partial results, redirected output and exit 0/2/3 behavior in both modes.
- [x] 2.2 Bring parser failures into sanitized error handling and validate execution inputs before access/state changes; verify unknown commands, missing options, malformed hashes and hostile synthetic values never leak secrets or trigger network, config publication or reservations.
- [x] 2.3 Render pairing/profile/doctor results through the shared boundary while preserving prompts, safe partial outcomes and diagnostic precedence; update their CLI tests for explicit JSON and verify noninteractive trust/removal refusal plus equivalent staged text/JSON reports.
- [x] 2.4 Document the envelope, per-command result shapes, stable error-code mapping, stdout/stderr policy and help/version/completion exceptions in `docs/usage.md`, updating pairing examples; verify documented examples against synthetic outputs and both formats retain qualification and uncertainty information.

## 3. Separate reviewed submission operations

- [x] 3.1 Make `files upload` require `--sha256` and `--execute` with no implicit dry run, using `gcode inspect` for review; adapt upload CLI tests and verify missing/malformed/mismatched review fails before access, successful bytes remain identical and no print command is sent.
- [x] 3.2 Implement `print plan` and execution-only `print start` adapters over existing plan/start engines with explicit preparation inputs; verify read-only planning, format-independent plan hashes, changed-plan refusal, verified receipt enforcement, final idle checks and one-send ordering.
- [x] 3.3 Add regression scenarios exercising existing synthetic device/file attempt markers through new routes, alternate profiles and custom state directories; verify duplicate/uncertain attempts stay blocked and configuration, receipts, permissions and marker identities are preserved.
- [x] 3.4 Update operation documentation and help with the full inspect/upload/plan/start workflow, hashes and experimental evidence boundaries; verify both renderers show copyable review hashes, target, slot/material/preparations and accurate acknowledged/active/uncertain states.

## 4. Deliver offline shell completion

- [x] 4.1 Implement `completions.py` and `completion bash|zsh|fish` using canonical command/option metadata; verify generation without config or installed shell binaries and check command/flag/fixed-choice coverage, local file operands and absence of operational network/state callbacks.
- [x] 4.2 Smoke-test generated scripts in available bash/zsh/fish shells, checking sourcing and representative completions including root options; record any unavailable-shell limitation explicitly and verify completion does not execute printer commands or expose private contents.
- [x] 4.3 Document user-level completion installation for all three shells without modifying shell startup files; verify examples consume the generator supplied by the installed CLI rather than checkout-relative resources.

## 5. Integrate packages, probes and source release metadata

- [x] 5.1 Add new modules to Python/Debian build and archive allowlists and adapt relevant fixtures/tests; verify wheel/sdist/Debian content checks accept only intended files and preserve runtime dependencies, GPL-3.0-only and NOTICE attribution.
- [x] 5.2 Update synthetic pairing/profile probes, installed diagnostics tests, `accept_deb.py` and other executable CLI consumers for the canonical commands and explicit JSON; verify installed healthy/failing diagnostics, local inspection, safe parse errors, help/version and all completion generators outside the checkout.
- [x] 5.3 Update `debian/kobra-lan.1`, documentation index, roadmap and development/release examples to match the new interface and completion delivery; verify maintained links, packaged documents and CLI references while leaving historical archived changes intact.
- [x] 5.4 Prepare source version 0.5.0 in the single authoritative version source and corresponding changelog notes describing command/output breaks and unchanged private state; verify `scripts/release_version.py --tag v0.5.0` and package/runtime version agreement without creating a tag or publishing.

## 6. Verify the integrated change

- [x] 6.1 Run `uv sync --locked`, `uv run --locked python -m unittest discover -s tests -v`, `uv run --locked ruff check kobra_lan scripts tests`, `sh -n kobra-lan` and `git diff --check`; verify all pass with synthetic transports and record concrete blockers without weakening analyzer or review gates.
- [x] 6.2 Run the relevant Python archive/build/install and Debian build/lintian/disposable Debian 13/Ubuntu 24.04 acceptance gates from `docs/releases.md`; verify both formats and completions work outside the checkout and upgrade/removal preserve seeded user data without hardware access or host package lifecycle changes.
- [x] 6.3 Validate the OpenSpec change and review the integrated command/help/docs/package contract against every delta scenario; record evidence and limitations before handoff, without live migration, physical operations or publication.

## 7. Remove legacy setup after owner testing

- [x] 7.1 Require --name for CLI pairing, remove automatic root-config lookup and legacy inventory/default/cleanup branches, use a null unselected default, and reject old state without migration; verify no-name pairing and absent selection fail before network or storage changes.
- [x] 7.2 Update profile/pairing/diagnostic tests, installed probes, fixtures, documentation and changelog to named-only setup; retain explicit --config access and runtime trust, private publication and device-marker safeguards.
- [x] 7.3 Run the full offline/lint/shell/OpenSpec checks and Python/Debian build/install/lintian plus Debian 13/Ubuntu 24.04 disposable acceptance on the final named-only interface; record exact evidence and shell limitations.
- [x] 7.4 Complete the owner-authorized one-time local data reset; verify fresh offline inventory/no-target refusal and update the local access guide without printer operations.

## 8. Align doctor qualification with observed firmware

- [x] 8.1 Make optional MQTT device/model IDs follow pairing semantics, distinguish missing required evidence from conflicts, and disclose omitted optional IDs without adding queries or changing trust/authentication safeguards.
- [x] 8.2 Add offline regressions and installed probes for omitted optional IDs, missing required fields and conflicting identifiers; update diagnostic documentation and change artifacts.
- [x] 8.3 Run offline, lint, shell, OpenSpec and installed-package checks; verify doctor read-only on the owner-authorized target and record current evidence and limitations.
