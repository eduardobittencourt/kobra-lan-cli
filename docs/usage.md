# Operation and protocol guarantees

The examples use the source-checkout launcher. After installation, use `kobra-lan`.

## Output and exit contract

Output is readable English text by default, including when redirected. Put
`--json` before the command for one JSON document. Prompts and progress use
stderr; final successes and failures use stdout. No renderer queries a printer
or writes operational state. Help, version and `completion` always emit native
text, even with root `--json`.

```sh
kobra-lan --json printer list
kobra-lan --json --printer bench doctor
```

Version 1 success: `{"schema_version":1,"ok":true,"result":{"profiles":[],"default":null}}`.
Failure: `{"schema_version":1,"ok":false,"error":{"code":"invalid_arguments","message":"Invalid arguments; use kobra-lan --help for supported commands and required options"}}`.
An operational failure retains `result` when safe partial information is available.
Do not parse human text; optional absent fields render as unknown and empty
collections as none. URLs and terminal controls are removed from display strings.
The output envelope does not change private receipt or registry schemas.

| Error code | Exit | Meaning |
| --- | --- | --- |
| `invalid_arguments` | 2 | Parser failure or malformed required execution hash |
| `validation_failed` | 2 | Selection, trust, protocol, qualification or reviewed-content refusal |
| `operation_failed` | 3 | Configuration, dependency, I/O or network failure; may retain local partial outcome |
| `diagnostic_failed` | 2 or 3 | Failed ordered doctor checks; exit 3 takes precedence |

Every result also includes a `qualification` string with the narrow model/firmware and experimental-start boundary. The `result` payloads retain these command-specific fields. Consumers should
allow additional safe fields and inspect outcome flags rather than infer success
from a filename or network acknowledgement.

| Command | Result shape |
| --- | --- |
| `printer pair` | `config_path`, `model_id`, `firmware`, `tls_sha256`, plus named `name`/`default` |
| `printer list` | `profiles` array, `default` (null or named selection); entries report availability |
| `printer info` | Selection metadata, `config_path`, `available`, host/device/model/firmware/pin metadata |
| `printer use` | `name`, `default` |
| `printer remove` | `name`, `registration_removed`, `deleted_files`, `preserved_files`, cleanup outcome |
| `doctor` | Inner `version: 1`, safe `target`, ordered `checks`, `healthy` |
| `status` | `identity`, sanitized `info`, nullable `print`, `last_print` |
| `files list` | `records` array of filename/size/directory metadata |
| `files info` | `filename` and available safe file details |
| `gcode inspect` | `sha256`, `md5`, `size_bytes`, `remote_filename`, nullable `layer_count`, `slicer_version`, operation/qualification flags |
| `files upload` | Manifest, verification/status flags, timestamp and `receipt_path` |
| `print plan` | `file_sha256`, `device_digest`, model/firmware, canonical `payload`, `plan_sha256`, slot and experimental/qualification flags |
| `print start` | Plan fields, `dry_run: false`, status/ack/observation evidence and `receipt_path` |

Both formats preserve full review hashes, experimental qualification and uncertain
outcomes. Upload metadata confirmation does not prove remote byte equality;
start acknowledgement and observed activity do not prove completion or quality.

## Inspect, upload, plan and start

Set up access with `printer pair --name bench --host 192.0.2.10 --default
--trust-sha256 FINGERPRINT`, inspect `printer list`, then diagnose with
`--printer bench doctor`. Pairing needs an independently trusted full fingerprint.
Read [initial trust](pairing.md) before any provisioning.

```sh
kobra-lan gcode inspect model.gcode --name model.gcode
kobra-lan --printer bench files upload model.gcode --name model.gcode --sha256 FILE_HASH --execute
kobra-lan --printer bench print plan model.gcode --name model.gcode --slot 1 \
  --auto-leveling on --vibration-compensation off --flow-calibration off
kobra-lan --printer bench print start model.gcode --name model.gcode --slot 1 \
  --auto-leveling on --vibration-compensation off --flow-calibration off \
  --plan-sha256 PLAN_HASH --execute
```

Replace FILE_HASH with the full SHA-256 from inspection and PLAN_HASH with the
full reviewed plan digest. `files upload` has no implicit dry run and never
starts a print. `print plan` never uploads, starts or writes an attempt. Review
the device digest, filename, slot, material/color mapping and all three
preparation settings in either format. The final start rebuilds that plan;
changed execution inputs require fresh review. These examples do not authorize
physical actions. Only execute when the particular upload or print is authorized.

`uploaded_verified_by_listing_and_metadata` means metadata checks passed and
`remote_byte_hash_verified` remains false. `start_acknowledged_not_confirmed`
means an acknowledgement without observed activity; `start_observed_active`
means bounded observation saw the selected project active. Uncertain results
retain durable reservations and explicitly forbid automatic resend. No outcome
here claims completed printing or physical quality. Existing configs, receipts
and device/file markers, including under `--state-dir`, remain authoritative.

## Experimental print start

`print plan` only queries the printer and builds a plan. It requires an already uploaded file, slot **1..4** (human numbering), matching material, one color/paint index 0, and the onboard four-slot configuration. External ACE units and multicolor prints are not supported in this version.

```sh
./kobra-lan print plan /path/to/model.gcode --name agent-model.gcode --slot 1 \
  --auto-leveling on --vibration-compensation off --flow-calibration off
```

All three preparation options are required. The example does not claim to reproduce the graphical application's defaults. Both formats include the payload and full `plan_sha256`. Changing the file, slot, or options changes the hash. The plan includes `experimental=true`; `hardware_start_validated=true` only for the observed configuration described above, and false for other combinations. This flag describes the start operation, not the quality of an arbitrary model.

To request execution later, use `print start` with the same explicit arguments plus `--execute --plan-sha256 REVIEWED_PLAN_HASH`. This is a physical action: run it only when printing is authorized and the printer is prepared. It requires a verified upload receipt from this CLI, rechecks the file/state/material, and writes a durable reservation before publishing **one** MQTT `print/start` command. It does not upload again. An ACK is not treated as proof of physical printing; the client subsequently queries the active project and distinguishes observed activity from an uncertain result. It never automatically repeats the command.

## Guarantees and limitations

- Upload is currently qualified only for model 20030 / firmware 2.0.2.2, Next-generated G-code, and the Kobra X profile. It requires an idle printer with no active project.
- Hashing and multipart construction use the same bytes in memory. No G-code translation, `print=true` flag, or HTTP redirects.
- Exclusive reservations are persisted with fsync per device and file hash in `~/.local/share/kobra-lan/uploads/`. Upload and start use separate markers. A second attempt is blocked after success or timeout, including across processes and restarts.
- After an ambiguous response, inspect status/files/receipts. Do not delete markers to retry blindly. A different state directory or program does not share this protection; intentionally printing the same part again requires operational review.
- Uploads sharing a device state directory hold a private device lock through
  listing, reservation, POST and verification. A concurrent contender fails
  before printer access, including for different hashes or profile names.
  The lock file is retained; closing its descriptor releases the lease.
  State paths are walked without following symlinks; an existing device directory
  must be user-owned and private (0700). Invalid permissions are refused without
  changing them, and the lock must be a private regular file (0600).
  Other clients or state directories do not share this lock, and firmware-side
  atomic rejection of an existing filename has not been established.
- Existing remote files are not overwritten. Names must be safe ASCII basenames; only `.gcode` files up to 128 MiB are accepted.
- Remote verification checks filename, size, layers, and printer model. The endpoints used did not provide a checksum of stored bytes: `remote_byte_hash_verified=false` explicitly indicates that the internal copy was not downloaded and independently hashed.
- Firmware 2.0.2.2 sends a correlated ACK followed by a report with a different msgid. Queries are synchronous and accept a fresh report after the ACK. An idle printer does not produce a report for `print/query`; status uses `info/report`.
- There is no transactional lock against another computer between a query and an action. Credentials/pins may change after firmware or LAN-mode changes; reassess provisioning.


## Validation evidence

Manual upload validation: one actual POST of an Autodesk FDM Test generated by Next 2.0.0.3, 6,856,570 bytes, 460 layers, HTTP 200/code 200. Listing and metadata confirmed an estimated time of 1h44m09s and approximately 31.74 g. The printer remained idle without heating. This does not validate physical print quality or the experimental start operation.

End-to-end validation on 2026-10-07: Autodesk FDM Test sliced with Next Linux 2.0.0.5 and official Kobra X / 0.20mm Standard / PLA High Speed profiles, using one CPU and preserving model position/orientation. Output: 6,835,381 bytes, 460 layers, estimated 1h44m12s and approximately 31.74 g. One upload was verified, followed by one MQTT start using the reviewed plan. Telemetry confirmed the correct active file, preparation phases, and printing at layer 1/460 with bed/nozzle targets of 60°C/220°C. No upload or start was repeated. Completion and physical quality were not assessed in this validation.


## Saved target selection

Use `kobra-lan printer list`, `printer info [name]` and `printer use <name>` for
offline inventory, inspection and default selection. For an individual command,
place `--printer <name>` or `--config <path>` before the command; they conflict.
Explicit selection overrides the saved named default. With a null default,
select --printer, use an explicit --config, or run printer use NAME first. Missing or broken selected access never chooses a
different printer. Local `gcode inspect` needs no config.
See [pairing and profile storage](pairing.md) for paths and recovery.

## Diagnose a selected connection

```sh
kobra-lan doctor
kobra-lan --printer bancada doctor
kobra-lan --config "$HOME/.config/kobra-lan/profiles/bancada/config.json" doctor
```

Doctor never provisions, repairs, uploads or controls a printer. It performs no
address scan or retry. It reports eight ordered stages: `configuration`,
`dependencies`, `http_tcp`, `mqtt_tcp`, `tls_pin`, `mqtt_auth`, `status`,
`compatibility`. Failed dependencies cause later checks to be `skipped`;
independent HTTP/MQTT TCP checks continue. HTTP failure does not block MQTT.
TCP success proves only that a port accepts connections, not protocol support.
TLS pins are compared before MQTT credentials. One authenticated session requests
only a fresh correlated `info` report. A busy/printing target can pass.
Compatibility requires the fresh MQTT report to identify `Anycubic Kobra X`,
firmware `2.0.2.2` and a valid state. As in pairing, `deviceId`, `modelId` and
`modeId` are optional in this report; every supplied identifier must match the
selected configuration. Every omitted optional identifier is named without failing:
target trust still requires the saved TLS pin and successful MQTT authentication.
Missing required model/firmware/state evidence fails with `qualification_incomplete`;
contradictory, unsupported or invalid values fail with `outside_qualification`.
Successful connection stages remain passed in both cases. No HTTP identity
fallback, additional query or trust update is performed.

Each network stage has at most 12 seconds and all network work shares a
60-second monotonic deadline. No reconnect, provisioning request, HTTP request,
trust update or state write occurs. Compatibility requires matching Kobra X
model 20030 / firmware 2.0.2.2 identity; a healthy connection does not expand
hardware qualification or authorize a physical operation.

The JSON `ok` envelope contains `result` even on failure: schema `version: 1`,
safe `target` metadata (null when unavailable), ordered `checks` and `healthy`.
Each check has `stage`, `status` (`passed`, `failed`, `skipped`), safe `code`,
`message` and nullable `next_step`. Failure adds the shared safe `error` object.
Exit 0 means all stages passed; exit 2 means selection, trust, authentication,
protocol or compatibility failure; exit 3 means local config/dependency/I/O or
network failure. Exit 3 takes precedence when independent failures mix.
Malformed/conflicting selectors fail with exit 2 before diagnosis.

Use each failed check's next step: inspect saved selection and private file modes,
install the declared runtime, check LAN mode/address/ports/firewall, or review
qualification. Never accept a changed pin, re-pair automatically or clear
operational markers in response to a diagnostic failure. Reports exclude raw
status, session tokens, passwords, certificate bodies and private keys.

## Shell completion

The installed `kobra-lan completion bash|zsh|fish` generator works offline without
configuration, shell binaries or printer queries. It completes canonical
commands, flags, fixed choices and local file operands; it never discovers
printer names or reads credential contents. Root options go before commands.
No startup file is modified automatically.

Bash (load explicitly in each session, or source the generated file from your
own startup configuration):

```sh
mkdir -p "$HOME/.local/share/bash-completion/completions"
kobra-lan completion bash > "$HOME/.local/share/bash-completion/completions/kobra-lan"
. "$HOME/.local/share/bash-completion/completions/kobra-lan"
```

Zsh (after your usual `compinit`; explicitly source in the current session):

```sh
mkdir -p "$HOME/.local/share/zsh"
kobra-lan completion zsh > "$HOME/.local/share/zsh/kobra-lan.zsh"
source "$HOME/.local/share/zsh/kobra-lan.zsh"
```

Fish loads the user completion directory automatically in subsequent sessions:

```fish
mkdir -p "$HOME/.config/fish/completions"
kobra-lan completion fish > "$HOME/.config/fish/completions/kobra-lan.fish"
source "$HOME/.config/fish/completions/kobra-lan.fish"
```

These instructions use the installed CLI from any working directory. Regenerate
scripts after upgrading to keep them aligned with the installed command tree.
