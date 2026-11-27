# Tasks

## 1. macOS-Safe Private Directory Traversal

- [x] 1.1 Add narrow `darwin`-only root system alias normalization (`/var` → `/private/var`, `/tmp` → `/private/tmp`, verified via `os.lstat`/`os.readlink` as `uid == 0` symlinks to `private/var` or `private/tmp`) shared by `kobra_lan/profiles.py:open_directory` and `kobra_lan/pairing.py:PrivateStage.__init__` without weakening `O_NOFOLLOW` or `0700`/`0600` checks; verify with targeted unit tests in `tests/test_profiles.py` and `tests/test_pairing.py` covering both allowed root-owned Darwin aliases and rejected non-root, unexpected-target, or descendant symlinks.

## 2. Bash 3.2 Compatibility and Native `zsh` Completion

- [x] 2.1 Update `kobra_lan/completions.py` to replace Bash 4-only `mapfile` usage with a Bash 3.2+ `while IFS= read -r` loop and guard `compopt -o filenames` with `type compopt >/dev/null 2>&1 && compopt -o filenames` while preserving `zsh` and `fish` output; verify with `uv run --locked python -m unittest tests/test_completions.py -v` and confirm `scripts/probe_completions.py` assertions still pass.
- [x] 2.2 Update `tests/test_completions.py` so `test_bash_sources_and_completes_root_nested_choices_and_files` runs cleanly on Bash 3.2 (including simulated missing `compopt`) and Bash 4+, while `test_bash_readline_inserts_spaced_paths_as_single_arguments` explicitly skips only when `bash` reports `BASH_VERSINFO[0] < 4`; verify offline with `uv run --locked python -m unittest tests/test_completions.py -v`.

## 3. Portable Source Launcher and macOS Documentation

- [x] 3.1 Update root `./kobra-lan` to resolve symlinks portably in POSIX `/bin/sh` (without GNU-only `readlink -f`) and execute `python3` from `PATH` with fallback to `/usr/bin/python3`; verify with `sh -n kobra-lan`, a direct and symlinked launcher test in `tests/`, and confirm Debian packaging checks (`tests/test_debian_docs.py` / `scripts/check_deb.py` expectations) remain untouched.
- [x] 3.2 Document macOS (`arm64`) Python `>=3.11` venv/wheel/source installation, optional `ffmpeg` for `camera snapshot`, and non-published PyPI/Homebrew status in `docs/releases.md`, `docs/development.md`, and `README.md`; verify all relative Markdown links pass `tests/test_debian_docs.py`.

## 4. macOS CI Acceptance Workflow

- [x] 4.1 Add an unprivileged `macos` (`macos-latest`, `arm64`) job to `.github/workflows/package-checks.yml` that syncs the committed `uv.lock`, runs `ruff`, `sh -n kobra-lan`, `./kobra-lan --version`, the full offline `unittest` suite, an explicit non-skipping native `zsh` completion check, and `scripts/check_python.py` outside-checkout wheel/sdist acceptance against hash-locked `requirements-runtime.txt` wheels; verify workflow syntax and ensure existing Linux `unit`, `build`, `acceptance`, and `sonar` jobs remain intact.

## 5. Real macOS Verification and Compatibility Matrix Evidence

- [x] 5.1 Run offline unit tests, `sh -n kobra-lan`, `./kobra-lan --version`, native `zsh` and stock Bash 3.2 completion tests, and `scripts/check_python.py` on the linked `MacBook Air de Eduardo` (`arm64`), fixing any real macOS/BSD issues discovered (such as `discovery.py` socket option behavior) with matching unit tests.
- [x] 5.2 With explicit operator coordination and an isolated temporary config/state directory on the linked `MacBook Air de Eduardo`, execute strictly read-only LAN verification against Kobra X (`20030` / firmware `2.0.2.2`) covering `printer discover` and read-only status/inspection (`doctor`, `status`, `slots list`, `camera status`) without mutating printer state or existing Linux profiles, and confirm zero secret/token leakage.
- [x] 5.3 Record sanitized macOS (`arm64`) offline CI and live read-only LAN hardware evidence (explicitly separating untested mutating macOS runs, `x86_64` macOS, Windows, Linux `arm64`, PyPI, and Homebrew) in `docs/compatibility.md`, `ROADMAP.md`, and `CHANGELOG.md` (`Unreleased`); verify with `uv run --locked ruff check kobra_lan scripts tests`, `sh -n kobra-lan`, and `uv run --locked python -m unittest discover -s tests -v`.

## Workflow follow-up

- Open PR and confirm GitHub Actions passes all Linux (`unit`, `build`, `acceptance`, `sonar`) and `macos` (`arm64`) jobs.
- Archive the change (`openspec archive qualify-macos-platform`) after review requirements are satisfied and verify specs sync cleanly.
