# Kobra LAN CLI

A direct Anycubic Kobra X LAN client with readable text and opt-in JSON for automation. Slicing is handled separately by the official Anycubic Slicer Next. This client preserves G-code bytes and does not require KX-Bridge, Moonraker, a desktop, or Home Assistant at runtime.

**Status:** upload and print start validated on Kobra X hardware running firmware 2.0.2.2 for one PLA High Speed print using onboard slot 1, automatic leveling on, vibration compensation off, and flow calibration off. Starting the stored file with `url=""` worked. Other combinations remain unqualified; the start feature is still experimental. Physical print quality and completion have not yet been assessed.

Product direction, proposed command areas, independent onboarding, and installation/distribution plans are tracked in the [product roadmap](ROADMAP.md). The [release guide](docs/releases.md) describes the implemented package tooling; a public package release and the roadmap's other proposed channels remain pending.

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
# Local inspection needs no configuration:
./kobra-lan gcode inspect /path/to/model.gcode --name agent-model.gcode
# Read-only operations on the selected printer:
./kobra-lan status
./kobra-lan files list
./kobra-lan files info agent-model.gcode
# Upload only when authorized, using the inspected SHA-256:
./kobra-lan files upload /path/to/model.gcode --name agent-model.gcode --sha256 FILE_HASH --execute
# Review a read-only experimental start plan:
./kobra-lan print plan /path/to/model.gcode --name agent-model.gcode --slot 1 \
  --auto-leveling on --vibration-compensation off --flow-calibration off
# Physical start only when separately authorized, using the reviewed plan hash:
./kobra-lan print start /path/to/model.gcode --name agent-model.gcode --slot 1 \
  --auto-leveling on --vibration-compensation off --flow-calibration off \
  --plan-sha256 PLAN_HASH --execute
./kobra-lan --json --printer bench status
./kobra-lan completion fish
```

The canonical tree is `printer pair|list|info|use|remove`, `doctor`, `status`,
`files list|info|upload`, `gcode inspect`, `print plan|start`, and
`completion bash|zsh|fish`. Group `--help` describes observation and execution.
Upload requires both execution controls and never starts a print. Inspection is
local; planning queries the printer without changing it. Text is the default;
root `--json` selects the versioned machine contract. Exit codes are 0 (success),
2 (arguments/protocol/validation), and 3 (configuration/network failure).
Global `--config`, `--printer`, `--state-dir` and `--json` precede the command.
These examples describe the workflow; automated checks use synthetic fixtures.

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
