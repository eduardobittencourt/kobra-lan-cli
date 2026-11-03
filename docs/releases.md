# Releases and compatibility

The source of truth is the literal `__version__` in `kobra_lan/__init__.py`.
Python metadata and `kobra-lan --version` derive from it. A release accepts only
final `X.Y.Z` versions (for example `0.3.0`), matching `vX.Y.Z` tags and Debian
version `X.Y.Z-1`. Leading zeroes, prereleases (`0.3.0-rc.1`, `0.3.0rc1`) and
build metadata (`0.3.0+build`) fail validation. They need explicit Python/Debian
ordering rules before they can be supported. Do not use packaging-only revisions:
changed published bytes require a new application version.

## Compatibility and version preparation

The public interface includes commands, flags, JSON output, exit codes (0, 2, 3),
configuration and durable upload receipts/start attempt markers. In the experimental
0.x series, new functionality and incompatible changes increment MINOR; compatible
fixes increment PATCH. Starting with 1.0, incompatible changes increment MAJOR,
compatible features increment MINOR, and compatible fixes increment PATCH.
Preserving duplicate protection and explaining state migrations are part of this
contract. Package availability does not expand the hardware qualification in README.

For each release, the maintainer chooses the version and records compatibility,
migration and hardware limitations in `CHANGELOG.md` under `## X.Y.Z`. Update the
literal version, move the relevant Unreleased notes into that section, then run:

```sh
python3 scripts/release_version.py --tag v0.3.0  # after setting version 0.3.0
python3 -m unittest discover -s tests -v
```

The build baseline is Debian 13 with setuptools >=77 for SPDX license metadata.
Ubuntu 24.04 consumes the same Debian-built package; installation requires only
the declared system Python runtime and `python3-cryptography (>=41)`, without setuptools or other build tools. Python distributions declare `cryptography>=41`; installers resolve it before the command runs. Debian 13 provides version 43 and Ubuntu 24.04 provides version 41. The package remains pure Python; its crypto dependency uses distro-supported native libraries.

Debian packages keep Markdown guides uncompressed so relative links resolve.
The upstream changelog is installed as `changelog.gz`; Debian's `copyright`
uses `License: GPL-3`, specifies version 3 only, and points to `/usr/share/common-licenses/GPL-3` for the full
license. Source and Python distributions retain the repository LICENSE file.

## Debian build validation

The binary package is built with debhelper and pybuild's pyproject plugin, without
installer-time pip, bundled Python or custom maintainer hooks. Lintian must report
no errors. The expected `initial-upload-closes-no-bugs` warning is justified: this
is a GitHub-distributed package with no Debian ITP bug or Debian archive upload.
Do not invent a Debian bug number to suppress it.

Build in a disposable Debian 13 amd64 system (these dependencies are build-only):

```sh
apt-get update
apt-get install --no-install-recommends build-essential debhelper dh-sequence-python3 \
  pybuild-plugin-pyproject python3-all python3-setuptools python3-wheel \
  python3-build python3-venv python3-cryptography lintian
python3 scripts/release_version.py --tag v0.3.0
python3 scripts/build_deb.py --output build/debian --tag v0.3.0
python3 scripts/check_deb.py build/debian/kobra-lan-cli_0.3.0-1_all.deb
lintian build/debian/kobra-lan-cli_0.3.0-1_all.deb
(cd build/debian && sha256sum --check SHA256SUMS)
python3 scripts/check_python.py build/python-acceptance
```

Replace example versions with the current source version. Output includes
`kobra-lan-cli_X.Y.Z-1_all.deb`, `SHA256SUMS`, staging sources and Debian build
records. Keep outputs under ignored `build/` or a task directory under
`~/research/kobra-lan-cli/`. Use a fresh output directory for each build;
the helper refuses to reuse staging trees. It fixes SOURCE_DATE_EPOCH to the
source commit timestamp (or an explicit override in an exported source tree).
Byte-for-byte reproducibility across build environments is not yet promised.

The supported acceptance targets are Debian 13 and Ubuntu 24.04 on amd64.
`Architecture: all` describes the pure Python package; it does not claim physical
testing on other CPUs or wider printer support. Both systems consume the same
Debian-built artifact. Acceptance provisions Python, python3-cryptography with its distro dependency closure, passwd and util-linux,
then runs `scripts/accept_deb.py PACKAGE VERSION` as root in a disposable system
with networking disabled and `/run/kobra-package-acceptance` containing
`disposable`. It intentionally installs/upgrades/removes/purges the package and
creates a synthetic non-root user's fixtures. Never run it on the host system.
The CI workflow provides the complete disposable-container invocation.
Installed checks include pairing help, refusal of existing config before network
access, and synthetic onboarding followed by ordinary status. No real printer is
contacted, and installation hooks never provision a printer.

Development and the CI unit job use the committed `uv.lock`:

```sh
uv sync --locked
uv run --locked python -m unittest discover -s tests -v
```

Update the lockfile deliberately with `uv lock` when changing runtime dependencies,
then regenerate the pip manifest used for package validation:

```sh
uv export --locked --no-dev --no-emit-project --no-header --no-annotate \
  --format requirements-txt --output-file requirements-runtime.txt > /dev/null
```

CI checks that this export matches the committed `requirements-runtime.txt`.
This development lock records exact versions and hashes. Distribution metadata
continues to allow `cryptography>=41` for distro and third-party installers;
their dependency versions need not match the development lock. The Debian build
and acceptance paths explicitly verify the supported distro runtime closure.

The offline unit suite requires the runtime dependency and pip-enabled virtual
environments (`python3-cryptography` and `python3-venv` for distro Python, or
`pip install 'cryptography>=41'` in an environment with venv/ensurepip support).
The runtime-install tests create fresh virtual environments and invoke pip offline.
`scripts/check_python.py` builds sdist and wheel, checks
exact dependency metadata and content allowlists, and prepares the runtime closure
from `requirements-runtime.txt`. Both download and installation require hashes
and `--only-binary=:all:`; source dependency builds are refused. It then installs
the application wheel with `--no-deps --no-index` before outside-checkout probes.
For offline dependency preparation, supply the complete locked wheel closure:

```sh
python3 -m venv build/runtime-download
build/runtime-download/bin/python -m pip download --require-hashes --only-binary=:all: \
  --requirement requirements-runtime.txt --dest build/runtime-wheels
python3 scripts/check_python.py build/python-acceptance --wheelhouse build/runtime-wheels
```

The build job uses this explicit wheelhouse flow. If `--wheelhouse` is omitted,
the helper downloads the same locked, hash-verified wheels during preparation.
Installation always uses `--no-index`, requires pinned hashes and rejects sdists,
including with a caller-supplied wheelhouse. No runtime dependency fetches are
performed by `kobra-lan` itself.

## Download, install and deliberately switch commands

Download the package and `SHA256SUMS` from the same GitHub version release into
an empty directory, verify, and install the local package:

```sh
sha256sum --check SHA256SUMS
sudo apt install ./kobra-lan-cli_0.3.0-1_all.deb
/usr/bin/kobra-lan --version
/usr/bin/kobra-lan --help
command -v kobra-lan
type -a kobra-lan
```

Checksums identify bytes and detect transfer corruption; they are not an
independent package signature. This is a downloadable package channel, with no
hosted/signed apt feed or automatic update discovery. To upgrade, download and
verify a newer version and run `sudo apt install ./kobra-lan-cli_NEW-1_all.deb`.
Removal uses `sudo apt remove kobra-lan-cli`; `sudo apt purge kobra-lan-cli`
also removes package metadata. Both preserve configuration, keys, upload receipts
and start attempt markers under user home directories.

The existing `~/.local/bin/kobra-lan` symlink can precede `/usr/bin` in PATH.
Installing a package does not replace that launcher. Use `/usr/bin/kobra-lan`
explicitly while validating. When deliberately migrating, inspect `type -a` and
the link target, save the known launcher/link target, then rename only that
symlink (for example to `kobra-lan.checkout`) and refresh shell command lookup
(`hash -r` in bash). Verify `command -v` and the version again. Do not remove or
reset private configuration or state to switch executables.

Rollback requires reviewing the previous version's state-format compatibility.
Restore the saved checkout launcher, or install a previously verified package
with `sudo apt install --allow-downgrades ./kobra-lan-cli_OLD-1_all.deb` after that
review. Never delete durable markers to make an older version run. An authorized migration must also update the installation documentation and check
command consumers. Package validation does not authorize a live migration.

## Tag-driven release and recovery

1. Prepare the literal version and its `## X.Y.Z` changelog section, including
   compatibility/migration notes. Merge reviewed code and require the package
   checks to pass. Creating a release tag is a separate authorized action.
2. On the exact reviewed commit, run `python3 scripts/release_version.py --tag
   vX.Y.Z`, then `git tag -a vX.Y.Z -m 'Release X.Y.Z'` and
   `git push origin vX.Y.Z`. The workflow listens to all `v*` tags so unsupported
   formats fail visibly; final tags must exactly match the source version.
3. The release workflow checks out the event commit, reruns offline tests and
   source/wheel/Debian archive checks, and builds one candidate .deb. Both
   disposable distribution jobs install that identical candidate with networking
   disabled and emit digest-bound acceptance reports. Failed/missing acceptance
   prevents the publish job and is also rejected by the publication helper.
4. Only the final publish job has `contents: write`, through the workflow's
   `GITHUB_TOKEN`. Other jobs have `contents: read`; no personal token or follow-up
   release-event workflow is required. Actions are pinned by commit. Runs for
   the same tag serialize without cancelling an active run.
5. The publish job downloads the exact tested artifact and acceptance reports,
   verifies `SHA256SUMS`, and checks that the remote tag resolves to the tested
   commit (including annotated tags). It creates or recovers an unpublished draft
   only for that exact tag/commit. It uploads
   `kobra-lan-cli_X.Y.Z-1_all.deb` and `SHA256SUMS`, downloads both assets and
   compares their complete bytes, then publishes. Notes come only from that
   version's changelog section and identify the tag, commit and supported targets.

If validation or acceptance fails, inspect the failed job and fix the cause;
there is no new public release. A malformed tag needs a correctly prepared final
version/tag. Never move a published tag. If the source must change, select a new
version and new tag rather than rewriting released history.

If upload is interrupted or remote verification fails, the helper returns a
nonzero status and leaves a draft. Inspect the draft and workflow logs, verify
its tag and commit, then rerun **all jobs** of the same workflow to repeat every
gate. This is necessary because artifacts/reports are scoped to the run attempt.
An unpublished matching draft may have incomplete assets deleted and replaced.
A draft pointing at another commit is rejected and requires manual investigation.
No public release or public asset is deleted/replaced by the helper.

If publication succeeded but the response was lost, a retry fails on the already
published version without mutation. Inspect/download the public assets and check
the manifest; do not force an overwrite or retag. Any changed public artifact
requires a new application version. GitHub-hosted CI execution and the actual
release API remain separate from the local fixture-based verification; this
setup does not publish a real release.

References: [setuptools pyproject configuration](https://setuptools.pypa.io/en/latest/userguide/pyproject_config.html),
[Debian Python packaging](https://www.debian.org/doc/manuals/debmake-doc/ch14.en.html#python),
[GitHub release API](https://docs.github.com/en/rest/releases/releases).
