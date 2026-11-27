# Design

## Context

See [proposal.md](proposal.md) for motivation and scope.

Today, all runtime modules in `kobra_lan/` are pure Python with one external dependency (`cryptography>=41`), and `uv.lock` / `requirements-runtime.txt` already include SHA-256 hashes for macOS (`macosx_10_15_x86_64`, `macosx_11_0_arm64`, universal2) wheels of `cryptography` and `cffi`. However, four concrete platform gaps prevent macOS from passing the offline suite, outside-checkout Python acceptance, and real-world CLI usage cleanly:

1. **Strict `O_NOFOLLOW` traversal on macOS system root aliases**: Both `kobra_lan/profiles.py:open_directory` and `kobra_lan/pairing.py:PrivateStage.__init__` walk every path component from `/` using `os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW` on `os.path.abspath(path)`. On macOS, `/var` → `private/var` and `/tmp` → `private/tmp` are root-owned OS symlinks (and Python's `tempfile.TemporaryDirectory()` defaults to `/var/folders/...`). Walking `var` or `tmp` with `O_NOFOLLOW` raises `ELOOP`.
2. **Bash 4+ builtins in generated bash completion**: `kobra_lan/completions.py` emits `mapfile -t` and unguarded `compopt -o filenames`. macOS ships GNU Bash 3.2 (`/bin/bash`), where neither `mapfile` nor `compopt` exists. Meanwhile, `zsh` is macOS's default shell and `tests/test_completions.py` skips `zsh` on Linux CI where `zsh` is absent.
3. **Linux-specific source launcher**: Root `./kobra-lan` uses `readlink -f` and hardcodes `/usr/bin/python3`. On macOS, `/usr/bin/python3` is Apple's Xcode CLT Python 3.9 (below `Requires-Python: >=3.11`), while user/Homebrew/uv Python `>=3.11` lives on `PATH`.
4. **Linux-only CI acceptance**: `.github/workflows/package-checks.yml` runs unit tests and `scripts/check_python.py` only on `ubuntu-24.04` / `debian:13`.

## Goals / Non-Goals

**Goals:**
- Make the entire offline unit suite, `scripts/check_python.py`, and source launcher pass cleanly on macOS (`arm64`, Python `>=3.11`) with zero weakening of symlink-race, permission, trust, or packaging security invariants.
- Add a non-privileged `macos-latest` (`arm64`) job to `.github/workflows/package-checks.yml` that validates unit tests, native `zsh` completion execution, `sh -n kobra-lan`, and outside-checkout sdist/wheel installation with hash-verified runtime wheels.
- Verify strictly read-only LAN operations against the Kobra X (`20030` / firmware `2.0.2.2`) from macOS Apple Silicon and record exact evidence boundaries in `docs/compatibility.md` and supporting docs.

**Non-Goals:**
- Publishing to PyPI or creating a Homebrew tap/formula.
- Qualifying Windows, Linux `arm64`, or Intel (`x86_64`) macOS.
- Changing Debian `.deb` packaging (`Architecture: all`, `/usr/bin/python3`, Debian 13 / Ubuntu 24.04 acceptance) or Sonar coverage collection.
- Changing MQTT/HTTP wire headers (including `X-BBL-OS-Type: linux` / `X-BBL-OS-Version: Debian` in `kobra_lan/upload.py`, which are slicer-emulation protocol headers observed on Kobra X firmware `2.0.2.2`).
- Running mutating live print/upload/delete/control commands from macOS.

## Decisions

### 1. Narrow, root-verified macOS system alias normalization (instead of `os.path.realpath`)

- **Decision**: Introduce one small helper (shared by `kobra_lan/profiles.py:open_directory` and `kobra_lan/pairing.py:PrivateStage.__init__`) that normalizes `os.path.abspath(path)` *only* when `sys.platform == "darwin"` and the path starts with `/var` or `/tmp` (exact directory or prefix `/var/...`, `/tmp/...`). Before rewriting the leading prefix to `/private/var` or `/private/tmp`, inspect the top-level entry with `os.lstat` and `os.readlink` to verify it is a symlink owned by `uid == 0` whose target is `private/var` / `/private/var` (for `/var`) or `private/tmp` / `/private/tmp` (for `/tmp`). Every subsequent path component is then traversed strictly from `/` with `O_RDONLY | O_DIRECTORY | O_NOFOLLOW`, preserving existing ownership (`st_uid == os.geteuid()`) and `0700`/`0600` checks unchanged.
- **Rationale**: Preserves complete symlink-race protection and every existing symlink-refusal test (`test_profiles.py`, `test_pairing.py`, `test_client.py`, `test_control.py`, `test_watch.py`, `test_jobs.py`, `test_delete_file.py`). Works identically for real user `$TMPDIR` (`/var/folders/...`), `/tmp/...`, and tests without requiring callers to manually `resolve()` paths.
- **Alternatives considered**:
  - Calling `Path(path).resolve()` before walking: **Rejected** — silently follows user-controlled symlinks in ancestors or target roots, weakening the security model and breaking symlink refusal invariants.
  - Only calling `.resolve()` in test fixtures: **Rejected** — leaves real macOS CLI invocations with `--config /tmp/...` or `--state-dir "$TMPDIR/..."` broken.
- **Note on `PrivateStage` config path consistency**: When `PrivateStage` normalizes `/var/...` → `/private/var/...`, `self.path` reflects the normalized destination (or preserves consistent parent/PEM paths) while `Registry` compares `config_path` consistently; unit tests will explicitly cover both synthetic Darwin alias normalization (mocking `sys.platform == "darwin"` on Linux too, so Linux CI exercises the branch) and rejection of non-root or unexpected symlink targets.

### 2. Bash 3.2-compatible completion generation and mandatory native `zsh` verification

- **Decision**: In `kobra_lan/completions.py`:
  - Replace `mapfile -t COMPREPLY < <(compgen ...)` with a Bash 3.2+ loop:
    ```bash
    local _kobra_item
    while IFS= read -r _kobra_item; do
      COMPREPLY+=("$_kobra_item")
    done < <(compgen ...)
    ```
    (using the same pattern for file completions instead of `local -a files; mapfile -t files < <(...)`).
  - Guard `compopt -o filenames` with `type compopt >/dev/null 2>&1 && compopt -o filenames`, and when `compopt` is unavailable (Bash 3.2) register `complete -o filenames -F _kobra_lan kobra-lan` (keeping `complete -F _kobra_lan kobra-lan` on Bash 4+) so Readline preserves filename quoting for spaced paths on both Bash 3.2 and Bash 4+.
  - Keep `zsh` and `fish` generated scripts unchanged (unless macOS native `zsh` reveals a concrete defect during testing).
  - In `tests/test_completions.py`:
    - Keep `test_bash_sources_and_completes_root_nested_choices_and_files` running unconditionally on both Bash 3.2 and Bash 4+.
    - Keep `test_bash_readline_inserts_spaced_paths_as_single_arguments` running unconditionally on both Bash 3.2 and Bash 4+ (exercising both normal and disabled-`compopt` registration) so spaced-path quoting is continuously verified across both Bash versions.
    - Keep `test_zsh_sources_and_calls_completion_without_device_commands` and a real PTY native `zsh` file-completion test (without `compadd`/`_files` stubs) running on any host with `zsh`, and in macOS CI run an explicit assertion step confirming `zsh` is installed and both `zsh` completion tests pass without skipping.
- **Rationale**: Fixes real macOS `/bin/bash` users without losing Bash 4+ filename escaping or breaking existing assertions in `scripts/probe_completions.py` and `tests/test_completions.py`.
- **Alternatives considered**:
  - Declaring Bash 4+ required and skipping bash tests on macOS: **Rejected** — easy to support Bash 3.2 cleanly with 3 lines of standard bash.

### 3. Portable POSIX source launcher (`./kobra-lan`)

- **Decision**: Update root `./kobra-lan` to:
  1. Resolve symlinks portably using a POSIX `/bin/sh` loop (`while [ -L "$script_path" ]` with `readlink "$script_path"`, handling both relative and absolute symlink targets) instead of `readlink -f`.
  2. Choose `python3` via `command -v python3` (falling back to `/usr/bin/python3` if `python3` is not in `PATH`).
  - Keep Debian's packaged `/usr/bin/kobra-lan` untouched (built by `pybuild` with `#!/usr/bin/python3` and verified by `scripts/check_deb.py`).
- **Rationale**: On Debian/Ubuntu without an active venv, `command -v python3` resolves to `/usr/bin/python3` (same behavior as today), while in a venv or on macOS with Homebrew/uv/python.org Python 3.11+ on `PATH`, it automatically picks the user's Python 3.11+ instead of Apple's Python 3.9. Keeping `sh -n kobra-lan` clean ensures POSIX portability.
- **Alternatives considered**:
  - Using `#!/usr/bin/env python3` as a Python script instead of `/bin/sh`: **Rejected** — `AGENTS.md` and CI explicitly check `sh -n kobra-lan`, and keeping the shell launcher avoids changing packaging/test expectations.

### 4. macOS CI job in `.github/workflows/package-checks.yml`

- **Decision**: Add a `macos` job running on `macos-latest` (`arm64`) inside `.github/workflows/package-checks.yml`, using the same pinned `actions/checkout` and `astral-sh/setup-uv` SHAs as `unit`:
  1. Pin a Python `>=3.11` interpreter present in `uv.lock` / `requirements-runtime.txt` (e.g., Python 3.12 via `uv`) and run `uv sync --locked --no-build --no-install-project`.
  2. Run `.venv/bin/ruff check kobra_lan scripts tests`, `sh -n kobra-lan`, `./kobra-lan --version` (with `.venv/bin` on `PATH`), and `.venv/bin/python -m unittest discover -s tests -v`.
  3. Run an explicit native `zsh` completion verification check confirming `zsh` is installed and `test_zsh_sources_and_calls_completion_without_device_commands` passes without skipping.
  4. Run `scripts/check_python.py build/python-acceptance` using an `ensurepip`-capable Python with the `build` frontend installed in an isolated build environment, verifying that `requirements-runtime.txt` hash-locked macOS wheels download and install offline (`--require-hashes --only-binary=:all:`) into the fresh test venv and pass every outside-checkout probe.
  5. Keep `release.yml` gating on `package-checks.yml`, so tagged releases also require the `macos` job to pass while continuing to publish only the Debian `.deb` + `SHA256SUMS` assets.
- **Rationale**: Gives continuous, unprivileged, fork-safe macOS `arm64` CI coverage without altering Linux Sonar coverage artifacts or Debian `.deb` release artifacts.
- **Alternatives considered**:
  - Putting macOS in a separate optional workflow: **Rejected** — would let regressions slip into `main` and tagged releases.

### 5. Live read-only LAN verification on macOS (`arm64` test host)

- **Decision**: During implementation, run a strictly read-only verification session from the authorized macOS `arm64` test host against the local Kobra X (`20030` / firmware `2.0.2.2`) using an isolated temporary directory (`HOME` / `--config`) so no persistent Mac or Linux profiles or printer state are modified:
  1. `printer discover` (validates macOS BSD UDP multicast `IP_MULTICAST_TTL`, `IP_MULTICAST_IF`, and unicast SSDP reply parsing against live Kobra X).
  2. Read-only connection checks (`doctor`, `status`, `slots list`, `camera status`) — coordinated with the user regarding credentials/client-slot budget (using either a temporary isolated pairing or an operator-provided temporary config without exposing or persisting secrets, and never touching `code 19002` blindly or modifying existing Linux access).
  3. Record exact sanitized evidence (macOS version, Apple Silicon `arm64`, Python version, `zsh` version, commands verified, and explicit non-claims for mutating operations) in `docs/compatibility.md`, `docs/usage.md` (if appropriate), `docs/releases.md`, `README.md`, `ROADMAP.md`, and `CHANGELOG.md`.
- **Note on SSDP socket options**: Inspect and test `kobra_lan/discovery.py` on live macOS (`setsockopt(IPPROTO_IP, IP_MULTICAST_TTL, ...)` and `IP_MULTICAST_IF`); if macOS requires `struct.pack("B", SSDP_MULTICAST_TTL)` or specific `bind()` ordering, adjust cleanly and add unit test coverage.

## Risks / Trade-offs

- **[Risk] Over-broad path normalization weakens symlink refusal** → **Mitigation**: Restrict alias normalization strictly to `sys.platform == "darwin"`, exact leading `/var` or `/tmp` prefixes, and verified `uid == 0` symlinks targeting `private/var` or `private/tmp`; keep `O_NOFOLLOW` on every component below and cover malicious/non-root symlink targets in unit tests.
- **[Risk] `uv`-managed Python on `macos-latest` differs in `ensurepip` or `build` behavior for `scripts/check_python.py`** → **Mitigation**: Test `scripts/check_python.py` on both the authorized macOS `arm64` test host and `macos-latest` CI before merging; keep `requirements-runtime.txt` hash enforcement (`--require-hashes --only-binary=:all:`) unchanged.
- **[Risk] `macos-latest` CI runner time or `cryptography` wheel mismatch on newer Python versions** → **Mitigation**: Pin the macOS CI Python version to a version present in `uv.lock` / `requirements-runtime.txt` (e.g., Python 3.12 or 3.13, both of which have `macosx_11_0_arm64` wheels in `uv.lock`) so `--only-binary=:all:` always resolves deterministically.
- **[Risk] Live pairing on macOS could consume a printer LAN client slot (`code 19002`)** → **Mitigation**: Start with strictly zero-auth `printer discover`, and confirm with the user before any temporary `printer pair` or reuse of an isolated read-only test config on the Mac.
- **[Risk] Readers assume macOS qualification implies Homebrew or validated live printing from macOS** → **Mitigation**: Explicitly distinguish offline CI validation, live read-only LAN observation, untested mutating commands, and future Homebrew/PyPI channels across `docs/compatibility.md`, `docs/releases.md`, `README.md`, and `ROADMAP.md`.
