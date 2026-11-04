# Documentation

Start with the [project overview](../README.md) for experimental status and qualified hardware.

| Purpose | Guide |
| --- | --- |
| Pair a LAN-enabled printer; select/remove profiles; establish trust; recover private configuration | [Pairing](pairing.md) |
| Canonical commands, text/JSON contract, shell completion, reviewed upload/start, diagnostics and state guarantees | [Operation and protocol](usage.md) |
| Offline tests and validation evidence | [Development](development.md), [hardware observations](usage.md#validation-evidence) |
| Reproducible contributions and agent instructions | [Contributing](../CONTRIBUTING.md), [agents](../AGENTS.md) |
| Package builds, supported targets, installation and release gates | [Releases](releases.md) |
| Firmware protocol risks and analyzer decisions | [Pairing security review](pairing-security-review.md) |
| Review, CI services, protections and recovery | [Maintenance](maintenance.md) |
| Planned capabilities and distribution channels | [Roadmap](../ROADMAP.md) |

The CLI and JSON automation interface are experimental and under active
development. [GitHub Releases](https://github.com/eduardobittencourt/kobra-lan-cli/releases)
is the downloadable `.deb` channel; select a published version with its package
and checksums. PyPI, mise, Homebrew and a hosted apt repository remain future
work. Only Kobra X model 20030 / firmware 2.0.2.2 is initially qualified; see
each guide for the narrower limits of its operations.
