# Tasks

## 1. MQTT Freshness Skew and Monotonic Timestamp Support

- [x] 1.1 Extend `MQTT.query()` in `kobra_lan/mqtt.py` with optional keyword-only `max_backward_skew_ms=0` and `min_timestamp=None` while keeping non-retained and correlated/post-ACK checks intact, and add unit tests in `tests/test_mqtt.py` and `tests/test_watch.py` verifying bounded backward clock-skew acceptance, out-of-window stale rejection, retained-packet rejection, and strictly increasing `min_timestamp` enforcement (`uv run --locked python -m unittest tests/test_mqtt.py tests/test_watch.py -v`).

## 2. Continuous Coherent Observation and Firmware 2.0.2.2 State Coverage

- [x] 2.1 Expand `PREPARATION_STATES` in `kobra_lan/watch.py` with live-observed firmware `2.0.2.2` calibration and filament-change states (`auto_leveling`, `vibrating`, `flow_calibrating`, `filament_cutting`, `extfilbox_filament_unfeeding`), define `START_ONLY_PREPARATION_STATES`, and verify shared `control.py` preconditions/confirmations with unit tests in `tests/test_control.py` (`uv run --locked python -m unittest tests/test_control.py -v`).
- [x] 2.2 Update `WatchProgress` and `observe()` in `kobra_lan/watch.py` for continuous coherent tracking across preparation, printing, filament-change, pause (`paused`, `pausing`), `resuming`, and `stopping` phases using bounded clock-skew (`max_backward_skew_ms=5000`) and monotonic `min_timestamp`; preserve high-water printing progress across temporary non-printing transitions and end-of-print layer-counter zeroing; stop with `identity_unverified` on missing/hostile filenames, counter regressions, or post-printing start-only calibration phases, and with `job_replaced` / `job_disappeared` / `last_project_unattributed` as specified; verify with unit tests in `tests/test_watch.py` (`uv run --locked python -m unittest tests/test_watch.py -v`).
- [x] 2.3 Update `OBSERVATION_PHASES` in `kobra_lan/jobs.py` to accept `paused` and `stopping` alongside `preparing` and `printing` while preserving backwards compatibility for existing observation files, and verify with unit tests in `tests/test_jobs.py` (`uv run --locked python -m unittest tests/test_jobs.py -v`).

## 3. Live Sanitized `stderr` Progress, `--quiet` Flag, and Documentation

- [x] 3.1 Add optional `--quiet` to `print watch` in `kobra_lan/cli.py`, wire sanitized deduplicated live progress rendering to `stderr` (scalar phase, state, progress, layers, optional remaining time, and safe temperatures only — never filenames, URLs, tokens, or terminal controls), and verify CLI text/JSON/stderr/quiet behavior and `bash`/`zsh`/`fish` completions in `tests/test_watch.py`, `tests/test_cli.py`, and `tests/test_completions.py` (`uv run --locked python -m unittest tests/test_watch.py tests/test_cli.py tests/test_completions.py -v`).
- [x] 3.2 Update `docs/usage.md`, `docs/compatibility.md`, and `ROADMAP.md` to document continuous coherent `print watch` tracking on firmware `2.0.2.2`, `--quiet` and `stderr` live progress, expanded `PREPARATION_STATES` for watch and lifecycle controls, clock-skew bounds, and retained honest `unknown` terminal-outcome boundaries; verify consistency against CLI help (`./kobra-lan print watch --help`).

## 4. Integration Validation

- [x] 4.1 Run the full offline validation suite (`uv run --locked python -m unittest discover -s tests -v`, `uv run --locked ruff check kobra_lan scripts tests`, `sh -n kobra-lan`, and `openspec validate improve-print-watch --strict`) and confirm all checks pass cleanly with no new packaging modules required.
- [x] 4.2 Perform read-only live observation verification against the paired Kobra X (`20030` / firmware `2.0.2.2`) using an isolated `0700` `--state-dir` (confirming multi-poll live progress on `stderr`, `--quiet` suppression, clean `--json` stdout, preserved local observation record readable via `jobs list`/`jobs info`, and zero mutation to production state/profiles).

## Workflow follow-up

- Archive the change with `openspec archive improve-print-watch` after implementation and review requirements are satisfied.
