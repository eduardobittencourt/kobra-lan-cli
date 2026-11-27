# release-distribution Specification

## Purpose

Provide versioned CLI releases that users can install independently of a source checkout, with verified Debian packages and preserved private operational data.

## Requirements

### Requirement: Consistent release version identity
The project SHALL derive runtime and package versions from one authoritative source, accept final SemVer X.Y.Z release versions, and require the release tag vX.Y.Z to match. The Debian version SHALL be X.Y.Z-1. Unsupported version forms SHALL fail before publication.

#### Scenario: Matching version
- **WHEN** version 0.3.0 is released from tag v0.3.0
- **THEN** the installed command reports 0.3.0 and the Debian package reports 0.3.0-1

#### Scenario: Invalid or mismatched version
- **WHEN** a release tag differs from the source version or includes a prerelease or build-metadata suffix
- **THEN** validation fails with an explanation and publishes no release assets

### Requirement: Documented compatibility policy
Release documentation SHALL define the public interface as commands, flags, JSON, exit statuses, configuration, and persistent state. During 0.x development incompatible changes SHALL increment MINOR and fixes SHALL increment PATCH; compatible features SHALL increment MINOR. Release notes SHALL disclose compatibility and migration changes without claiming stable printer support.

#### Scenario: Preparing a breaking preview release
- **WHEN** a release changes an existing command or receipt contract incompatibly during 0.x
- **THEN** its minor version increases and its release notes describe the change and migration

### Requirement: Independent Debian installation
Each supported release SHALL provide a kobra-lan-cli Architecture: all package exposing kobra-lan and declaring Python >=3.11 as a runtime dependency. The installed command SHALL run outside the checkout without a slicer, bridge, pip installation at runtime, or development files. Debian 13 and Ubuntu 24.04 SHALL pass package acceptance checks.

#### Scenario: Clean package install
- **WHEN** a user installs the release .deb through apt on a supported clean system
- **THEN** help, version, local inspection, and a missing-configuration diagnostic work without the source directory or network access to a printer

### Requirement: Preserve private data and operational safeguards
Package installation, upgrade, removal, and purge SHALL preserve user configuration and state under their existing home-directory paths. Packages SHALL exclude credentials, keys, G-code jobs, and receipts. Lifecycle hooks SHALL NOT contact printers, pair devices, initiate actions, or reset duplicate protection.

#### Scenario: Upgrade and removal
- **WHEN** the package is upgraded and later removed or purged with seeded user configuration and attempt markers
- **THEN** those user files and their permissions remain unchanged

### Requirement: Verified release assets
A supported version-tag push SHALL trigger offline tests, package construction, and acceptance checks before publication. A successful run SHALL publish a GitHub release for the exact tagged commit containing kobra-lan-cli_X.Y.Z-1_all.deb and SHA256SUMS. A failed check SHALL prevent publication of a new public release.

#### Scenario: Successful tagged release
- **WHEN** all version, offline, archive-content, installation, and lifecycle checks pass for v0.3.0
- **THEN** the release contains the checked package, its matching checksum, and release notes identifying the source tag and supported systems

#### Scenario: Acceptance failure
- **WHEN** either supported distribution fails package acceptance
- **THEN** the workflow reports failure and does not publish the new release

### Requirement: Safe release recovery
Published version contents SHALL NOT be overwritten by reruns. Release publication SHALL detect an already published version and fail without mutation. Failed runs with unpublished staging assets SHALL have a documented retry procedure. Local build and CI SHALL use the same packaging entry point.

#### Scenario: Rerun after publication
- **WHEN** a workflow is rerun for an already published version
- **THEN** it leaves the release and assets unchanged and explains that changed contents require a new version

### Requirement: Installation and release instructions
Documentation SHALL explain version selection, tag creation, local builds, release recovery, checksum verification, `.deb` install/upgrade/removal, macOS `arm64` Python/wheel/venv installation, and development-symlink PATH precedence. It SHALL distinguish downloadable `.deb` assets, local macOS Python installs, and future channels (PyPI, Homebrew, hosted apt), keeping live setup migration separate.

#### Scenario: Existing checkout installation
- **WHEN** an operator follows package installation instructions with a user-local kobra-lan symlink already present
- **THEN** the instructions explain how to identify the selected executable and deliberately switch installations without deleting credentials or markers

#### Scenario: macOS source or wheel installation guidance
- **WHEN** a macOS user consults the installation documentation
- **THEN** the documentation provides concrete Python `>=3.11` venv/wheel/source setup steps, notes optional `ffmpeg` for `camera snapshot`, and states that Homebrew and PyPI channels are not yet published

### Requirement: Qualified macOS Python installation and CI acceptance
The project SHALL qualify macOS (`arm64`) for Python `>=3.11` source and wheel/venv installs without altering Debian `.deb` contracts or claiming PyPI/Homebrew availability. macOS CI SHALL run locked offline unit tests, launcher syntax checks, native `zsh` completion checks, and outside-checkout archive/wheel acceptance. `./kobra-lan` SHALL resolve symlinks portably and use `python3` from `PATH` (fallback `/usr/bin/python3`).

#### Scenario: macOS CI offline unit and wheel installation acceptance
- **WHEN** the package-checks workflow runs on macOS (`arm64`)
- **THEN** the locked offline unit suite (including native `zsh` completion verification), `sh -n kobra-lan`, and outside-checkout sdist/wheel build and runtime-locked installation probes pass with zero network printer access

#### Scenario: Portable source checkout launcher on Linux and macOS
- **WHEN** `./kobra-lan` is invoked directly or through a symlink on macOS or Linux with Python `>=3.11` on `PATH`
- **THEN** it resolves the repository directory without GNU-only flags and executes `kobra_lan.cli` using the resolved `python3` interpreter while Debian's packaged `/usr/bin/kobra-lan` continues to target `/usr/bin/python3`
