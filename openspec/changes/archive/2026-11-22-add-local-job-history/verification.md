# Local job history and watch observation verification

## Hardware validation (2026-11-23)

During an operator-authorized Kobra X (model 20030 / firmware 2.0.2.2) session
on 2026-11-23, `print watch` observation persistence and offline `jobs list` /
`jobs info` inspection were exercised alongside live starts, lifecycle controls,
and an intentional reprint chain:

- **Idle and unverified phases create no observation:** Running
  `print watch --timeout 1` while the printer reported `state: "free"` returned
  `outcome: "no_active_job"`, `reason: "idle"` (exit 0) and left `jobs list` at
  `total_count: 0`. Running `print watch` while the printer reported `init`
  (immediately after start) or `paused` returned `outcome: "unknown"`,
  `reason: "active_job_unverified"` (exit 0) without creating an observation
  record.
- **Active preparation and printing persist sanitized observations:** Running
  `print watch --timeout 3` during `nozzle_heating` persisted an `obs-...`
  record (`phase: "preparing"`, `observation_recorded: true`). Running
  `print watch --timeout 5` during active `printing` on both the slot-2 initial
  start and the slot-4 reprint persisted separate `obs-...` records
  (`phase: "printing"`, `current_layer: 1`, `total_layers: 290`,
  `observation_recorded: true`). In all cases `print watch` stdout omitted
  `observed_filename`.
- **Offline `jobs list` and `jobs info`:** Both text and root `--json` modes
  inspected the local store with zero network traffic and zero state writes,
  supporting `--kind all`, `--kind start`, and `--kind observation`.
  - Start attempts reported `client_attribution: "cli"`, verified upload
    provenance (`remote_byte_hash_verified: false`), `terminal_outcome: "unknown"`,
    and local-only `coverage` metadata.
  - After the reviewed reprint, `jobs info` linked `previous_attempt_id` and
    `next_attempt_id`, marked the superseded root attempt
    `reprint_eligibility: "superseded"` and the successor `"eligible_for_plan"`,
    and correlated each saved observation under `unattributed_matching_observations`
    (`attribution: "unattributed_filename_match"`) against its corresponding
    timestamp-ordered attempt.
  - Saved watch observations reported `client_attribution: "unattributed"` and
    `terminal_outcome: "unknown"`.
  - Existing receipts, `.attempt` markers, and observations remained untouched
    across `print pause`, `print resume`, and `print cancel`.
