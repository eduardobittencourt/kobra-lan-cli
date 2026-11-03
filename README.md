# Kobra LAN CLI

A direct Anycubic Kobra X LAN client with JSON output for CLI and agent automation. Slicing is handled separately by the official Anycubic Slicer Next. This client preserves G-code bytes and does not require KX-Bridge, Moonraker, a desktop, or Home Assistant at runtime.

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
./kobra-lan status
./kobra-lan files
./kobra-lan inspect /path/to/model.gcode --name agent-model.gcode
./kobra-lan upload /path/to/model.gcode --name agent-model.gcode
# Actual upload: use the same file and SHA-256 reviewed in the dry run
./kobra-lan upload /path/to/model.gcode --name agent-model.gcode --sha256 HASH --execute
./kobra-lan file agent-model.gcode
```

`upload` is a local dry run unless given `--execute` and the reviewed hash. It never starts a print. Output is JSON; exit codes are 0 (success), 2 (protocol/validation error), and 3 (configuration/network error). Global options `--config` and `--state-dir` go before the subcommand.

## Setup and safe operation

Pairing and status access require private configuration. Read [LAN onboarding and initial trust](docs/pairing.md) before connecting: initial HTTP provisioning is unauthenticated and exposes credentials on the network. Provision only on a trusted network and establish the TLS fingerprint explicitly.

Read [operation and protocol guarantees](docs/usage.md) before uploading or starting a print. Print start is experimental, requires an explicitly reviewed plan and authorization for the physical action, and never repeats automatically. Preserve private credentials, upload receipts and durable attempt markers.

## Documentation and contribution

- [Documentation map](docs/README.md): pairing, operation, protocol, development and releases.
- [Contributing](CONTRIBUTING.md): reproducible environment and offline checks.
- [Security policy](SECURITY.md): private vulnerability reporting.
- [Code of conduct](CODE_OF_CONDUCT.md) and [repository maintenance](docs/maintenance.md).

## License and references

GPL-3.0-only. Independent implementation based on protocol references from [KX-Bridge](https://gitea.it-drui.de/viewit/KX-Bridge-Release), commit `f0ce700fbcc9b3aed54f1a142b4e0318bc11638e`, and the [Anycubic Kobra X Home Assistant integration](https://github.com/stribor/anycubic_kobrax), version 0.1.6. No modules from either project are imported at runtime. See [NOTICE.md](NOTICE.md) and [LICENSE](LICENSE).
