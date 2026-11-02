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
Documentation SHALL explain version selection, tag creation, local builds, release failures, checksum verification, apt installation of a downloaded .deb, upgrade/removal, supported systems, and PATH precedence of the current development symlink. It SHALL distinguish downloadable packages from an apt repository and keep live setup migration separate.

#### Scenario: Existing checkout installation
- **WHEN** an operator follows package installation instructions with a user-local kobra-lan symlink already present
- **THEN** the instructions explain how to identify the selected executable and deliberately switch installations without deleting credentials or markers
