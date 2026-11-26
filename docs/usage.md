# Operation and protocol guarantees

The examples use the source-checkout launcher. After installation, use `kobra-lan`.

## Output and exit contract

Output is readable English text by default, including when redirected. Put
`--json` before the command for one JSON document (except `camera pipe`, which
writes raw binary HTTP-FLV bytes to stdout and rejects `--json` with exit 2
before target lookup). Prompts, progress, and `camera pipe` diagnostics/errors
use stderr; final successes and failures for other commands use stdout. No
renderer queries a printer or writes operational state. Help, version and
`completion` always emit native text, even with root `--json`.

```sh
kobra-lan --json printer list
kobra-lan --json --printer bench doctor
```

Version 1 success: `{"schema_version":1,"ok":true,"result":{"profiles":[],"default":null}}`.
Failure: `{"schema_version":1,"ok":false,"error":{"code":"invalid_arguments","message":"Invalid arguments; use kobra-lan --help for supported commands and required options"}}`.
An operational failure retains `result` when safe partial information is available.
Do not parse human text; optional absent fields render as unknown and empty
collections as none. URLs and terminal controls are removed from display strings.
The output envelope does not change private receipt or registry schemas.

| Error code | Exit | Meaning |
| --- | --- | --- |
| `invalid_arguments` | 2 | Parser failure, invalid slot-map argument, or malformed execution hash, filename guard, or deletion filename |
| `validation_failed` | 2 | Selection, trust, protocol, qualification or reviewed-content refusal |
| `operation_failed` | 3 | Configuration, dependency, I/O or network failure; may retain local partial outcome |
| `diagnostic_failed` | 2 or 3 | Failed ordered doctor checks; exit 3 takes precedence |
| `interrupted` | 130 | User interrupted print observation, `camera pipe`, or a lifecycle control or deletion after publish |

Every result also includes a `qualification` string with the narrow model/firmware and experimental-start boundary. The `result` payloads retain these command-specific fields. Consumers should
allow additional safe fields and inspect outcome flags rather than infer success
from a filename or network acknowledgement.

| Command | Result shape |
| --- | --- |
| `printer pair` | `config_path`, `model_id`, `firmware`, `tls_sha256`, plus named `name`/`default` |
| `printer list` | `profiles` array, `default` (null or named selection); entries report availability |
| `printer info` | Selection metadata, `config_path`, `available`, host/device/model/firmware/pin metadata |
| `printer use` | `name`, `default` |
| `printer remove` | `name`, `registration_removed`, `deleted_files`, `preserved_files`, cleanup outcome |
| `doctor` | Inner `version: 1`, safe `target`, ordered `checks`, `healthy` |
| `status` | `identity`, sanitized `info`, nullable `print`, `last_print` |
| `slots list` | `device_digest`, `model`, `firmware`, `printer_state`, onboard box summary (`box_id: -1`, `box_kind: "onboard"`, `slot_count: 4`, `loaded_count`), and ordered `slots` (`slot`, `ams_index`, `status`, `status_label`, `available_for_start`, nullable `material_type`, `color_rgb`, `color_hex`) |
| `camera status` | `device_digest`, `model`, `firmware`, `printer_state`, `camera_present`, nullable `timelapse_supported`, `stream_url_announced`, nullable `stream_protocol`, nullable `stream_port`, `experimental: true`, `hardware_camera_validated` (never includes stream URLs or tokens) |
| `camera snapshot` | `output_path`, `format` (`"jpeg"` or `"png"`), `bytes`, `sha256`, `width`, `height`, `capture_mode` (`"direct"` or `"start_capture"`), `start_capture_used`, `stop_capture_sent`, `experimental: true`, `hardware_camera_validated` |
| `camera pipe` | Raw binary HTTP-FLV bytes on stdout (`--json` rejected with exit 2); stderr-only diagnostics; exits 0 on EOF, limit, or broken pipe, and 130 on interrupt |
| `files list` | `records` array of filename/size/directory metadata |
| `files info` | `filename` and available safe file details |
| `gcode inspect` | `sha256`, `md5`, `size_bytes`, `remote_filename`, nullable `layer_count`, `slicer_version`, filament/color metadata (`paint_info_present`, ordered `filaments`, `filament_count`, `multicolor`, `tool_indices`, nullable `total_filament_used_g`), operation/qualification flags |
| `files upload` | Manifest, verification/status flags, timestamp and `receipt_path` |
| `files delete` | `filename`, `device_digest`, model/firmware, `status`, `dry_run: false`, `experimental: true`, `hardware_delete_validated: false`, `local_state`, sanitized `before`/`before_listing`, `ack`/`report`, and `after`/`after_listing` when available |
| `print plan` | `file_sha256`, `device_digest`, model/firmware, canonical `payload`, `plan_sha256`, `slot_mapping`, `multicolor`, qualification flags, latest local `attempt_id` and `start_status` when available, and `previous_attempt_id` for a reprint review |
| `print start` | Plan fields, `dry_run: false`, local `attempt_id`, `previous_attempt_id` for a reprint, status/ack/observation evidence and `receipt_path`; an uncertain error may return a subset of that evidence |
| `print watch` | `outcome`, `reason`, verified `phase`, `progress` (percent), `current_layer`, `total_layers` when available, plus `observation_recorded` and `observation_id` when an active job was observed |
| `print pause\|resume\|cancel` | `action`, `wire_action`, `device_digest`, model/firmware, `status` (`control_observed_*`, `control_acknowledged_not_confirmed`, or `control_uncertain_no_retry`), `dry_run: false`, `experimental: true`, `hardware_control_validated: true`, `taskid`, optional `expected_filename`, sanitized `before`/`before_project`, `ack`, `after`, and `project` (subset retained on uncertain failure) |
| `jobs list` | `device_digest`, `kind`, `limit`, `total_count`, `returned_count`, `incomplete_count`, `truncated`, newest-first `jobs` summaries, and local-only `coverage` metadata |
| `jobs info` | Detailed start attempt (chain links, hashes, `slot_mapping`, preparation settings, `start_status`, `terminal_outcome: "unknown"`, `reprint_eligibility`, `upload_provenance`, `issues`, `unattributed_matching_observations`), saved watch observation, or `unreadable-<storage-key>` record, plus `coverage` metadata |

This 0.x interface uses `--slot-map 0=N` in place of `--slot N` for a
single filament with paint index 0. Replace reads of `selected_slot` on
`print plan`, `print start` and `jobs info` with reads of `slot_mapping`.
On `jobs info`, read `material_type` per entry in `slot_mapping`. The
version-1 envelope remains compatible; start records under `starts/<device>/`
use canonical attempt-keyed storage (`<attempt_id>.attempt` and
`<attempt_id>.json`) without `record_format`.

Both formats preserve full review hashes, experimental qualification and uncertain
outcomes. Upload metadata confirmation does not prove remote byte equality;
start acknowledgement and observed activity do not prove completion or quality.

## Inspect onboard filament slots

```sh
kobra-lan slots list
kobra-lan --json --printer bench slots list
```

`slots list` is strictly read-only: it resolves the selected printer via
`--printer`, `--config`, or the saved default, opens one pinned MQTT session
without writing local state or modifying device state, verifies a fresh `info`
report for Kobra X model 20030 / firmware 2.0.2.2 (succeeding whether the
printer is idle or actively printing), and queries `multiColorBox / getInfo`.
It reports the onboard four-slot box (`box_id: -1`, `box_kind: "onboard"`,
`slot_count: 4`, `loaded_count`) and four `slots` ordered by `ams_index` `0..3`
(`slot` `1..4`) with raw integer `status`, `status_label` (`loaded`, `empty`,
or `other`), `available_for_start`, and nullable `material_type`, `color_rgb`,
and `color_hex`. Raw unknown telemetry fields, URLs, and credentials are
excluded. External ACE or multi-box topologies (`id != -1` or box count other
than 1) and unqualified firmware fail with exit 2 (`validation_failed`).

Offline `gcode inspect <file> [--name <remote-name>]` inspects the other side
of filament planning without configuration, network, or state writes. It
validates every `; paint_info =` declaration in the file (rejecting malformed
or conflicting repeated headers with exit 2), extracts sorted unique `T<n>`
tool indices and optional `; filament used [g]` / `; total filament used [g]`
summaries, and reports `paint_info_present`, ordered `filaments` (supporting
non-contiguous `paint_index` values and mixed materials), `filament_count`,
`multicolor`, `tool_indices`, and `total_filament_used_g`. Minimal Kobra X
G-codes omitting `; paint_info =` remain inspectable and uploadable via
`files upload`. For start planning, use the declared paint indices and tool
indices.

## Inspect and capture camera video

```sh
kobra-lan camera status
kobra-lan --json --printer bench camera status
kobra-lan camera snapshot --output /tmp/bed.jpg --timeout 15
kobra-lan camera snapshot --output /tmp/bed.png --overwrite --no-start-capture
kobra-lan camera pipe --max-bytes 65536 > /tmp/sample.flv
kobra-lan camera pipe | ffplay -f flv -
```

- **`camera status`** is strictly read-only: it opens one pinned authenticated
  MQTT session, verifies fresh qualification for Kobra X model 20030 / firmware
  2.0.2.2, queries `info` and `peripherie`, and reports `camera_present`,
  `timelapse_supported`, `stream_url_announced`, `stream_protocol` (`"http-flv"`),
  `stream_port` (`18088`), `printer_state`, `experimental: true`, and
  centralized `hardware_camera_validated`. It never opens port `18088`, never
  mutates printer or local state, and never exposes stream URLs or tokens.
- **Read-only-first acquisition with optional fallback**: `camera snapshot` and
  `camera pipe` verify fresh qualification and `camera == 1`, validate the
  announced local stream URL, and attempt a direct read-only HTTP `GET` to
  `http://<paired-host>:18088/live/<token>` (accepting HTTP `200`/`206` with
  valid `FLV` magic bytes) without mutating printer state (`capture_mode:
  "direct"`, `start_capture_used: false`, `stop_capture_sent: false`). Only if
  that direct read fails and `--no-start-capture` is omitted do they send one
  MQTT `video/startCapture`, refresh `info`, retry the validated `GET` once,
  and always send best-effort `video/stopCapture` in cleanup (including on
  decode failure, downstream broken pipe, or `SIGINT`). Pass
  `--no-start-capture` to forbid any capture mutation and fail with exit 3 if
  direct read is unavailable.
- **Strict URL validation and token redaction**: announced stream URLs are
  accepted only as plain `http` targeting the exact paired IPv4 address and port
  `18088` with a bounded `/live/<token>` path and no userinfo, query, fragment,
  path traversal, or control characters; HTTP connections disable proxies and
  redirects. Stream URLs and tokens never appear in stdout, stderr, JSON
  envelopes, exceptions, or external subprocess command lines. Because the
  Kobra X firmware serves port `18088` in plaintext HTTP on the LAN, use camera
  capture only on a trusted local network.
- **`camera snapshot`** validates `--output` (`.jpg`, `.jpeg`, or `.png`,
  existing parent directory, absent destination including symlinks unless
  `--overwrite` is passed), `--timeout` (`1` to `60`, default `15`), and the
  presence of optional external `ffmpeg` on `PATH` before any target lookup or
  network access. Missing `ffmpeg` exits 3 (`operation_failed`) with
  installation guidance. Validated FLV bytes are piped to `ffmpeg` over `stdin`
  (never passing the stream URL in `argv`), verified in pure Python for valid
  JPEG/PNG magic and dimensions, and published atomically without clobbering
  existing files unless `--overwrite` is supplied.
- **`camera pipe`** requires no external video binaries (`ffmpeg` is not
  needed), validates optional `--timeout` (`1` to `86400` seconds) and
  `--max-bytes` (`1` to `10737418240` bytes), rejects global `--json` with exit
  2 (`invalid_arguments`) before target selection, verifies `FLV` magic before
  forwarding any bytes to `stdout`, and writes diagnostics/errors only to
  `stderr`. Downstream pipe closure (`BrokenPipeError`) exits 0 cleanly without
  a traceback; foreground `SIGINT` runs cleanup and exits 130.

## Inspect, upload, plan and start

Set up access with `printer pair --name bench --host 192.0.2.10 --default
--trust-sha256 FINGERPRINT`, inspect `printer list`, then diagnose with
`--printer bench doctor`. Pairing needs an independently trusted full fingerprint.
Read [initial trust](pairing.md) before any provisioning.

```sh
kobra-lan gcode inspect model.gcode --name model.gcode
kobra-lan --printer bench files upload model.gcode --name model.gcode --sha256 FILE_HASH --execute
kobra-lan --printer bench print plan model.gcode --name model.gcode --slot-map 0=1 \
  --auto-leveling on --vibration-compensation off --flow-calibration off
kobra-lan --printer bench print start model.gcode --name model.gcode --slot-map 0=1 \
  --auto-leveling on --vibration-compensation off --flow-calibration off \
  --plan-sha256 PLAN_HASH --execute
```

Replace FILE_HASH with the full SHA-256 from inspection and PLAN_HASH with the
full reviewed plan digest. `files upload` has no implicit dry run and never
starts a print. `print plan` never uploads, starts or writes an attempt. Review
the device digest, filename, slot mapping, materials, colors and all three
preparation settings in either format. The final start rebuilds that plan;
changed execution inputs require fresh review. These examples do not authorize
physical actions. Only execute when the particular upload or print is authorized.

`uploaded_verified_by_listing_and_metadata` means metadata checks passed and
`remote_byte_hash_verified` remains false. `start_acknowledged_not_confirmed`
means an acknowledgement without observed activity; `start_observed_active`
means bounded observation saw the selected project active. Uncertain results
retain durable reservations and explicitly forbid automatic resend. No outcome
here claims completed printing or physical quality. Existing configs, receipts
and device/file markers, including under `--state-dir`, remain authoritative.

## Delete a stored file

```sh
kobra-lan --printer bench files list
kobra-lan --printer bench files delete old-model.gcode --execute
```

Choose one root-level filename from `files list`. The command requires
`--execute` and checks fresh identity and status on a pinned MQTT session for
Kobra X model 20030 / firmware 2.0.2.2. It requires state `free` with no active
project and refuses an active target, a directory, or a name that is missing
or appears more than once. The result carries `dry_run: false`,
`experimental: true` and `hardware_delete_validated: false`.

The command sends once and waits for a correlated ACK and a successful delete
report. It checks the root listing up to three times, waiting one second
between polls, then requests fresh qualified status on the same session.

| Status | Exit | Meaning |
| --- | --- | --- |
| `delete_observed_removed` | 0 | The file was absent from a post-delete listing and fresh status passed qualification. |
| `delete_acknowledged_not_confirmed` | 0 | The printer reported success and the file still appeared at the end of polling. |
| `delete_uncertain_no_retry` | 2, 3 or 130 | A protocol failure, communication failure, or interrupt occurred after sending began. The result retains evidence collected so far. |

Inspect `files list` after an unconfirmed or uncertain result before taking
further action. The CLI never reconnects or resends the deletion automatically.
The per-device lease under `--state-dir` serializes cooperating CLI operations.
The touchscreen and mobile app can still change printer state or replace the
file between inspection and publish.

Deletion preserves local profiles, upload and start receipts and attempt
markers, and watch observations. The read-only `local_state` summary counts
matching upload and start receipts. `jobs list` and `jobs info` still read
the historical records. A preserved upload marker continues to block
uploading identical bytes under the same device and state directory. A file
with a new SHA-256 can use the freed filename after the normal upload checks.
`print plan` and `print start` still require current remote metadata.

## Experimental print start

`print plan` queries the printer and builds a plan for an already uploaded file
and the onboard four-slot box. Repeat `--slot-map PAINT_INDEX=SLOT` once for
each declared paint index. Use the zero-based index from `gcode inspect` and
the one-based slot number (1–4) from `slots list`.

```sh
./kobra-lan print plan /path/to/model.gcode --name agent-model.gcode --slot-map 0=1 \
  --auto-leveling on --vibration-compensation off --flow-calibration off
```

All three preparation options are required. Both formats include the payload
and full `plan_sha256`. Changing the file, mapped slot, mapped material or
color, or preparation options changes the hash. Plans and start receipts
include `multicolor` and `slot_mapping` ordered by `paint_index`. Each entry
reports `paint_index`, `slot`, `ams_index`, `gcode_material_type`,
`gcode_color_hex`, `slot_material_type`, and `slot_color_hex`. Changing the
order of the `--slot-map` arguments preserves the hash.

Plans and starts report `experimental: true`. `hardware_start_validated: true`
applies only to observed Kobra X firmware `2.0.2.2` configurations with
`PLA High Speed`, `--auto-leveling on`, `--vibration-compensation off`, and
`--flow-calibration off`: single-filament `paint_index: 0` on slot 1, 2, or 4,
and 4-color contiguous 1:1 mapping `0=1, 1=2, 2=3, 3=4`. Single-filament slot 3,
cross-remapped (`paint_index != ams_index`), subset, sparse, or shared-slot
multicolor mappings, non-zero single-filament paint indices, and other material
or preparation combinations report `hardware_start_validated: false`. External
ACE and multi-box configurations are rejected.

To request execution later, use `print start` with the same explicit arguments plus `--execute --plan-sha256 REVIEWED_PLAN_HASH`. This is a physical action: run it only when printing is authorized and the printer is prepared. It requires a verified upload receipt from this CLI, rechecks the file/state/material, and writes a durable reservation before publishing **one** MQTT `print/start` command. It does not upload again. An ACK is not treated as proof of physical printing; the client subsequently queries the active project and distinguishes observed activity from an uncertain result. It never automatically repeats the command.

### Plan and start a multicolor print

Inspect the file and the loaded slots in JSON for use from a script or agent.
Use `filaments[].paint_index` and `filaments[].material_type` from inspection.
Each value in `tool_indices` must appear in the declarations. For each index,
choose a slot with `available_for_start: true` whose base material matches the
G-code, such as PLA High Speed for PLA. Several indices can share one slot if
each material matches that spool. For a single declaration at index 2, use
one mapping such as `--slot-map 2=4`.

The example maps PLA at index 0 to slot 1 and PETG at index 2 to slot 4.
Use the inspected file hash for an authorized upload, then review the returned
plan and use its digest for an authorized start.

```sh
kobra-lan --json gcode inspect model.gcode --name model.gcode
kobra-lan --json --printer bench slots list
kobra-lan --json --printer bench files upload model.gcode --name model.gcode --sha256 FILE_HASH --execute
kobra-lan --json --printer bench print plan model.gcode --name model.gcode \
  --slot-map 0=1 --slot-map 2=4 --auto-leveling on --vibration-compensation off --flow-calibration off
kobra-lan --json --printer bench print start model.gcode --name model.gcode \
  --slot-map 0=1 --slot-map 2=4 --auto-leveling on --vibration-compensation off --flow-calibration off \
  --plan-sha256 PLAN_HASH --execute
```

### Deliberately reprint a stored file

After confirming that the previous run has ended and the printer is prepared,
locate the latest local `attempt_id` (text: `Attempt id`) using either ordinary
`print plan` (with the original file, remote name and state directory) or
offline `jobs list --kind start` / `jobs info <attempt-id>`. Copy it only if
ordinary `print plan` reports `start_status: start_observed_active`, or if
`jobs` reports `reprint_eligibility: eligible_for_plan`. These are local
references, not firmware task IDs. Ordinary `print plan` keeps the original hash
semantics; whichever command you used to find the ID, review a separate reprint
plan with `print plan --reprint-from`:

```sh
kobra-lan --printer bench print plan model.gcode --name model.gcode --slot-map 0=1 \
  --auto-leveling on --vibration-compensation off --flow-calibration off \
  --reprint-from PREVIOUS_ATTEMPT_ID
kobra-lan --printer bench print start model.gcode --name model.gcode --slot-map 0=1 \
  --auto-leveling on --vibration-compensation off --flow-calibration off \
  --reprint-from PREVIOUS_ATTEMPT_ID --plan-sha256 REVIEWED_REPRINT_HASH --execute
```

Execute only with separate authorization for this run. The review binds the
previous attempt, device, file and execution choices. The CLI reuses the same
verified upload receipt, checks fresh idle telemetry and reserves a single
successor with a new `attempt_id`. An idle printer does not establish that a
previous print completed successfully. A missing or inconsistent receipt, a
reservation without observed activity, or a bare ACK is not eligible. If a
start is interrupted or uncertain, inspect status and keep the records intact;
do not replay the review, change `--state-dir` or remove reservations to retry.

## Pause, resume and cancel an active print

```sh
kobra-lan --printer bench print pause --execute
kobra-lan --printer bench print pause --execute --filename agent-model.gcode
kobra-lan --printer bench print resume --execute --filename agent-model.gcode
kobra-lan --printer bench print cancel --execute --filename agent-model.gcode
```

`print pause`, `print resume`, and `print cancel` are **experimental**
single-shot lifecycle controls (`experimental: true`,
`hardware_control_validated: true` on qualified Kobra X model 20030 / firmware
2.0.2.2, where live `pause`, `resume`, and `stop` transitions were validated on
2026-11-23). They act on the active job on a qualified Kobra X
(model 20030 / firmware 2.0.2.2), including jobs started by another client.
Because `resuming` and `stopping` on firmware `2.0.2.2` often exceed the
bounded 5-second post-ACK polling window, `print resume` and `print cancel`
commonly return `control_acknowledged_not_confirmed` even when the printer
completes the transition shortly afterward.

- **Explicit execution guard and optional `--filename`:** Every lifecycle
  command requires `--execute`; omitting it fails with exit 2
  (`invalid_arguments`) before target selection, state locking, or printer
  access (there is no implicit dry run). Optional `--filename NAME` is
  validated before target selection as a safe printable filename (non-empty,
  at most 255 printable characters, no `/ \ : ? #`, no URL schemes or control
  characters). If the fresh active `project.filename` differs, the CLI exits 2
  (`validation_failed`) before publishing.
- **Strict pre-flight qualification and state preconditions:** Over one pinned
  MQTT session, the CLI verifies a fresh `info` report for Kobra X model 20030
  / firmware 2.0.2.2 and consistent optional identifiers, then enforces:
  - `print pause` (wire action `pause`): requires active `project.state == "printing"`.
  - `print resume` (wire action `resume`): requires `project.state == "paused"`.
  - `print cancel` (wire action `stop`): requires `project.state` in `printing`,
    a recognized firmware `2.0.2.2` preparation phase (`extfilbox_filament_feeding`,
    `frequency_sweeping`, `hotbed_cooling_off`, `hotbed_heating`, `nozzle_cooling`,
    `nozzle_heating`, `nozzle_purging`, `nozzle_wiping`, `z_offset_calibrating`),
    or `paused`.
  - Idle (`state == "free"`), already-reached states, transitional states
    (`pausing`, `resuming`, `stopping`), and unrecognized states fail with exit
    2 (`validation_failed`) without publishing.
- **Single-shot publish and bounded post-ACK verification:** The CLI sends at
  most one QoS 0 MQTT `print` command carrying the validated active `task_id`
  (or `"-1"` placeholder), waits for one correlated `/response` ACK (`code == 0`),
  and then polls fresh `info` up to 5 times at 1-second intervals on the same
  session without treating ACK as proof of state change:
  - `control_observed_paused`, `control_observed_resumed`, or
    `control_observed_stopped` (exit 0): bounded polling observed the expected
    post-action state (`paused` for pause; `printing` or a recognized
    preparation phase for resume; idle `free` with no active project, `stoped`,
    or `canceled` for cancel).
  - `control_acknowledged_not_confirmed` (exit 0): ACK succeeded and bounded
    polling completed cleanly while the printer remained in a prior or
    transitional state (for example, while parking or cooling). Inspect
    `status` or `print watch` rather than replaying blindly.
  - `control_uncertain_no_retry` (exit 2 on protocol rejection/malformed
    response, exit 3 on timeout, disconnect, or I/O failure): retains safe
    partial evidence (`before`, `before_project`, and `ack`/`after`/`project`
    when available) and performs no reconnect or retry. Always inspect `status`
    before taking further action; never resend blindly.
- **Per-device concurrency lease and state preservation:** Lifecycle controls
  acquire the shared private per-device lease (`.device.lock`) under
  `--state-dir` across pre-flight inspection, publish, and bounded observation,
  verifying directory binding before publish without following symlinks or
  changing permissions. Concurrent `files upload`, `files delete`, `print start`, and
  `print pause|resume|cancel` invocations targeting the same device and
  `--state-dir` fail before printer access. Existing profiles, upload receipts,
  start receipts, `.attempt` markers, and watch observations remain
  byte-for-byte unchanged. Because the printer has no compare-and-swap control
  primitive, external clients (touchscreen or mobile app) can still change
  printer state between pre-flight inspection and publish.

## Watch an active print

```sh
kobra-lan --printer bench print watch --timeout 3600
kobra-lan --json --printer bench print watch
```

Watch observes the job already active at startup on a Kobra X model 20030 /
firmware 2.0.2.2. It accepts jobs started from any client. It polls fresh
`info` reports on one pinned MQTT connection and releases the managed profile
lease as soon as that session is established. It requests status every five
seconds after the initial query. The timeout accepts 1 to 259200 whole seconds
and defaults to 86400. It includes connection setup, polls and closing the session.

The command sends one final summary to stdout. Exit 0 means the observer returned
a result. The outcome `no_active_job` describes verified idle at startup.
`unknown` covers cases such as an expired deadline, a lost job or telemetry
that cannot distinguish attempts. An acknowledgement, idle transition, unchanged
last project or 100 percent progress alone is insufficient evidence of completion.
Only terminal signals attributable to the same attempt and validated in hardware
can qualify for `completed`, `canceled` or `failed`.

A live observation on 2026-11-21 verified increasing percent and layer
counters, followed by an idle report with the initial `last_project` still
empty; a live cancellation on 2026-11-23 likewise settled to idle `free` with
`last_project` still empty. The active report had the `task_id` placeholder
`"-1"`. A repeated filename and that placeholder are insufficient to follow the
same attempt. Watch preserves the first verified progress and returns `unknown`
if a subsequent report cannot establish continuity. No terminal outcome mappings
are enabled for this firmware.

Exit 2 indicates argument, trust, qualification or protocol refusal. Exit 3
indicates a configuration or communication failure and 130 indicates a user
interrupt. A failure after observing a job includes the last verified progress
as a partial result. Clock skew between the printer and the host can cause a
report to fail the freshness check and time out. Part quality requires separate
physical inspection.

Once `print watch` establishes a verified active phase, it atomically saves one
sanitized private (`0600`) observation record (`obs-<32hex>.json`) under
`<state-dir>/observations/<device-prefix>/` (`0700`, walked without following
symlinks) before exiting, including on deadline expiration, post-observation
failure, or interruption. The saved record stores `client_attribution: "unattributed"`,
timestamps, validated `observed_filename` when available, outcome, reason, and
verified scalar progress without raw telemetry, credentials, or token URLs.
Stdout reports `observation_recorded` and `observation_id` without exposing
`observed_filename`. Idle runs (`no_active_job`) and pre-observation failures
create no directories or files. Existing profiles, credentials, upload/start
receipts, and `.attempt` markers are never modified. If the observation
directory is a symlink, has non-private permissions, or cannot be written,
`print watch` preserves its outcome and exit status, reports
`observation_recorded: false` (without `observation_id`), and neither follows
symlinks nor alters permissions.

## Inspect local job history

```sh
kobra-lan --printer bench jobs list
kobra-lan --printer bench jobs list --kind start --limit 20
kobra-lan --printer bench jobs list --kind observation --limit 10
kobra-lan --json --printer bench jobs info RECORD_ID
```

`jobs list` and `jobs info` are strictly offline and read-only: they resolve the
selected printer via `--printer`, `--config`, or the saved default solely to
derive its `device_digest`, read existing state under `--state-dir`, and never
contact a printer or modify files or permissions. Different profiles targeting
the same `printer_id` and `--state-dir` see identical local history.

- **Local-only coverage:** Firmware `2.0.2.2` exposes no attributable
  completed-run history over LAN. Every `jobs list` and `jobs info` result
  includes explicit `coverage` metadata (`scope: "local_state_only"`,
  `direct_printer_history_available: false`,
  `other_client_actions: "only_when_watched_unattributed"`,
  `terminal_outcomes_verified: false`). Prints started by other clients appear
  only when observed with `print watch` and are always marked
  `client_attribution: "unattributed"`.
- **Start attempts and reprint chains:** Canonical attempt-keyed start records
  (`<attempt_id>.attempt` and `<attempt_id>.json`, where `storage_key == attempt_id`)
  for both root starts and reprints under `<state-dir>/starts/<device-prefix>/` are
  reconstructed in place without modifying bytes or permissions, matching the
  deterministic `attempt_id` used by `print plan` and `--reprint-from`.
  `jobs info <attempt-id>` reports `previous_attempt_id`/`next_attempt_id`,
  plan/file hashes, preparation settings, `start_status`,
  `reprint_eligibility` (`eligible_for_plan`, `superseded`,
  `blocked_not_observed_active`, `blocked_incomplete`, or
  `blocked_missing_upload_provenance`), correlated upload provenance
  (`remote_byte_hash_verified: false`), and `unattributed_matching_observations`
  (same-filename watch observations at or after the start timestamp, explicitly
  labeled `attribution: "unattributed_filename_match"`). Start attempts always
  keep `terminal_outcome: "unknown"`.
- **Slot mapping:** `jobs info` reconstructs `slot_mapping` from the saved
  payload. Entries are ordered by `paint_index` and include `slot`,
  `ams_index`, `material_type`, `gcode_color_hex`, and `slot_color_hex`.
  The mapping is `null` when unavailable or unreadable. `jobs list` keeps
  its compact summary.
- **Incomplete and unreadable records:** Non-canonical (including preexisting
  pre-v1 file-keyed) files, marker-only reservations, receipt-only files,
  mismatched pairs, unverified active evidence, orphan successors, and
  unreadable/corrupt/non-private/symlinked files remain untouched and visible
  with `completeness: "incomplete"`, safe issue codes, and
  `reprint_eligibility: "blocked_incomplete"`. When neither marker nor receipt
  establishes a valid canonical `attempt_id` matching `storage_key` for the
  selected device, the record is exposed as `unreadable-<storage-key>`.
- **Record IDs and safety:** `jobs list` supports `--kind all|start|observation`
  (default `all`) and `--limit` from `1` to `500` (default `50`), ordered newest
  first with summary counts (`total_count`, `returned_count`,
  `incomplete_count`, `truncated`). `jobs info` accepts a 64-hex `attempt_id`,
  an `obs-<32hex>` `observation_id`, or an `unreadable-<64hex>` reference.
  Malformed arguments fail with exit 2 before target selection without echoing
  untrusted values; unknown or cross-device IDs exit 2. Existing device state
  directories (`<state-dir>/<device>`, `starts/<device>`,
  `observations/<device>`) are walked without following symlinks and must be
  user-owned mode `0700`; symlinked or permissive device directories fail with
  exit 3 without altering permissions.

## Guarantees and limitations

- Upload is currently qualified only for model 20030 / firmware 2.0.2.2, Next-generated G-code, and the Kobra X profile. It requires an idle printer with no active project.
- Hashing and multipart construction use the same bytes in memory. No G-code translation, `print=true` flag, or HTTP redirects.
- Exclusive reservations are persisted with fsync in `~/.local/share/kobra-lan/uploads/`. Upload receipts and markers are keyed by file SHA-256 under `<device-prefix>/`, while every start attempt (both root starts and reprints) is keyed by its deterministic `attempt_id` under `starts/<device-prefix>/<attempt_id>.attempt` and `<attempt_id>.json` without modifying earlier attempts. Each predecessor can be consumed at most once across processes and restarts.
- Mutating device commands (`files upload`, `files delete`, `print start`, and `print pause|resume|cancel`) sharing a device state directory hold a single private shared per-device lease (`.device.lock`) from before printer access until post-action observation ends. A concurrent contender fails before printer access, including for different hashes, operations, or profile names. After an ambiguous response, inspect status/files/receipts and preserve all markers. Different state directories, older binaries and other clients do not share this lease.
- Uploads keep listing, reservation, POST and verification inside that device lease.
  The lock file is retained; closing its descriptor releases the lease.
  State paths are walked without following symlinks; an existing device directory
  must be user-owned and private (0700). Invalid permissions are refused without
  changing them, and the lock must be a private regular file (0600).
  Marker checks, reservations and atomic receipt writes stay relative to the
  leased directory descriptor. A replaced state path blocks sending or records
  uncertainty after a send; reservations and receipts remain in the original
  directory and no request is replayed.
  Other clients or state directories do not share this lock, and firmware-side
  atomic rejection of an existing filename has not been established.
- Existing remote files are not overwritten. Names must be safe ASCII basenames; only `.gcode` files up to 128 MiB are accepted.
- Remote verification checks filename, size, layers, and printer model. The endpoints used did not provide a checksum of stored bytes: `remote_byte_hash_verified=false` explicitly indicates that the internal copy was not downloaded and independently hashed. Investigation of stock Kobra X model 20030 / firmware 2.0.2.2 LAN mode found no HTTP or MQTT endpoint for downloading stored `.gcode` files (or stored timelapse `.mp4` videos); `files download` therefore remains unsupported on this firmware (see [validation evidence](#validation-evidence)).
- Firmware 2.0.2.2 sends a correlated ACK followed by a report with a different msgid. Queries are synchronous and accept a fresh report after the ACK. An idle printer does not produce a report for `print/query`; status uses `info/report`.
- There is no transactional lock against another computer between a query and an action. Credentials/pins may change after firmware or LAN-mode changes; reassess provisioning.


## Validation evidence

Manual upload validation: one actual POST of an Autodesk FDM Test generated by Next 2.0.0.3, 6,856,570 bytes, 460 layers, HTTP 200/code 200. Listing and metadata confirmed an estimated time of 1h44m09s and approximately 31.74 g. The printer remained idle without heating. This does not validate physical print quality or the experimental start operation.

End-to-end validation on 2026-10-07: Autodesk FDM Test sliced with Next Linux 2.0.0.5 and official Kobra X / 0.20mm Standard / PLA High Speed profiles, using one CPU and preserving model position/orientation. Output: 6,835,381 bytes, 460 layers, estimated 1h44m12s and approximately 31.74 g. One upload was verified, followed by one MQTT start using the reviewed plan. Telemetry confirmed the correct active file, preparation phases, and printing at layer 1/460 with bed/nozzle targets of 60°C/220°C. No upload or start was repeated. Completion and physical quality were not assessed in this validation.


Live stored-file deletion on 2026-11-23 used a lifecycle-test G-code file on
Kobra X model 20030 / firmware 2.0.2.2. The printer reported `free` before and
after the operation. One delete request received a correlated ACK (code 0)
and a `deleteBatch` report with state `success` and code 200. The CLI returned
`delete_observed_removed` (exit 0), and a separate `files list` request confirmed
the file was absent. The local summary counted one matching upload receipt
and one matching start receipt. Byte-for-byte preservation was verified in
offline tests with synthetic state.

End-to-end 4-color validation on 2026-11-24 used a `by object` Cool Plate
G-code sliced with Anycubic Slicer Next Linux `2.0.0.6` for Kobra X (9,257,439
bytes, 207 layers, estimated ~60.68 g, four `PLA` paint entries `0..3` with
three filament changes). Executed end-to-end via the CLI (`slots list`,
`gcode inspect`, `files upload`, `print plan`, `print start`, and `status`)
with `--slot-map 0=1 --slot-map 1=2 --slot-map 2=3 --slot-map 3=4` across all
four onboard `PLA High Speed` slots (`1..4`, including slot 3 at `ams_index: 2`),
`--auto-leveling on`, `--vibration-compensation off`, and
`--flow-calibration off`. Upload returned
`uploaded_verified_by_listing_and_metadata`, start returned
`start_observed_active` (ACK code 0), status confirmed `busy` /
`nozzle_heating` with 35°C/220°C targets, and the operator confirmed physical
completion with all four colors and slots matching. Because this run used an
identity 1:1 mapping (`paint_index == ams_index`), cross-remapped, sparse,
subset, shared-slot, non-zero single-filament, and single-filament slot 3
starts remain `hardware_start_validated: false`.

End-to-end live camera validation on 2026-11-25 on Kobra X model 20030 /
firmware 2.0.2.2 verified `camera status` (text and `--json`, confirming
`camera_present: true`, `timelapse_supported: true`,
`stream_url_announced: true`, `stream_protocol: "http-flv"`,
`stream_port: 18088`, and zero URL/token exposure), `camera pipe`
(`--max-bytes 65536 --no-start-capture` streaming valid FLV v1 video-only bytes
directly, downstream broken-pipe exit `0`, foreground `SIGINT` exit `130`, and
`--json` rejection exit `2`), live `video/startCapture`
(`initSuccess` -> `joinSuccess` -> `pushStarted`) and `video/stopCapture`
(`pushStopped`) transitions, and `camera snapshot` with Debian 13 `ffmpeg`
`7.1.5-0+deb13u1` (1280×720 JPEG and PNG frames in `direct` mode, existing-file
refusal exit `2` without `--overwrite`, atomic replacement with
`--overwrite --no-start-capture`, and exit `3` before network access when
`ffmpeg` was absent). Camera commands therefore report
`hardware_camera_validated: true` on Kobra X model 20030 / firmware 2.0.2.2
(post-reboot cold-start behavior without prior capture remains unverified and
is covered by the automatic `startCapture`/`stopCapture` fallback).

Stored-file download investigation on 2026-11-25 evaluated whether stock Kobra X
model 20030 / firmware 2.0.2.2 exposes a LAN mechanism to retrieve stored
`.gcode` files (or stored timelapse `.mp4` videos) back from printer storage.
Static inspection of official `AnycubicSlicerNext` `1:2.0.0.6` (`/usr/lib/libmach_mqtt.so`,
`/usr/bin/AnycubicSlicerNext`, `/usr/lib/libWorkbench.so`, and
`/usr/lib/libcloud_sdk_cpp.so`) established that LAN `mach_mqtt::FDM::Control`
operations cover only `listLocal`, `listUdisk`, `fileDetails`, `deleteLocal`,
`renameFile`, `listVideo`, and `deleteVideo`, and `urls` exposes only
`fileUploadurl` and `rtspUrl`; download URL helpers target cloud REST APIs
only. Public protocol references (`Nino6689/anycubic-lan` and
`stribor/anycubic_kobrax`) likewise expose no LAN download route. Strictly
read-only live probes against Kobra X `20030` / `2.0.2.2` confirmed that only
TCP ports `9883` (MQTT/TLS), `18088` (HTTP-FLV camera), and `18910` (LAN HTTP)
were open across 17 common ports; `GET /gcode_upload?s=<token>` returned
code `19004` (`Only POST method is allowed`); all candidate download, file,
timelapse, and thumbnail paths on ports `18910` and `18088` returned HTTP `404`;
candidate MQTT `file/*` download actions received only the generic empty
`/response` ACK (`code: 0`) without a `/file/report`; and `listLocal`'s
`fileKey` equals `md5(filename)` rather than a content checksum or download
handle (`file/fileDetails` exposes embedded base64 preview images when present
in a G-code file, and `file/listUdisk` / `file/listVideo` expose read-only
metadata only). Because no LAN download endpoint was identified across these
checks, stored-file download (`files download`) is deferred on stock firmware
`2.0.2.2`.

## Saved target selection

Use `kobra-lan printer list`, `printer info [name]` and `printer use <name>` for
offline inventory, inspection and default selection. For an individual command,
place `--printer <name>` or `--config <path>` before the command; they conflict.
Explicit selection overrides the saved named default. With a null default,
select --printer, use an explicit --config, or run printer use NAME first. Missing or broken selected access never chooses a
different printer. Local `gcode inspect` needs no config.
See [pairing and profile storage](pairing.md) for paths and recovery.

## Diagnose a selected connection

```sh
kobra-lan doctor
kobra-lan --printer bancada doctor
kobra-lan --config "$HOME/.config/kobra-lan/profiles/bancada/config.json" doctor
```

Doctor never provisions, repairs, uploads or controls a printer. It performs no
address scan or retry. It reports eight ordered stages: `configuration`,
`dependencies`, `http_tcp`, `mqtt_tcp`, `tls_pin`, `mqtt_auth`, `status`,
`compatibility`. Failed dependencies cause later checks to be `skipped`;
independent HTTP/MQTT TCP checks continue. HTTP failure does not block MQTT.
TCP success proves only that a port accepts connections, not protocol support.
TLS pins are compared before MQTT credentials. One authenticated session requests
only a fresh correlated `info` report. A busy/printing target can pass.
Compatibility requires the fresh MQTT report to identify `Anycubic Kobra X`,
firmware `2.0.2.2` and a valid state. As in pairing, `deviceId`, `modelId` and
`modeId` are optional in this report; every supplied identifier must match the
selected configuration. Every omitted optional identifier is named without failing:
target trust still requires the saved TLS pin and successful MQTT authentication.
Missing required model/firmware/state evidence fails with `qualification_incomplete`;
contradictory, unsupported or invalid values fail with `outside_qualification`.
Successful connection stages remain passed in both cases. No HTTP identity
fallback, additional query or trust update is performed.

Each network stage has at most 12 seconds and all network work shares a
60-second monotonic deadline. No reconnect, provisioning request, HTTP request,
trust update or state write occurs. Compatibility requires matching Kobra X
model 20030 / firmware 2.0.2.2 identity; a healthy connection does not expand
hardware qualification or authorize a physical operation.

The JSON `ok` envelope contains `result` even on failure: schema `version: 1`,
safe `target` metadata (null when unavailable), ordered `checks` and `healthy`.
Each check has `stage`, `status` (`passed`, `failed`, `skipped`), safe `code`,
`message` and nullable `next_step`. Failure adds the shared safe `error` object.
Exit 0 means all stages passed; exit 2 means selection, trust, authentication,
protocol or compatibility failure; exit 3 means local config/dependency/I/O or
network failure. Exit 3 takes precedence when independent failures mix.
Malformed/conflicting selectors fail with exit 2 before diagnosis.

Use each failed check's next step: inspect saved selection and private file modes,
install the declared runtime, check LAN mode/address/ports/firewall, or review
qualification. Never accept a changed pin, re-pair automatically or clear
operational markers in response to a diagnostic failure. Reports exclude raw
status, session tokens, passwords, certificate bodies and private keys.

## Shell completion

The installed `kobra-lan completion bash|zsh|fish` generator works offline without
configuration, shell binaries or printer queries. It completes canonical
commands, flags, fixed choices and local file operands; it never discovers
printer names or reads credential contents. Root options go before commands.
No startup file is modified automatically.

Bash (load explicitly in each session, or source the generated file from your
own startup configuration):

```sh
mkdir -p "$HOME/.local/share/bash-completion/completions"
kobra-lan completion bash > "$HOME/.local/share/bash-completion/completions/kobra-lan"
. "$HOME/.local/share/bash-completion/completions/kobra-lan"
```

Zsh (after your usual `compinit`; explicitly source in the current session):

```sh
mkdir -p "$HOME/.local/share/zsh"
kobra-lan completion zsh > "$HOME/.local/share/zsh/kobra-lan.zsh"
source "$HOME/.local/share/zsh/kobra-lan.zsh"
```

Fish loads the user completion directory automatically in subsequent sessions:

```fish
mkdir -p "$HOME/.config/fish/completions"
kobra-lan completion fish > "$HOME/.config/fish/completions/kobra-lan.fish"
source "$HOME/.config/fish/completions/kobra-lan.fish"
```

These instructions use the installed CLI from any working directory. Regenerate
scripts after upgrading to keep them aligned with the installed command tree.
