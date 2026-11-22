# Tasks

## 1. Local attempt state

- [x] 1.1 Add stable local attempt references and read the original file-keyed marker and receipt in place. Use synthetic fixtures to verify eligible legacy records, marker-only and receipt-only records, malformed or inconsistent evidence, and stable references across profiles and custom state paths. Assert that reading preserves original bytes and permissions.
- [x] 1.2 Add exclusive successor reservations and the per-device start lease with private durable writes. Test restart after an incomplete reservation, concurrent callers with different plans or profiles, and state path replacement before and after reservation. Verify that a persisted successor blocks its predecessor even if the successor receipt is incomplete.

## 2. Reviewed execution and CLI

- [x] 2.1 Add read-only `--reprint-from` planning and expose the latest safe attempt reference. Test the unchanged ordinary digest, separate reprint digest, cross-device and cross-file refusal, stale predecessor refusal and the absence of plan writes. Document how to find and review the predecessor in `docs/usage.md`.
- [x] 2.2 Add guarded execution to the normal `print start` route. Test the first start and a separately reviewed reprint with one publish each, the same upload receipt and distinct linked IDs. Verify the fresh final idle check, refusal on unresolved predecessors, stale review and duplicate invocation, safe partial results on uncertainty, and state preservation on interruption. Document execution and uncertainty handling in `docs/usage.md`.
- [x] 2.3 Update text and JSON interface checks, contextual help, bash/zsh/fish completion, README and manual page. Verify that malformed references produce a safe exit 2 before printer access, and that installed help and completion expose the flag on both commands with empty configuration.

## 3. Integration and qualification

- [x] 3.1 Run the locked offline suite, Ruff, launcher syntax check and strict OpenSpec validation. Run the relevant Python archive and Debian acceptance checks in `docs/releases.md` for the installed interface changes.
- [ ] 3.2 With separate authorization and agreed timing, use the qualified Kobra X setup to validate two deliberate starts of the same stored file on the printer. Confirm activity for the first run and operator-confirmed end before the reprint. Verify that the reprint uses the same upload provenance and yields a distinct linked attempt ID. Record sanitized evidence and attribute terminal outcomes to their observed source. Keep concurrency, uncertain-start and replay checks offline.

  Hardware validation is deferred to a future integrated test session covering
  reprints and print lifecycle controls. This task remains open; agree on the
  timing and authorized actions before operating the printer.
