# Project instructions

## Map

- `kobra_lan/`: CLI, protocol, pairing, state and safety checks.
- `tests/`: offline unittest suite with synthetic transports and fixtures.
- `scripts/`, `debian/`: package/release gates and disposable acceptance.
- `.github/workflows/`: shared package checks, tests and release.
- `docs/README.md`: maintained documentation index.
- `openspec/`: project specifications and change planning.

Read CONTRIBUTING.md for setup, checks and review requirements. Use Python >=3.11
and the committed uv lock: `uv sync --locked`. Verify with
`uv run --locked python -m unittest discover -s tests -v` and `sh -n kobra-lan`.
Run `uv run --locked ruff check kobra_lan scripts tests` for lint.
For distribution changes, run the relevant gates documented in docs/releases.md.

## Constraints

Keep changes scoped; preserve JSON/exit-code contracts and the single package
version source. Documentation and community files are in English. Update links
and packaging consumers when moving files. Preserve GPL-3.0-only and NOTICE.md.

Never read out, log or commit real configs, PEMs, tokens, token-bearing URLs,
receipts or private state. Use synthetic fixtures. Offline tests must not access
printers. Do not operate hardware without explicit authorization for that action.
Preserve explicit initial trust, TLS pin verification before credentials, private
atomic config publication without replacement, reviewed hashes and durable
reservations. Never clear markers for retries, replay uncertain commands or
change existing access as part of verification. See docs/pairing.md and
docs/usage.md for the operational boundaries.

Run only unprivileged contribution checks for fork/Dependabot code. Never expose
secrets through privileged PR events or execute untrusted artifacts in a
privileged job. Do not weaken analyzer gates, suppress findings or reduce
required approvals merely to pass CI. Record concrete blockers and limitations.
