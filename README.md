# Kobra LAN CLI

A direct Anycubic Kobra X LAN client with JSON output for CLI and agent automation. Slicing is handled separately by the official Anycubic Slicer Next. This client preserves G-code bytes and does not require KX-Bridge, Moonraker, a desktop, or Home Assistant at runtime.

**Status:** upload and print start validated on Kobra X hardware running firmware 2.0.2.2 for one PLA High Speed print using onboard slot 1, automatic leveling on, vibration compensation off, and flow calibration off. Starting the stored file with `url=""` worked. Other combinations remain unqualified; the start feature is still experimental. Physical print quality and completion have not yet been assessed.

## Running the client

Python standard library only, Python >=3.11. No pip dependencies or daemon. The Linux launcher uses `/usr/bin/python3`.

```sh
git clone https://github.com/eduardobittencourt/kobra-lan-cli.git
cd kobra-lan-cli
./kobra-lan --help
./kobra-lan status
./kobra-lan files
./kobra-lan inspect /path/to/model.gcode --name agent-model.gcode
./kobra-lan upload /path/to/model.gcode --name agent-model.gcode
# Actual upload: use the same file and SHA-256 reviewed in the dry run
./kobra-lan upload /path/to/model.gcode --name agent-model.gcode --sha256 HASH --execute
./kobra-lan file agent-model.gcode
```

`upload` is a local dry run unless given `--execute` and the reviewed hash. It never starts a print. Output is JSON; exit codes are 0 (success), 2 (protocol/validation error), and 3 (configuration/network error). Global options `--config` and `--state-dir` go before the subcommand.

## Private configuration

Store configuration in `~/.config/kobra-lan/config.json`, with file permissions 0600 and directory permissions 0700. Fields:

- `host`: printer LAN IPv4 address; `type_id`: 20030; `printer_id`: device identity returned by LAN provisioning.
- `mqtt_username`, `mqtt_password`: per-device LAN credentials.
- `client_cert`, `client_key`: paths to private PEM files, with permissions 0600.
- `tls_sha256`: SHA-256 of the MQTT server's DER certificate, obtained through a trusted path.
- `mqtt_port`: 9883; `http_port`: 18910. Both are optional and use these defaults.

Obtain credentials and the certificate through Anycubic LAN provisioning, or import them from an existing integration. This client does not include a public pairing tool or third-party certificates/credentials. Do not commit configuration, keys, tokens, or receipts. Connections verify the TLS pin **before** sending the MQTT username/password; do not automatically update a mismatched pin. The operator must establish initial trust. This is certificate pinning rather than public CA validation.

The upload session token comes from `info/report`. URLs containing tokens are neither printed nor stored in receipts. The destination is restricted to the configured host/port and `/gcode_upload?s=...`. This implementation relies on community interoperability research, rather than an officially supported Anycubic SDK.

## Experimental print start

By default, the command only queries the printer and builds a plan. It requires an already uploaded file, slot **1..4** (human numbering), matching material, one color/paint index 0, and the onboard four-slot configuration. External ACE units and multicolor prints are not supported in this version.

```sh
./kobra-lan start /path/to/model.gcode --name agent-model.gcode --slot 1 \
  --auto-leveling on --vibration-compensation off --flow-calibration off
```

All three preparation options are required. The example does not claim to reproduce the graphical application's defaults. JSON output includes the payload and `plan_sha256`. Changing the file, slot, or options changes the hash. The plan includes `experimental=true`; `hardware_start_validated=true` only for the observed configuration described above, and false for other combinations. This flag describes the start operation, not the quality of an arbitrary model.

To request execution later, add `--execute --plan-sha256 REVIEWED_PLAN_HASH` to the same arguments. This is a physical action: run it only when printing is authorized and the printer is prepared. It requires a verified upload receipt from this CLI, rechecks the file/state/material, and writes a durable reservation before publishing **one** MQTT `print/start` command. It does not upload again. An ACK is not treated as proof of physical printing; the client subsequently queries the active project and distinguishes observed activity from an uncertain result. It never automatically repeats the command.

## Guarantees and limitations

- Upload is currently qualified only for model 20030 / firmware 2.0.2.2, Next-generated G-code, and the Kobra X profile. It requires an idle printer with no active project.
- Hashing and multipart construction use the same bytes in memory. No G-code translation, `print=true` flag, or HTTP redirects.
- Exclusive reservations are persisted with fsync per device and file hash in `~/.local/share/kobra-lan/uploads/`. Upload and start use separate markers. A second attempt is blocked after success or timeout, including across processes and restarts.
- After an ambiguous response, inspect status/files/receipts. Do not delete markers to retry blindly. A different state directory or program does not share this protection; intentionally printing the same part again requires operational review.
- Existing remote files are not overwritten. Names must be safe ASCII basenames; only `.gcode` files up to 128 MiB are accepted.
- Remote verification checks filename, size, layers, and printer model. The endpoints used did not provide a checksum of stored bytes: `remote_byte_hash_verified=false` explicitly indicates that the internal copy was not downloaded and independently hashed.
- Firmware 2.0.2.2 sends a correlated ACK followed by a report with a different msgid. Queries are synchronous and accept a fresh report after the ACK. An idle printer does not produce a report for `print/query`; status uses `info/report`.
- There is no transactional lock against another computer between a query and an action. Credentials/pins may change after firmware or LAN-mode changes; reassess provisioning.

## Tests

```sh
/usr/bin/python3 -m unittest discover -s tests -v
```

28 offline tests cover multipart preservation, MQTT framing, TLS pinning, response correlation, hashes, dry runs, existing files, busy state, slot/material mapping, reviewed plans, scoped hardware qualification, upload receipts, ACK versus confirmation, and timeouts without replay. Automated tests never access real printers.

Manual upload validation: one actual POST of an Autodesk FDM Test generated by Next 2.0.0.3, 6,856,570 bytes, 460 layers, HTTP 200/code 200. Listing and metadata confirmed an estimated time of 1h44m09s and approximately 31.74 g. The printer remained idle without heating. This does not validate physical print quality or the experimental start operation.

End-to-end validation on 2026-10-07: Autodesk FDM Test sliced with Next Linux 2.0.0.5 and official Kobra X / 0.20mm Standard / PLA High Speed profiles, using one CPU and preserving model position/orientation. Output: 6,835,381 bytes, 460 layers, estimated 1h44m12s and approximately 31.74 g. One upload was verified, followed by one MQTT start using the reviewed plan. Telemetry confirmed the correct active file, preparation phases, and printing at layer 1/460 with bed/nozzle targets of 60°C/220°C. No upload or start was repeated. Completion and physical quality were not assessed in this validation.

## License and references

GPL-3.0-only. Independent implementation based on protocol references from [KX-Bridge](https://gitea.it-drui.de/viewit/KX-Bridge-Release), commit `f0ce700fbcc9b3aed54f1a142b4e0318bc11638e`, and the [Anycubic Kobra X Home Assistant integration](https://github.com/stribor/anycubic_kobrax), version 0.1.6. No modules from either project are imported at runtime. See [NOTICE.md](NOTICE.md) and [LICENSE](LICENSE).
