# Design

## Context

See [proposal.md](proposal.md) for motivation and scope.

Currently, local operational state lives under `--state-dir` (default `~/.local/share/kobra-lan/uploads`):
- Upload markers and receipts: `<state-dir>/<device16>/<file_sha256>.{attempt,json}`
- Start markers and receipts: `<state-dir>/starts/<device16>/<key>.{attempt,json}`, where `<key>` is `<file_sha256>` for root attempts (legacy and current format) and `<attempt_id>` for reprint successors.
- `device16` is the first 16 lowercase hex characters of `device_digest = sha256(config.printer_id.encode()).hexdigest()`.
- `print watch` (`kobra_lan/watch.py`) currently emits a final summary without writing to `--state-dir`, and `WatchProgress` keeps validated scalar fields (`phase`, `progress`, `current_layer`, `total_layers`) plus `initial_filename` (validated by `project_filename()`).
- Firmware `2.0.2.2` reports placeholder `task_id: "-1"` during active runs and empty `last_project` after completion, so no LAN query provides attributable completed-run history.

## Goals / Non-Goals

**Goals:**
- Provide fast, 100% offline, strictly read-only `jobs list` and `jobs info` over local state for the selected device.
- Reuse `start.py`'s existing identity and receipt validation rules so `jobs list|info`, `print plan`, and `print start --reprint-from` always agree on `attempt_id`, chain continuity, and local reprint eligibility.
- Persist sanitized `print watch` observations in a separate private directory so watched prints — including those started by other clients — appear accurately in local history without weakening existing receipt/marker guarantees.
- Surface legacy, incomplete, mismatched, and unreadable records visibly without hiding them or crashing listing.

**Non-Goals:**
- Querying the printer or cloud APIs from `jobs list` or `jobs info`.
- Inferring terminal completion (`completed`/`canceled`/`failed`) from start receipts, idle transitions, or unattributed filename matches.
- Modifying, migrating, repairing, or deleting existing upload/start markers or receipts.
- Adding a SQLite database or external runtime dependencies (stay stdlib-only + existing `cryptography`).

## Decisions

### Separate private store for persisted watch observations
Store watch observations as individual JSON files under `<state-dir>/observations/<device16>/<observation_id>.json`, where `observation_id` is `obs-<32 lowercase hex>` (`"obs-" + uuid.uuid4().hex`).

- **Why:** Keeps `starts/` and upload directories completely untouched (preserving legacy compatibility, downgrade safety, and existing duplicate-protection tests). Individual files written via `atomic_json_at` (`O_CREAT | O_EXCL | O_NOFOLLOW`, `0o600`, `fsync`, atomic `os.replace`) avoid cross-process lock contention when multiple watches run or finish concurrently, and require no new dependencies.
- **Prefix rationale:** Using `obs-<32hex>` makes observation IDs immediately distinguishable from 64-hex start `attempt_id`s, ensuring passing an observation ID to `--reprint-from` fails validation cleanly.
- **Alternative considered:** SQLite or an append-only JSONL log. Rejected because SQLite adds schema migration/locking complexity and WAL sidecar files with tricky `0600` private-permission guarantees, and JSONL risks partial-line corruption on crashes.

### Persist observations only after an active job is observed, without breaking `observe()`
Keep `watch.observe()` purely read-only over MQTT and return/capture the target `device_digest` alongside `WatchProgress`. Track `observed_at` (first verified active report Unix timestamp) inside `WatchProgress`. In the CLI `print watch` completion/error/interrupt boundary, if `watch.last is not None` and `device_digest` is known, persist one sanitized observation record using `--state-dir`:

```json
{
  "version": 1,
  "observation_id": "obs-<32hex>",
  "device_digest": "<64hex>",
  "observed_at": 1700000000,
  "ended_at": 1700000300,
  "observed_filename": "sample.gcode",
  "client_attribution": "unattributed",
  "outcome": "unknown",
  "reason": "deadline_expired",
  "phase": "printing",
  "progress": 12,
  "current_layer": 8,
  "total_layers": 100
}
```

- **Why:** Idle runs (`no_active_job`) and pre-observation failures (config, pin, firmware, initial connect) create zero directories and write zero files. Post-observation exits (normal stop, deadline, disconnect, `KeyboardInterrupt`) all capture the observed job.
- **Non-fatal persistence failure:** If `<state-dir>/observations/<device16>` is a symlink, has unsafe permissions, or fails I/O when saving, `print watch` must never follow symlinks, change permissions, or discard the user's watch result; it keeps the watch outcome and exit code and sets `observation_recorded: false` (omitting `observation_id`). When persistence succeeds, the stdout result gains `observation_id` and `observation_recorded: true` (while keeping `observed_filename` out of `print watch` stdout to preserve the existing watch output contract).
- **Alternative considered:** Failing `print watch` with exit 3 before connecting if `--state-dir` is unsafe. Rejected because `print watch` should remain usable even without writing state if the printer is idle, and should never discard an already observed result.

### Reconstruct start attempt chains from `starts/<device16>/` in place
Create `kobra_lan/jobs.py` to scan `<state-dir>/starts/<device16>/` read-only using `open_directory(..., create=False, require_private=True)` and `state_record()` from `start.py`.

1. **Grouping:** Scan entries matching `^([a-f0-9]{64})\.(attempt|json)$` (ignoring `.start.lock`, `.upload.lock`, and stray `*.tmp` files; never echoing arbitrary filenames). Group by `storage_key`.
2. **Classification per `storage_key`:**
   - **Root attempt** (`storage_key == file_sha256`): recognized when a readable marker has `sha256 == storage_key` and `previous_attempt_id is None` (covering both legacy `{"sha256", "plan_sha256"}` and current root markers), or a readable receipt has `file_sha256 == storage_key` and `previous_attempt_id is None`. Derive `attempt_id = start.attempt_id(device_digest, storage_key, None)`.
   - **Successor attempt** (`storage_key == attempt_id`): recognized when a readable marker or receipt has `attempt_id == storage_key` and valid 64-hex `previous_attempt_id`, with `file_sha256` from marker/receipt. Verify `start.attempt_id(device_digest, file_sha256, previous_attempt_id) == storage_key`.
   - **Device check:** Reject/flag records whose `device_digest` (when present) does not equal the selected device's full 64-hex `device_digest` (protecting against 16-hex prefix collisions or misplaced files).
   - **Integrity & validation:** Run `start.matching_receipt()` and `start.attempt_outcome()` to determine whether the pair is valid, legacy vs. current, and what `issues` exist (`missing_marker`, `missing_receipt`, `unreadable_marker`, `unreadable_receipt`, `receipt_mismatch`, `invalid_status`, `unverified_active_evidence`, `device_mismatch`, `invalid_successor_identity`, `missing_predecessor`).
   - **Unreadable fallback:** If neither marker nor receipt can establish a valid `attempt_id` for the selected device, assign `record_id = f"unreadable-{storage_key}"`, `attempt_id = None`, `completeness = "incomplete"`, and safe issue codes.
3. **Chain linkage & local reprint eligibility:**
   - Link `previous_attempt_id -> next_attempt_id` across discovered attempts for each `file_sha256`.
   - Walk from each root forward using the same invariant as `start.latest_attempt()`: a successor is only chain-valid if every ancestor had `start_observed_active`.
   - Correlate read-only upload provenance from `<state-dir>/<device16>/<file_sha256>.json` (if `<state-dir>/<device16>` exists and is private `0700`; missing upload directory is treated as missing provenance, whereas a symlinked/non-private upload directory fails with exit 3).
   - Compute `reprint_eligibility`:
     - `"eligible_for_plan"` when the record is complete (current or legacy), `start_status == "start_observed_active"`, all ancestors in the chain are valid `start_observed_active`, `next_attempt_id is None`, and correlated upload provenance is `uploaded_verified_by_listing_and_metadata` matching `file_sha256` and `filename`.
     - Otherwise one of `"superseded"`, `"blocked_not_observed_active"`, `"blocked_incomplete"`, `"blocked_missing_upload_provenance"`.
   - Always keep `terminal_outcome: "unknown"` on start attempts.

### Observation scanning and unattributed correlation
Scan `<state-dir>/observations/<device16>/` read-only via `open_directory(..., create=False, require_private=True)`:
- Match filenames `^(obs-[a-f0-9]{32})\.json$`.
- Validate schema strictly (`version == 1`, matching `observation_id`, matching full `device_digest`, valid timestamps/outcome/reason/scalars, validated `observed_filename`).
- Any unreadable, non-private, symlinked, oversized, or schema-invalid `obs-*.json` file is surfaced as an incomplete observation record (`completeness: "incomplete"`, `issues: ["unreadable_observation"]` or `["invalid_observation"]`) rather than crashing `jobs list`.
- In `jobs info <attempt_id>`, compute `unattributed_matching_observations`: a bounded list of valid observation IDs (and safe summary metadata) where `observed_filename == attempt.filename` and `observed_at >= attempt.timestamp` (when both are known), explicitly flagged with `attribution: "unattributed_filename_match"` so consumers never treat it as firmware-proven attribution.

### Command surface, record ID grammar, and output contract
Add top-level `jobs` subcommand group in `kobra_lan/cli.py`:
- `jobs list [--kind all|start|observation] [--limit N]` (`N` in `1..500`, default `50`)
- `jobs info RECORD_ID` where `RECORD_ID` matches:
  - `^[a-f0-9]{64}$` (start `attempt_id`)
  - `^obs-[a-f0-9]{32}$` (watch `observation_id`)
  - `^unreadable-[a-f0-9]{64}$` (unreadable start storage reference)
- Reject malformed `RECORD_ID` or invalid `--limit` with exit 2 (`invalid_arguments`) before target selection, without echoing untrusted values.
- Use `registry.access(args.config, args.selected_printer)` purely to read `config.printer_id` (no `MQTT` or HTTP calls).
- Every `jobs list` and `jobs info` result includes:
  - `device_digest` (full 64-hex)
  - `coverage`:
    ```json
    {
      "scope": "local_state_only",
      "direct_printer_history_available": false,
      "other_client_actions": "only_when_watched_unattributed",
      "terminal_outcomes_verified": false
    }
    ```
- `jobs list` returns compact per-record summaries (`record_id`, `record_kind`, `completeness`, `client_attribution`, `timestamp`, `filename`, `start_status` / `outcome`, `terminal_outcome`, `reprint_eligibility` / `reason`, `issues`) ordered by `(timestamp is not None, timestamp or -1, record_id)` descending, plus `total_count`, `returned_count`, `incomplete_count`, `truncated`, `kind`, and `limit`.
- `jobs info` returns the full safe detail payload for that record (including upload provenance, preparation/slot/material, chain links, and unattributed matching observations for start attempts).
- Completions in `kobra_lan/completions.py` automatically pick up `jobs`, `list`, `info`, `--kind` choices, and `--limit` from `build_parser()` metadata with zero state or network access.

## Risks / Trade-offs

- **Unbounded observation directory growth over time** → `jobs list` defaults to `--limit 50` (max `500`) and each observation file is a few hundred bytes; reading/sorting remains fast for realistic personal printer usage while staying bounded on stdout. Retention/pruning can be considered separately if needed without deleting start markers.
- **Individual non-private file vs. non-private directory** → Refusing a non-private/symlinked device directory with exit 3 preserves the strict security boundary of `start.py`/`upload.py`/`profiles.py`, while degrading individual unreadable/non-private files inside a valid directory into `incomplete` entries prevents one damaged receipt from blinding the operator to all other jobs.
- **Unattributed filename matches could be misread as proof** → Labeling `client_attribution: "unattributed"` on watch records, naming the correlation field `unattributed_matching_observations`, and keeping `terminal_outcome: "unknown"` on start attempts makes the epistemic boundary explicit in both text and JSON.
- **`print watch` now writes under `--state-dir` when an active job is observed** → Confined to a dedicated `observations/<device16>/` subdirectory, skipped when idle or failing pre-observation, and non-fatal if persistence fails, preserving all existing receipts, markers, profiles, and read-only printer behavior.

## Migration Plan

No migration of existing state is required. Existing legacy and current start markers/receipts and upload receipts are read in place with zero modifications. The `observations/<device16>/` directory is created lazily (mode `0700`) only when `print watch` actually observes an active job. Downgrading to an earlier CLI version continues working cleanly because upload and start formats are unchanged and earlier versions ignore `observations/`.
