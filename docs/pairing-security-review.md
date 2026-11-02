# Pairing protocol security review

The LAN protocol is fixed by the printer firmware, initially qualified only for
Kobra X model 20030 / firmware 2.0.2.2. The following are bounded compatibility
constraints, not recommendations for designing a new protocol. The public setup
instructions describe their remaining risks. No analyzer rules or quality gates
are disabled for this feature.

## Initial TLS observation: S4830 and S5527

`observe_fingerprint` deliberately observes the server's DER certificate before
trust exists. The device uses a private certificate; public CA validation and
IPv4 hostname validation cannot establish the initial trust required by this
protocol. This connection exchanges the provisioned client certificate, but sends
no MQTT CONNECT packet, username or password, and never sends the private key.

The observed SHA-256 fingerprint must then be accepted explicitly on a terminal
or match an externally supplied `--trust-sha256` exactly. Refusal, missing consent,
malformed pins and mismatches prevent MQTT authentication and config publication.
The subsequent MQTT connection independently checks the accepted pin before
sending username/password, including when the certificate changes between the
two handshakes. Observation does not disable pinning for authenticated use.

First-use observation cannot authenticate the printer against an active network
attacker. The initial HTTP provisioning exchange is also unauthenticated.
Provision only on a trusted network. An independently obtained fingerprint
protects the later MQTT connection; it does not authenticate or encrypt the HTTP
exchange, which exposes credentials to observers on that network.
Accepting this device protocol requires that documented boundary.

Evidence: `TransportTests.test_observation_is_tls_only`, `TrustTests`, and
`TerminalTests` in `tests/test_pairing.py`; the existing real MQTT implementation
is exercised by `test_changed_cert_rejected_before_credentials`. Hardware
acceptance used a previously known fingerprint, a separate config, and only
pairing/status; original access and operational state remained unchanged.

## Credential decoding: S5542

The printer returns AES-128-CBC ciphertext with PKCS#7 padding. The application
only decrypts that firmware-defined format. Replacing it with AES-GCM or a new
padding scheme would make the supported device protocol unusable; the client
cannot change the printer's implementation. No production encryption operation
is introduced by this code.

CBC does not authenticate this bundle. Strict Base64/padding/JSON validation,
required identity/model fields and certificate/private-key matching reject
malformed responses but do not make HTTP provisioning authenticated. Explicit
TLS trust and the pinned read-only status query remain separate prerequisites
for saving, and the unauthenticated HTTP boundary remains a documented risk.

Evidence: `CryptoTests` in `tests/test_provisioning.py`, including an independent
OpenSSL known-answer vector and invalid encoding, padding, JSON, identity and
PEM mismatch cases. No real printer secrets are test fixtures.

## Firmware version false positives: S1313

`2.0.2.2` is the qualified firmware version, not an IPv4 endpoint. It is compared
with the authenticated `info.version` field. Network destinations come from the
explicit validated user address and restricted same-host control URL. The
version value is never used as a socket or HTTP destination.

## Dependency resolution: S8565

`uv.lock` records the Python development/CI runtime dependency closure and hashes.
The unit job and documented development setup use `uv sync --locked`. The setup
uv action is commit-pinned and the uv version is fixed. Package metadata remains
`cryptography>=41` so the supported Debian/Ubuntu system packages satisfy it;
Debian acceptance still verifies each distribution's installed dependency closure.
The lockfile does not claim that third-party pip/distro installations select the
same versions as the development environment.
