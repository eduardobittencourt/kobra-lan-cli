# Design

## Context

See proposal.md for motivation and the five spec deltas for behavior. `cli.py` currently combines argparse construction, routing, exception mapping and JSON printing. Parsing occurs before its exception boundary, so argparse errors do not use the operational result contract. It already has `--version` and global target/state options. `upload.describe` is local; `upload.execute` checks the hash and uses durable reservations. `start.start` already builds a plan, matches a reviewed hash when executing, requires an upload receipt and reserves before publishing.

Profiles and doctor have explicit JSON-only requirements; their deltas replace presentation rules rather than weakening selection or verification. `release-distribution` already permits breaking 0.x minor versions. Package scripts use exact module/document allowlists, and synthetic probes currently parse default JSON and invoke flat commands. These consumers must change with the parser.

## Goals / Non-Goals

**Goals:** establish one canonical command tree, keep presentation separate from operations, make errors scriptable and preserve physical safety and existing on-disk identities.

**Non-Goals:** redesign protocol exchanges, change configuration/receipt schemas, introduce a new job identity, add an interactive wizard, implement raw commands, install completion hooks automatically or contact hardware during validation.

## Decisions

### 1. Keep argparse and explicit global options

Retain the standard-library parser and split construction/routing into small helpers in `cli.py`. Add shared presentation in `cli_output.py` and offline completion generation in `completions.py`, with no new runtime dependency. Root options are `--printer`, `--config`, `--state-dir`, `--json`, `--help` and `--version`; document and complete root options before commands rather than duplicating them on every parser. Disable option abbreviation so execution controls cannot be shortened accidentally.

Canonical leaf signatures retain current operands and guards, except for the approved hierarchy and separation:

```text
printer pair --host IPv4 --name NAME [--default] [--trust-sha256 HASH]
printer list
printer info [NAME]
printer use NAME
printer remove NAME [--yes]
doctor
status
files list
files info NAME
files upload FILE [--name NAME] --sha256 HASH --execute
gcode inspect FILE [--name NAME]
print plan FILE --name NAME --slot N --auto-leveling on|off
    --vibration-compensation on|off --flow-calibration on|off
print start FILE --name NAME --slot N --auto-leveling on|off
    --vibration-compensation on|off --flow-calibration on|off
    --plan-sha256 HASH --execute
completion bash|zsh|fish
```

`printer pair` requires `--name` and rejects both global target selectors. `--config` is an explicit access selector only. Profile-management selector conflicts remain enforced. A missing leaf exits 2 with safe group guidance; explicit `--help` exits 0. Removed leaves fail directly. No alias registry is needed because the owner explicitly waived command compatibility. There is no automatic root-config lookup, unnamed pairing, legacy inventory section or migration. Empty inventory contains only profiles and a null default; selection requires --printer, explicit --config, or a saved named default. Old default strings are invalid rather than translated.

Alternative: switching to a new CLI framework would add dependency and packaging work without solving a requirement that argparse cannot meet.

### 2. Produce one safe result, then render it

Domain operations continue returning dictionaries; neither renderer performs I/O against a printer or mutates state. Make one output boundary responsible for result envelopes and errors. Default text uses labels, compact lists/tables and staged doctor checks; empty inventories are explicit and optional absent data is shown as unknown. Preserve relevant file/plan hashes in copyable full form and show experimental/uncertain outcomes prominently. Avoid color, terminal-width dependencies and terminal control injection from device strings. JSON exposes sanitized operational fields without rebuilding raw reports.

JSON envelope version 1:

```json
{"schema_version": 1, "ok": true, "result": {}}
```

```json
{"schema_version": 1, "ok": false,
 "error": {"code": "invalid_arguments", "message": "Required execution options are missing"}}
```

A failure includes `result` when diagnostics or a partial local outcome provide safe structured information. Retain existing per-command result keys where useful, including doctor's inner `version: 1`; the new outer schema and its command-specific payloads are documented together. Compatibility with old stdout is explicitly unnecessary. Persistent receipts are not rewritten to match display envelopes.

Stable coarse error codes are `invalid_arguments` (exit 2), `validation_failed` (exit 2), `operation_failed` (exit 3) and `diagnostic_failed` (exit determined by diagnostic stage precedence). Retain safe domain/stage codes inside results where already available. Help/version/completion are native text, including when a root `--json` flag is present; they are explicitly excluded from the operational envelope.

Alternative: TTY-based output switching is rejected because redirection should not alter semantics. JSON-only output would leave the accepted human-facing interface incomplete.

### 3. Bring parsing into the safe failure boundary

Use a parser error override that records safe command/option context rather than printing argparse's raw interpolated argument values. Resolve explicit root JSON mode even on parsing failure using a root-option-aware pass, never by scanning arbitrary positional strings or reading config. Missing or malformed execution flags/hashes are rejected before opening registry leases, network sessions or writing reservations. Do not include arbitrary paths, token-bearing URLs or exception bodies in parse diagnostics. Standard help can list expected options and fixed choices.

Prompts and progress remain on stderr. A final operational failure is a result on stdout in the selected format; its exit status carries failure. Keep the existing no-hang behavior for noninteractive trust and removal, and do not add implicit confirmation because stdout is redirected or JSON was requested.

Alternative: wrapping raw argparse messages in JSON would make the shape consistent but risk echoing sensitive supplied values.

### 4. Adapt submission commands around existing safety engines

`gcode inspect` delegates to local `describe`. `files upload` is execution-only with both `--execute` and full 64-hex SHA-256 required. A valid invocation calls the existing execution path; it never calls start. `print plan` calls the current read-only plan path. `print start` uses the same explicit inputs plus execution controls and calls the current guarded start path. It always rebuilds the plan rather than accepting editable saved JSON as authority.

Keep the existing canonical plan digest inputs; presentation fields such as profile labels and format never affect the digest. Show safe target selection metadata separately from the canonical plan if needed. Revalidate local bytes, device, remote metadata, slot/material/preparations and idle status as today. A different execution-relevant plan requires another review. Preserve existing receipt requirements, reservation paths, statuses and before-send ordering. No new operation identity or retry mechanism is introduced.

The complete documented workflow is:

```sh
kobra-lan printer pair --name bench --host 192.0.2.10 --default --trust-sha256 FINGERPRINT
kobra-lan printer list
kobra-lan --printer bench doctor
kobra-lan gcode inspect model.gcode --name model.gcode
kobra-lan --printer bench files upload model.gcode --name model.gcode --sha256 FILE_HASH --execute
kobra-lan --printer bench print plan model.gcode --name model.gcode --slot 1 --auto-leveling on --vibration-compensation off --flow-calibration off
kobra-lan --printer bench print start model.gcode --name model.gcode --slot 1 --auto-leveling on --vibration-compensation off --flow-calibration off --plan-sha256 PLAN_HASH --execute
kobra-lan --json --printer bench status
```

These are documentation examples, not authorization to run hardware actions. Real reviewed hashes replace placeholders; the start remains experimental. Upload metadata verification is not remote byte-hash verification, and start observation is not completion.

### 5. Generate completions without live discovery

`completion` returns shell-native script text from packaged Python code. Keep the supported command/flag/choice map aligned with parser metadata and cover local file operands; do not implement dynamic printer-name lookups. No generated script runs operational subcommands while completing. Document shell-specific user installation steps without modifying startup files. Generation works from wheel, sdist-installed wheel and Debian installation without source files or shell executables. Validate native script loading/completion in bash, zsh and fish where the acceptance environment supplies them; explicitly record a missing-shell limitation instead of claiming runtime validation.

Alternative: installed global completion files create multiple filesystem layouts and privileges to maintain. The generator gives all installation channels the same entry point.

### 6. Update every packaging and documentation consumer

Add new Python modules to exact allowlists in `scripts/check_python.py` and `scripts/build_deb.py`, and update related tests. Since completion code lives in the package, no unrelated package-data mechanism is needed. Update `scripts/probe_pairing.py`, `scripts/probe_profiles.py`, installed diagnostics tests and package acceptance invocations to opt into JSON explicitly and use new command paths. Update `scripts/accept_deb.py`, man page `debian/kobra-lan.1`, README, usage/pairing guides, roadmap, release/development documentation and examples where applicable. Do not modify old archived OpenSpec history to rewrite old command names.

Prepare `kobra_lan.__version__ = 0.5.0` and matching changelog notes through the existing single-source policy. Update documentation examples using the selected source version as appropriate. GPL-3.0-only, NOTICE attribution and exclusions of private data remain intact. Release workflows remain gated; this change creates no tag or public artifact.

## Risks / Trade-offs

- Default text breaks current probes and local scripts: update repository consumers atomically and document explicit `--json`; no compatibility layer.
- Two renderers can hide different safety information: use identical synthetic results to verify hashes, target, preparation, qualification and uncertainty in both modes.
- Parser diagnostics can echo hostile input: use safe structured errors and adversarial synthetic tests for both streams and both formats.
- Completion metadata can drift: compare emitted command/option choices against parser structure and smoke-test shell behavior.
- Interface refactoring can accidentally change device/file reservation keys: retain existing state formats and test old synthetic markers through new command routes and alternate profiles.
- Existing firmware evidence is narrow: keep qualification and experimental labels visible; installed tests never claim hardware acceptance.

## Migration Plan

Implement and validate in a normal change branch. Replace commands and consumers together and prepare source version 0.5.0 without publication. Remove unnamed access and legacy selection without migration or compatibility code. The owner authorized a one-time local data reset. This one-time local action is separate from package lifecycle behavior and is not a CLI capability. Newly created profiles retain the existing private publication, trust and device-based reservation guarantees. No physical operation is authorized by the reset or implementation.

## Named-only setup revision

The owner rejected legacy compatibility after testing unnamed pairing. Registry default is now null or a registered profile name object. Profiles and default are the entire local inventory; arbitrary root config files are never discovered or consulted for selection/cleanup. Explicit config access remains useful for deliberate diagnostics and recovery of a complete named publication. No conversion, default promotion or automatic re-pairing occurs. Runtime profile removal still protects shared managed files and never clears operational markers.

## Doctor qualification revision after device validation

The qualified firmware's MQTT info report omits `deviceId` and numeric model IDs.
Doctor must align with pairing: the pinned authenticated session must return the
qualified model name, firmware and valid state; optional IDs must match whenever
supplied. Absence of optional IDs is disclosed in the compatibility message and
does not fail the connection. Missing required evidence uses
`qualification_incomplete`; conflicting or invalid supplied values retain
`outside_qualification` and take precedence. No extra HTTP identity request,
query, retry or trust update is added. Certificate pin/auth ordering, deadline,
stage/envelope shape, exit precedence and physical-operation limits are unchanged.
Offline and installed probes must cover the real report shape, incomplete
required evidence and contradictory optional identifiers.

## PR review follow-up

Bash file-completion branches enable filename quoting so spaced paths remain
one operand. Uploads use a nonblocking per-device lease in shared state storage
from preflight through verification, preserving existing hash-based markers.
The lock inode remains after release. Other clients/state directories do not
participate in this coordination; atomic firmware-side exclusion is not claimed.
