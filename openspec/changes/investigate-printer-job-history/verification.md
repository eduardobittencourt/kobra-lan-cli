# Kobra X print history investigation

## Public protocol references

The target is Kobra X model 20030 on firmware 2.0.2.2. This review used
public source snapshots and the project's existing sanitized capture.

| Source | Evidence |
| --- | --- |
| KX-Bridge, `f0ce700fbcc9b3aed54f1a142b4e0318bc11638e` | [`query_info()`](https://gitea.it-drui.de/viewit/KX-Bridge-Release/src/commit/f0ce700fbcc9b3aed54f1a142b4e0318bc11638e/kobrax_client.py#L692) publishes MQTT `info/query`. [The printer-files handler](https://gitea.it-drui.de/viewit/KX-Bridge-Release/src/commit/f0ce700fbcc9b3aed54f1a142b4e0318bc11638e/bridge_endpoints.py#L122) reads storage entries via `file/listLocal`. [The history handler](https://gitea.it-drui.de/viewit/KX-Bridge-Release/src/commit/f0ce700fbcc9b3aed54f1a142b4e0318bc11638e/bridge_endpoints.py#L540) pages the bridge's own SQLite job store with `limit` and `offset`. [The MQTT consumer](https://gitea.it-drui.de/viewit/KX-Bridge-Release/src/commit/f0ce700fbcc9b3aed54f1a142b4e0318bc11638e/bridge_mqtt.py#L82) can create a job when an observed printing filename matches a file in the store and update it on observed terminal states. |
| `stribor/anycubic_kobrax` v0.1.6, `9e22712454b5c65fec6e33c92fd894a61f7f4d6f` | [The startup query table](https://github.com/stribor/anycubic_kobrax/blob/9e22712454b5c65fec6e33c92fd894a61f7f4d6f/custom_components/anycubic_kobrax/const.py#L64-L74) includes live `info/query` and `status/query`. [The event handler](https://github.com/stribor/anycubic_kobrax/blob/9e22712454b5c65fec6e33c92fd894a61f7f4d6f/custom_components/anycubic_kobrax/coordinator.py#L1474-L1553) maps observed lifecycle states to Home Assistant events and keeps the latest event. The reviewed query and event paths expose no printer execution-list operation. |
| `Nino6689/anycubic-lan`, `361aadae0cb0784ff11cafcc68226a21659346eb` | The [Kobra S1 firmware 2.7.2.7 evidence](https://github.com/Nino6689/anycubic-lan/blob/361aadae0cb0784ff11cafcc68226a21659346eb/docs/PROTOCOL.md#L525-L570) describes storage listing and a single `info.last_project` after a run. Its `task_id` was a placeholder. This is a model-specific indication that a last-job snapshot can exist on LAN. |
| `Nino6689/anycubic-cloud-api`, `f41ab06c5530a4bdc0a05dbdeaa45b60fc6ce7a8` | [The endpoint table](https://github.com/Nino6689/anycubic-cloud-api/blob/f41ab06c5530a4bdc0a05dbdeaa45b60fc6ce7a8/src/anycubic_cloud_api/const/api_endpoints.py#L71-L74) declares `GET /v2/project/printHistory` and [a private helper](https://github.com/Nino6689/anycubic-cloud-api/blob/f41ab06c5530a4bdc0a05dbdeaa45b60fc6ce7a8/src/anycubic_cloud_api/api/functions.py#L381-L383) calls it using the library's [cloud domain](https://github.com/Nino6689/anycubic-cloud-api/blob/f41ab06c5530a4bdc0a05dbdeaa45b60fc6ce7a8/src/anycubic_cloud_api/const/const.py#L3). This is static third-party source evidence. Response contents and the official app's use of the endpoint are unverified. |

The [PR 11 capture](../archive/2026-11-21-add-print-watch/verification.md#kobra-x-model-20030--firmware-2022)
provides the target-firmware baseline for current and last project telemetry.
The reviewed references leave open whether this Kobra X firmware has a
separate LAN query for past executions or returns usable `last_project`
records under other conditions.

## Android app history source

Analyzed Anycubic Android 1.1.27 (version code 1127, package
`ac.cloud.com`), obtained from [APKPure](https://apkpure.net/anycubic/ac.cloud.com/download).
The APK SHA-256 is
`7913edb205d83b2872f721c09dea21db1390fa189fcaee61b9ef3dfa6e35d087`.
`apksigner` 35.0.2 verified the signature. The certificate names Anycubic
and has SHA-256
`ec79c0378a16d863293a51959462d5d16654ae94ff10fda60ad1fb8cbb2a9736`.
The signer fingerprint was not independently verified against a
first-party copy. The [Google Play listing](https://play.google.com/store/apps/details?id=ac.cloud.com)
identifies the package. The analysis used JADX 1.5.7 without installing or
running the app. The decompiler reported errors elsewhere in the APK, and
the activity, repository, Retrofit declaration and configuration below
were readable. The findings cover this build and this screen.

| Step | Evidence in the APK |
| --- | --- |
| Open, refresh or load another page | `PrintHistoryActivity.initView` and its refresh and load-more callbacks call `R(refresh, printerId)`, which delegates to `WorkbenchViewModel`. The layout title uses `main_cloud_printing_history`. |
| Fetch history | `WorkbenchViewModel.getNewHistory` (coroutine metadata) calls `ac.cloud.workbench.main.viewmodel.a.o` with the page and printer ID. Its coroutine calls `z.a.p` via `z.b`. The Retrofit declaration in `z/a.java`, from `MainApiService.kt`, is GET `api/v2/project/printHistory` with query parameters `page` and `printer_id`. |
| Resolve the destination | `z.b` builds the Retrofit service with the environment URL from `e.b.p()`. `e.a`, `ConfigConstants` and the `release_domain_name_no_http` string resource build the release base `https://cloud-platform.anycubicloud.com/p/p/workbench/`. This connects the history screen to a configured cloud origin. Live routing and account behavior were not exercised. |
| Consume the response | `PrintHistoryResponse` declares `task_id`, `gcode_name`, `create_time`, `end_time`, `printer_name`, `machine_type`, `print_status`, `reason` and `img`. The adapter renders status 2 with the finished label and status 3 with the returned reason. A row opens details using `machine_type` and `task_id`. Refresh resets the page to 1 and the activity ends load-more on a page with fewer than ten entries. These are client behaviors observable in this build. |
| Retain visible rows | The activity constructs its adapter with an empty list. The success callback replaces rows on refresh and appends rows on pagination. It shows errors or offers retry through the error callback. The traced initialization, request and callback chain identifies in-memory rows and yielded no persistent history fallback or printer-local request. No offline app run was performed. Cache behavior outside that chain, other app builds, and any separate printer-local history view remain unverified. |

## Fresh LAN sessions

On 2026-11-21, the operator authorized read-only queries to their Kobra X
while a print was in progress. Each row used a separate MQTT connection
with the existing configuration. TLS pin verification and MQTT
authentication succeeded before each query. Each session published one
request through the existing read-only MQTT allowlist with
`require_fresh=True`. `info/query` reported firmware 2.0.2.2, and the
configured model was 20030.

| Time from first read | Request | Sanitized evidence |
| --- | --- | --- |
| 0 s and 63 s | `info/query` | Top-level state `busy`. Active project had a filename, string `task_id="-1"`, progress 44, and zero layer and time counters. The active state was excluded by the original sanitizer. The last project had an empty state, no filename and zero counters. The 63 s sample confirmed integer `task_id=0` in the last project. |
| About 63 s | `print/query` | Code 200 with a data object containing string `taskid="-1"`, no nonempty filename and no data `state`. The sample yielded no attributable outcome or execution list. |
| 68 s | `file/listLocal`, page 1, size 200, path `/` | Code 200, `list_mode=0` and 89 storage records. All had `filename`, `size`, `is_dir` and `timestamp`. None had the checked run identifiers, outcome states, reasons, or execution start/end fields. The response exposed no `current`, `pages`, `size` or `total` pagination counters at the data-object level. |
| 85 s | `info/query` | Top-level state `busy`; active state `nozzle_purging`, with the same placeholder and counters shown above. The last project again had empty state, integer `task_id=0`, no filename and zero counters. The value 44 is a preparation progress sample. |

The current print's completion fell outside this capture. The earlier
[PR 11 capture](../archive/2026-11-21-add-print-watch/verification.md)
observed idle after a run the operator later confirmed had finished
normally. In that capture the last project still had empty identity and
state and zero counters. No public reference or traced app path identified
a dedicated read-only LAN history request for this firmware, so the live
comparison covered the status, current-print and storage queries above.

## Execution identity, coverage and retention

- **Target printer.** The PR 11 run supplies one operator-confirmed outcome
  to compare against the empty last-project record. This round yielded
  the same empty last-project shape while a later observed print was
  in preparation. The active `task_id` and `print/query`'s `taskid` were
  `"-1"`. The last project had no filename or outcome and its integer ID
  was zero in the samples that classified the value explicitly. A file's
  storage timestamp provides no evidence of when it ran or how it ended.
  Separate runs of the same file, past jobs from another client, terminal
  records for cancellation or failure, retention after reboot, and
  pagination of execution history were untested. Multiple retained LAN
  executions could not be compared because these queries yielded none.
  Storage pagination beyond the first page was outside the comparison.
- **Cloud.** The Android response model provides a task ID, timestamps
  and status fields. The page and printer ID are sent to the cloud.
  No authenticated response was fetched, so coverage of LAN-only or
  other-client jobs, uniqueness across repeated runs of one file, server
  retention and server-side paging behavior remain untested.
- **Client-side data.** KX-Bridge's SQLite pagination and the Android
  list held in memory have separate provenance. The investigation did
  not measure retention in the bridge's database or test reading an
  offline history in the app.

## Recommendation

Defer a direct LAN history command for Kobra X firmware 2.0.2.2.
[The live reads](#fresh-lan-sessions) establish preparation, a
current-print reply and file storage metadata. Those reads and
[the earlier completed-run capture](../archive/2026-11-21-add-print-watch/verification.md)
yielded no identifiable completed execution, so the evidence does not
qualify even a last-job result for this target.
[The Android trace](#android-app-history-source) establishes a cloud
request path for the analyzed history screen, and
[the public protocol review](#public-protocol-references) identifies
bridge-managed history and a different model's last-job telemetry.

Revisit the decision if a supported, read-only LAN source is identified
for this model or if a fresh-session capture yields a last-project
record that can be matched to a known run. Repeated runs of the same
file and a run initiated from another client are the outstanding
comparisons for qualifying broader coverage.

## Reproducibility

Verify the downloaded build with `sha256sum` and
`apksigner verify --print-certs`. Decode it with
`jadx --no-imports -d <output-directory> anycubic.apk` and inspect the
manifest, classes and resource named in the Android evidence table.
The public revisions, APK fingerprint, code references and sanitized
LAN sample summaries above are the retained evidence. The local APK,
decompiled tree and disposable probe and research files were removed.
