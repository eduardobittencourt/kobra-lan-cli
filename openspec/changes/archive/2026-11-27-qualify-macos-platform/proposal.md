# Proposal

## Why

Kobra LAN CLI is currently offline-validated and CI-gated only on Linux `amd64` (Debian 13 and Ubuntu 24.04), leaving macOS (`arm64`) unqualified in `docs/compatibility.md` and blocking Milestone 4 cross-platform expansion and future Homebrew packaging. Qualifying macOS now uncovers and fixes concrete POSIX/BSD portability gaps (macOS `/var`/`/tmp` root system symlinks under strict `O_NOFOLLOW` traversal, macOS stock Bash 3.2 completion compatibility, and the Linux-hardcoded source launcher), validates native `zsh` completions in CI, and enables live read-only Kobra X LAN verification from macOS without weakening any Linux or Debian guarantees.

## What Changes

- **macOS-safe private directory traversal**: Preserve strict `O_NOFOLLOW` rejection of user and managed symlinks in `kobra_lan/profiles.py` and `kobra_lan/pairing.py` while safely canonicalizing only verified OS-owned macOS root system aliases (`/var` → `/private/var`, `/tmp` → `/private/tmp`) on `darwin` so `$TMPDIR` (`/var/folders/...`) and `/tmp` paths work without relaxing symlink-race protections.
- **Bash 3.2 compatibility and native `zsh` completion verification**: Update `kobra_lan/completions.py` so generated `bash` completions work on macOS stock Bash 3.2 (`mapfile`-free array population and guarded `compopt`) as well as Bash 4+, keep `tests/test_completions.py` exercising both `bash` and native `zsh` accurately on macOS and Linux, and keep `fish` completion unchanged.
- **Portable source launcher (`./kobra-lan`)**: Make the repository source launcher resolve symlinks portably across POSIX `/bin/sh` (Linux and macOS) and select `python3` from `PATH` (falling back to `/usr/bin/python3`) instead of hardcoding Linux `/usr/bin/python3` (which is Python 3.9 on macOS), without changing the Debian-packaged `/usr/bin/kobra-lan` launcher.
- **macOS CI acceptance gate**: Add a dedicated `macos-latest` (`arm64`) job to `.github/workflows/package-checks.yml` running the locked offline `unittest` suite (including native `zsh` completion verification), `sh -n kobra-lan`, and `scripts/check_python.py` outside-checkout wheel/sdist build and installation probes against `requirements-runtime.txt`.
- **Live read-only macOS LAN verification and documentation updates**: Verify strictly read-only CLI workflows (`printer discover`, `doctor`, `status`, `slots list`, `camera status`) against the qualified Kobra X (`20030` / firmware `2.0.2.2`) from macOS Apple Silicon (using a dedicated temporary/isolated test setup without disturbing existing Linux profiles or printer state), and update `docs/compatibility.md`, `docs/releases.md`, `docs/development.md`, `README.md`, `ROADMAP.md`, and `CHANGELOG.md` to record macOS (`arm64`) offline CI and live read-only hardware evidence while keeping mutating macOS runs, Windows, Linux `arm64`, PyPI, and Homebrew explicitly unqualified/future.

## Capabilities

### New Capabilities

<!-- None: all behavioral updates extend existing capabilities cleanly. -->

### Modified Capabilities

- `printer-profiles`: Clarify that private crash-safe directory traversal rejects all user/managed symlinks and symlink races while permitting verified OS-owned macOS root system aliases (`/var` → `/private/var`, `/tmp` → `/private/tmp`) on `darwin`.
- `cli-interface`: Require generated `bash` completions to remain compatible with macOS stock Bash 3.2 as well as Bash 4+, and require native `zsh` completion runtime validation on macOS CI.
- `release-distribution`: Add macOS (`arm64`, Python `>=3.11` source/wheel/venv installation) as an offline-validated CI acceptance target alongside Debian 13 and Ubuntu 24.04 (`amd64`), with a portable source checkout launcher and documented macOS installation guidance, without adding Homebrew or PyPI publication yet.
- `hardware-qualification`: Update the maintained compatibility matrix (`docs/compatibility.md`) to distinguish macOS (`arm64`) implemented, offline-validated (CI + native `zsh`), and live read-only LAN hardware-observed status from untested mutating operations and unqualified platforms/channels.

## Impact

- **Runtime code**: `kobra_lan/profiles.py`, `kobra_lan/pairing.py`, `kobra_lan/completions.py`, and root launcher `kobra-lan`. No wire-protocol, MQTT, HTTP upload header, JSON schema, exit-code, or qualification-predicate changes.
- **Tests & scripts**: `tests/test_profiles.py`, `tests/test_pairing.py`, `tests/test_completions.py`, and `tests/test_client.py` (macOS path/symlink/launcher/Bash-3.2 & `zsh` coverage); `scripts/check_python.py` / `scripts/probe_completions.py` verified on macOS without weakening Linux/Debian allowlists.
- **CI workflows**: `.github/workflows/package-checks.yml` adds a macOS `arm64` offline unit + Python archive/install acceptance job (leaving existing Debian 13 / Ubuntu 24.04 `.deb` build/acceptance and Sonar gates intact).
- **Documentation**: `docs/compatibility.md`, `docs/releases.md`, `docs/development.md`, `README.md`, `ROADMAP.md`, and `CHANGELOG.md`.
- **Non-goals**: No Homebrew formula, no PyPI publishing workflow, no Windows or Linux `arm64` qualification, no changes to Debian `.deb` packaging (`Architecture: all`, `/usr/bin/python3`), and no live print-start/upload/delete/control hardware runs from macOS in this change.
