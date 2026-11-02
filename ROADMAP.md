# Product roadmap

Working direction, recorded on 2026-10-16. This is a product vision and an ordered set of milestones, not a release schedule or a promise that the printer protocol supports every proposed operation. Command names below are proposals; see [README.md](README.md) and `kobra-lan --help` for implemented behavior.

## Product boundary

Make Kobra LAN CLI an installable, well-documented LAN remote control for the Anycubic Kobra X, usable by people, scripts, and agents. A new user should be able to install it, connect their own printer, inspect its state, manage stored files, and control and follow a print without Home Assistant or another bridge.

The workflow boundary is:

```text
CAD/modeling → STL/3MF → external slicer → G-code → Kobra LAN CLI → printer
```

Modeling, mesh editing, orientation, supports, toolpaths, and slicing profiles belong to CAD and slicing tools. The CLI takes already sliced G-code and preserves its bytes. Anycubic Slicer Next need not be installed on the computer running this client; it currently must generate the input file because the client explicitly checks for Next output and the Kobra X profile. Other slicers require separate compatibility work.

Our local `anycubic-next` launcher is a separate wrapper around the official slicer. It is not part of this repository or a runtime dependency. Optional slicer integration could come later, with an explicit boundary and recorded versions/profiles; building a slicer is outside this product's scope.

## Starting point

Version 0.2.1 already implements direct MQTT/TLS and HTTP communication, status and file queries, local G-code inspection, reviewed uploads, and an experimental reviewed print start. It has 28 offline tests and one scoped hardware validation of upload and start. Completion and physical print quality have not been recorded.

Current limits include model 20030 / firmware 2.0.2.2, Next-generated G-code, one filament, and the onboard four-slot configuration. The new `printer pair --host <IPv4>` flow provisions direct access for an already LAN-enabled printer, with explicit first-use trust or an exact externally supplied fingerprint. It saves a compatible private config only after a read-only status query; existing configs are preserved. Discovery, named profiles, replacement/revocation, and initial printer/app LAN-mode setup remain outside this implementation. Runtime operation is independent of HA, Next, and cloud services.

The project has Python metadata and a console entry point in `pyproject.toml`, but the current documented installation is a source checkout with a Linux launcher. This roadmap does not assert that PyPI, Homebrew, apt, or mise installation has been published or tested.

## Proposed command areas

| Area | Candidate commands | Intended behavior |
| --- | --- | --- |
| Printers and access | `printer discover`, `printer pair`, `printer list`, `printer use`, `printer info`, `printer remove` | Find printers, provision access, manage named profiles, and select a target. |
| Stored files | `files list`, `files info`, `files upload`, `files delete` | Inspect storage and manage already sliced files with clear overwrite/deletion rules. Investigate download support separately. |
| Print jobs | `print plan`, `print start`, `print watch`, `print pause`, `print resume`, `print cancel` | Review, execute, and observe jobs; report the difference between a request accepted and a change observed. |
| Information | `status`, `filament list` | Read state, temperatures, active job, progress, and available filament slots/materials. |
| History | `jobs list`, `jobs info` | Find previous attempts, their source file/configuration, receipts, and observed outcomes. |
| Diagnostics | `doctor` | Check configuration, reachability, authentication, certificate trust, and supported capabilities; explain the next useful step. |

Prefer documented operations with validated semantics. Axis movement, homing, heating, fans, calibration, camera access, and other device controls are possible future areas only after protocol research and hardware validation. An unrestricted raw MQTT/G-code command is not required for the initial product.

## Milestone 1 — Independent onboarding

Direct onboarding is implemented for an already LAN-enabled model 20030 / firmware 2.0.2.2. Synthetic coverage exercises provisioning, trust, persistence and the installed command. Hardware acceptance results are recorded separately; support for initial printer setup and other firmware remains unqualified.

- Investigate the actual discovery and LAN provisioning mechanisms, then implement pairing in the CLI where possible. Support an explicit address when discovery cannot cross network boundaries.
- Document the exact printer-panel and Anycubic-app steps, any physical confirmation or pairing code, and whether an account/internet connection is required during setup. Do not promise cloud-free provisioning until verified independently.
- Obtain per-device identity, credentials, client certificate/key, and initial server trust through a documented process. Protect stored secrets and never silently accept a changed certificate pin.
- Add named printer profiles, an explicit `--printer` override, a persistent default, connection verification, and local removal/re-pairing. Distinguish deleting a local profile from revoking access on the device.
- Provide useful diagnostics for unsupported firmware, stale credentials, changed addresses, TLS changes, and network isolation.

Exit evidence: an owner can follow public instructions from a fresh client installation to a successful status query using their own printer, with no HA/bridge configuration dependency. Record every external requirement and unresolved limitation.

## Milestone 2 — A coherent CLI and an installable preview

- Establish the command hierarchy above, with concise top-level help, contextual `--help`, real examples, and `--version`.
- Add readable terminal output and an explicit `--json` mode with a documented schema, error codes, and exit statuses. Keep stdout suitable for automation and diagnostics/progress on stderr.
- Define noninteractive behavior and explicit execution controls. Prompts must not hang scripts or accidentally approve physical actions.
- Preserve existing automation through aliases or a documented deprecation/migration path; changing today's JSON default is a compatibility change.
- Add shell completions for bash, zsh, and fish, and documentation for installation, onboarding, common workflows, troubleshooting, and compatibility.
- Implement and validate the packaging/release path below. A preview can ship with clearly stated onboarding and hardware limits; broad availability is not a claim of broad compatibility.

Exit evidence: install a built artifact into a clean environment outside the checkout, run help/version, diagnose missing configuration, and query a configured printer. Users can discover the supported workflow from help and public docs.

## Milestone 3 — A complete everyday print cycle

- Provide one preflight view: printer, file/hash, remote metadata, material, physical slot/color, preparation settings, available estimates, and qualification limits. Material family matching is not a full filament-grade/profile check.
- Follow preparation and printing through completion, cancellation, failure, or an unknown outcome after connection loss. A publish ACK and disappearance of an active project are not sufficient evidence of successful completion.
- Separate file identity from job identity. Allow an explicit new print of an existing file while retaining durable duplicate protection for each individual attempt. Preserve and migrate existing receipts/markers; do not teach users to delete them to print again.
- Expose useful job history backed by receipts and observations, with clear handling of incomplete records and actions performed by other clients.
- Add pause/resume/cancel after validating their state transitions and recovery behavior. Reconcile uncertain results through queries rather than blind command replay.
- Validate file deletion and its interaction with active jobs, stored receipts, and future reprints. Only add download if the device provides a suitable endpoint.

Exit evidence: record an entire authorized physical print and inspect the part; exercise an intentional second print and supported lifecycle controls. Preserve the difference between telemetry-confirmed completion and operator-assessed quality.

## Milestone 4 — Broader compatibility and stable releases

- Publish a matrix of model, firmware, filament-box configuration, operation, and validation level. Keep implemented, offline-tested, and hardware-observed support distinct.
- Expand firmware/material/preparation combinations, then investigate multicolor and external ACE support. Do not infer support for other Anycubic models from similar protocol fields.
- Audit portability and test declared platforms. Linux is the first supported target; qualify macOS next. Assess Windows separately, including permissions, paths, durable reservations, and filesystem behavior.
- Add release notes, configuration/state migrations, a documented compatibility policy for commands/JSON, and an issue template for sanitized diagnostics.
- Consider other slicers and optional slicing orchestration only with qualified G-code/profile semantics. Keep the LAN client independently usable.

Stable-release evidence: reproducible independent onboarding, a supported installation path, a full validated print cycle, recovery from uncertainty, and clear compatibility and migration documentation.

## Installation and distribution strategy

Start with the existing Python implementation and one canonical Python distribution. The installed command remains `kobra-lan`; the proposed distribution name remains `kobra-lan-cli`, subject to checking registry ownership/availability. Rewriting in another language or producing a standalone executable is not a prerequisite.

| Channel | Recommendation | Additional work |
| --- | --- | --- |
| Python package / PyPI | First distribution channel; recommend `uv tool install`, with `pipx` as an alternative. | Explicit build backend/package selection, complete metadata, wheel and source distribution, clean-install verification, registry setup and release automation. |
| mise | Document consumption of the same Python package, initially without a custom plugin. | Verify the supported Python-package backend and exact commands with the supported mise version. |
| Homebrew | Add a project tap after macOS is qualified and the Python package is stable enough to maintain. | A formula with managed Python environment, installation tests, and updates per release. A tap is separate from acceptance into Homebrew core. |
| Debian/Ubuntu | Add a `.deb` if there is demand for system-managed installs. | Declare Python/runtime dependencies, test target distributions, and preserve user configuration/state during upgrades/removal. A downloadable `.deb` is separate from a signed apt repository or inclusion in distribution archives. |
| Standalone executable | Optional later convenience for users without a Python toolchain. | Bundle/build per supported OS/architecture, verify artifacts, and maintain another release/testing path. |

Target commands **after package publication and validation**, not installation instructions for today's checkout:

```sh
uv tool install kobra-lan-cli
# Alternative isolated installer:
pipx install kobra-lan-cli
# With a supported mise version and its Python-package backend prerequisites:
mise use -g pypi:kobra-lan-cli
```

`uv` and `pipx` isolate a CLI's environment from system/project Python packages. mise can consume a Python package through its Python-package backend; it does not require a separate Kobra binary or plugin for this initial route. Homebrew and apt are additional packaging/integration channels, not alternatives that require changing the application's language.

Before publishing:

1. Choose and explicitly configure the build backend and package contents. Include README, license/provenance and project links; exclude private configuration, keys, G-code, receipts, and local artifacts.
2. Build wheel and source distribution, inspect their contents, and install the artifacts in a clean environment. Exercise installed entry points outside the repository, without the launcher's `PYTHONPATH` workaround.
3. Define one version source and tagged release process. Run offline and packaging checks in CI; never make package installation or CI initiate printer actions.
4. Verify registry name availability/ownership and configure publishing, preferably with trusted publishing rather than a long-lived registry token. Publish matching release notes and checksums for attached artifacts.
5. Document install, upgrade, version pinning, uninstall, and separate removal of private user data. Use the chosen package manager for upgrades; do not add a competing self-updater initially.

The first implementation slice should combine provisioning research with a minimal build/install check. It should not start by maintaining four packaging ecosystems at once. This roadmap does not itself publish packages or change the current installation.

Distribution references consulted on 2026-10-16:

- [Python packaging tutorial](https://packaging.python.org/en/latest/tutorials/packaging-projects/) and [pyproject.toml guide](https://packaging.python.org/en/latest/guides/writing-pyproject-toml/).
- [uv tool installation and upgrades](https://docs.astral.sh/uv/guides/tools/).
- [mise Python-package backend](https://mise.jdx.dev/dev-tools/backends/pypi.html); older releases/documentation may use the `pipx:` name. Check the supported version before publishing examples.
- [Homebrew Formula Cookbook](https://docs.brew.sh/Formula-Cookbook).

## Decisions still open

- What exactly does independent pairing require from the owner, the printer, and Anycubic services?
- Which discovery, storage, and lifecycle operations does the supported firmware expose reliably?
- What is the least disruptive migration from the current flat commands and JSON output?
- Which platforms and firmware versions can we maintain and physically qualify?
- When do additional distribution channels justify their ongoing maintenance?

Keep the README focused on what works today. Update this roadmap as evidence resolves these questions; turn individual milestones into implementation issues/specifications when work begins.
