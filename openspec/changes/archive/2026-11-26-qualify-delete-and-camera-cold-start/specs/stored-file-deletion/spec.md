# Spec Delta: stored-file-deletion

## MODIFIED Requirements

### Requirement: Bounded post-delete verification and honest outcome reporting
After a successful `file/deleteBatch` report, the CLI SHALL verify removal on the same pinned session via bounded `file/listLocal` polling and a fresh qualified `info` snapshot without treating acknowledgement as proof of removal. Output SHALL report `delete_observed_removed`, `delete_acknowledged_not_confirmed`, or `delete_uncertain_no_retry`, plus `dry_run: false`, `experimental: true`, and centralized `hardware_delete_validated`.

#### Scenario: Confirmed file removal
- **WHEN** `file/deleteBatch` reports success and subsequent `file/listLocal` polling confirms `<name>` is absent alongside a fresh qualified `info` report on Kobra X model `20030` / firmware `2.0.2.2`
- **THEN** the CLI exits 0 with `status: "delete_observed_removed"`, sanitized `before`, `before_listing`, `ack`, `report`, `after`, `experimental: true`, and `hardware_delete_validated: true`

#### Scenario: Acknowledged delete still listed after bounded polling
- **WHEN** `file/deleteBatch` reports success and bounded `file/listLocal` polling completes cleanly while `<name>` still appears in printer storage
- **THEN** the CLI exits 0 with `status: "delete_acknowledged_not_confirmed"`, sanitized `before`, `before_listing`, `after`, and `after_listing`, and performs no retry

#### Scenario: Post-publish communication, protocol, or interrupt failure
- **WHEN** a timeout, disconnect, protocol error, or foreground interrupt occurs during ACK wait, report wait, or post-delete verification
- **THEN** the CLI exits with the failure's exit class (2 for protocol failure, 3 for I/O or timeout, 130 for interrupt), includes `status: "delete_uncertain_no_retry"` and available safe partial evidence in `result`, and performs no retry
