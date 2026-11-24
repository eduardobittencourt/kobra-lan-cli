# Proposal

## Why

Kobra LAN CLI can list, inspect, upload, plan, start, reprint, watch, and control prints, but owners still cannot remove old or failed files from the printer's internal storage without falling back to the touchscreen or a bridge. Adding guarded `files delete <name> --execute` advances Milestone 3 toward a complete everyday print cycle while enforcing strict idle/active-job preconditions, single-shot non-replaying deletion, and strict preservation of local receipts and durable attempt markers.

## What Changes

- Add `files delete <name> --execute` as a single-target, explicitly executed subcommand under `files` (refusing with exit 2 before target selection, state locking, or printer access when `--execute` is omitted or `<name>` is malformed; no implicit dry run or interactive prompt).
- Add a dedicated single-shot MQTT file-deletion path (`MQTT.delete_file_once(filename)`) strictly separated from the read-only `MQTT.query()` allowlist, publishing one QoS 0 `type: "file"`, `action: "deleteBatch"` request targeting `{"root": "local", "files": [{"path": "/", "filename": "<name>"}]}` and waiting for its correlated `/response` ACK and fresh `file/report` outcome on the same pinned session with zero automatic reconnects or retries.
- Enforce fresh pre-flight `info` qualification (Kobra X model `20030` / firmware `2.0.2.2` and consistent optional identifiers), an idle printer check (refusing whenever any print is active, and specifically refusing when `<name>` matches the active project), and a pre-flight `file/listLocal` check verifying that `<name>` exists as a single non-directory entry before publishing.
- Acquire the shared per-device exclusive lease (`.device.lock`) under `--state-dir` across pre-flight inspection, single publish, and bounded post-delete verification while leaving all existing profiles, upload receipts, upload `.attempt` markers, start receipts/markers, and watch observations byte-for-byte untouched, and reporting a safe read-only summary of preserved local receipt matches.
- Perform bounded post-delete `file/listLocal` and fresh `info` verification on the same pinned session to distinguish confirmed removal (`delete_observed_removed`), acknowledged-not-confirmed (`delete_acknowledged_not_confirmed`), and post-publish uncertainty (`delete_uncertain_no_retry` with safe partial result and explicit non-replay guidance), reporting `experimental: true` and `hardware_delete_validated: false` until operator-authorized live Kobra X verification is recorded.
- Update contextual help, offline bash/zsh/fish shell completions, English documentation (`README.md`, `docs/usage.md`, `ROADMAP.md`, `debian/kobra-lan.1`), and Python/Debian installed-package verification probes.

## Capabilities

### New Capabilities
- `stored-file-deletion`: Guarded, single-shot deletion of a root-level stored file on a qualified Kobra X over a pinned authenticated MQTT session, enforcing fresh idle/active-job and listing preconditions, per-device concurrency locking, read-only local receipt/marker preservation, bounded post-delete listing verification, and non-replaying uncertainty reporting.

### Modified Capabilities
- `cli-interface`: Extend the canonical command tree, `files --help`, installed workflow documentation, and offline bash/zsh/fish completions to expose `files delete <name> --execute`.

## Impact

- Adds a new deletion module (`kobra_lan/delete_file.py`), a single-shot `delete_file_once()` method on `kobra_lan/mqtt.py` (keeping `query()` strictly read-only), shared `.device.lock` support for `"delete"` in `kobra_lan/upload.py`, and CLI dispatch/validation in `kobra_lan/cli.py`.
- Reuses `compatibility_issue` from `kobra_lan/diagnostics.py`, `validate_filename` from `kobra_lan/control.py`, `project_filename` from `kobra_lan/watch.py`, and `list_files`/`payload_data`/`sanitized` from `kobra_lan/printer.py`, without modifying any existing profile, upload receipt, `.attempt` marker, start receipt, or watch observation files.
- Updates packaging module allowlists and offline installed-CLI probes in `scripts/check_python.py`, `scripts/build_deb.py`, and `scripts/accept_deb.py`.
- Adds offline unit tests (`tests/test_delete_file.py`) and updates `tests/test_cli.py`, `tests/test_completions.py`, and `tests/test_mqtt.py` using synthetic transports and fixtures.
- Updates English documentation in `README.md`, `docs/usage.md`, `ROADMAP.md`, and `debian/kobra-lan.1`.
- Multi-file batch CLI deletion, subdirectory traversal/deletion, file download, deleting local receipts or attempt markers, automatic retries, deleting files while a print is active, and live Kobra X hardware qualification remain out of scope (live hardware qualification requires separate operator authorization after implementation).
