# Design

## Context

`status` obtains the active and last project through MQTT `info/query`. During the PR 11 capture, the active project used a placeholder `task_id` and `last_project` remained empty after the operator confirmed completion. The stored-file listing describes G-code files. Use the [PR 11 evidence](../archive/2026-11-21-add-print-watch/verification.md) as the baseline for current and last project behavior. See [the proposal](proposal.md) for the scope of the investigation.

## Goals and Boundaries

- Determine what a fresh LAN client can retrieve about past executions with the existing trust model.
- Establish whether a source represents multiple executions, a single last job, or live status. Document observable limits on retention, outcome attribution, and access from another client.
- Treat the app and protocol references as evidence for finding candidate sources. Keep probes read-only, bounded, and limited to operations whose read semantics are supported by documentation or reference code. Use an existing authorized connection for any hardware probe and preserve TLS pin verification before authentication.

## Decisions

### Establish the source before testing coverage

Review the pinned references in [NOTICE.md](../../../NOTICE.md), public material, and, if needed, an available official app build. Trace how the history view gets its data and record evidence for LAN, cloud, or app cache. Record the version or revision of each source. An app screenshot or an offline screen can show that records exist, while a fresh direct query to the printer establishes LAN availability for that source.

### Test retrieval from a fresh session

With separate authorization for device reads and timing agreed with the owner, verify supported candidates from a fresh session with no watcher history. If the current long print is still running and the timing works, collect a baseline near the end and query again after the operator confirms the outcome. If the window has passed, use known completed jobs or a later naturally occurring print. Look for the newly completed job alongside older executions and record whether a known job from another client appears. If two known executions used the same file, check whether their identifiers or other qualified fields distinguish them. Use only available executions and record untested cases.

For each candidate, capture the verified source, model and firmware, query procedure, relative timing, response shape, record count, identifiers and outcome semantics in sanitized form. Record pagination and retention where observable. Treat an ACK, idle, progress, and filenames as insufficient for terminal attribution on their own.

### Base the recommendation on the evidence

Recommend direct on-demand access if fresh LAN requests reliably return distinguishable execution records. Recommend only the proven subset if the source is limited to a last job, selected outcomes, or a narrow retention window. If the tested sources are cloud-only, expose only live status, or remain inconclusive, document the coverage and limitations and leave any local history decision for a later change.

## Risks and Trade-offs

- A missed completion window or a single successful run limits outcome and identity claims. Use retained records where available and identify cases that still need evidence.
- A timeout, an empty response, or an app cache hit can be ambiguous. Record the tested conditions and separate observations from conclusions about source or coverage.
- Keep disposable outputs in a temporary directory and sanitized findings in `verification.md` in this change. If a reusable app analysis setup is needed, record its provenance and keep it in an ignored investigation directory only while the investigation needs it.
