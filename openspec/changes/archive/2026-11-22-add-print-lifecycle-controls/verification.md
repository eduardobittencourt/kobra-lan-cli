# Print lifecycle control verification

## Hardware validation (2026-11-23)

On 2026-11-23 the operator authorized a live Kobra X (model 20030 / firmware
2.0.2.2) qualification session covering `print pause`, `print resume`, and
`print cancel` on a small dedicated single-part PLA High Speed print (48 layers,
slot 2, `auto-leveling on`, `vibration-compensation off`, `flow-calibration off`),
with `task_id` reported as `"-1"` throughout.

### Pre-flight guards (all exit 2, zero publish)

- Omitting `--execute` on `pause`, `resume`, and `cancel` failed locally with
  `invalid_arguments`.
- Running `pause --execute`, `resume --execute`, and `cancel --execute` while
  idle (`state: "free"`) failed with `validation_failed`.
- During preparation (`nozzle_heating`), `pause --execute`, `resume --execute`,
  and `cancel --execute --filename <wrong>` failed with `validation_failed`.
- During active `printing` (layer 4/48), `resume --execute` and
  `pause --execute --filename <wrong>` failed with `validation_failed`.
- During `paused` (layer 4/48), `pause --execute` and
  `resume --execute --filename <wrong>` failed with `validation_failed`.
- During transitional `stopping`, `cancel --execute` failed with
  `validation_failed`.

### Live control transitions

| Action | Wire action | Pre-flight state | ACK | Bounded 5 s poll outcome | Subsequent `status` observation |
| --- | --- | --- | --- | --- | --- |
| `print pause --execute --filename ...` | `pause` | `printing` (layer 4/48, 16%) | `code: 0` | `control_observed_paused` (`project.state: "paused"`, layer 4/48) | `busy`, `project.state: "paused"` |
| `print resume --execute --filename ...` | `resume` | `paused` (layer 4/48, 16%) | `code: 0` | `control_acknowledged_not_confirmed` (`project.state: "resuming"`) | `busy`, `project.state: "nozzle_purging"` (`progress: 16`, `curr_layer: 0`, `total_layers: 0`) |
| `print cancel --execute --filename ...` | `stop` | `nozzle_purging` (during resume) | `code: 0` | `control_acknowledged_not_confirmed` (`project.state: "stopping"`, layer counters restored to 4/48) | ~30 s later: `state: "free"`, `print: null`, heater targets `0`, `last_print` empty |

### Findings and remaining limits

- All three MQTT `print` control wire actions (`pause`, `resume`, `stop`) were
  accepted (`code: 0`) with `taskid: "-1"` and drove the expected physical and
  telemetry transitions on Kobra X model 20030 / firmware 2.0.2.2.
- On firmware 2.0.2.2, `resuming` and `stopping` routinely exceed the bounded
  5-second post-ACK polling window; returning `control_acknowledged_not_confirmed`
  without replaying is accurate and expected.
- **Terminal-signal finding for `print watch`:** After cancellation settled to
  `state: "free"`, `last_print` remained completely empty (`state: ""`,
  `filename: ""`, zero counters), matching normal completion. Firmware 2.0.2.2
  therefore does not expose an attributable cancel signal in `last_project`
  after returning to idle, so `print watch` retains `outcome: "unknown"`.
- Existing profiles, upload receipts, start receipts, `.attempt` markers, and
  watch observations remained untouched across all three control invocations.
- **Scope note:** Controls remain `experimental: true` while reporting
  `hardware_control_validated: true` on the qualified Kobra X model 20030 /
  firmware 2.0.2.2 target. Direct `cancel` from `printing` or `paused` and a
  full `resume` back into `printing` were not separately timed; uncertain
  post-publish failures and lock contention remain covered by offline tests.
