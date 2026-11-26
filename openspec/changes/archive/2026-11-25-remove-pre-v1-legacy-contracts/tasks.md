# Tasks

## 1. Remove `single_filament_start_compatible` from G-code inspection

- [x] 1.1 Remove `single_filament_start_compatible` calculation and return field from `inspect_gcode_filaments()` in `kobra_lan/filaments.py` and verify `uv run --locked python -m unittest tests/test_filaments.py tests/test_client.py -v` passes after updating their assertions to assert key absence.
- [x] 1.2 Update G-code inspection documentation in `docs/usage.md`, `docs/compatibility.md`, `debian/kobra-lan.1`, `README.md`, and `ROADMAP.md` to omit `single_filament_start_compatible`, and verify no stale references remain via `grep -rn single_filament_start_compatible kobra_lan/ tests/ docs/ debian/ README.md ROADMAP.md`.

## 2. Unify per-device concurrency locking on `.device.lock`

- [x] 2.1 Simplify `device_lock(directory)` in `kobra_lan/upload.py` to open and lock only `.device.lock`, remove `upload_lock()`, and update all call sites in `kobra_lan/upload.py`, `kobra_lan/start.py`, `kobra_lan/control.py`, and `kobra_lan/delete_file.py`; verify lock contention and no-symlink/private-permission guarantees in `tests/test_client.py`, `tests/test_control.py`, and `tests/test_delete_file.py` (asserting `.upload.lock` and `.start.lock` are never created) pass with `uv run --locked python -m unittest tests/test_client.py tests/test_control.py tests/test_delete_file.py -v`.
- [x] 2.2 Update locking documentation in `docs/usage.md` to describe `.device.lock` as the sole shared per-device lease (removing `.upload.lock`/`.start.lock` references), and verify no production or docs references to `.upload.lock` or `.start.lock` remain outside historical changelog/archive entries.

## 3. Unify canonical attempt-keyed start records and remove `record_format`

- [x] 3.1 Update `kobra_lan/start.py` (`matching_receipt`, `latest_attempt`, `publish_start`) so both root starts and reprints always store and look up `<attempt_id>.attempt` and `<attempt_id>.json`, drop the legacy `{"sha256", "plan_sha256"}` marker/receipt branch, and update `tests/test_start.py` to test canonical attempt-keyed root/reprint chains and verify unrecognized pre-v1 file-keyed files remain untouched and ineligible (`uv run --locked python -m unittest tests/test_start.py -v`).
- [x] 3.2 Update `kobra_lan/jobs.py` (`_parse_start_candidate`, `_build_unreadable_start`, `_reconstruct_start_entry`) to accept only canonical attempt-keyed start records (`storage_key == attempt_id`), remove `record_format` from all start records and `jobs info`, surface pre-v1 file-keyed or pre-`attempt_id` files read-only as `unreadable-<storage-key>` (`completeness: "incomplete"`, `reprint_eligibility: "blocked_incomplete"`), and update `tests/test_jobs.py` to verify canonical chains, `record_format` absence, and non-destructive unreadable handling (`uv run --locked python -m unittest tests/test_jobs.py -v`).
- [x] 3.3 Update `_matching_start_receipt()` in `kobra_lan/delete_file.py` to require canonical `key == identity` and explicit `record.get("attempt_id") == identity`, update `tests/test_delete_file.py` fixtures/assertions accordingly, and verify `uv run --locked python -m unittest tests/test_delete_file.py -v` passes.
- [x] 3.4 Update local state and job history documentation in `docs/usage.md`, `debian/kobra-lan.1`, `ROADMAP.md`, and `CHANGELOG.md` (`## Unreleased` breaking changes) to document canonical attempt-keyed start storage, removal of legacy start parsing/`record_format`, single `.device.lock`, and removal of `single_filament_start_compatible`.

## 4. Full offline integration and lint validation

- [x] 4.1 Run the full offline test suite, shell syntax check, and linter (`uv run --locked python -m unittest discover -s tests -v && sh -n kobra-lan && uv run --locked ruff check kobra_lan scripts tests`) and confirm all checks pass with zero warnings or regressions.

## Workflow follow-up

- Sync delta specs and archive `remove-pre-v1-legacy-contracts` after implementation and review are complete.
