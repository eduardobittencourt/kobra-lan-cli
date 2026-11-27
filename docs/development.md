# Development and validation

With uv, use the committed development dependency lock:

```sh
uv sync --locked
uv run --locked ruff check kobra_lan scripts tests
uv run --locked coverage run -m unittest discover -s tests -v
uv run --locked coverage xml
uv run --locked coverage report
```

With `/usr/bin/python3` 3.11 or newer and `python3-cryptography` already installed on Linux, use
`/usr/bin/python3 -m unittest discover -s tests -v`. On macOS (`arm64`), use Python `>=3.11`
via `uv sync --locked` or an isolated virtual environment (Apple's `/usr/bin/python3` is 3.9);
optional `ffmpeg` on `PATH` is needed only if running live `camera snapshot` commands.
See [macOS installation](releases.md#macos-arm64-source-and-wheel-installation) for setup details.

The original 28 offline application tests cover multipart preservation, MQTT framing, TLS pinning, response correlation, hashes, dry runs, existing files, busy state, slot/material mapping, reviewed plans, scoped hardware qualification, upload receipts, ACK versus confirmation, and timeouts without replay. Additional release tests cover version rejection, draft recovery, acceptance gates and asset verification. Automated tests never access real printers.


See [CONTRIBUTING.md](../CONTRIBUTING.md) for the full contribution workflow.

CI also runs a dedicated macOS (`macos-latest`, `arm64`) offline job covering
`ruff`, `sh -n kobra-lan`, `./kobra-lan --version`, the locked offline unit
suite with non-skipping native `zsh` completion verification, and
`scripts/check_python.py` outside-checkout wheel/sdist acceptance against
hash-locked `requirements-runtime.txt` wheels. On Linux, CI also instruments the
existing Python archive and Debian build/content gates.
The build container installs the hash-locked dev wheels into an isolated tooling
directory; those tools are not packaged or installed in application acceptance
environments. Sonar imports unit `coverage.xml` and `build-coverage.xml` from the
same run. Package scripts executed only in these gates are not covered by the
local unit-only report. Both sets of checks must succeed before analysis.

## CLI 0.5.0 contract checks

The offline suite covers the canonical command tree, sanitized parser failures,
root option placement, text and version-1 JSON, reviewed execution routes and
device markers preserved by normal operations. Named-only pairing and null
defaults are tested without legacy conversion or root-config discovery. Completion metadata is derived from argparse; bash,
zsh, and fish smoke tests run when available (missing shells are explicitly
skipped, Bash 4+ readline escaping skips only on Bash `< 4` such as stock macOS
Bash 3.2, and macOS CI requires native `zsh` without skipping). Installed archive/Debian probes use `--json` before operational
commands and exercise `gcode inspect`, all completion generators and safe parse
failures outside the checkout. See [usage](usage.md) for the supported workflow.
