# Design

## Context

See [proposal.md](proposal.md) for motivation. Currently `kobra_lan/watch.py` polls fresh MQTT `info` reports every 5 seconds on one pinned session (`observe()`), and delegates state tracking to `WatchProgress.update()`. On Kobra X model `20030` / firmware `2.0.2.2`:

- Active jobs always report placeholder `task_id: "-1"`, and `last_project` remains empty after both completion and cancellation.
- `WatchProgress.update()` returns `self.result("unknown", "identity_unverified")` unconditionally on the second active poll.
- `PREPARATION_STATES` (shared with `kobra_lan/control.py`) lists only 9 legacy KX-Bridge states and omits live-observed firmware `2.0.2.2` states (`auto_leveling`, `vibrating`, `flow_calibrating`, `filament_cutting`, `extfilbox_filament_unfeeding`), while `watch.py` also rejects `paused`, `pausing`, `resuming`, and `stopping`.
- Near the end of a normal print on firmware `2.0.2.2`, telemetry holds `progress: 99` while resetting `curr_layer` and `total_layers` to `0` for ~15 seconds before transitioning to `state: "free"` (documented in the 2026-11-21 live capture).
- `MQTT.query(..., require_fresh=True)` rejects any report whose timestamp is even 1 ms earlier than local `sent_timestamp`, causing long watch sessions to time out on minor RTC drift.

## Goals / Non-Goals

**Goals:**
- Allow `print watch` to continuously follow an active Kobra X firmware `2.0.2.2` print from preparation through printing, filament changes, pauses, and eventual disappearance/deadline without sacrificing conservative outcome honesty.
- Detect real job replacements and same-file restarts via filename/task-id changes, counter regressions, and post-printing start-only calibration phases.
- Provide clean, sanitized live progress feedback on `stderr` with an opt-out `--quiet` flag, keeping `stdout` strictly for one final text or JSON result.
- Prevent minor negative host-to-printer clock skew from breaking long watch sessions while maintaining strict replay/retained-message protection.
- Keep `kobra_lan/control.py` and `kobra_lan/jobs.py` aligned with the expanded state and phase sets, with zero new modules and full backwards compatibility for existing local state files.

**Non-Goals:**
- Inferring or claiming `outcome: "completed"`, `"canceled"`, or `"failed"` on firmware `2.0.2.2` from idle transitions, `99%`/`100%` progress, or empty `last_project`.
- Changing the v1 JSON envelope, stdout result keys, exit codes, or persisted observation record version.
- Adding reconnect/retry logic to `MQTT` or introducing streaming unsolicited MQTT listeners (firmware `2.0.2.2` did not emit unsolicited `info` reports during passive listening).

## Decisions

### 1. Continuous coherent tracking with high-water regression guards

`WatchProgress` will track:
- `initial_filename`: validated printable filename from the first active report (`None` if missing or hostile).
- `initial_task_id`: validated non-placeholder `task_id` if present (anything valid other than `"-1"`), else `None`.
- `saw_printing_progress`: boolean set once `printing` reports positive `progress > 0` or `curr_layer > 0`.
- `max_progress`, `max_layer`, `observed_total_layers`: high-water printing counters.
- `last`: latest verified `{phase, ...scalar progress}` dictionary (carrying forward high-water `progress`, `current_layer`, `total_layers` across temporary non-printing states and end-of-print layer zeroing).

On subsequent polls (`self.last is not None`):
1. If `last_project` changed from `initial_last_project` -> stop with `("unknown", "last_project_unattributed")`.
2. If `project` is absent/empty (or `info["state"] == "free"`) -> stop with `("unknown", "job_disappeared")`.
3. Validate `filename = project_filename(project)` and `task_id` on the current report:
   - If `initial_filename` is `None` or `filename` is `None` -> stop with `("unknown", "identity_unverified")` (cannot establish continuity without a valid filename).
   - If `filename != initial_filename` -> stop with `("unknown", "job_replaced")`.
   - If `initial_task_id` is set and the new report carries a different validated non-placeholder `task_id` -> stop with `("unknown", "job_replaced")`.
4. Classify `project.get("state")`:
   - `printing`:
     - Extract validated `progress_fields(project)`.
     - **Regression check**: if `saw_printing_progress` is true, stop with `("unknown", "identity_unverified")` (retaining prior `self.last`) when:
       - reported `progress` is strictly less than `max_progress`, OR
       - reported `curr_layer` is positive (`> 0`) and strictly less than `max_layer`, OR
       - reported `total_layers` is positive (`> 0`) and `observed_total_layers` is set and `total_layers != observed_total_layers`.
     - **End-of-print zeroing preservation**: if `progress >= max_progress` and `curr_layer == 0` (or `total_layers` is absent/0 because firmware zeroed layer counters at `99%` right before finishing), retain the prior verified `current_layer` and `total_layers` in `self.last` instead of overwriting them with `0`.
     - Otherwise update `max_progress`, `max_layer`, `observed_total_layers`, `saw_printing_progress`, and `self.last = {"phase": "printing", ...}`.
   - Start-only calibration states (`START_ONLY_PREPARATION_STATES = {"auto_leveling", "vibrating", "flow_calibrating", "z_offset_calibrating", "frequency_sweeping"}`):
     - If `saw_printing_progress` is already true -> a new calibration cycle on the same filename indicates a restarted run; stop with `("unknown", "identity_unverified")` preserving prior `self.last`.
     - Otherwise update `phase = "preparing"` and continue watching.
   - Other `PREPARATION_STATES` (heating, cooling, wiping, purging, filament cutting/feeding/unfeeding) and `resuming`:
     - Mid-print filament changes and pause resumes legitimately enter these states. Keep watching with `phase = "preparing"` while preserving any previously established printing progress scalars in `self.last`.
   - `paused` / `pausing`:
     - Keep watching with `phase = "paused"` while preserving previously established printing progress scalars in `self.last`.
   - `stopping`:
     - Keep watching with `phase = "stopping"` while preserving previously established printing progress scalars in `self.last`.
   - Unrecognized or non-string `project.state`:
     - Stop with `("unknown", "active_job_unverified")` preserving prior `self.last`.

*Alternatives considered:*
- Requiring a separate `--follow` flag to enable continuous polling while keeping the 5-second bailout as default. Rejected because the primary purpose of `print watch` is to watch a print continuously, and exiting after 5 seconds on every qualified Kobra X print makes the default command unusable.
- Inferring `outcome: "completed"` when `progress >= 99` and `curr_layer == total_layers` before `free`. Rejected because firmware `2.0.2.2` exposes no attributable terminal signal; cancellation or failure near the end cannot be reliably distinguished from completion without firmware support.

### 2. Complete firmware `2.0.2.2` preparation state set shared with `control.py`

Expand `PREPARATION_STATES` in `kobra_lan/watch.py` from 9 states to 14 by adding the 5 live-observed firmware `2.0.2.2` states:
- `auto_leveling`
- `vibrating`
- `flow_calibrating`
- `filament_cutting`
- `extfilbox_filament_unfeeding`

Because `kobra_lan/control.py` imports `PREPARATION_STATES` for `CANCEL_ALLOWED` and `transition_confirmed("resume", ...)`, both `print cancel` and `print resume` automatically recognize these states without duplicating allowlists. `pause` remains strictly limited to `printing`, and `paused`/`pausing`/`resuming`/`stopping` remain excluded from `PREPARATION_STATES` so `control.py`'s transitional-state refusal (`stopping`, `pausing`, `resuming`) stays intact.

### 3. Sanitized live progress on `stderr` with `--quiet`

Add an optional `--quiet` boolean flag to `print watch` in `kobra_lan/cli.py` (automatically picked up by `kobra_lan/completions.py` for `bash`, `zsh`, and `fish`).

When `--quiet` is not set, `WatchProgress` (or a callback wired from `cli.py`) formats one single-line progress status to `stderr` whenever the sanitized progress tuple changes:
- Fields included (strict allowlist of validated scalars only): normalized `phase`, validated ASCII identifier `state` (e.g. `auto_leveling`, `printing`, `paused`), `progress` (`<N>%`), `current_layer`/`total_layers` (`layer <C>/<T>`), optional `remain_time` (`remaining <M>m`, integer `1..1_000_000`), and optional `temp` (`nozzle <curr>/<target>C bed <curr>/<target>C`, validated ints/floats within safe bounds).
- Fields explicitly excluded: `filename`, URLs, tokens, credentials, unknown raw fields, and any non-printable/control characters (all text passed through `safe_text()`).
- Deduplication: emit a line only when the rendered progress state (phase, state, progress, layer, remain_time) changes, avoiding noisy duplicate lines every 5 seconds during long flat periods (temperatures alone do not trigger spam unless phase/progress/layer/remain_time changes).
- `no_active_job` and pre-observation errors emit nothing to `stderr`.

### 4. Bounded clock-skew tolerance with monotonic timestamp enforcement in `MQTT.query`

Extend `MQTT.query()` signature with optional keyword-only parameters that default to current strict behavior:
```python
def query(self, kind, action="query", data=None, *, require_fresh=False,
          max_backward_skew_ms=0, min_timestamp=None):
```
Freshness gate when `require_fresh=True`:
- Retain bit MUST be `0` (`header & 1 == 0`).
- Report MUST be correlated or post-ACK (`correlated or acknowledged`).
- Timestamp MUST be numeric (`int` or `float`) and satisfy:
  - `sent_timestamp - max_backward_skew_ms <= stamp <= int(time.time() * 1000) + 5000`
  - If `min_timestamp is not None`: `stamp > min_timestamp`

`watch.observe()` passes `max_backward_skew_ms=5000` (symmetric with the existing `+5000` ms forward tolerance) and tracks `last_report_timestamp`, passing it as `min_timestamp` on subsequent polls.

*Alternatives considered:*
- Removing the timestamp lower bound completely when `acknowledged=True`. Rejected because a stale queued report delivered right after an ACK could still sneak through; combining `±5000 ms` with strictly increasing `stamp > min_timestamp` tolerates normal LAN RTC drift while rejecting stale or replayed reports.
- Changing the global default `max_backward_skew_ms` for all commands. Keeping the default at `0` avoids changing behavior or breaking mock signatures for unrelated commands (`camera`, `filaments`, `start`, `delete_file`, `control`) unless explicitly opted in.

### 5. Observation persistence and `jobs` compatibility

Update `OBSERVATION_PHASES` in `kobra_lan/jobs.py` from `{"preparing", "printing"}` to `{"preparing", "printing", "paused", "stopping"}`. Keep `OBSERVATION_OUTCOMES`, `OBSERVATION_REASONS`, `version: 1`, file naming (`obs-<32hex>.json`), permissions (`0700`/`0600`), and all existing observation fields unchanged so existing persisted observations remain valid in place.

## Risks / Trade-offs

- **Undetected rapid same-file restart between 5-second polls** → If an operator cancels a print at `5%` and restarts the exact same file before the next poll reaches `>5%`, firmware `2.0.2.2` exposes only `task_id: "-1"` and identical `filename`; regression checks catch any drop in `progress`/`curr_layer` or re-entry into start-only calibration phases, and `outcome` remains `"unknown"` with `client_attribution: "unattributed"` so downstream automation never mistakes unattributed continuity for firmware-proven identity.
- **Unexpected mid-print firmware state name** → Firmware `2.0.2.2` could emit an unlisted state during an unusual recovery or error condition. Unrecognized states continue to stop cleanly with `active_job_unverified` while preserving the latest verified progress and persisted observation rather than silently looping or crashing.
- **Large host/printer clock skew (> 5 seconds)** → A printer clock more than 5 seconds behind or ahead of the host will still fail the freshness gate and time out; this remains documented as a clock-sync requirement rather than disabling freshness protection.
- **Existing tests asserting empty `stderr` on `print watch`** → Tests in `tests/test_watch.py` that assert empty `stderr` during active observation will be updated to verify sanitized `stderr` progress by default and empty `stderr` under `--quiet`.

## Migration Plan

- Purely additive and backwards-compatible within CLI schema version 1 and observation record version 1.
- Preexisting observation files (`preparing`/`printing`) remain readable by `jobs list` and `jobs info` without migration.
- Rollback requires only reverting the touched modules (`watch.py`, `mqtt.py`, `cli.py`, `jobs.py`) and docs/tests; no state files or profiles are modified in an incompatible format.
