# Contributing

The client is experimental and initially qualified only for Kobra X model 20030 /
firmware 2.0.2.2. Read the [documentation map](docs/README.md),
[code of conduct](CODE_OF_CONDUCT.md) and [security policy](SECURITY.md).
Report vulnerabilities privately; public issues are for sanitized nonsecurity
reports. Hardware qualification claims require specific evidence.

## Reproducible development

Use Python >=3.11 and uv (CI currently pins uv 0.13.5). No printer, daemon, cloud
account or private configuration is needed for offline checks. Three synthetic
Debian-documentation tests additionally use `dpkg-deb` (provided by `dpkg` on
Debian/Ubuntu); they are skipped when it is absent. CI runs those probes.

```sh
git clone https://github.com/eduardobittencourt/kobra-lan-cli.git
cd kobra-lan-cli
uv sync --locked
uv run --locked ruff check kobra_lan scripts tests
uv run --locked coverage run -m unittest discover -s tests -v
uv run --locked coverage xml
uv run --locked coverage report
sh -n kobra-lan
uv export --locked --no-dev --no-emit-project --no-header --no-annotate \
  --format requirements-txt | diff -u requirements-runtime.txt -
```

The source launcher uses `/usr/bin/python3`; install distro
`python3-cryptography` to use it, or use `.venv/bin/kobra-lan` after syncing.
Use the project's declared development dependencies, not global packages.
Initial lint checks syntax and Pyflakes (`E9`, `F`); formatting is not enforced.
See [release checks](docs/releases.md) for Python archive, Debian build, lintian
and Debian 13/Ubuntu 24.04 acceptance commands when distribution inputs change.

## Changes and reviews

Keep changes focused and add meaningful offline tests for changed behavior.
Preserve JSON contracts, exit codes and the package's single version source
`kobra_lan.__version__`. Do not add CLI features to a documentation/tooling change.
Update consumers when moving documentation, including `MANIFEST.in`, Debian
packaging and archive checks. Preserve GPL-3.0-only and attribution in NOTICE.md.

Open a PR with the problem, resulting behavior, validation and any limitations.
Follow the [maintenance policy](docs/maintenance.md): one eligible approval,
resolved discussions and universal checks are required. New commits invalidate
old approvals. A bot comment or successful check is not an approval. Fork and
Dependabot checks run without repository secrets; record when external analysis
is unavailable and obtain an eligible human review if needed.

For dependency updates, update `uv.lock`, regenerate `requirements-runtime.txt`
using the export command in [maintenance](docs/maintenance.md), and verify both.
Do not add development tools to runtime requirements.

## Secrets and physical operations

Never commit real configuration, credentials, PEMs, tokens, token-bearing URLs,
upload receipts or private printer state. Sanitize logs and issue attachments;
use synthetic identities, addresses and keys in tests. Do not print private
configuration to diagnose a failure.

Automated tests must never contact real printers. Pairing, upload and print
start require separate explicit authorization for the relevant device/action.
A code change does not authorize hardware operations. Preserve initial-trust
consent, TLS pinning before authentication, no-replacement config publication,
reviewed file/plan hashes and durable attempt reservations. Never remove markers
to force a retry, auto-update mismatched pins, overwrite existing access or
repeat ambiguous physical commands. Read [pairing](docs/pairing.md) and
[operation guarantees](docs/usage.md) before any authorized manual validation.
