# Verification

## Offline and installed checks

- Working tree based on `ea09cf7`, using uv 0.13.9 and Python 3.14.10:
  `uv sync --locked`, `uv run --locked python -m unittest discover -s tests -v`
  (212 discovered, 210 passed, two native shell tests skipped locally),
  `uv run --locked ruff check kobra_lan scripts tests`, `sh -n kobra-lan`,
  and `openspec validate enable-intentional-reprints --strict` passed.
- All five completion tests passed, including Bash, Zsh and Fish, in a
  disposable Debian 13 amd64 environment with networking disabled.
- `scripts/check_python.py` passed the source archive, wheel and independent
  installation checks on Debian 13. The Debian build, `scripts/check_deb.py`,
  `lintian` and `sha256sum --check SHA256SUMS` passed. Lintian reported only
  the expected `initial-upload-closes-no-bugs` warning.
- `scripts/accept_deb.py` passed on clean Debian 13 and Ubuntu 24.04 amd64
  environments with separate empty network namespaces. Both tested the same
  `kobra-lan-cli_0.5.0-1_all.deb` candidate, SHA-256
  `8351ce4e7113ad44dccd2239bae8911c3aba8600fb08464da88b4993f4f6dd05`.
  The installed probes covered help and all three generated completions with
  empty configuration. The test candidate was not published.

## Hardware qualification (2026-11-23)

On 2026-11-23 the operator authorized an integrated Kobra X (model 20030 /
firmware 2.0.2.2) session validating two deliberate starts of the same stored
290-layer Anycubic Slicer Next (`2.0.0.6`) PLA High Speed G-code file across
different onboard slots, using `auto-leveling on`, `vibration-compensation off`,
and `flow-calibration off`:

1. **Upload and first start (slot 2):** `files upload` returned HTTP 200 and
   `uploaded_verified_by_listing_and_metadata`. Ordinary `print plan` and
   `print start --execute` returned `ack` `code == 0`, `status: "start_observed_active"`,
   active project `state: "init"` with `task_id: "-1"`, and a root `attempt_id`.
   Subsequent read-only `status` and `print watch --timeout 5` confirmed active
   `printing` (`curr_layer: 1`, `total_layers: 290`). After the run ended,
   `status` reported `state: "free"`, `print: null`, and empty `last_print`;
   the operator independently confirmed physical completion and cleared the bed.
2. **Pre-reprint guards:** Ordinary `print plan` for slot 4 surfaced the root
   `attempt_id` and `start_status: "start_observed_active"` while keeping the
   ordinary plan digest. Executing `print start` without `--reprint-from` exited
   2 (`validation_failed`) without publishing. Calling `print plan --reprint-from`
   with an unrelated file's `attempt_id` also exited 2 (`validation_failed`).
3. **Reviewed reprint (slot 4):** `print plan --reprint-from <root-attempt>`
   produced a distinct reprint `plan_sha256` bound to `previous_attempt_id` with
   `upload_performed: false`. Executing `print start --reprint-from <root-attempt>`
   returned `ack` `code == 0`, `status: "start_observed_active"`, and a distinct
   successor `attempt_id` linked to `previous_attempt_id` while reusing the
   original upload receipt without re-uploading. Subsequent `status` and
   `print watch --timeout 5` confirmed active `printing` (`curr_layer: 1`,
   `total_layers: 290`). After the run ended, `status` reported `state: "free"`,
   `print: null`, and empty `last_print`; the operator independently confirmed
   physical completion (including printer power-loss recovery near the end of
   the print).

Both runs confirmed that fresh idle and empty `last_print` do not prove
completion on firmware 2.0.2.2; physical completion is attributed to operator
confirmation. Concurrency, uncertain-start, and replay checks remain offline.
