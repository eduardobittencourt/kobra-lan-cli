# LAN pairing and private configuration

### LAN onboarding and initial trust

Pairing targets a printer already in LAN mode at a known IPv4 address, reachable
on TCP 18910 (HTTP) and 9883 (MQTT/TLS). The local exchange uses `/info` and a
signed `/ctrl` request without HA, Slicer, or cloud requests. The HTTP exchange
is unauthenticated: its token, signature and encrypted credential bundle do not
prove the printer's identity against an active network attacker. Provision only
on a trusted network: a fingerprint obtained through an independent trusted path
protects the later MQTT connection, but does not authenticate or protect the HTTP
provisioning exchange or its credentials. Enabling LAN mode, account setup and resets are separate from this
command; no claims are made about their internet requirements.

The examples use the source-checkout launcher. After package installation, use
`kobra-lan` in place of `./kobra-lan`.

Interactive first use (prompts and fingerprint are shown on stderr):

```sh
./kobra-lan printer pair --host 192.0.2.10
./kobra-lan status
```

Unattended setup requires a fingerprint obtained through a trusted path. Replace
`EXPECTED_SHA256` with its 64 hexadecimal digits; there is no `--yes` bypass:

```sh
./kobra-lan printer pair --host 192.0.2.10 --trust-sha256 EXPECTED_SHA256
```

For an existing installation, use a separate absent destination. Global options
go before `printer`; a missing private directory is created automatically:

```sh
./kobra-lan --config ~/.config/kobra-lan-test/config.json printer pair \
  --host 192.0.2.10 --trust-sha256 EXPECTED_SHA256
./kobra-lan --config ~/.config/kobra-lan-test/config.json status
# Original access remains available:
./kobra-lan status
```

Running pairing again with an existing destination returns exit 3 before network
access and preserves the config. It never replaces or resets existing access.

Initial qualification is limited to Kobra X model 20030 / firmware 2.0.2.2.
Pairing observes TLS using the provisioned client certificate, then requires
explicit acceptance of the observed server SHA-256 fingerprint. Only `y` or
`yes` accepts interactively; empty input, EOF or noninteractive input refuses.
Unattended setup requires an exact `--trust-sha256` value of 64 hexadecimal
digits. Malformed or mismatched pins fail and never fall back to a prompt.

The TLS handshake sends the client certificate, but never its private key.
MQTT username/password are sent only on a subsequent connection after the
accepted server fingerprint is checked again. A changed certificate fails.
Pairing only queries `info`, accepts either free or busy state, and requires
fresh supported identity/firmware before saving. It never uploads or controls
the printer. Keep the accepted pin for subsequent connections.

The selected config must be absent, including dangling symlinks. Pairing refuses
replacement before any network access; choose another `--config` for an isolated
setup. Its parent must be a nonsymlink, user-owned directory with mode 0700.
Missing directories are created privately; existing shared directories are
refused without changing their permissions. Directory symlinks are refused.

Generated PEMs live in an unpredictable `.pair-<id>/` directory under the config
parent. Directories have mode 0700, files mode 0600. The complete config is
published atomically without replacement only after trust and status checks.
Handled failures remove unpublished secrets. If a persistence error leaves a
visible config, keep its referenced PEM directory: it may already be committed.

To remove an isolated setup, first inspect its config's `client_cert` and
`client_key` paths privately. Remove only that config and the `.pair-<id>/`
directory it owns after checking no retained config references it. A process kill
may leave an unreferenced private `.pair-<id>/` staging directory containing PEMs
and possibly `candidate.json`; remove it only after confirming no pairing is
running and no config references it. Do not promote `candidate.json` manually.
Local deletion does not revoke printer credentials. Preserve original configs,
PEMs, upload receipts and attempt markers; pairing never updates those markers.

Store configuration in `~/.config/kobra-lan/config.json`, with file permissions 0600 and directory permissions 0700. Fields:

- `host`: printer LAN IPv4 address; `type_id`: 20030; `printer_id`: device identity returned by LAN provisioning.
- `mqtt_username`, `mqtt_password`: per-device LAN credentials.
- `client_cert`, `client_key`: paths to private PEM files, with permissions 0600.
- `tls_sha256`: SHA-256 of the MQTT server's DER certificate, obtained through a trusted path.
- `mqtt_port`: 9883; `http_port`: 18910. Both are optional and use these defaults.

Use `printer pair` above to obtain credentials directly from the LAN-enabled printer, or retain an existing compatible configuration. This project includes no third-party certificates/credentials. Do not commit configuration, keys, tokens, or receipts. Connections verify the TLS pin **before** sending the MQTT username/password; do not automatically update a mismatched pin. The operator must establish initial trust. This is certificate pinning rather than public CA validation.

The upload session token comes from `info/report`. URLs containing tokens are neither printed nor stored in receipts. The destination is restricted to the configured host/port and `/gcode_upload?s=...`. This implementation relies on community interoperability research, rather than an officially supported Anycubic SDK.


## Managed profile storage and recovery

Named profiles use `~/.config/kobra-lan/profiles.json` (registry version 1) and
`~/.config/kobra-lan/profiles/<name>/config.json`. Names match
`[a-z][a-z0-9-]{0,47}`. Each config retains the existing schema and references
pairing material in its private `.pair-<id>/` directory. Managed directories must
be owned by the current user with mode 0700; files use 0600. Symlink components
and existing destinations are rejected. The registry records destinations and
owned filenames, never passwords or PEM contents.

A bounded advisory lock serializes writers. Managed consumers hold a shared
lease for their entire operation; deletion requires an exclusive lease. A busy
store fails locally rather than interrupting an active consumer. Index writes
fsync a private temporary file, atomically replace the index and fsync its parent.
A failure after replacement can mean the complete new index is already visible;
inspect the inventory before deciding what to do next. Unknown registry versions
fail closed and must be preserved for local review.

Publication commits a complete verified config first, its registration second,
and an optional default third. A complete config can therefore survive without
registration, or a registered profile can survive without becoming default.
Keep its PEMs and inspect the complete `config.json` locally; never automatically
adopt `candidate.json` or repeat provisioning to recover a local write failure.
An empty reserved directory after failed pairing also requires local inspection
before manual cleanup and a new pairing attempt. Existing files are never replaced.

## Select and inspect saved printers

```sh
kobra-lan printer list
kobra-lan printer info bancada
kobra-lan printer use bancada
kobra-lan --printer oficina status
kobra-lan --config "$HOME/.config/kobra-lan/config.json" status
```

These inventory, info and use operations are offline. Inventory reports an
unavailable entry if its local config is damaged; addresses are saved metadata,
not a reachability claim. Firmware is labeled last observed. `info` without a
name follows ordinary selection. Explicit `--printer` or `--config` overrides
the saved named default; both together are an error. With no registry or before
any default is selected, ordinary commands still use the unchanged legacy config.
A broken named default fails for that target without falling back to legacy.
Registration alone never selects a default. An explicitly cleared default
requires `printer use NAME` or an explicit selector on subsequent operations.

Global options precede the command. `printer list/use/remove` reject global
target selectors; `printer info NAME` rejects them when a positional name is
present. Local `inspect` and upload dry runs validate selector syntax but do not
require config or network access. Legacy credentials stay in place; use explicit
`--config` to reach them after choosing a named default, without pairing again.

## Pair into a new named profile

```sh
kobra-lan printer pair --name bancada --host 192.0.2.10
kobra-lan printer pair --name oficina --host 192.0.2.11 --default
# Unattended pairing additionally requires --trust-sha256 with an exact trusted pin.
```

`--name` reserves a new managed destination before provisioning and conflicts
with explicit `--config` and global `--printer`. `--default` requires `--name`;
omitting it preserves the existing selection, even on a fresh installation.
Unnamed pairing always uses the absent legacy or explicit config destination,
regardless of the saved default. It never replaces existing access. Trust consent,
exact fingerprint verification and qualified fresh status remain mandatory.

A local finalization error reports whether registration/default selection was
observed committed, unchanged or uncertain. Preserve complete configs and PEMs.
For an already registered profile, inspect `printer list` and `printer info NAME`,
then run `printer use NAME` to finish selection offline. For an unregistered
complete config, inspect via explicit `--config` without re-provisioning; preserve
its directory for manual review. There is no automatic orphan adoption command.

## Remove local managed access

```sh
kobra-lan printer remove bancada       # terminal preview and affirmative consent
kobra-lan printer remove bancada --yes # unattended local deletion consent
```

Removal never contacts a printer or revokes its credentials. Refusal, EOF and
nonterminal input without `--yes` leave files unchanged. Metadata is revalidated
after consent and an active managed consumer prevents exclusive removal. Global
target selectors and legacy configs are excluded from this command.

Removal commits registry detachment first. Removing the default persists
`require-explicit`, so an unqualified command refuses even when legacy or other
profiles exist. Use `printer use NAME`, `--printer NAME` or explicit `--config`.
Removing a nondefault profile preserves the selected default.

Only recorded, exclusively owned regular private files are cleanup candidates.
Known shared references, external material, symlinks and unexpected files remain.
The JSON receipt lists `deleted_files`, `preserved_files`, registration removal,
cleanup failure and `device_credentials_revoked: false`. A cleanup I/O failure
returns exit 3 with the receipt; a detached directory is an orphan requiring
local review. Repeated removal cannot reclaim arbitrary orphan files. A failed
index commit preserves files and reports whether detachment was observed.

Manually sharing managed PEM paths in arbitrary external configs is unsupported:
the CLI checks retained managed and legacy configs, but cannot discover every
external reference. Preserve and review ambiguous files manually. Local removal,
new names and re-pairing never delete upload receipts or start attempt markers;
identities remain based on `printer_id`, including with explicit `--state-dir`.
Never clear markers to retry an uncertain operation.

## Diagnose without pairing again

Run `kobra-lan --printer bancada doctor` after saving access. See the
[diagnostic contract](usage.md#diagnose-a-selected-connection) for stage order,
12-second stage / 60-second total network limits and exits 0/2/3. A missing local
config or dependency prevents printer connections. TCP checks do not prove
protocol support. Pin mismatches fail before MQTT credentials; preserve existing
trust and inspect locally. Doctor reads fresh status without provisioning or
requiring idle state and never repairs profile/default/receipt state.
