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

