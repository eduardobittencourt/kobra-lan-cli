# Tasks

## 1. Qualify telemetry

- [x] 1.1 With explicit authorization for read-only observation, compare fresh pre-terminal and post-terminal `info` observations for an existing print against its operator-observed outcome. Record the model, firmware, relative timing, sanitized field transitions and physical outcome in the project validation evidence. Use the ongoing run if still available and record which phases were missed. This task is verified by the documented paired observations and needs no new start or intervention.
- [x] 1.2 Identify which fields can safely tie a terminal record to the original attempt. Record confirmed, ambiguous and untested cases in the validation evidence and encode supported cases and counterexamples in synthetic fixtures. Require distinct evidence for any enabled cancellation or failure mapping. Verify that unsupported outcomes and insufficient identity remain unknown.

## 2. Observe an active print

- [x] 2.1 Implement the bounded single-session `info` polling path using existing pinned authentication and qualification. Test deadlines during setup and polling, pin refusal before MQTT credentials, stale reports, network closure, interruption and the absence of control requests, reconnection or state writes.
- [x] 2.2 Implement attempt attribution and safe progress and outcome extraction with the evidence from group 1. Test idle startup, a job from another client, attributable terminal reports, unchanged last-project data, full progress without terminal evidence and a replacement attempt with the same filename. Verify that partial results retain only validated fields and that nested or unsafe field content stays out of output.

## 3. Expose and document the command

- [x] 3.1 Route `print watch` through the common target selection and output paths. Test named, default and explicit selection, profile lease release after TLS setup, equivalent text and JSON outcomes, a single JSON document, invalid timeout before network access, partial results and exit codes 0, 2, 3 and 130.
- [x] 3.2 Update installed help, generated completions, README and usage with timeout, outcome, qualification and hardware evidence. Exercise help and completion outside the checkout with no config or network. Verify that the documentation distinguishes observation outcome, CLI exit status and part quality.

## 4. Check integration

- [x] 4.1 Run locked Ruff and the full offline unittest suite, check the shell launcher with `sh -n kobra-lan`, and run the relevant installed package probes for help and completion on supported targets. Record results and any remaining hardware evidence gaps.
