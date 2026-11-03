# Security policy

This experimental project has no long-term supported release branches. Security
fixes target the current development version; update after reviewing compatibility
and state migration notes. No response-time or remediation SLA is promised.

## Report privately

Do not post vulnerabilities, real credentials or private configuration in issues,
PRs or public logs. Use [GitHub private vulnerability reporting](https://github.com/eduardobittencourt/kobra-lan-cli/security/advisories/new).
If that channel is unavailable, email the maintainer at
[eduardo@bittencourt.dev](mailto:eduardo@bittencourt.dev).
Include affected versions, a minimal synthetic reproduction, impact and relevant
sanitized evidence. Agree on disclosure with the maintainer before publishing.

## Protocol and operational boundaries

See [initial trust](docs/pairing.md), [operation guarantees](docs/usage.md) and
[reviewed firmware constraints](docs/pairing-security-review.md). Unauthenticated
HTTP provisioning and firmware-defined cryptography remain risks. Accepted
analyzer findings are not claims that those risks were fixed. Qualification is
limited to model 20030 / firmware 2.0.2.2; other devices need separate review.
Never include live printer keys, receipts, pins tied to private identities, or
token-bearing URLs in a report. Do not operate hardware to demonstrate a flaw
without the owner's explicit authorization.
