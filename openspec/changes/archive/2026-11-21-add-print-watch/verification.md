# Print observation validation

## Kobra X model 20030 / firmware 2.0.2.2

On 2026-11-21 the operator authorized observation of a print already in
progress and first-use pairing. The identity endpoint confirmed model 20030,
and pairing used explicit first-use TLS trust. The capture requested fresh
`info/query` reports approximately every five seconds over pinned MQTT.
It started after print preparation and the first five layers. Times below
are seconds relative to the first fresh report. The capture retains field
types, safe counters and identity comparisons.

| Relative time | Printer state | Active project | Last project |
| --- | --- | --- | --- |
| 0.0 s | `busy` | `printing`, 2%, layer 6/685 | Empty identity and zero counters |
| 661.9 s | `busy` | `printing`, 13%, layer 55/685 | Same baseline |
| 4745.6 s | `busy` | `printing`, 81%, layer 520/685 | Same baseline |
| About 5298.6 s | `busy` | `printing`, 90%, layer 588/685 | Empty identity and zero counters |
| About 5875.1 s | `busy` | `printing`, 99%, layer 685/685 | Same baseline |
| About 5880.1–5895.3 s | `busy` | 99%, layer counters reset to zero, same candidate identity fields | Same baseline |
| About 5900.3–5945.8 s | `free` | Absent | Same baseline, including empty `state` |

The active report uses an integer `progress` and supplies `curr_layer`,
`total_layers`, `print_time` and `remain_time`. The only identity candidates
observed in the active report were `task_id` and `filename`. The string
`task_id` was `"-1"`, also used as the local start request placeholder.
A repeat can use the same filename and placeholder.

The original capture session hit a read timeout after 4745.6 s. Three
independent timed queries received an ACK followed about 39–41 ms after send
by an `info` report whose timestamp was about 14 ms earlier than local send.
The production freshness gate rejected those reports. A separate diagnostic
session resumed at about 5298.6 s with a 60 ms clock correction confined to
the diagnostic process. It kept the correlated ACK gate and required strictly
increasing report timestamps. This left a gap between 81% and 90% and did not
change the CLI or either system clock.

The operator confirmed that the observed print finished normally and worked
perfectly. They had already started a separate print when they confirmed the
outcome. The firmware reports showed the final layer and transition to idle
but supplied no attributable terminal state. The operator's report is the
evidence of physical completion. Watch does not assess part quality.

An installed local CLI run with `--timeout 1` during the same print returned
exit 0, `unknown` and `deadline_expired`, retaining the verified printing
phase, 14% and layer 58/685. It sent only a pinned `info/query`.

The preparation phase allowlist follows KX-Bridge's fixture for states observed
on firmware 2.0.2.2. Those states have their own progress, so watch exposes
only the preparation phase until it can verify printing counters for the same
attempt. [KX-Bridge firmware-state fixture](https://gitea.it-drui.de/viewit/KX-Bridge-Release/src/commit/f0ce700fbcc9b3aed54f1a142b4e0318bc11638e/tests/test_fw2_print_states.py)

## Attempt identity and outcome mappings

- **Confirmed:** safe percent and layer observations are available during
  printing. The observed active `task_id` is a placeholder and the after-print
  `last_project` provides no identity for this job.
- **Ambiguous:** a repeated filename, the placeholder, progress at or near
  100% and a transition to idle cannot distinguish attempts. A changed last
  record also needs a verified attempt match before it can settle an outcome.
- **Untested:** distinct non-placeholder attempt IDs, a same-file replacement
  on hardware and terminal reports from cancellation or failure. None provides
  a positive mapping for this change.

Synthetic cases cover the observed idle transition, an unchanged last project,
full progress alone, candidate terminal labels with inadequate identity,
same-file replacement and unsafe field values. Watch keeps the first verified
job sample and reports `unknown` when continuity cannot be established. There
is no attributable terminal fixture for the observed protocol, so the suite
does not invent a success, cancellation or failure mapping.

## Integration checks

- `uv sync --locked` and the runtime requirements export matched the committed
  lock. Locked Ruff, `sh -n kobra-lan` and strict OpenSpec validation passed.
- `uv run --locked python -m unittest discover -s tests -v` ran 202 tests.
  The devbox skipped two native shell probes because fish and zsh were absent.
  The five completion tests all passed separately in a network-isolated
  Debian 13 environment with bash, fish and zsh installed.
- `scripts/check_python.py` verified the sdist, wheel and independent
  installation. A separate network-isolated run with an empty home verified
  installed watch help and all three completion generators outside the checkout.
- `scripts/build_deb.py`, `scripts/check_deb.py`, Lintian and the package SHA-256
  check succeeded. Lintian reported the existing `initial-upload-closes-no-bugs`
  warning. `scripts/accept_deb.py` ran in networkless Debian 13 and Ubuntu 24.04
  amd64 chroots and verified help and completion after a fresh installation
  and an upgrade. Both acceptance runs used the same package with SHA-256
  `fd81c762558cbfc68be83471eaa6b5f81d1d1f2e967ed27213263e4afe18e07d`.
