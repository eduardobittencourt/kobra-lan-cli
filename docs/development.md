# Development and validation

With uv, use the committed development dependency lock:

```sh
uv sync --locked
uv run --locked ruff check kobra_lan scripts tests
uv run --locked coverage run -m unittest discover -s tests -v
uv run --locked coverage xml
uv run --locked coverage report
```

With `/usr/bin/python3` 3.11 or newer and `python3-cryptography` already installed, use
`/usr/bin/python3 -m unittest discover -s tests -v`.

The original 28 offline application tests cover multipart preservation, MQTT framing, TLS pinning, response correlation, hashes, dry runs, existing files, busy state, slot/material mapping, reviewed plans, scoped hardware qualification, upload receipts, ACK versus confirmation, and timeouts without replay. Additional release tests cover version rejection, draft recovery, acceptance gates and asset verification. Automated tests never access real printers.


See [CONTRIBUTING.md](../CONTRIBUTING.md) for the full contribution workflow.

CI also instruments the existing Python archive and Debian build/content gates.
The build container installs the hash-locked dev wheels into an isolated tooling
directory; those tools are not packaged or installed in application acceptance
environments. Sonar imports unit `coverage.xml` and `build-coverage.xml` from the
same run. Package scripts executed only in these gates are not covered by the
local unit-only report. Both sets of checks must succeed before analysis.

## CLI 0.5.0 contract checks

The offline suite covers the canonical command tree, sanitized parser failures,
root option placement, text and version-1 JSON, reviewed execution routes and
device markers preserved by normal operations. Named-only pairing and null
defaults are tested without legacy conversion or root-config discovery. Completion metadata is derived from argparse; bash
and fish smoke tests run when available, and missing shells are explicitly
skipped. Installed archive/Debian probes use `--json` before operational
commands and exercise `gcode inspect`, all completion generators and safe parse
failures outside the checkout. See [usage](usage.md) for the supported workflow.
