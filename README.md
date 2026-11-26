# Kobra LAN CLI

A direct Anycubic Kobra X LAN client with readable text and opt-in JSON for automation. Slicing is handled separately by the official Anycubic Slicer Next. This client preserves G-code bytes and does not require KX-Bridge, Moonraker, a desktop, or Home Assistant at runtime.

**Status: experimental, under active development.** The CLI and its JSON automation interface are intended for testing and feedback. Commands, output and stored-state contracts can change during 0.x; read each version's [compatibility notes](https://github.com/eduardobittencourt/kobra-lan-cli/releases) before upgrading. A downloadable package does not imply stable or broadly qualified printer support.

Upload, print start, reviewed intentional reprints (`--reprint-from`), read-only `print watch` observation persistence, offline `jobs list|info`, and guarded `print pause|resume|cancel` were observed on Kobra X hardware running firmware 2.0.2.2 for `PLA High Speed` prints with automatic leveling on, vibration compensation off, and flow calibration off: single-filament starts (`0=1|2|4`) and a 4-color contiguous 1:1 print (`0=1, 1=2, 2=3, 3=4`, exercising slot 3 as `2=3`). Starting the stored file with `url=""` worked across initial starts, operator-confirmed reprints, and the 4-color run. Single-filament slot 3, cross-remapped/sparse/shared/subset multicolor, non-zero single paint indices, other materials/preparation settings, and external ACE units remain unqualified.

See the [compatibility matrix](docs/compatibility.md) for supported models, firmwares, materials, preparation flags and host platforms, the [roadmap](ROADMAP.md) for implemented capabilities and future work, and the [release guide](docs/releases.md) for supported installation targets, package checks and recovery.

## Experimental packages

Versioned Debian packages are distributed through [GitHub Releases](https://github.com/eduardobittencourt/kobra-lan-cli/releases). Select a published version with both its `.deb` and `SHA256SUMS` attached; CI artifacts and merged source alone do not establish package availability. Debian 13 and Ubuntu 24.04 on amd64 are the acceptance targets. There is no hosted apt repository or automatic update channel.

Download both assets from the same release into an empty directory, then verify and install. The example uses 0.6.0; replace the `.deb` filename with the asset from your selected release:

```sh
sha256sum --check SHA256SUMS
sudo apt install ./kobra-lan-cli_0.6.0-1_all.deb
/usr/bin/kobra-lan --version
/usr/bin/kobra-lan --help
```

The package installs `/usr/bin/kobra-lan`. If a checkout launcher already exists in your PATH, inspect `type -a kobra-lan` and follow the [deliberate switching instructions](docs/releases.md#download-install-and-deliberately-switch-commands). Installation preserves private configuration and operational state and does not contact a printer. PyPI, mise and Homebrew distribution remain future work.

## Running the client

For independent package builds, supported Debian/Ubuntu targets, compatibility
policy and installation/release procedures, see the [release guide](docs/releases.md).

Python >=3.11 with `cryptography>=41`; no daemon. Python package installers resolve the declared dependency. For the source launcher on Debian 13 / Ubuntu 24.04, install `python3-cryptography` with apt first; the launcher uses `/usr/bin/python3`.

```sh
git clone https://github.com/eduardobittencourt/kobra-lan-cli.git
cd kobra-lan-cli
./kobra-lan --help
# Set up a named profile, with explicit initial trust on a terminal:
./kobra-lan printer pair --name bench --host 192.0.2.10 --default
# Local inspection needs no configuration (hashes, metadata, and filament/color info):
./kobra-lan gcode inspect /path/to/model.gcode --name agent-model.gcode
# Read-only operations on the selected printer:
./kobra-lan status
./kobra-lan slots list
./kobra-lan camera status
./kobra-lan files list
./kobra-lan files info agent-model.gcode
# Capture a single camera frame (requires optional external ffmpeg) or pipe raw FLV:
./kobra-lan camera snapshot --output /tmp/bed.jpg
./kobra-lan camera pipe --max-bytes 65536 > /tmp/sample.flv
# Upload only when authorized, using the inspected SHA-256:
./kobra-lan files upload /path/to/model.gcode --name agent-model.gcode --sha256 FILE_HASH --execute
# Review a read-only experimental start plan:
./kobra-lan print plan /path/to/model.gcode --name agent-model.gcode --slot-map 0=1 \
  --auto-leveling on --vibration-compensation off --flow-calibration off
# Physical start only when separately authorized, using the reviewed plan hash:
./kobra-lan print start /path/to/model.gcode --name agent-model.gcode --slot-map 0=1 \
  --auto-leveling on --vibration-compensation off --flow-calibration off \
  --plan-sha256 PLAN_HASH --execute
# Observe a job already active on the selected printer:
./kobra-lan --printer bench print watch --timeout 3600
# Experimental guarded lifecycle controls (explicit --execute, optional --filename guard):
./kobra-lan --printer bench print pause --execute --filename agent-model.gcode
./kobra-lan --printer bench print resume --execute --filename agent-model.gcode
./kobra-lan --printer bench print cancel --execute --filename agent-model.gcode
# Inspect local job history offline (start receipts/markers and saved watch observations):
./kobra-lan --printer bench jobs list --kind all --limit 20
./kobra-lan --printer bench jobs info RECORD_ID
# Delete a stored file once the printer is idle:
./kobra-lan --printer bench files delete old-model.gcode --execute
./kobra-lan --json --printer bench status
./kobra-lan completion fish
```

To deliberately reprint a stored file, find the latest eligible local `attempt_id`
with `print plan` or `jobs list`, then review and explicitly execute a new plan
with `--reprint-from PREVIOUS_ATTEMPT_ID` on both commands. See the
[reprint workflow](docs/usage.md#deliberately-reprint-a-stored-file) for eligibility and safety checks.

The canonical tree is `printer pair|list|info|use|remove`, `doctor`, `status`,
`slots list`, `camera status|snapshot|pipe`, `files list|info|upload|delete`,
`gcode inspect`, `print plan|start|watch|pause|resume|cancel`, `jobs list|info`,
and `completion bash|zsh|fish`. Group `--help` describes read-only inventory,
camera inspection/capture, local history inspection, observation, planning and
execution controls.
`slots list` inspects the qualified Kobra X onboard four-slot filament box
(slots `1..4`, idle or printing) over one pinned MQTT session without writing
local state; `gcode inspect` reports parsed `paint_info` filaments/colors,
`T<n>` tool indices, optional weights, `multicolor`, and
`single_filament_start_compatible` offline.

For multicolor prints, use `gcode inspect` to get the file hash and paint
indices, then `slots list` to find loaded, material-compatible slots. After
`files upload`, use one `--slot-map PAINT_INDEX=SLOT` per declared index
on both `print plan` and `print start`. For example, `--slot-map 0=1
--slot-map 2=4` maps two indices to onboard slots 1 and 4. Only the observed
4-color contiguous 1:1 `PLA High Speed` combination (`0=1, 1=2, 2=3, 3=4`,
`auto-leveling on`, vibration/flow off) reports `hardware_start_validated: true`
among multicolor starts; other multicolor mappings and single-filament
non-zero-index starts report `hardware_start_validated: false`.
External ACE units remain outside the supported topology.
See the [multicolor workflow](docs/usage.md#plan-and-start-a-multicolor-print).

This 0.x change replaces `--slot` with `--slot-map`. Read `slot_mapping`
in place of `selected_slot` on `print plan`, `print start` and `jobs info`,
and read `material_type` per mapping entry on `jobs info`.

Upload requires both execution controls and never starts a print. Inspection and
job history are local and read-only; planning queries the printer without changing
it. Text is the default; root `--json` selects the versioned machine contract.
Exit codes are 0 (success, or `camera pipe` downstream pipe closure), 2
(arguments/protocol/validation), 3 (configuration/dependency/network failure),
and 130 (interrupted print observation, `camera pipe`, lifecycle control, or
stored-file deletion after publish).
Global `--config`, `--printer`, `--state-dir` and `--json` precede the command.
These examples describe the workflow; automated checks use synthetic fixtures.

`camera status` performs strictly read-only inspection over pinned MQTT (`info`
and `peripherie`) without opening port `18088` or exposing stream URLs or
tokens. `camera snapshot --output PATH` captures one JPEG or PNG frame by
piping validated local HTTP-FLV bytes via `stdin` into an optional external
`ffmpeg` binary (never passing stream URLs in process arguments) and writes the
file atomically; `camera pipe` streams raw validated FLV bytes directly to
`stdout` with zero external video dependencies and rejects global `--json` with
exit 2 before target lookup. Both capture commands attempt a direct read-only
stream read first and fall back to one MQTT `video/startCapture` + best-effort
`video/stopCapture` cleanup pair only when needed (pass `--no-start-capture` to
disable fallback). Camera results carry `experimental: true` and
`hardware_camera_validated: true` on qualified Kobra X model 20030 / firmware
2.0.2.2. See [camera inspection and capture](docs/usage.md#inspect-and-capture-camera-video).

`files delete <name> --execute` removes one root-level file from an idle
Kobra X with no active job. It preserves local receipts, attempt markers, and
watch observations. Results include `experimental: true` and
`hardware_delete_validated: false`. After an uncertain or unconfirmed result,
inspect `files list` before taking further action. The CLI never resends the
delete command automatically. The 2026-11-25 investigation of stock Kobra X LAN
firmware 2.0.2.2 found no stored-file download endpoint, so `files download`
remains unsupported. See
[stored-file deletion](docs/usage.md#delete-a-stored-file) and
[validation evidence](docs/usage.md#validation-evidence).

`print pause`, `print resume`, and `print cancel` are experimental single-shot
lifecycle controls (`experimental: true`, `hardware_control_validated: true` on
qualified Kobra X model 20030 / firmware 2.0.2.2) requiring `--execute`, fresh
qualification, and strict state preconditions, with an optional `--filename`
active-job guard. They hold the per-device lease under `--state-dir` without
modifying existing profiles, receipts, markers, or watch observations, and
never replay uncertain commands automatically. See
[lifecycle controls](docs/usage.md#pause-resume-and-cancel-an-active-print).

`print watch` uses read-only telemetry on Kobra X model 20030 / firmware
2.0.2.2. It defaults to 86400 seconds, saves a sanitized local observation under
`--state-dir` once an active job is observed, and returns `unknown` when telemetry
cannot establish a job's outcome. `jobs list` and `jobs info` inspect local
CLI start receipts/markers and saved watch observations without contacting the
printer; unwatched prints started by other clients are absent, watched jobs are
labeled unattributed, and incomplete or unreadable records remain visible. See
[watch outcomes](docs/usage.md#watch-an-active-print) and
[local job history](docs/usage.md#inspect-local-job-history).

## Setup and safe operation

Pairing and status access require private configuration. Read [LAN onboarding and initial trust](docs/pairing.md) before connecting: initial HTTP provisioning is unauthenticated and exposes credentials on the network. Provision only on a trusted network and establish the TLS fingerprint explicitly.

Every new pairing requires `--name`; unnamed access and automatic root-config
fallback are unsupported. A fresh inventory is empty with a null default.
Named access supports offline `printer list`, `printer info [name]` and `printer use <name>`. Use `--printer <name>` for one command, `printer pair --name <name> --host <IPv4> [--default]` for new managed access, and confirmed `printer remove <name>` for local deletion. `doctor` performs bounded read-only checks without provisioning or repair. See [profile selection and recovery](docs/pairing.md#select-and-inspect-saved-printers) and [diagnostics](docs/usage.md#diagnose-a-selected-connection).

Read [operation and protocol guarantees](docs/usage.md) before uploading or starting a print. Print start is experimental, requires an explicitly reviewed plan and authorization for the physical action, and never repeats automatically. Preserve private credentials, upload receipts and durable attempt markers.

## Documentation and contribution

- [Documentation map](docs/README.md): pairing, operation, protocol, development and releases.
- [Contributing](CONTRIBUTING.md): reproducible environment and offline checks.
- [Security policy](SECURITY.md): private vulnerability reporting.
- [Code of conduct](CODE_OF_CONDUCT.md) and [repository maintenance](docs/maintenance.md).

## Support

If this project has been useful to you, consider
[sponsoring my open-source work](https://github.com/sponsors/eduardobittencourt).
Your support helps me keep building and maintaining these projects.

## License and references

GPL-3.0-only. Independent implementation based on protocol references from [KX-Bridge](https://gitea.it-drui.de/viewit/KX-Bridge-Release), commit `f0ce700fbcc9b3aed54f1a142b4e0318bc11638e`, and the [Anycubic Kobra X Home Assistant integration](https://github.com/stribor/anycubic_kobrax), version 0.1.6. No modules from either project are imported at runtime. See [NOTICE.md](NOTICE.md) and [full license text](https://www.gnu.org/licenses/gpl-3.0.html).
