# Proposal

## Why

Kobra LAN CLI can inspect, upload, plan, start, reprint, watch, and review local history of prints, but owners still cannot pause, resume, or cancel an active print without falling back to the printer touchscreen, mobile app, or a bridge. Adding guarded `print pause`, `print resume`, and `print cancel` commands advances Milestone 3 toward a complete everyday print cycle while enforcing strict state-transition preconditions, single-shot non-replaying execution, and honest hardware-qualification boundaries.

## What Changes

- Add `print pause`, `print resume`, and `print cancel` subcommands requiring explicit `--execute` (refusing with exit 2 before printer access when omitted; no implicit dry run) and accepting an optional `--filename <remote-name>` guard to assert the active project filename before publishing.
- Add a dedicated single-shot MQTT control publish path (`type: "print"`, action `"pause"`, `"resume"`, or `"stop"` for cancel, carrying the validated active `task_id` or `"-1"` placeholder) strictly separated from the read-only `MQTT.query()` allowlist, with one correlated `/response` ACK wait and zero automatic reconnects or retries.
- Enforce fresh pre-flight `info` qualification (Kobra X model 20030 / firmware `2.0.2.2` and consistent optional identity fields) and strict state preconditions before sending: `pause` requires active `printing`; `resume` requires `paused`; `cancel` requires `printing`, a recognized firmware `2.0.2.2` preparation phase, or `paused`. Idle, already-reached, transitional (`pausing`, `resuming`, `stopping`), and unrecognized states fail with exit 2 before any command is published.
- Acquire the shared per-device exclusive lease under `--state-dir` across pre-flight verification, single publish, and bounded post-action observation while preserving all existing profiles, upload/start receipts, `.attempt` markers, and watch observations untouched.
- Perform bounded post-ACK fresh `info` polling on the same pinned session to distinguish observed target state (`control_observed_paused`, `control_observed_resumed`, `control_observed_stopped`), acknowledged-not-confirmed transitions (`control_acknowledged_not_confirmed`), and post-publish uncertainty (`control_uncertain_no_retry` with safe partial result and explicit non-replay guidance), reporting `experimental: true` and `hardware_control_validated: false` until live Kobra X verification is recorded.
- Update contextual help, offline bash/zsh/fish shell completions, English documentation (`README.md`, `docs/usage.md`, `ROADMAP.md`, `debian/kobra-lan.1`), and Python/Debian installed-package verification probes.

## Capabilities

### New Capabilities
- `print-lifecycle-control`: Guarded, single-shot execution of `print pause`, `print resume`, and `print cancel` on a qualified Kobra X over a pinned authenticated MQTT session, with fresh state-transition preconditions, optional active-filename binding, per-device concurrency locking, bounded post-action verification, and safe uncertainty reporting without automatic replay.

### Modified Capabilities
- `cli-interface`: Extend the canonical command tree, `print --help`, installed workflow documentation, and offline bash/zsh/fish completions to expose `print pause`, `print resume`, and `print cancel` with `--execute` and optional `--filename`.

## Impact

- Adds a new control module (`kobra_lan/control.py`), a single-shot `control_once()` method on `kobra_lan/mqtt.py` (keeping `query()` read-only), and CLI dispatch/validation in `kobra_lan/cli.py`.
- Reuses existing directory-binding helpers from `kobra_lan/upload.py` and extends `upload.device_lock()` to also acquire a shared per-device `.device.lock` across `files upload`, `print start`, and `print pause|resume|cancel` (preserving `.upload.lock`/`.start.lock` compatibility), reuses compatibility checks from `kobra_lan/diagnostics.py`, and reuses validated filename/state helpers from `kobra_lan/watch.py` without modifying any existing profile, upload receipt, start receipt, `.attempt` marker, or watch observation files.
- Updates offline unit tests (`tests/test_control.py`, `tests/test_cli.py`, `tests/test_completions.py`, `tests/test_mqtt.py`), English documentation (`README.md`, `docs/usage.md`, `ROADMAP.md`, `debian/kobra-lan.1`), and distribution probes (`scripts/check_python.py`, `scripts/build_deb.py`, `scripts/accept_deb.py`).
- Stored-file deletion (`files delete`), file download, temperature/fan/light/axis controls, automatic retries, `print watch` terminal-outcome inference, and non-Kobra-X models/firmwares remain out of scope. Live hardware validation of pause/resume/cancel (and deferred `--reprint-from` validation) requires separate operator authorization in an integrated Kobra X session.
