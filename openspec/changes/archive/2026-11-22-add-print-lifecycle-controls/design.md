# Design

## Context

See [proposal.md](proposal.md) for motivation and scope. Currently:
- `kobra_lan/mqtt.py` keeps `MQTT.query()` strictly read-only via an explicit `(kind, action)` allowlist and provides a dedicated single-shot `start_once(payload)` method for `print/start`.
- `kobra_lan/start.py` holds a per-device exclusive lease via `upload.device_lock()` and `upload.ensure_directory_bound()`, validates Kobra X model `20030` / firmware `2.0.2.2`, publishes once without retry, polls fresh `info` up to 5 times at 1-second intervals, and raises `StartUncertain` with safe partial evidence on post-publish failure.
- `kobra_lan/watch.py` defines the firmware `2.0.2.2` `PREPARATION_STATES` allowlist and `project_filename()` validation helper.
- Public protocol references (`KX-Bridge` commit `f0ce700fbcc9b3aed54f1a142b4e0318bc11638e`, `kobrax_client.py:718-725` and `bridge_constants.py`; `stribor/anycubic_kobrax` `9e22712454b5c65fec6e33c92fd894a61f7f4d6f`, `coordinator.py:482-505`) send `type: "print"` with actions `"pause"`, `"resume"`, and `"stop"` and `data: {"taskid": "<taskid>"}` (default `"-1"`). Live Kobra X model `20030` / firmware `2.0.2.2` state transitions for pause/resume/cancel have not yet been captured on physical hardware.

## Goals / Non-Goals

**Goals:**
- Provide guarded, single-shot `print pause`, `print resume`, and `print cancel` commands that work on any active job on the qualified Kobra X (including jobs started by other clients) with zero automatic retry.
- Enforce strict pre-flight qualification and state preconditions so invalid, idle, already-reached, transitional, or mismatched-filename requests fail safely before publishing.
- Clearly separate broker acknowledgement (`ack`), observed target state (`control_observed_*`), acknowledged-not-confirmed (`control_acknowledged_not_confirmed`), and post-publish uncertainty (`control_uncertain_no_retry`), preserving existing exit codes and JSON/text contracts.
- Coordinate with concurrent `files upload`, `print start`, and sibling lifecycle commands via the existing per-device state lease while leaving profiles, upload/start receipts, `.attempt` markers, and watch observations untouched.

**Non-Goals:**
- Persistent control-history receipts or changes to `jobs list|info` schemas.
- Inferring terminal outcomes in `print watch` before live hardware evidence qualifies attributable terminal signals.
- Automatic retry/reconnect, interactive stdin prompts, `files delete`, file download, or temperature/fan/light/axis controls.
- Expanding hardware qualification beyond Kobra X model `20030` / firmware `2.0.2.2`.

## Decisions

### 1. Require `--execute` with optional `--filename` guard (no two-step plan hash)

Unlike `print start` (which binds 6+ execution choices—file bytes, remote name, slot, material/color mapping, and three preparation booleans—into a reviewed `plan_sha256`), `pause`, `resume`, and `cancel` take no print parameters and act on the currently running job (which may have been started by another client without a local G-code copy). Requiring `--execute` (with no implicit dry run; omitting it exits 2 before printer access) matches `files upload` and `print start`'s explicit execution barrier without hanging non-interactive callers.

Adding an optional `--filename <remote-name>` guard lets operators and scripts assert that the active job's validated `project.filename` matches what they previously observed via `status` or `print watch`, refusing with exit 2 before publish if another job is running. `--filename` is validated before target selection using the same safe printable non-separator constraints as `watch.project_filename()` (non-empty, <= 255 printable chars, no `/ \ : ? #`, and no URL scheme/control chars).

*Alternative considered:* Interactive confirmation prompt for `print cancel`. Rejected because `kobra-lan` avoids TTY-dependent operational commands for `files upload` and `print start`; `--execute` (plus optional `--filename`) works identically for humans, scripts, and agents.

*Alternative considered:* Two-step `print control-plan` + hash. Rejected as disproportionate friction when operators need to pause or cancel an active print promptly; pre-flight state checks + optional `--filename` provide targeted safety without extra round-trips.

### 2. Separate single-shot `MQTT.control_once()` from read-only `MQTT.query()`

`MQTT.query()` remains strictly read-only with its existing allowlist. Add `MQTT.control_once(action, taskid="-1")` in `kobra_lan/mqtt.py` allowing only `{"pause", "resume", "stop"}`, publishing one QoS 0 message to `{BASE}/slicer/printer/{type_id}/{printer_id}/print` with `{"type": "print", "action": action, "msgid": msgid, "timestamp": ms, "data": {"taskid": taskid}}`, and waiting up to `self.timeout` for one correlated `/response` packet matching `msgid`.

To handle QoS 1 broker packets cleanly during ACK wait (matching `MQTT.query()`), `control_once()` should handle QoS 0/1 packet parsing consistently rather than dropping QoS 1 publishes silently, reject `code != 0`, and never reconnect or republish on timeout, close, or protocol error.

The `taskid` sent in `data` is taken from the fresh pre-flight `project.task_id` (or `project.taskid`) if it matches `[A-Za-z0-9_-]{1,128}` (which includes firmware `2.0.2.2`'s `"-1"` placeholder), otherwise falling back to `"-1"`.

### 3. Strict state-transition matrix and post-ACK verification

All three commands open one pinned `MQTT` session, issue a fresh `info` query (`require_fresh=True`), and validate `compatibility_issue(config, info) is None`. They then inspect `info.get("state")` and `project = info.get("project")` (requiring `info["state"] != "free"` and `isinstance(project, dict)` with a string `project.get("state")`):

| CLI Command | Wire Action | Allowed Pre-Flight `project.state` | Confirmed Post-ACK State | Observed Status |
| --- | --- | --- | --- | --- |
| `print pause` | `pause` | `{"printing"}` | `info.state != "free"` and `project.state == "paused"` | `control_observed_paused` |
| `print resume` | `resume` | `{"paused"}` | `info.state != "free"` and `project.state in ({"printing"} \| PREPARATION_STATES)` | `control_observed_resumed` |
| `print cancel` | `stop` | `{"printing", "paused"} \| PREPARATION_STATES` | `(info.state == "free" and not project)` or `project.state in {"stoped", "canceled"}` | `control_observed_stopped` |

Rationale:
- `pause` is restricted to `printing` (excluding preparation phases like heating/leveling/sweeping where mid-calibration pause behavior on FW `2.0.2.2` is unverified).
- `resume` is restricted to `paused` and accepts either `printing` or a recognized preparation phase (e.g., `nozzle_heating` / `hotbed_heating`) as observed resumption.
- `cancel` is permitted during `printing`, any recognized FW `2.0.2.2` preparation phase, or `paused` so an operator can abort a misbehaving preparation or paused run. It recognizes both `free` (idle with absent/empty `project`) and KX-Bridge's documented terminal cancel states (`"stoped"` / `"canceled"`) as observed stop.
- Transitional states (`pausing`, `resuming`, `stopping`), already-reached states, idle, and unrecognized states are refused before publish with exit 2 (`validation_failed`).

After a correlated ACK (`code == 0`), poll `client.query("info", require_fresh=True)` up to 5 times at 1-second intervals (matching `start.py`) on the same pinned session:
- Stop early as soon as the confirmed target state is observed and return exit 0 with `status: "control_observed_*"`.
- If all 5 polls succeed without reaching the target state (for example, still `pausing`, `resuming`, or `stopping`), return exit 0 with `status: "control_acknowledged_not_confirmed"`, sanitized `before`, `after`, `project`, `ack`, and explicit guidance to inspect `status` rather than replay blindly.
- If ACK wait or post-ACK polling raises an error (`MQTTIOFailure`, `MQTTClosed`, `MQTTFailure`, `ProtocolError`, `OSError`, `ValueError`, etc.), raise `ControlUncertain(partial, exit_code=...)` carrying `action`, `wire_action`, `status: "control_uncertain_no_retry"`, `ack` (if received), `before`, `after`, `project`, `experimental: True`, `hardware_control_validated: False`. Preserve exit 3 for I/O/timeout errors (`MQTTIOFailure`, `OSError`, timeout `MQTTFailure`) and exit 2 for protocol rejections (`ProtocolError` / non-timeout `MQTTFailure`).

### 4. Shared per-device lease without mutating existing state

Extend `upload.device_lock(device_dir, operation)` in `kobra_lan/upload.py` so every mutating device operation (`upload`, `start`, and lifecycle `control`) acquires a shared private regular `.device.lock` (`0600`, `O_NOFOLLOW`) under `<state-dir>/<device16>` (while retaining `.upload.lock` and `.start.lock` for `upload` and `start` compatibility), and reuse `upload.device_lock(device_dir, "control")` plus `upload.ensure_directory_bound(device_dir, device_fd, action)` before opening the MQTT session and again immediately before `control_once()`:
- Prevents concurrent `files upload`, `print start`, and `print pause|resume|cancel` invocations targeting the same device and `--state-dir` from racing.
- Fails fast before printer access when contended or when `<state-dir>/<device16>` is a symlink or non-private directory, without following symlinks or changing permissions.
- Does not write any markers, receipts, or observation files, leaving `<state-dir>/<device16>` upload receipts, `starts/<device16>` markers/receipts, and `observations/<device16>` records byte-for-byte untouched.

Note on `device_lock` creation: `upload.device_lock(device_dir, "control")` creates `<state-dir>/<device16>` (0700) and `.device.lock` (0600) if absent (without creating separate `.pause.lock`/`.resume.lock`/`.cancel.lock` files). Because `print pause|resume|cancel` is an explicit mutating execution (requiring `--execute`), acquiring the device lease after validating `--execute`, `--filename`, and target selection (and before MQTT connect) matches `files upload` and `print start`. Pre-flight CLI argument errors still happen before acquiring the lease or touching `--state-dir`.

### 5. Module placement and CLI/output integration

Create `kobra_lan/control.py` owning:
- Safe filename validation for `--filename` (`validate_filename`).
- State-transition constants and predicates (`PAUSE_ALLOWED`, `RESUME_ALLOWED`, `CANCEL_ALLOWED`, confirmation checks).
- `ControlUncertain(ProtocolError)` with `result` and `exit_code`.
- `control_print(config, action, state_dir, *, expected_filename=None)` returning a sanitized result dict:
  - `action` (`"pause" | "resume" | "cancel"`), `wire_action` (`"pause" | "resume" | "stop"`), `device_digest`, `model`, `firmware`, `status`, `dry_run: False`, `experimental: True`, `hardware_control_validated: False`, `expected_filename` (when supplied), `taskid`, `before`, `before_project`, `ack`, `after`, `project`.
- Wire `print pause`, `print resume`, and `print cancel` in `kobra_lan/cli.py`, adding contextual `Parser.error()` guidance for all three subcommands and validating `--filename` before target selection. `kobra_lan/completions.py` derives bash/zsh/fish completions directly from `build_parser()`, automatically covering the new subcommands and flags once registered.

## Risks / Trade-offs

- **Unvalidated firmware `2.0.2.2` transition strings** → Public references (KX-Bridge, `stribor/anycubic_kobrax`) document `"paused"`, `"pausing"`, `"resuming"`, `"stopping"`, `"stoped"`, `"canceled"`, and `taskid: "-1"`, but FW `2.0.2.2` has not yet been tested live for these actions. Mitigation: mark every result `experimental: True` and `hardware_control_validated: False`, require strict state preconditions so unexpected strings fail safely without publishing, and require an operator-authorized integrated Kobra X qualification session before upgrading qualification claims.
- **Slow mechanical transitions (e.g. parking toolhead or cooling)** → A pause or cancel can take longer than the 5-second post-ACK observation window. Mitigation: treat clean post-ACK polling without observed final state as `control_acknowledged_not_confirmed` (exit 0 with `before`/`after` snapshots) rather than an error, and instruct the operator to inspect `status` or `print watch` rather than replay.
- **TOCTOU window with external clients** → Another client (touchscreen/app) can change print state between our pre-flight `info` read and `control_once()` publish, since the printer offers no compare-and-swap MQTT control primitive. Mitigation: keep pre-flight check and single publish back-to-back on the same pinned session, hold the local per-device lease against cooperating CLI callers, support `--filename` binding, and document the firmware limitation clearly in `docs/usage.md`.
- **Clock skew on fresh post-ACK polls** → As observed during `print watch` hardware verification, printer/host clock skew can reject fresh reports and time out post-ACK polling. Mitigation: classify post-ACK timeout as `control_uncertain_no_retry` (retaining `ack` in partial `result`) and never replay the control command.

## Migration Plan

- Purely additive CLI subcommands (`print pause`, `print resume`, `print cancel`) and internal module (`kobra_lan/control.py`).
- No configuration, profile, receipt, marker, or watch-observation schema changes; rollback to earlier versions requires no state migration and leaves all existing local records intact.
- Update `scripts/check_python.py`, `scripts/build_deb.py`, and `scripts/accept_deb.py` to include `kobra_lan/control.py` in package manifests and verify offline help/completions for `print pause|resume|cancel`.
