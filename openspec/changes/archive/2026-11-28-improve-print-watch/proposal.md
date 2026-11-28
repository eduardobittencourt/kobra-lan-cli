# Proposal

## Why

On Kobra X model `20030` / firmware `2.0.2.2`, `kobra-lan print watch` currently cannot follow a print through its run. Because firmware `2.0.2.2` always reports the placeholder `task_id: "-1"` during active jobs and leaves `last_project` empty after completion or cancellation, `WatchProgress.update()` exits unconditionally on the second poll (~5 seconds after startup) with `outcome: "unknown"` and `reason: "identity_unverified"`. In addition, live testing during active prints revealed two practical gaps: `PREPARATION_STATES` omits firmware `2.0.2.2` calibration and filament-change states observed on hardware (`auto_leveling`, `vibrating`, `flow_calibrating`, `filament_cutting`, `extfilbox_filament_unfeeding`) as well as pause/transition states (`paused`, `pausing`, `resuming`, `stopping`), causing immediate `active_job_unverified` exits; `print watch` emits no live progress updates to `stderr`; and the zero-backward-skew MQTT timestamp gate (`sent_timestamp <= stamp`) drops long observation sessions whenever the printer's RTC drifts even a few milliseconds behind the host.

## What Changes

- Enable continuous observation in `print watch` while fresh telemetry remains coherent for the job active at startup (same validated `filename`, non-regressing printing progress/layer counters, and recognized preparation, filament-change, printing, and pause/transition states), instead of terminating on the second poll with `identity_unverified`.
- Preserve honest outcome reporting: `print watch` still never claims `completed`, `canceled`, or `failed` without a hardware-validated attributable terminal signal from firmware; when the active job ends and the printer returns to `free` with empty `last_project`, `print watch` exits `0` with `outcome: "unknown"`, `reason: "job_disappeared"`, and the **latest** verified phase and scalar progress, while stopping with `job_replaced`, `last_project_unattributed`, or `identity_unverified` if the filename changes, `last_project` changes without attribution, or progress/layer counters regress inconsistently on the same filename.
- Expand the recognized firmware `2.0.2.2` preparation/active state set (`PREPARATION_STATES`) with live-observed calibration and filament-change phases (`auto_leveling`, `vibrating`, `flow_calibrating`, `filament_cutting`, `extfilbox_filament_unfeeding`), and handle `paused`, `pausing`, `resuming`, and `stopping` during `print watch` without aborting as `active_job_unverified`.
- Emit concise, sanitized live progress lines to `stderr` whenever observed phase, progress percentage, layer counters, or elapsed/remaining time changes (excluding filenames, URLs, credentials, and terminal controls), and add an optional `--quiet` flag to `print watch` to suppress live `stderr` updates while keeping `stdout` strictly reserved for the single final text or `--json` result.
- Add bounded negative clock-skew tolerance plus monotonic report-timestamp tracking for correlated, non-retained post-ACK `info` reports during `print watch` so small RTC drift between host and printer does not time out long watches while still rejecting retained or stale reports.
- Keep local observation persistence (`<state-dir>/observations/<device>/obs-*.json`) and offline `jobs list|info` aligned with the `paused` and `stopping` phases while remaining fully backwards-compatible with existing stored observations.

## Capabilities

### New Capabilities

### Modified Capabilities
- `print-observation`: Support continuous coherent observation across preparation, printing, filament-change, and pause/transition states on firmware `2.0.2.2`; emit sanitized live progress to `stderr` with optional `--quiet`; add bounded clock-skew tolerance with monotonic timestamp checks for fresh post-ACK reports; detect same-file counter regressions as `identity_unverified`; and persist the latest observed phase (`preparing`, `printing`, `paused`, `stopping`) and scalar progress.
- `print-lifecycle-control`: Recognize the additional live-observed firmware `2.0.2.2` preparation and filament-change states (`auto_leveling`, `vibrating`, `flow_calibrating`, `filament_cutting`, `extfilbox_filament_unfeeding`) in `print cancel` pre-flight validation and `print resume` post-ACK confirmation.
- `job-history`: Accept persisted watch observations whose final observed phase is `paused` or `stopping` (alongside `preparing` and `printing`) in `jobs list` and `jobs info` without altering existing observation files.
- `cli-interface`: Expose optional `--quiet` on `print watch` in CLI help, documentation, and offline `bash`, `zsh`, and `fish` completions.

## Impact

- Affected runtime modules: `kobra_lan/watch.py`, `kobra_lan/mqtt.py`, `kobra_lan/cli.py`, `kobra_lan/jobs.py`, and shared state definitions imported by `kobra_lan/control.py`. No new modules are added (packaging allowlists remain unchanged).
- Affected offline tests: `tests/test_watch.py`, `tests/test_control.py`, `tests/test_jobs.py`, `tests/test_cli.py`, `tests/test_completions.py`, and `tests/test_mqtt.py`.
- Affected documentation: `docs/usage.md`, `docs/compatibility.md`, and `ROADMAP.md` (keeping English prose, JSON envelope v1, exit codes, and security/redaction guarantees intact).
