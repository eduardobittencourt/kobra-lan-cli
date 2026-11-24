# Tasks

## 1. MQTT Single-Shot File Deletion and Shared Device Lease

- [x] 1.1 Add `MQTT.delete_file_once(filename, *, on_ack=None)` in `kobra_lan/mqtt.py` (strictly separated from the read-only `MQTT.query()` allowlist), publishing one QoS 0 `type: "file"`, `action: "deleteBatch"` request with `data: {"root": "local", "files": [{"path": "/", "filename": filename}]}` and waiting on the same pinned session for its correlated `/response` ACK (`code == 0`, invoking `on_ack` before report wait) and fresh non-retained `file/report` (`action == "deleteBatch"`, `state == "success"`, no failing `code`) with QoS 0/1 handling and zero retries; verify with unit tests in `tests/test_mqtt.py` covering success (correlated and post-ACK fresh report), QoS 1 PUBACK, non-zero ACK rejection, failed `file/report`, malformed packet, retained-packet ignore, timeout after ACK, and read-only `MQTT.query()` refusal of `("file", "deleteBatch")`.
- [x] 1.2 Extend `upload.device_lock(directory, operation)` in `kobra_lan/upload.py` so `operation == "delete"` shares `.device.lock` without creating a separate `.delete.lock` file (matching `"control"`), keeping `files upload`, `print start`, `print pause|resume|cancel`, and `files delete` mutually exclusive on the same device and `--state-dir`; verify with unit tests in `tests/test_delete_file.py` confirming lock contention refusal before printer access and symlink/non-private directory rejection.

## 2. Guarded Stored-File Deletion Module

- [x] 2.1 Create `kobra_lan/delete_file.py` implementing `DeleteUncertain`, read-only `summarize_local_state` (counting matching local upload/start receipts without modifying files or creating missing `starts/` or `observations/` directories), and `delete_file(config, filename, state_dir)` (fresh qualified `info` check, strict idle check with distinct error when `<name>` is the active project, pre-flight `list_files` single non-directory check, directory-binding recheck, single `delete_file_once` call, bounded post-delete `list_files` polling + fresh `info` check, returning `delete_observed_removed`, `delete_acknowledged_not_confirmed`, or raising `DeleteUncertain` with `delete_uncertain_no_retry`, `experimental: True`, `hardware_delete_validated: False`); verify with comprehensive synthetic unit tests in `tests/test_delete_file.py` covering confirmed removal, delayed removal within poll window, acknowledged-not-confirmed, active-target refusal, busy-printer refusal, missing-file refusal, directory refusal, ambiguous duplicate listing refusal, unqualified firmware/TLS pin mismatch refusal, post-publish timeout/disconnect/protocol/interrupt uncertainty with partial evidence and zero retries, byte-for-byte preservation of upload receipts/markers, start receipts/markers, and watch observations, and safe downstream `jobs list|info` / duplicate-upload protection behavior.
- [x] 2.2 Add `"delete_file"` to the module allowlists in `scripts/check_python.py` and `scripts/build_deb.py`, and verify both scripts compile cleanly with `python3 -m py_compile scripts/check_python.py scripts/build_deb.py scripts/accept_deb.py`.

## 3. CLI Subcommand, Shell Completions, Packaging Probes, and Documentation

- [x] 3.1 Register `files delete <name> --execute` in `kobra_lan/cli.py` with contextual `Parser.error()` guidance, pre-target filename validation (`invalid_arguments` exit 2 without echoing unsafe input), and dispatch to `delete_file`; verify with unit tests in `tests/test_cli.py`, `tests/test_delete_file.py`, and `tests/test_completions.py` covering `files --help`, `files delete --help`, missing `--execute`, malformed/URL `<name>`, text and root `--json` parity (exit 0/2/3/130), and offline bash/zsh/fish completions exposing `files:delete` and `files delete:--execute`.
- [x] 3.2 Update offline installed-CLI and completion probes in `scripts/check_python.py` and `scripts/accept_deb.py` to verify `files --help`, `files delete --help`, missing `--execute` refusal without leaking untrusted input, and offline completion entries for `files delete` / `--execute`; verify via `uv run --locked ruff check scripts`.
- [x] 3.3 Document `files delete <name> --execute` (including idle/active-job preconditions, preserved local receipts/markers, `experimental: true` / `hardware_delete_validated: false`, and non-replay uncertainty outcomes) in `README.md`, `docs/usage.md`, `ROADMAP.md`, and `debian/kobra-lan.1`; verify documented commands and flags match `kobra-lan files --help` and `kobra-lan files delete --help`.

## 4. Integrated Offline Verification

- [x] 4.1 Run the full offline validation suite (`uv run --locked python -m unittest discover -s tests -v`, `uv run --locked ruff check kobra_lan scripts tests`, `sh -n kobra-lan`, and `openspec validate add-stored-file-deletion --strict`) and confirm all checks pass without contacting real hardware or modifying private state.

## Live verification

On 2026-11-23, one operator-authorized deletion on a Kobra X (`20030` /
firmware `2.0.2.2`) returned ACK code 0 and a successful `deleteBatch` report
with code 200. The CLI returned `delete_observed_removed` and a separate
`files list` confirmed removal. The local summary counted one upload receipt
and one start receipt. Byte-for-byte preservation of receipts and markers was
verified offline with synthetic state. The CLI continues to report
`hardware_delete_validated: false`.

See the [usage guide evidence](../../../../docs/usage.md#validation-evidence).
