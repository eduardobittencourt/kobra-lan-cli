# Verification — profiles and doctor

Verified locally on 2026-11-04 against implementation branch
`feat/printer-profiles-and-doctor`, based on merged main `4c653be`.
Source version preparation: 0.4.0. No tag or release was created.

## Initial implementation gates and artifacts

- Locked Ruff and coverage-backed unittest discovery: **152 tests passed**.
- `profiles.py` and `diagnostics.py`: each **91%** branch-aware unit coverage.
  Package acceptance runs independently of unit instrumentation; the total
  includes release scripts that only execute in disposable environments.
- Shell syntax, runtime requirements export comparison and version/tag-format
  validation (`scripts/release_version.py --tag v0.4.0`) passed.
- Sdist -> wheel build, dependency/content allowlists and independent installed
  runtime probes passed with declared runtime dependencies outside the checkout.
- Debian 13 build, 35-file archive allowlist, metadata and checksums passed.
  Lintian reported only the documented `initial-upload-closes-no-bugs` warning.
- The identical Debian artifact passed network-disabled clean install, controlled
  older-fixture upgrade, remove and purge in Debian 13 and Ubuntu 24.04 amd64.
  Non-root private registry/config/PEM/uncertain marker fixtures preserved bytes,
  ownership and modes after every operation. Hooks never ran live diagnosis or
  provisioning. Installed probes explicitly substitute synthetic transports.
- Artifact SHA-256 (`kobra-lan-cli_0.4.0-1_all.deb`):
  `e93f94d2ada6d9fe0a0816422c1d51b9ddb2b76475dffa5fbd5415852a79cf77`.
- The initial local wheel matched all 11 application source modules at that implementation snapshot.

Retained validation evidence includes unit/coverage
reports, `build-candidate.log`, distribution acceptance logs and digest-bound JSON
reports, official rootfs download checksums and `artifacts/`. Disposable chroots
were used because Docker/Podman are unavailable; the repository's Docker CI
wrapper was not executed locally. Gate commands remain in `docs/releases.md`.

## Scenario evidence

Names below identify automated tests in `tests/test_profiles.py` (P),
`tests/test_diagnostics.py` (D), existing `tests/test_pairing.py` (T), and installed
`scripts/probe_profiles.py` / `scripts/probe_pairing.py` (I). Every transport is
synthetic; local CLI tests forbid real sockets.

### printer-profiles

| Spec scenario | Automated evidence |
| --- | --- |
| Printers are offline | P `test_local_commands_and_selector_conflicts` |
| Empty or partially damaged inventory | P `test_names_and_read_only_empty`, `test_unavailable_inventory_and_no_secrets`, `test_damaged_config_types_do_not_hide_healthy_entries` |
| Inspect an offline profile | P `test_local_commands_and_selector_conflicts` |
| Omitted name | P `test_local_commands_and_selector_conflicts` |
| Temporary override | P `test_selection_override_legacy_and_local_dry_runs` |
| Conflicting selectors | P `test_local_commands_and_selector_conflicts`; D `test_cli_envelope_and_conflict` |
| Broken selected target | P `test_local_commands_and_selector_conflicts`, `test_default_states_and_failures` |
| Select an offline printer | P `test_local_commands_and_selector_conflicts` |
| Invalid profile | P `test_default_states_and_failures` |
| Existing installation | P `test_names_and_read_only_empty`, `test_legacy_without_registry_preserves_old_parent_permissions`; I |
| Explicit legacy selection after adopting profiles | P `test_selection_override_legacy_and_local_dry_runs`; I |
| Unattended refusal | P `test_removal_consent_revalidation_and_receipt` |
| Confirmed removal | P `test_removal_consent_revalidation_and_receipt`; I |
| Remove default with legacy config still present | I legacy -> named -> remove -> implicit refusal -> explicit legacy access |
| Unsafe destination or concurrent writers | P `test_managed_modes_existing_and_symlinks`, `test_bounded_concurrent_writers_and_shared_leases`, `test_atomic_failures_never_replace_config`, `test_write_failure_and_managed_parent_permissions` |
| Interrupted removal or shared files | P `test_removal_shared_symlink_unknown_and_io_failure`, `test_removal_active_lease_and_metadata_change`, `test_removal_commit_failure_reports_retained_files_and_actual_state`, `test_legacy_symlink_references_preserve_shared_config_and_pems` |
| Same device through another profile | P `test_same_device_markers_survive_other_name_and_repair`; I legacy/named/re-paired upload marker |
| Scripted local selection and removal | P `test_local_commands_and_selector_conflicts`, `test_removal_consent_revalidation_and_receipt`; I |

### printer-pairing

| Spec scenario | Automated evidence |
| --- | --- |
| Pair a new named printer | P `test_named_pairing_real_publication_and_default`; I |
| Invalid or duplicate name | P `test_named_pairing_real_publication_and_default`, `test_managed_modes_existing_and_symlinks` |
| Existing unnamed automation | Original T suite (54 tests); I original synthetic provisioning/status |
| Pair and select | P `test_named_pairing_real_publication_and_default` |
| Failed pairing | P `test_partial_named_publication_and_default_reconciliation`; original T trust/qualification/private publication tests reused by named path |
| Profile committed but default update interrupted | P `test_partial_named_publication_and_default_reconciliation` |
| Two names for one device | P `test_named_pairing_real_publication_and_default`, `test_same_device_markers_survive_other_name_and_repair` |
| No trust bypass | P named path real-publication integration; original T `TrustTests.test_declined_empty_eof_noninteractive`, `test_exact_pin_without_prompt_or_fallback` (same trust primitive); CLI exposes no pairing `--yes` |

### connection-diagnostics

| Spec scenario | Automated evidence |
| --- | --- |
| Missing config or dependency | D `test_configuration_and_dependency_failures_have_no_network`, `test_doctor_missing_crypto_in_a_fresh_process` |
| HTTP unavailable but MQTT usable | D `test_http_failure_does_not_block_mqtt_and_exit3_wins` |
| MQTT timeout | D `test_mqtt_tcp_timeout_skips_dependents`, `test_typed_failure_stages_and_compatibility`, `test_shared_deadline_and_no_retries` |
| Changed certificate | D `test_real_transport_pin_before_credentials_and_auth_rejections`; I |
| Rejected authentication or stale reports | D `test_real_transport_pin_before_credentials_and_auth_rejections`, `test_typed_failure_stages_and_compatibility`; T `QualificationTests.test_real_query_drops_stale_then_fails_without_fresh_report` exercises the unchanged fresh-query gate |
| Busy printer | D `test_healthy_busy_report_safe_and_byte_preservation`; I |
| Connected but unsupported firmware | D `test_typed_failure_stages_and_compatibility`, `test_http_failure_does_not_block_mqtt_and_exit3_wins` |
| Structured failure report | D `test_cli_envelope_and_conflict`, `test_configuration_and_dependency_failures_have_no_network`, `test_typed_failure_stages_and_compatibility`; I |
| Healthy target | D `test_healthy_busy_report_safe_and_byte_preservation`; I |
| Installed synthetic diagnosis | I under independent wheel, Debian 13 and Ubuntu 24.04 installations |

## Qualification limits

No printer, private config or live operational state was accessed for validation.
No physical command, executable migration, hosted CI run, release publication or
new hardware qualification is claimed. Qualification remains the previously
recorded Kobra X model 20030 / firmware 2.0.2.2 case. Arbitrary external configs
sharing managed paths cannot be exhaustively discovered; known legacy/managed
references and ambiguous material are retained conservatively. See pairing and
release guides for local recovery and rollback/default-selection limitations.

## PR security follow-up

PR #6's hosted unit/build/Debian/Ubuntu gates passed on `60c7d5d`.
Sonar reported a path-traversal flow into profile-directory deletion. Although
public removal already validates the profile name, cleanup now independently
validates the name and the entire ownership manifest before filesystem access,
and removes only the validated path's final directory component relative to its
opened parent descriptor. A regression test directly supplies traversal names
and manifest paths and verifies rejection before any filesystem operation.
All **153 offline tests** and locked Ruff passed after this hardening. Hosted
checks and Sonar must run again on the resulting commit before merge; no analyzer
suppression, gate change or new hardware qualification is part of this fix.


## CodeRabbit review follow-up

The ten review threads were addressed with legacy symlink compatibility before
registry adoption, explicit orphan-config recovery, stricter fresh-report
identity qualification, and more auditable registry/cleanup/diagnostic helpers.
Managed storage still fails closed after adoption. A first-adoption race test
confirms that managed access acquires the newly created operation lease.

Doctor now requires matching `deviceId` plus `modelId` or `modeId` in the fresh
report. Missing fields fail compatibility; firmware field availability was not
validated on real hardware and is not claimed. Synthetic installed probes supply
explicit identifiers. Pairing's existing identity rules are preserved.

All **156 offline tests** passed, with coverage instrumentation. Additional
assertions verify pin-stage callbacks, credential-send ordering, the actual
60-second deadline, shrinking remaining budgets, and marker-specific duplicate
errors in installed probes. The updated sdist-derived wheel and independent
installed probes passed with the declared locked runtime closure. Hosted Debian /
Ubuntu gates and external review must rerun on this revision before merge.
