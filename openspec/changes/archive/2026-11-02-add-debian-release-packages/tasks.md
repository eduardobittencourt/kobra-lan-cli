# Tasks

## 1. Version identity and installable Python distribution

- [x] 1.1 Configure the Python build backend, explicit package selection, metadata, and dynamic version from kobra_lan.__version__; build sdist and wheel and verify metadata agrees with installed `kobra-lan --version` outside the checkout.
- [x] 1.2 Add shared release-version validation for final X.Y.Z and matching vX.Y.Z tags; verify acceptance of a valid release and rejection of mismatches, leading zeroes, prerelease suffixes, and build metadata before publication.
- [x] 1.3 Document the 0.x and 1.x compatibility policy and version preparation in a release guide, add CHANGELOG.md, and verify examples agree with the validator and the CLI/JSON/state compatibility boundary.
- [x] 1.4 Add archive-content and clean Python-install checks using a wheel built from the sdist; verify only intended application/documentation files ship and the console command works without PYTHONPATH or the development launcher.

## 2. Debian package and lifecycle acceptance

- [x] 2.1 Add native debian/ metadata and the shared local/CI build helper with clean allowlisted staging and derived changelog; verify dpkg-deb reports package kobra-lan-cli, version X.Y.Z-1, Architecture all, Python >=3.11 dependency, and the expected /usr/bin entry point.
- [x] 2.2 Add package file-list checks and Lintian validation; verify credentials, jobs, receipts, research/build artifacts, planning files, and unintended packages are absent, resolve errors, and record justified warnings.
- [x] 2.3 Add disposable Debian 13 and Ubuntu 24.04 acceptance runs consuming the same .deb; verify apt installation, help/version, valid synthetic G-code inspection, and exit-3 JSON on missing config from outside the checkout with PYTHONPATH unset and no printer access.
- [x] 2.4 Add an older fixture package and non-root synthetic private-data fixtures; verify upgrade, removal, and purge preserve configuration, receipt/attempt bytes, and permissions on both supported distributions without contacting a printer.
- [x] 2.5 Document build dependencies, local artifact output, supported targets, checksum verification, apt local-package install/upgrade/removal, PATH precedence, and deliberate migration/rollback; verify documented commands in disposable environments and keep the live devbox installation unchanged.

## 3. Continuous integration and release publication

- [x] 3.1 Integrate package builds and acceptance into pull-request CI while retaining offline unit and shell checks; verify a candidate build passes both distribution jobs and archive/metadata gates before publication work is enabled.
- [x] 3.2 Add the v* tag release workflow with exact commit checkout, version gates, all offline/package checks, per-version concurrency, and pinned Actions; verify malformed/mismatched tag fixtures fail and only the final publish job has contents: write.
- [x] 3.3 Implement transfer of the tested .deb and SHA256SUMS to publication, draft creation/recovery for the matching tag/commit, remote checksum verification, changelog-derived notes, and final publication; verify the release API sequence with fixtures without publishing a real version.
- [x] 3.4 Exercise publication failure cases with fixtures: failed acceptance, interrupted asset upload, checksum mismatch, draft retry, and already published version; verify no public version or asset is overwritten and only a fully verified draft becomes public.
- [x] 3.5 Document the tag-driven release and recovery checklist, including the unsupported prerelease formats and absent apt feed; verify the documented expected filenames, permissions, and retry behavior against the workflow and publication checks.

## 4. Integrated verification

- [x] 4.1 Run the existing offline suite and the complete source-to-package acceptance path for both targets, including lifecycle and negative release cases; verify all gates pass without printer credentials, a real release tag, or live installation migration.
- [x] 4.2 Run strict OpenSpec validation and diff checks, inspect final scope for accidental operational changes, and record build/test evidence plus remaining limitations; verify only authorized implementation/docs/test files changed and no private data is included.

## Workflow follow-up

- After implementation review and merge, select the next release version and authorize its tag separately; publishing a release is not required to complete this setup change.
- If later migrating the active devbox installation, update its maintained tooling guide and verify all affected command consumers while preserving credentials and state.
