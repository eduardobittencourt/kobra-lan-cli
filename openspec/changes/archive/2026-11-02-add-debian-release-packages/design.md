# Design

## Context

See proposal.md for motivation and specs/release-distribution/spec.md for the behavioral contract. The repository has no main specs, local version tags, Debian packaging, or release workflow. The existing GitHub Actions workflow runs offline unittest and shell syntax checks. Version 0.2.1 appears in both pyproject.toml and kobra_lan/__init__.py. The shell launcher resolves its checkout and injects PYTHONPATH. Runtime requires only Python >=3.11. Private configuration and duplicate-protection state live under the invoking user's home directory.

## Goals / Non-Goals

**Goals:** Establish an independently installable artifact, a single release identity, and a gated release path that can be maintained as printer features mature. Provide an identical packaging entry point locally and in CI.

**Non-Goals:** Publish a release during implementation by default; bump to 1.0; change printer behavior or receipt semantics; replace the active devbox command; promise a hosted apt feed, macOS support, or every Debian derivative. Building artifacts in CI is distinct from authorization to publish a particular new version.

## Decisions

### 1. Explicit SemVer releases with one literal version source

Keep the literal __version__ in kobra_lan/__init__.py as the source, and configure setuptools dynamic version metadata using static attribute extraction. It currently contains only a docstring and version, so builds need no application imports or printer access. Explicitly select the kobra_lan package and add README, GPL/provenance metadata, project links, and build configuration. Validate sdist and wheel contents and install a wheel built from the sdist outside the checkout; installed entry points replace the development launcher's PYTHONPATH workaround.

Maintain final X.Y.Z versions initially; reject leading zeroes, prerelease/build suffixes, and tag mismatches before publishing. Tags are vX.Y.Z and Debian versions X.Y.Z-1. The Debian revision stays 1 for this first workflow; any changed published artifact requires a new application version. This avoids introducing a second packaging-only release identity now. Explain that 0.x is experimental: incompatible changes and new functionality increment MINOR; compatible fixes increment PATCH. At 1.0+, apply the normal MAJOR compatibility boundary. Document commands, flags, JSON, exit codes, configuration, and durable state as the public interface. Version choice is a maintainer decision recorded in release notes; commit-message conventions and automatic bump bots are unnecessary here.

Alternatives: duplicating version strings risks drift; deriving versions from git would complicate source archives and clean Debian builds. Full SemVer prerelease support needs explicit PEP 440 and Debian ordering mappings and is deferred with a clear rejection rather than a silent conversion.

### 2. Native Debian packaging using the Python build backend

Add debian/ metadata using debhelper, dh-sequence-python3, pybuild-plugin-pyproject, and the setuptools build backend. The package is kobra-lan-cli, Architecture: all, with generated Python dependencies and an explicit python3 (>= 3.11) minimum. Install the entry point as /usr/bin/kobra-lan and modules in Debian's Python installation paths; include license/provenance documentation. Do not ship a private interpreter, a virtual environment, the checkout shell launcher, or installer-time pip operations. No maintainer hook needs to touch user homes or printers.

Provide a documented helper under scripts/ accepting an output directory and expected release tag. It reads the canonical version, creates a clean staging source tree from an explicit allowlist, generates Debian changelog metadata for X.Y.Z-1 without another hand-maintained version, and invokes the Debian build tooling. Source, wheel, and .deb builds share version and file-selection checks. Build outputs stay in ignored project build directories or /root/research/kobra-lan-cli/<task> during local investigation; CI uses its own workspace.

The .deb is architecture-independent because it contains pure Python and scripts, but distribution acceptance is initially Debian 13 and Ubuntu 24.04 on amd64 runners. Do not present Architecture: all as physical validation of other CPUs/printers. Both supported distributions consume the exact same built package.

Alternatives: assembling files manually with dpkg-deb reduces initial boilerplate but bypasses the standard Python/Debian dependency and installation tooling. PyPI publication is not needed to build the Debian package.

### 3. Acceptance checks run before publication

Extend CI to build and validate packaging on pull requests as well as releases. In disposable Debian 13 and Ubuntu 24.04 containers, install the exact .deb via apt, run from an unrelated directory with PYTHONPATH unset, and verify help, version, a valid synthetic local G-code inspection, and the existing exit-3 JSON diagnostic for missing configuration. Network may provision container/build dependencies, but acceptance invokes no live printer operations.

Inspect wheel/sdist/.deb file lists and metadata; forbid private data, research artifacts, .agents, openspec planning files, tests as installed modules, and accidental nested packages. Run Lintian and resolve errors; document any justified warnings. Seed synthetic configuration/receipts/attempt markers in a non-root test user's home, then upgrade from a controlled older fixture package, remove, and purge. Compare file bytes and permissions after each phase. These tests verify installed lifecycle contracts, rather than repeating application internals. Keep the existing 28 offline tests.

### 4. Tag-triggered release workflow with staged publication

Add a release workflow triggered by pushed v* tags. Validate the exact supported tag syntax and check out its exact commit; broad tag matching lets unsupported prerelease attempts fail visibly. Run unit tests and package checks directly in the release workflow or a reusable workflow; do not rely on a previous unrelated successful main-branch run. Build jobs use contents: read; only the final publication job receives contents: write. Pin third-party Actions by immutable commit as the existing workflow does. Serialize runs per version.

Pass the tested package and SHA256SUMS between jobs as workflow artifacts and verify the checksum again before upload. After all acceptance jobs pass, create or reuse only an unpublished draft release for the same tag and source commit, upload the checked artifacts, verify remote asset checksums by downloading them, then publish. Use the workflow GITHUB_TOKEN without requiring a personal token or a second release-event workflow. The release body comes from a checked-in version section in CHANGELOG.md and identifies tag, commit, distribution targets, and current experimental support.

Before writing, reject any already published release for that version; never use clobber on public assets. A failed upload leaves a draft for diagnosis and a nonzero workflow result. Retrying an unpublished draft may replace incomplete draft assets after checking tag/commit identity and re-running all gates. If publication already completed before a lost response, a rerun fails without modifying it; the maintainer checks the existing release. Never move a published tag or silently replace packages.

Alternatives: releasing on every main push creates unwanted versions; triggering builds only after a release is published exposes releases without packages during failures. A tag-triggered build followed by final publication keeps the public result coherent.

### 5. Preserve development setup and explain migration

Document sudo apt install ./kobra-lan-cli_X.Y.Z-1_all.deb, sha256sum verification, upgrades using a downloaded newer package, removal/purge, and the absence of automatic update discovery without an apt feed. Mention that a checksum identifies bytes but is not an independent package signature. Describe command -v/type -a and the current ~/.local/bin symlink precedence. Provide deliberate migration/rollback instructions without executing them or deleting user data. If a future task changes the active installation, update /root/.codex/docs/devbox-tooling/kobra-lan.md and check affected consumers then.

## Risks / Trade-offs

- Build tools vary between distributions → build in a declared container environment, document tool dependencies, and test the same .deb on both targets.
- Pure Python packaging accidentally discovers openspec or local files → explicit package selection and archive-content acceptance checks.
- Packaging success looks like printer maturity → keep hardware support limitations and 0.x status in release notes.
- Development symlink shadows /usr/bin → explicit executable selection in acceptance and documented operator migration.
- Published draft recovery has multiple steps → per-version concurrency, remote verification, and a tested failure/retry checklist; never overwrite a public version.
- Full byte-for-byte rebuild reproducibility is not yet proven → record build environment and source commit; reuse one tested artifact for publication rather than rebuilding it in the publish job.

## Migration Plan

Implement and validate on a branch without altering installed tools or generating a public tag. Check packaging in CI and locally, using an older synthetic package for upgrade tests because no historical .deb exists. After merge, a separately authorized release selects and records the next version, commits its notes, and pushes its matching tag. The workflow generates and publishes assets automatically for that tag. No existing release or old validation record is rewritten. Installation on the devbox is a separate operational action; rollback selects a previous installed artifact or restores the existing checkout launcher while preserving state and checking data-format compatibility.

## References

- Python packaging: https://packaging.python.org/en/latest/tutorials/packaging-projects/
- Debian Python CLI packaging: https://www.debian.org/doc/manuals/debmake-doc/ch14.en.html#python
- Debian version fields: https://www.debian.org/doc/debian-policy/ch-controlfields.html#version
- Semantic Versioning: https://semver.org/spec/v2.0.0.html
- GitHub workflow triggers and GITHUB_TOKEN event behavior: https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow
