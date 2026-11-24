# Design

## Context

See [proposal.md](proposal.md) for motivation and scope. Currently:
- `kobra_lan/mqtt.py` keeps `MQTT.query()` strictly read-only via an explicit `(kind, action)` allowlist (including `("file", "listLocal")` and `("file", "fileDetails")`) and separates mutating single-shot actions into dedicated methods (`start_once()` and `control_once()`).
- `kobra_lan/printer.py` implements `list_files(client)` (paginating `file/listLocal` on `path: "/"`, returning sanitized `{filename, size, is_dir}` records) and `sanitized()` / `payload_data()`.
- `kobra_lan/upload.py` implements `device_lock(directory, operation)` (acquiring `.device.lock` for shared per-device exclusion across `upload`, `start`, and `control`) and `ensure_directory_bound()`.
- `kobra_lan/control.py` establishes the single-shot experimental command pattern: required `--execute`, `validate_filename()`, fresh `info` + `compatibility_issue()` pre-flight, shared `.device.lock`, bounded post-action polling on one pinned session, and a typed uncertain exception retaining safe partial evidence with exit 2/3/130 preservation.
- Public protocol reference (`KX-Bridge` commit `f0ce700fbcc9b3aed54f1a142b4e0318bc11638e`, `bridge_endpoints.py:144-169` and `bridge_mqtt.py:280-360`) deletes files from printer internal storage via MQTT `type: "file"`, `action: "deleteBatch"`, `data: {"root": "local", "files": [{"path": "/", "filename": "<name>"}]}`, where the printer replies with an immediate correlated `/response` ACK (`code: 0`) followed by a `file/report` message with `action: "deleteBatch"` and `state: "success"`. Live Kobra X model `20030` / firmware `2.0.2.2` deletion behavior has not yet been captured by this client on physical hardware.

## Goals / Non-Goals

**Goals:**
- Provide a guarded, single-shot `files delete <name> --execute` command for root-level files stored on a qualified Kobra X with zero automatic retry.
- Prevent deleting an active job or mutating storage while a print is active by enforcing fresh idle qualification and pre-flight `file/listLocal` presence/non-directory checks before publishing.
- Coordinate with concurrent `files upload`, `print start`, `print pause|resume|cancel`, and sibling `files delete` invocations via the existing per-device `.device.lock` while keeping all existing profiles, upload receipts, `.attempt` markers, start receipts/markers, and watch observations byte-for-byte intact.
- Confirm removal via bounded post-delete `file/listLocal` polling on the same pinned session and honestly distinguish `delete_observed_removed`, `delete_acknowledged_not_confirmed`, and `delete_uncertain_no_retry`.

**Non-Goals:**
- Multi-file batch deletion in one CLI invocation (avoids partial-batch uncertainty reporting).
- Subdirectory traversal or deletion (`is_dir: true` entries are rejected).
- File download from the printer (separate roadmap investigation).
- Deleting, mutating, or invalidating local upload receipts, upload `.attempt` markers, start receipts/markers, or watch observations.
- Automatic retry/reconnect, interactive stdin confirmation prompts, or claiming hardware qualification before an operator-authorized live Kobra X session.

## Decisions

### 1. Single-target CLI (`files delete <name> --execute`) with no implicit dry run

Match `files info <name>` for target naming and `print pause|resume|cancel --execute` for the explicit execution barrier:
- `<name>` is validated before target selection using `control.validate_filename()` (non-empty, `<= 255` printable chars, not `.`/`..`, no `/ \ : ? #`, no URL/control characters). Unlike `files upload` (which restricts to plain `.gcode`), `files delete` allows any safe printable root filename returned by `files list` (e.g., `.gcode` or other root-level files visible on the printer), while strictly rejecting directories (`is_dir: true`).
- `--execute` is required; omitting it fails with exit 2 (`invalid_arguments`) before target selection or printer access.
- Single file per command: even though the underlying firmware command is `file/deleteBatch`, sending a 1-element `files` array keeps outcome states binary and unambiguous (`delete_observed_removed` vs `delete_acknowledged_not_confirmed` vs `delete_uncertain_no_retry`).

*Alternative considered:* Accepting multiple positional filenames (`files delete a.gcode b.gcode --execute`). Rejected for the initial implementation because partial failures inside one batch complicate atomic uncertainty reporting and operator recovery; single-file deletion can be scripted cleanly and batch support remains straightforward to evaluate later once firmware behavior is hardware-qualified.

*Alternative considered:* Interactive `[y/N]` prompt like `printer remove`. Rejected because all network-mutating operational commands (`files upload`, `print start`, `print pause|resume|cancel`) use explicit `--execute` so humans, scripts, and agents share one non-hanging contract.

### 2. Dedicated single-shot `MQTT.delete_file_once(filename)` separated from `MQTT.query()`

`MQTT.query()` remains strictly read-only. Add `MQTT.delete_file_once(filename, *, on_ack=None)` in `kobra_lan/mqtt.py`:
- Re-validates `filename` with safe basename constraints.
- Sets `self.begin_stage("file_delete")` and publishes one QoS 0 packet to `{BASE}/slicer/printer/{type_id}/{printer_id}/file`:
  `{"type": "file", "action": "deleteBatch", "msgid": msgid, "timestamp": sent_timestamp_ms, "data": {"root": "local", "files": [{"path": "/", "filename": filename}]}}`.
- Waits up to `self.stage_deadline` on the same pinned session, handling QoS 0/1 packets cleanly (sending PUBACK for QoS 1) and ignoring retained packets (`header & 1`):
  1. Correlated `/response` (`topic.endswith("/response")` and `result.get("msgid") == msgid`): requires integer `code == 0`, records `ack = {"code": 0, "msgid": msgid}`, invokes `on_ack(ack)` if provided (so a subsequent timeout before `file/report` still preserves `ack` in uncertain partial evidence), and continues waiting for `file/report`.
  2. Fresh `file/report` (`topic.endswith("/file/report")`, `result.get("type") == "file"`, `result.get("action") == "deleteBatch"`): accepted when correlated (`result.get("msgid") == msgid`) OR when `acknowledged` is true and `timestamp` (if integer/float) falls within `[sent_timestamp, now_ms + 5000]` (matching `query(require_fresh=True)` while tolerating firmware reports where `data` is `null` or omitted). Requires `result.get("state") == "success"` and (when `code` is present) `code in (0, 200)`; any other `state` or failing `code` raises `ProtocolError("File deletion was rejected; do not retry automatically")`.
- Returns sanitized `{"ack": ack, "report": {"action": "deleteBatch", "state": "success", ...}}` (including integer `code` when present, excluding raw unknown fields/URLs). Never reconnects or replays.

*Alternative considered:* Treating `/response` `code == 0` alone as completion without waiting for `file/report`. Rejected because KX-Bridge explicitly documents that the immediate `/response` is only a generic ACK skeleton and the actual deletion outcome arrives in `file/report`.

### 3. Strict idle precondition and pre-flight listing verification

Before calling `delete_file_once()`:
1. Query fresh `info` (`client.query("info", require_fresh=True)`) and require `compatibility_issue(config, info) is None`.
2. Require the printer to be idle (`info.get("state") == "free"` and no active `info.get("project")`):
   - If `info.get("project")` is a dict whose `project_filename(project) == filename`, fail with exit 2 (`validation_failed`) specifically stating that the target file is currently active on the printer.
   - Otherwise, if `info.get("state") != "free"` or `info.get("project")` is truthy, fail with exit 2 (`validation_failed`) stating that stored file deletion requires an idle printer.
3. Query `list_files(client)` (`file/listLocal`) and match `r.get("filename") == filename`:
   - 0 matches → exit 2 (`validation_failed`), file not found.
   - >1 matches → exit 2 (`validation_failed`), ambiguous listing.
   - `matches[0].get("is_dir")` truthy → exit 2 (`validation_failed`), directories cannot be deleted.
4. Re-check `ensure_directory_bound(device_dir, device_fd, "delete")` immediately before publish.

*Alternative considered:* Allowing deletion of non-active files while another print is running. Rejected for initial unvalidated support because firmware `2.0.2.2` storage I/O behavior during active printing has not been qualified; requiring an idle printer matches `files upload` and `print start` and eliminates mid-print I/O interference risk.

### 4. Shared per-device lease and strict local state preservation (with read-only provenance summary)

- Extend `upload.device_lock(directory, operation)` in `kobra_lan/upload.py` so `operation in ("control", "delete")` acquires only `.device.lock` (matching `control` and serializing against `files upload`, `print start`, `print pause|resume|cancel`, and concurrent `files delete` without creating a separate `.delete.lock`).
- Never create, modify, or remove any profiles, upload receipts (`<state-dir>/<device16>/<64hex>.json`), upload `.attempt` markers (`<state-dir>/<device16>/<64hex>.attempt`), start receipts/markers (`<state-dir>/starts/<device16>/*`), or watch observations (`<state-dir>/observations/<device16>/*`).
- Perform a strictly read-only scan of `<state-dir>/<device16>` (using the already-opened `device_fd`) and `<state-dir>/starts/<device16>` (only if it already exists, opened with `O_NOFOLLOW` private checks without creating it) to count valid receipts referencing `filename`, returning:
  `local_state: {"preserved": True, "matching_upload_receipts": <int>, "matching_start_receipts": <int>}`.
  Unreadable or non-matching local files are ignored without failing the delete or altering any files/permissions.
- Resulting interaction with downstream commands:
  - `jobs list` / `jobs info` retain full historical visibility of prior uploads/starts/observations.
  - `print plan` / `print start` still query `file/fileDetails` remotely and refuse cleanly when the deleted file is gone, so preserved upload receipts cannot cause a stale start.
  - `files upload` allows uploading a *new* G-code (new SHA-256) to the freed filename once absent from `listLocal`, while keeping the preserved `.attempt` marker authoritative for the original SHA-256.

### 5. Bounded post-delete verification and module placement

Create `kobra_lan/delete_file.py` owning:
- `DeleteUncertain(ProtocolError)` with `result` and `exit_code` (2, 3, or 130 — mirroring `control.ControlUncertain`).
- Read-only local receipt counter helper (`summarize_local_state(device_fd, state_dir, device_prefix, filename)`).
- `delete_file(config, filename, state_dir)` executing the single-shot delete and bounded post-delete verification on the same pinned `MQTT` session:
  - Polls `list_files(client)` up to `POLL_COUNT = 3` times at `POLL_INTERVAL = 1` second, stopping early as soon as `filename` is absent from `records`.
  - Fetches one fresh `info` (`require_fresh=True`) and checks `compatibility_issue(config, after_info) is None`.
  - Sets `status` to `"delete_observed_removed"` when absent from `records`, or `"delete_acknowledged_not_confirmed"` when all polls succeeded cleanly yet `filename` remained listed (including sanitized `after_listing` when still present).
  - On any exception or `KeyboardInterrupt` after publish begins, raises `DeleteUncertain(result, exit_code=...)` with `status: "delete_uncertain_no_retry"` and available partial evidence (`ack`, `report`, `after`, `after_listing`), preserving exit 2 for protocol errors, 3 for I/O/timeout, and 130 for interrupt.
- Wire `files delete <name> --execute` in `kobra_lan/cli.py`, validating `<name>` before target selection, adding contextual `Parser.error()` guidance, and letting `kobra_lan/completions.py` derive bash/zsh/fish completions automatically from `build_parser()`.

## Risks / Trade-offs

- **Unvalidated firmware `2.0.2.2` `deleteBatch` report format** → KX-Bridge documents `file/report` with `action: "deleteBatch"` and `state: "success"`, but exact `timestamp`/`code`/`data` fields on Kobra X firmware `2.0.2.2` have not yet been captured by this client. Mitigation: mark every result `experimental: True` and `hardware_delete_validated: False`, tolerate absent/null `data` on `deleteBatch` reports while still requiring correlated `msgid` or post-ACK fresh timestamp + `state == "success"`, verify removal via `file/listLocal`, and defer flipping `hardware_delete_validated` until an operator-authorized live hardware test is recorded.
- **Re-uploading identical bytes after deleting a remote file** → Preserving upload `.attempt` markers means re-uploading the exact same SHA-256 to the same device remains blocked under the same `--state-dir`. Mitigation: this preserves the repository's non-negotiable invariant (never clear durable attempt markers); document the behavior clearly in `docs/usage.md` (uploading modified/new G-code with a new SHA-256 works immediately).
- **TOCTOU window with external clients** → Another client (touchscreen/app) could start a print or remove/replace the file between pre-flight checks and `delete_file_once()`. Mitigation: keep pre-flight checks and single publish back-to-back on the same pinned MQTT session, hold `.device.lock` against cooperating CLI callers, and document the firmware limitation in `docs/usage.md`.
- **Clock skew on fresh reports** → Host/printer clock skew can reject fresh timestamped `info` or `file/report` packets. Mitigation: classify post-publish timeouts as `delete_uncertain_no_retry` (retaining `ack` when received) and never replay the delete command.

## Migration Plan

- Purely additive CLI subcommand (`files delete <name> --execute`) and internal module (`kobra_lan/delete_file.py`).
- No configuration, profile, receipt, marker, or watch-observation schema changes; rollback to earlier versions requires no state migration and leaves all existing local records intact.
- Update module allowlists and offline installed-CLI probes in `scripts/check_python.py`, `scripts/build_deb.py`, and `scripts/accept_deb.py`.
