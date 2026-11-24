# Product roadmap

Current direction as of 2026-11-04. Kobra LAN CLI is experimental and under active development. This roadmap distinguishes implemented behavior from future work; it is not a release schedule or a promise that the firmware supports every proposed operation. Use [README.md](README.md), [release notes](https://github.com/eduardobittencourt/kobra-lan-cli/releases) and `kobra-lan --help` for the interface of a particular version.

## Product boundary

Make Kobra LAN CLI an installable LAN client for the Anycubic Kobra X, usable by people, scripts and agents. The intended workflow connects a user's own printer, inspects its state, manages sliced files and eventually follows a complete print cycle without Home Assistant or another bridge.

```text
CAD/modeling → STL/3MF → external slicer → G-code → Kobra LAN CLI → printer
```

Modeling, mesh editing, orientation, supports, toolpaths and slicing profiles belong to external CAD and slicing tools. The CLI preserves already sliced G-code bytes. Current input checks require Anycubic Slicer Next output declaring the Kobra X profile; the slicer need not be installed on the computer running the CLI. Other slicers require separate compatibility work.

## Current baseline — 0.5.0

| Area | Implemented behavior |
| --- | --- |
| Access | Explicit-address named pairing, [first-use trust](docs/pairing.md), pinned authentication, local profiles, explicit/default selection and confirmed local removal |
| Diagnostics | Bounded read-only `doctor`, fresh status, qualified model/firmware checks and disclosure of optional MQTT identifiers omitted by firmware |
| Stored files | `files list`, `files info`, local `gcode inspect` and reviewed execution-only `files upload` |
| Print submission | Read-only `print plan` and experimental `print start`, with explicit material/slot/preparation choices and reviewed hashes |
| Automation | English text by default, root `--json` version-1 envelope, documented error/exit contracts and offline bash/zsh/fish completion |
| Distribution | Python archive/build/install validation and a gated GitHub release workflow for a downloadable `.deb` plus checksums; Debian 13 and Ubuntu 24.04 acceptance |

Initial HTTP provisioning is unauthenticated and exposes credentials on the network. Use a trusted LAN and explicitly establish server trust; pinned MQTT authentication applies only after that trust is established. Follow the [pairing prerequisites and trust procedure](docs/pairing.md).

The source launcher and Python archives work outside a desktop, bridge, HA or cloud service. Publication state is recorded on [GitHub Releases](https://github.com/eduardobittencourt/kobra-lan-cli/releases), not inferred from a source version or merged PR. PyPI, mise, Homebrew and a hosted apt repository are not current distribution channels.

The CLI and JSON automation interface remain subject to documented changes during 0.x. Version 0.5.0 intentionally replaces flat commands and JSON-default output, requires named pairing, and removes automatic root-config fallback without migration. Existing private credentials and device-based receipt/attempt identities remain protected in normal operations; never clear markers to make a retry work.

Hardware evidence covers Kobra X model 20030 / firmware 2.0.2.2, Next-generated G-code, single-filament PLA High Speed prints using onboard slots 1, 2, and 4 (automatic leveling on, vibration compensation off, flow calibration off), reviewed intentional reprints (`--reprint-from`), read-only `print watch` observation persistence, offline `jobs list|info`, live `print pause|resume|cancel` wire transitions (`pause`, `resume`, `stop`), and live `files delete` wire confirmation (`deleteBatch` `success`/200 and follow-up `files list` removal, with byte-for-byte local state preservation verified offline), with operator-confirmed completion of both runs in a two-slot reprint cycle. Slot 3, other materials and preparation combinations, multicolor, and external ACE units remain unqualified. Package acceptance and offline tests do not expand hardware evidence.

## Milestone 1 — Independent onboarding

Implemented: named pairing by explicit IPv4 address for an already LAN-enabled qualified printer, explicit first-use trust, private atomic publication, local selection/removal and read-only diagnosis. Installed synthetic probes verify the onboarding path without contacting a printer.

Remaining work:

- Verify and document every printer-panel/app step and external prerequisite for initial LAN-mode setup. Do not infer cloud-free initial setup from cloud-independent runtime operation.
- Investigate discovery across supported network arrangements and add it only with validated protocol behavior.
- Research credential replacement/revocation and recovery while preserving existing access and device-based attempt protection.

Exit evidence: a new owner can follow public instructions from a fresh client installation to a successful status query, with external requirements and unresolved limitations recorded.

## Milestone 2 — A coherent CLI and an installable preview

Implemented: canonical command groups, contextual help, text/JSON output, noninteractive refusal, explicit execution controls, reviewed hashes, completion generators, packaging and disposable installation/upgrade/removal acceptance. The release workflow publishes one tested Debian artifact and its checksums only after both supported distributions accept it.

Ongoing work:

- Publish versioned experimental packages through the documented gates, verify public downloads and keep release notes aligned with the actual supported interface.
- Collect installation and onboarding feedback. Record missing native-shell validation instead of claiming that generated scripts prove runtime support.
- Preserve clear differences between local inspection, network observation, planning and explicitly authorized execution.

Exit evidence: a published artifact installs outside the checkout, exposes help/version/completion and supports the documented setup/diagnosis workflow. Published package assets remain the evidence of download availability.

## Milestone 3 — A complete everyday print cycle

The source CLI includes a read-only `print watch` for an already active job.
It preserves verified progress, saves a sanitized local observation under
`--state-dir` once an active job is observed, and reports uncertainty when it
cannot identify the same attempt. See
[watch outcomes and evidence](docs/usage.md#watch-an-active-print).
The source CLI also includes reviewed intentional reprints (`--reprint-from`)
with durable local per-attempt identities while preserving legacy file-keyed
markers and receipts, offline read-only `jobs list|info` over local start
receipts/markers, upload provenance, and saved watch observations with explicit
local-only coverage, unattributed other-client observations, and incomplete
record visibility, and experimental guarded lifecycle controls
(`print pause`, `print resume`, `print cancel`) requiring `--execute`, optional
`--filename` active-job matching, strict fresh state preconditions, shared
per-device locking, bounded post-ACK verification, and non-replaying uncertainty
reporting (`experimental: true`, `hardware_control_validated: true` on qualified
Kobra X model 20030 / firmware 2.0.2.2). An integrated Kobra X hardware session
on 2026-11-23 validated intentional reprints across slots 2 and 4, watch
observation persistence and `jobs list|info` chain inspection, and live
`pause`, `resume`, and `cancel` (`stop`) transitions (confirming that
`resuming`/`stopping` can exceed the 5-second post-ACK poll window and that
`last_project` remains empty after cancellation as well as completion). See
[reprint workflow](docs/usage.md#deliberately-reprint-a-stored-file),
[lifecycle controls](docs/usage.md#pause-resume-and-cancel-an-active-print),
and [local job history](docs/usage.md#inspect-local-job-history).

The source CLI includes `files delete <name> --execute` for an idle printer
with no active job. It sends one request, checks removal with bounded listing
polls, and preserves local receipts, attempt markers, and watch observations.
A live Kobra X test on 2026-11-23 confirmed the correlated ACK (`code 0`),
`deleteBatch` report (`success` / `200`), `delete_observed_removed` (exit 0),
and absence in a follow-up `files list`; byte-for-byte preservation of local
receipts and markers was verified offline with synthetic state, so results
currently keep `experimental: true` and `hardware_delete_validated: false`.
An uncertain result retains partial evidence for inspection with `files list`
and never triggers a replay. See [stored-file deletion](docs/usage.md#delete-a-stored-file)
and [validation evidence](docs/usage.md#validation-evidence).

The source CLI also includes read-only onboard four-slot filament inventory
(`slots list`) over one pinned MQTT session without requiring idle state or
writing local state, plus multicolor-aware offline `gcode inspect` reporting
validated `; paint_info =` filament/color entries, `T<n>` tool indices,
optional filament weights, `multicolor`, and `single_filament_start_compatible`
while keeping `files upload` byte-preserving. The multicolor workflow
uses `gcode inspect`, `slots list`, `files upload`, `print plan --slot-map`,
and `print start --slot-map`. The 0.x interface replaces `--slot` with repeatable
`--slot-map PAINT_INDEX=SLOT` and exposes `slot_mapping` in place of
`selected_slot` on plan, start and job details. On `jobs info`, material is
reported per entry in `slot_mapping`. Existing receipts and reprint chains are
readable in place. Multicolor and non-zero single-filament paint indices report
`hardware_start_validated: false`. See the
[multicolor workflow](docs/usage.md#plan-and-start-a-multicolor-print).

Remaining work:

- Qualify attempt identity and terminal signals if future firmware exposes them (firmware 2.0.2.2 reports `task_id: "-1"` and empty `last_project` after both normal completion and cancellation).
- Investigate stored-file download support separately (live Kobra X stored-file deletion wire report and `files list` removal were verified on 2026-11-23; `hardware_delete_validated` remains `false` because byte-for-byte local state preservation was verified offline).
- Expand hardware coverage beyond PLA High Speed on slots 1, 2, and 4 with `auto-leveling on` (slot 3, other materials, and other preparation settings).
- Qualify multicolor and non-zero paint-index starts, including sparse paint indices and shared physical slots.

External ACE units, discovery and other device controls require separate work.

## Milestone 4 — Broader compatibility and stable releases

Implemented: centralized hardware qualification rules in `kobra_lan/qualification.py` and the published [compatibility matrix](docs/compatibility.md) separating implemented, offline-validated, and hardware-observed evidence across models, firmwares, slicers, filament-box topology, slots, materials, preparation flags, operations, and host platforms.

Remaining work:

- Expand material and preparation evidence, qualify onboard multicolor starts, and investigate external ACE support. Do not infer other Anycubic model support from similar fields.
- Qualify additional platforms separately. Current package acceptance targets Linux on amd64; macOS, Windows and other architectures need their own evidence.
- Maintain release notes, compatibility policy and explicit migration decisions for commands, JSON and persisted state.
- Consider other slicers and optional orchestration while keeping the LAN client independently usable.

A stable release requires reproducible onboarding, a supported installation path, a full validated print cycle, recovery from uncertainty and maintained compatibility/migration documentation. Version 0.5.0 does not claim those stable-release guarantees.

## Distribution channels

| Channel | Current position | Remaining work |
| --- | --- | --- |
| GitHub `.deb` downloads | Gated build and acceptance on Debian 13 / Ubuntu 24.04; versioned assets include `SHA256SUMS` | Verify each public release and maintain install/upgrade/removal guidance |
| Python archives / PyPI | Canonical Python package, wheel/sdist content checks and independent installation are implemented | Verify registry ownership and configure publishing before documenting registry installation as available |
| mise | Possible consumer of a future published Python package | Validate the supported backend, prerequisites and commands before recommending installation |
| Homebrew | Future channel after macOS qualification | Maintain a formula, isolated runtime, installation checks and release updates |
| Hosted apt repository | Future channel, separate from downloadable `.deb` assets | Repository signing, index hosting and update/recovery procedures |
| Standalone executable | Optional future convenience | Per-platform builds, dependency bundling and another maintained acceptance path |

Keep one authoritative version and the existing Python implementation. Additional channels do not require rewriting the application. Installation must preserve private state and never initiate a printer action; updates should use the selected package manager rather than a competing self-updater.

## Open questions

- Which initial setup steps require Anycubic services, an account or physical confirmation?
- Which discovery, file-management and lifecycle operations does the qualified firmware expose reliably?
- How should intentional reprints be represented without weakening durable attempt protection?
- Which additional platforms and firmware versions can be maintained and physically qualified?
- When does an additional distribution channel justify its ongoing maintenance?

Keep the README focused on available behavior and qualified limits. Use implementation changes for new capabilities; update this roadmap as evidence resolves these questions.
