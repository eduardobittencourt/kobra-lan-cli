## Problem and resulting behavior

## Validation

List offline checks and relevant package gates, with results and limitations.
For dependencies, verify uv.lock and the derived runtime export.

## Review checklist

- [ ] Scope and compatibility are explained; documentation/packaging consumers are updated.
- [ ] No real credentials, private state or token URLs are included.
- [ ] Automated checks do not contact printers; any manual physical operation had explicit authorization.
- [ ] Hash review, TLS trust, no-replacement state and no-replay guarantees are preserved.
- [ ] External analysis availability is recorded; any unavailable Sonar/CodeRabbit review has an explicit review path.

One eligible approval is required; a completed check or bot comment is not an approval.
Vulnerabilities belong in the private channel in SECURITY.md.
