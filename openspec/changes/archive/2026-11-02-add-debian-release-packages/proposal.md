# Proposal

## Why

The working CLI currently runs from a checkout through a user-local symlink. Preparing tested Debian packages and a repeatable release process now will make future versions distributable without tying installations to the development directory or implying the printer feature set is stable.

## What Changes

- Establish one version source and a documented SemVer policy for the CLI, JSON output, exit codes, and persistent data, including the experimental `0.x` period.
- Build an installable Python distribution and a `kobra-lan-cli` Debian package exposing `kobra-lan`, independent of the checkout.
- Automatically validate, build, and attach an `Architecture: all` `.deb` and SHA-256 manifest to each supported version-tag GitHub release, publishing only after all checks pass.
- Exercise clean installation, upgrade, removal, and user-data preservation on Debian 13 and Ubuntu 24.04 without printer access.
- Document local package builds, version preparation, release recovery, installation, and the existing symlink's PATH precedence.
- Limit this increment to final `X.Y.Z` versions. Prerelease/build-metadata tags must fail clearly until an explicit Python/Debian version mapping is added.
- Defer apt repository hosting/signing, Homebrew, PyPI publication, automatic version selection from commits, printer onboarding, and migration of the active devbox installation.

## Capabilities

### New Capabilities

- `release-distribution`: Version identity, tested Debian artifacts, and publication of downloadable versioned releases.

### Modified Capabilities

None. The project currently has no main capability specs.

## Impact

Affected areas include `pyproject.toml`, `kobra_lan/__init__.py`, version reporting, new Debian packaging/build helpers, `.github/workflows/`, package acceptance checks, and release/install documentation. Build-only Python and Debian tooling will be introduced; runtime remains the Python standard library on Python >=3.11. No printer command, credentials, receipt format, or live environment changes are part of this proposal.
