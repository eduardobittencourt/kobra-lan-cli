# Design

## Context

`printer.snapshot` reads MQTT `info/query` and returns `project` and `last_project` separately. It also makes an HTTP identity request. The qualified firmware can acknowledge `print/query` without a report while idle. Existing start verification records activity through preparation and the first layer. It supplies no validated terminal mapping or evidence of job ID continuity into `last_project`. See [the proposal](proposal.md).

## Goals / Non-Goals

Use fresh pinned telemetry to observe an existing print with bounded resource use and a conservative result for automation. The observer uses in-memory state. Durable job identity, history, receipt migration and physical controls belong to later changes.

## Decisions

### Poll the same pinned MQTT session

Query `info` on one authenticated session at five-second intervals after the initial query, with no catch-up bursts. Start with its current and last project records. The existing query transport handles a correlated ACK and fresh report. Reuse the compatibility predicate used by `doctor` and enforce the qualified model and firmware. Keep the shared profile lease through loading the config and opening the pinned session so its PEMs remain available during TLS setup. Release the profile lease after connection establishment and keep the selected connection fixed.

Use a monotonic deadline, with `--timeout SECONDS` accepting integers from 1 to 259200 and defaulting to 86400. Cap waits, network stages and session cleanup by the remaining budget. Connection failure or a stage timeout before the observation deadline ends this invocation. A stage constrained by the overall deadline reports deadline expiry when that deadline is reached. Preserve the last verified progress on either path. Repeated `status` invocations would add HTTP requests, TLS handshakes and new target resolutions. Streaming unsolicited reports would require separate qualification of their ordering and freshness.

### Follow an attempt only while telemetry can identify it

Normalize a small allowlist of typed scalar fields. Check timestamp freshness through the MQTT query contract and track the initial last-project baseline. Use a firmware identifier or combination of fields only after evidence shows it is stable within an attempt and distinguishes distinct attempts. Use the filename and progress for display only when safe. If identity is insufficient, report only verified observations and finish as unknown when attribution cannot be sustained. A changed active job ends the observation of the original. A fresh, attributable terminal record for the original can still settle it in that same report.

Enable terminal mappings individually when paired telemetry and operator observation substantiate them on the qualified firmware. A successful run provides evidence about completion. Cancellation and failure can be recognized only with separate evidence for those outcomes. Track preparation and printing phases where validated. An ACK, idle transition, unchanged last-project record or full progress alone supplies no terminal evidence.

### Keep automation on the existing output envelope

Use the existing root target and format flags. Emit one final summary on stdout. Send any live progress to stderr with equivalent final text and JSON semantics. Include an outcome, a stable reason, and the last verified phase or progress when available. Exit 0 means observation returned a result, including an attributable printer failure or an unknown result at the deadline. Exit 2 covers validation or protocol failure, 3 covers I/O or connection failure, and 130 covers user interruption. An error after observation includes a safe partial result. A JSON event stream would introduce a second machine-output contract.

## Risks / Trade-offs

- Firmware may report no stable attempt identity or no attributable terminal event. Retain the conservative unknown result and record exactly which tested signals were insufficient.
- The operator may first join after preparation, or a poll may miss a brief transition. Record observed phases and preserve uncertainty when the outcome cannot be established.
- External changes can replace the active project between polls. Keep the initial attempt fixed and test same-file replacement and preexisting last-project records.
- Telemetry can contain private values even in expected fields. Validate field type and content before display and retain only sanitized evidence needed to reproduce a conclusion.

## Migration Plan

The command is additive and uses no new persistent data. Rolling back removes the new command while prior profiles, receipts and attempt markers remain usable.
