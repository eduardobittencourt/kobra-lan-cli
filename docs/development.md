# Development and validation

With uv, use the committed development dependency lock:

```sh
uv sync --locked
uv run --locked ruff check kobra_lan scripts tests
uv run --locked coverage run -m unittest discover -s tests -v
uv run --locked coverage xml
uv run --locked coverage report
```

With distro Python and `python3-cryptography` already installed, use
`/usr/bin/python3 -m unittest discover -s tests -v`.

The original 28 offline application tests cover multipart preservation, MQTT framing, TLS pinning, response correlation, hashes, dry runs, existing files, busy state, slot/material mapping, reviewed plans, scoped hardware qualification, upload receipts, ACK versus confirmation, and timeouts without replay. Additional release tests cover version rejection, draft recovery, acceptance gates and asset verification. Automated tests never access real printers.


See [CONTRIBUTING.md](../CONTRIBUTING.md) for the full contribution workflow.
