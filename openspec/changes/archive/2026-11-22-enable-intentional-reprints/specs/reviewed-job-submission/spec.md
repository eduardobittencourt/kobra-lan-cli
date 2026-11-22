# Spec Delta

## MODIFIED Requirements

### Requirement: Existing device state remains authoritative
The CLI SHALL preserve configuration, credentials, existing device-based receipts, reservation paths, permissions and custom `--state-dir` behavior. A first start SHALL retain the existing device/file guard. Existing start records SHALL be interpreted in place and SHALL continue blocking ordinary start. Only the explicit reviewed reprint workflow can authorize a successor to an eligible attempt.

#### Scenario: Old marker with new command
- **WHEN** an existing-format attempt is accessed through the current command tree or another profile for the same device
- **THEN** ordinary start retains the same duplicate protection and preserves the original files and permissions

#### Scenario: Legacy attempt is eligible
- **WHEN** a legacy marker and matching receipt establish an observed-active start for the selected device and file
- **THEN** planning exposes a stable local reference and applies the same reprint checks as for newly created attempts
- **AND** a reprint preserves both legacy files and the verified upload receipt

#### Scenario: Legacy evidence is incomplete
- **WHEN** a prior marker has a missing, malformed or inconsistent receipt, or a receipt exists without its matching marker
- **THEN** both ordinary start and explicit reprint refuse to send a print command for that device and file

## ADDED Requirements

### Requirement: Local identity for each start attempt
Each durably reserved start SHALL have a stable local attempt ID independent of firmware task IDs and distinct from other executions of the same file. The state SHALL associate the attempt with its device, file and plan, and record its predecessor for a reprint. Text and JSON SHALL expose safe attempt references and available start evidence.

#### Scenario: Two deliberate runs share the same stored file
- **WHEN** an initial start and its eligible reviewed reprint are reserved
- **THEN** each has its own durable attempt ID and evidence record, and the second record links to the first
- **AND** the upload receipt remains usable as provenance for both

#### Scenario: Result becomes uncertain after reservation
- **WHEN** the CLI can report a safe partial result for an uncertain start
- **THEN** it includes the reserved attempt ID and known evidence without claiming completion

### Requirement: Review an intentional reprint
`print plan --reprint-from PREVIOUS_ATTEMPT_ID` SHALL bind the review hash to the immediate predecessor for the selected device and file. Planning SHALL remain read-only and retain existing file, metadata, material and qualification checks. Ordinary planning SHALL preserve its hash semantics and expose a safe reference to the latest local attempt when available.

#### Scenario: Review context changes
- **WHEN** the reviewed predecessor, file, target or execution choices differ at execution
- **THEN** the prior reviewed hash grants no authorization to publish a start

#### Scenario: Wrong or superseded predecessor
- **WHEN** planning specifies an attempt for another device or file, or one that already has a successor
- **THEN** planning refuses and creates no reservation

### Requirement: Execute an intentional reprint once
`print start --reprint-from PREVIOUS_ATTEMPT_ID` SHALL require the matching reprint review and `--execute`, the existing verified upload receipt, and a fresh idle report immediately before reservation. It SHALL require the predecessor to have recorded observed-active start evidence and SHALL reserve at most one successor per predecessor before publishing one start command.

#### Scenario: Deliberate reprint on an idle printer
- **WHEN** the current predecessor has observed-active start evidence and the fresh plan, verified upload provenance, reviewed hash and final idle check pass
- **THEN** the CLI durably reserves a successor and publishes one start without another upload
- **AND** the prior run's terminal outcome remains unclassified by the reprint

#### Scenario: Unresolved predecessor
- **WHEN** the predecessor is reserved, interrupted, acknowledged without observed activity, otherwise uncertain or unreadable
- **THEN** reprint refuses even when fresh telemetry shows idle

#### Scenario: Replayed or competing review
- **WHEN** a predecessor already has a reserved successor or concurrent executions compete to use it, including with different plan hashes or profile names
- **THEN** at most one execution reserves a successor and publishes a start in the shared device state
- **AND** later invocations preserve the existing reservations and publish nothing for that predecessor

#### Scenario: Printer becomes busy
- **WHEN** the final read shows an active job or fails to establish fresh idle state
- **THEN** the CLI creates no successor and publishes no start
