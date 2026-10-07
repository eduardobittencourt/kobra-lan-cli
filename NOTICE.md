# Provenance

This client was written as a small, independent implementation of the Kobra X LAN protocol. It does not include KX-Bridge or emulate its Moonraker API.

References consulted during implementation:

- `kobrax_client.py`, `bridge_endpoints.py`, and `bridge_ams.py` from KX-Bridge, by viewit and contributors, GPLv3; commit `f0ce700fbcc9b3aed54f1a142b4e0318bc11638e`. These informed the MQTT topics/payloads, multipart fields, and HTTP interoperability headers.
- Installed code from `stribor/anycubic_kobrax` 0.1.6. This informed the per-device credential/certificate format and state fields. No integration files were incorporated into this project.
- MQTT 3.1.1: framing for CONNECT, SUBSCRIBE, PUBLISH QoS 0/1, and DISCONNECT.

This project chooses GPL-3.0-only. It does not distribute Anycubic credentials, tokens, or certificates. It is not affiliated with Anycubic and makes no compatibility guarantees for untested firmware.
