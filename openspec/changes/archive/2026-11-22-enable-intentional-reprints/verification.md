# Verification

## Offline and installed checks

- Working tree based on `ea09cf7`, using uv 0.13.9 and Python 3.14.10:
  `uv sync --locked`, `uv run --locked python -m unittest discover -s tests -v`
  (212 discovered, 210 passed, two native shell tests skipped locally),
  `uv run --locked ruff check kobra_lan scripts tests`, `sh -n kobra-lan`,
  and `openspec validate enable-intentional-reprints --strict` passed.
- All five completion tests passed, including Bash, Zsh and Fish, in a
  disposable Debian 13 amd64 environment with networking disabled.
- `scripts/check_python.py` passed the source archive, wheel and independent
  installation checks on Debian 13. The Debian build, `scripts/check_deb.py`,
  `lintian` and `sha256sum --check SHA256SUMS` passed. Lintian reported only
  the expected `initial-upload-closes-no-bugs` warning.
- `scripts/accept_deb.py` passed on clean Debian 13 and Ubuntu 24.04 amd64
  environments with separate empty network namespaces. Both tested the same
  `kobra-lan-cli_0.5.0-1_all.deb` candidate, SHA-256
  `8351ce4e7113ad44dccd2239bae8911c3aba8600fb08464da88b4993f4f6dd05`.
  The installed probes covered help and all three generated completions with
  empty configuration. The test candidate was not published.

## Hardware qualification pending

No printer was contacted. Task 3.2 requires separate authorization and agreed
timing for two deliberate starts of the same stored file on the qualified
Kobra X. Observe activity on the first run, confirm its end with the operator,
then verify shared upload provenance and distinct linked IDs on the reprint.
Record the source of each terminal observation; fresh idle is not proof of
successful completion. Keep ambiguity, concurrency and replay tests offline.
