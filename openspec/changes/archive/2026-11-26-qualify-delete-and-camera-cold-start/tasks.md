# Tasks

## 1. Live `files delete` local-state preservation qualification

- [x] 1.1 Obtain explicit operator authorization for a non-printing live session on Kobra X (`20030` / `2.0.2.2`), confirm idle state with `./kobra-lan --json status` (`state: "free"`, no active project), prepare an isolated `0700` disposable `--state-dir` under `~/research/kobra-lan-cli/qualify-delete-camera/`, and upload a small disposable Next-generated Kobra X `.gcode` via `./kobra-lan --json --state-dir <tmp> files upload <file> --sha256 <sha256> --execute`; verify `uploaded_verified_by_listing_and_metadata` and creation of the real upload `.attempt` marker and `.json` receipt.
- [x] 1.2 Seed private (`0600`) canonical start (`starts/<device>/<attempt_id>.attempt` + `.json`) and watch observation (`observations/<device>/obs-<32hex>.json`) records referencing the uploaded test filename inside the disposable `--state-dir`, verify `jobs list`/`jobs info` read them cleanly, snapshot `(relative_path, mode, size, sha256)` of the entire `--state-dir` tree, run `./kobra-lan --json --state-dir <tmp> files delete <name> --execute`, and verify exit `0`, `status: "delete_observed_removed"`, `local_state.preserved: true`, follow-up `files list` absence, identical `(mode, size, sha256)` for every pre-existing file and directory, intact `jobs list`/`jobs info` output, and duplicate-upload refusal on the preserved `.attempt` marker.
- [x] 1.3 Only after task 1.2 passes, set `KOBRA_X.delete_hardware_validated = True` in `kobra_lan/qualification.py`, update `tests/test_qualification.py`, `tests/test_delete_file.py`, and `tests/test_cli.py` to assert `hardware_delete_validated: true` for Kobra X `20030` / `2.0.2.2` and `false` for unqualified models/firmwares, and verify with `uv run --locked python -m unittest tests.test_qualification tests.test_delete_file tests.test_cli -v`.
- [x] 1.4 Record the live `files delete` byte-for-byte preservation evidence and `hardware_delete_validated: true` status in `docs/usage.md`, `docs/compatibility.md`, `README.md`, `ROADMAP.md`, and `CHANGELOG.md` (`Unreleased`), and verify via grep that no stale `hardware_delete_validated: false` claims remain for qualified Kobra X `20030` / `2.0.2.2`.

## 2. Live post-reboot cold-start camera qualification

- [x] 2.1 Coordinate an operator-authorized clean reboot of Kobra X (`20030` / `2.0.2.2`) with no prior app, slicer, or CLI camera capture, verify idle qualification via `./kobra-lan --json doctor`, and run read-only `./kobra-lan --json camera status`; save sanitized JSON evidence under `~/research/kobra-lan-cli/qualify-delete-camera/` and confirm zero stream URL or token exposure.
- [x] 2.2 Immediately after task 2.1 on the cold-booted printer, run `./kobra-lan camera pipe --max-bytes 65536 --no-start-capture > <tmp>/cold-direct.flv` to observe direct cold-boot behavior, then run `./kobra-lan --json camera snapshot --output <tmp>/cold-snapshot.jpg` and `./kobra-lan camera pipe --max-bytes 65536 > <tmp>/cold-pipe.flv`; verify valid decoded JPEG (`1280x720`), valid `FLV` header, accurate `capture_mode`/`start_capture_used`/`stop_capture_sent` metadata, zero URL/token leakage in stdout/stderr/JSON, and healthy post-capture `./kobra-lan --json status` and `camera status`.
- [x] 2.3 If cold-start testing uncovers a firmware edge case, apply the minimal scoped fix in `kobra_lan/camera.py`, add offline regression tests in `tests/test_camera.py`, and re-verify after a fresh cold reboot; if current read-only-first + fallback behavior passes cleanly, confirm zero regressions with `uv run --locked python -m unittest tests.test_camera -v`.
- [x] 2.4 Record the live post-reboot cold-start camera evidence in `docs/usage.md`, `docs/compatibility.md`, `ROADMAP.md`, and `CHANGELOG.md` (`Unreleased`), retiring the Milestone 3 cold-start camera item from `ROADMAP.md`.

## 3. Final offline validation gates

- [x] 3.1 Run `uv run --locked python -m unittest discover -s tests -v && sh -n kobra-lan && uv run --locked ruff check kobra_lan scripts tests` and verify every test and lint gate passes.
- [x] 3.2 Run `openspec validate qualify-delete-and-camera-cold-start` and inspect `git status` and `git diff` to verify specs validate cleanly and no real configs, PEMs, tokens, or stream URLs were staged or committed.

## Workflow follow-up

- Sync delta specs and archive `qualify-delete-and-camera-cold-start` after review requirements are satisfied.
- Open a PR against `main` with sanitized hardware validation notes and verify all required CI checks pass.
