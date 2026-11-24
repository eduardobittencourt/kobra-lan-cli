# stored-file-deletion Specification

## Purpose

Delete one root-level stored file on a qualified Kobra X over a pinned authenticated MQTT session while enforcing explicit execution, fresh idle/active-job and listing preconditions, bounded post-delete verification, device concurrency locking, strict preservation of local receipts and attempt markers, and non-replaying uncertainty reporting.

## Requirements

### Requirement: Explicit execution guard and safe filename validation
`files delete <name> --execute` SHALL require explicit `--execute` and one positional `<name>`. Omitting `--execute` or supplying an empty, over-255-character, non-printable, dot-only, separator-bearing, or URL-bearing `<name>` SHALL fail with exit 2 (`invalid_arguments`) before target selection, state locking, or printer access, without an implicit dry run or echoing unsafe input.

#### Scenario: Missing execute flag
- **WHEN** `files delete model.gcode` runs without `--execute` in text or JSON mode
- **THEN** the CLI exits 2 with `invalid_arguments`, emits safe guidance pointing to `files list` and `--execute`, and performs no target lookup, state locking, or printer access

#### Scenario: Malformed filename argument
- **WHEN** `files delete ../secret.gcode --execute` or a token-bearing URL is supplied in text or JSON mode
- **THEN** the CLI exits 2 with `invalid_arguments` before target selection or printer access without echoing unsafe input

### Requirement: Fresh qualification, idle/active-job guard, and pre-flight target check
Before publishing, the CLI SHALL verify a fresh `info` report over one pinned MQTT session for Kobra X model `20030` / firmware `2.0.2.2`, require an idle printer (`state == "free"` with no active `project`), and verify via `file/listLocal` that `<name>` exists as one non-directory root entry. Unqualified targets, pin mismatches, busy printers, missing or duplicate entries, and directories SHALL exit 2 (`validation_failed`) without publishing.

#### Scenario: Active job matches target file
- **WHEN** `files delete active.gcode --execute` runs while the printer reports `active.gcode` as the active project
- **THEN** the CLI exits 2 with `validation_failed`, states that the target file is active on the printer, publishes no delete command, and leaves local state unchanged

#### Scenario: Printer is busy with another job or preparation state
- **WHEN** `files delete other.gcode --execute` runs while the printer is not idle (for example printing, preparing, paused, or stopping)
- **THEN** the CLI exits 2 with `validation_failed`, publishes no delete command, and leaves local state unchanged

#### Scenario: Target file is missing or is a directory
- **WHEN** `files delete missing.gcode --execute` runs for an absent filename, or `files delete folder --execute` targets a listing entry with `is_dir: true`
- **THEN** the CLI exits 2 with `validation_failed` without publishing any delete command

#### Scenario: Unqualified firmware or TLS pin mismatch
- **WHEN** `files delete model.gcode --execute` encounters a TLS pin mismatch or unqualified model/firmware/identity fields
- **THEN** the CLI exits 2 without publishing any delete command
- **AND** a TLS pin mismatch prevents transmission of MQTT credentials

### Requirement: Single-shot MQTT file deletion without replay
Stored-file deletion SHALL publish at most one QoS 0 MQTT `file/deleteBatch` request for `{"root": "local", "files": [{"path": "/", "filename": "<name>"}]}` through a write path separate from read-only queries. It SHALL wait on the same pinned session for the correlated `/response` ACK (`code == 0`) and fresh non-retained `file/report` (`state == "success"`, no failing code), and SHALL never reconnect or replay on rejection, timeout, disconnect, or malformed packets.

#### Scenario: Valid deletion publishes once with correlated ACK and report
- **WHEN** pre-flight checks pass for an idle qualified printer and an existing root file
- **THEN** the CLI publishes exactly one `file/deleteBatch` message targeting `{"root": "local", "files": [{"path": "/", "filename": "<name>"}]}` and waits for its correlated `/response` ACK and fresh `file/report`

#### Scenario: Rejected or dropped delete command is never replayed
- **WHEN** `/response` returns a non-zero code, `file/report` indicates failure, or the session times out, closes, or returns malformed data after publish
- **THEN** the CLI does not retry or reconnect and reports an uncertain outcome instructing the operator to inspect `files list` before taking further action

### Requirement: Bounded post-delete verification and honest outcome reporting
After a successful `file/deleteBatch` report, the CLI SHALL verify removal on the same pinned session via bounded `file/listLocal` polling and a fresh qualified `info` snapshot without treating acknowledgement as proof of removal. Output SHALL report `delete_observed_removed`, `delete_acknowledged_not_confirmed`, or `delete_uncertain_no_retry`, plus `dry_run: false`, `experimental: true`, and `hardware_delete_validated: false`.

#### Scenario: Confirmed file removal
- **WHEN** `file/deleteBatch` reports success and subsequent `file/listLocal` polling confirms `<name>` is absent alongside a fresh qualified `info` report
- **THEN** the CLI exits 0 with `status: "delete_observed_removed"`, sanitized `before`, `before_listing`, `ack`, `report`, `after`, `experimental: true`, and `hardware_delete_validated: false`

#### Scenario: Acknowledged delete still listed after bounded polling
- **WHEN** `file/deleteBatch` reports success and bounded `file/listLocal` polling completes cleanly while `<name>` still appears in printer storage
- **THEN** the CLI exits 0 with `status: "delete_acknowledged_not_confirmed"`, sanitized `before`, `before_listing`, `after`, and `after_listing`, and performs no retry

#### Scenario: Post-publish communication, protocol, or interrupt failure
- **WHEN** a timeout, disconnect, protocol error, or foreground interrupt occurs during ACK wait, report wait, or post-delete verification
- **THEN** the CLI exits with the failure's exit class (2 for protocol failure, 3 for I/O or timeout, 130 for interrupt), includes `status: "delete_uncertain_no_retry"` and available safe partial evidence in `result`, and performs no retry

### Requirement: Device concurrency safety and local receipt/marker preservation
`files delete` SHALL hold the shared per-device exclusive lease under `--state-dir` across pre-flight inspection, publish, and bounded verification, verifying directory binding before publish without following symlinks or altering permissions. It SHALL NOT create, modify, or remove profiles, upload receipts, `.attempt` markers, start receipts/markers, or watch observations, and SHALL report a safe read-only `local_state` preservation summary.

#### Scenario: Concurrent device operation refused
- **WHEN** another CLI upload, start, lifecycle control, or file deletion holds the per-device lease under `--state-dir`
- **THEN** `files delete` fails before printer access without waiting, retrying, or publishing a command

#### Scenario: Existing upload receipts, attempt markers, and start history remain untouched
- **WHEN** `files delete model.gcode --execute` deletes a file that has local upload receipts, upload `.attempt` markers, start receipts/markers, and watch observations under `--state-dir`
- **THEN** every existing local profile, receipt, marker, and observation remains byte-for-byte unchanged with original permissions
- **AND** the result reports `local_state.preserved: true` with safe matching upload and start receipt counts without creating missing `starts/` or `observations/` directories
- **AND** subsequent `jobs list` / `jobs info` continue reading the preserved history and subsequent duplicate uploads of the same SHA-256 remain blocked by the preserved upload `.attempt` marker

#### Scenario: Unsafe or replaced state directory refused
- **WHEN** the device state directory is a symlink, has non-private permissions, or is replaced before publish
- **THEN** the CLI refuses before sending any MQTT command without following symlinks or changing permissions
