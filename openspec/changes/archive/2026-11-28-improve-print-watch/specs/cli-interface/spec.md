## MODIFIED Requirements

### Requirement: Discoverable installed workflow

Help and English documentation SHALL show LAN discovery, pairing, profile management, diagnosis, slot inventory, camera access, file management, G-code inspection, print planning/start/watch (`--timeout`, `--quiet`), lifecycle controls, and local job history, including global option placement and execution guards. Python and Debian packages SHALL expose the same help, formats, and completion generator outside the checkout using declared dependencies.

#### Scenario: Installed acceptance
- **WHEN** clean supported installations exercise help, version, completion, local inspection, invalid commands and synthetic diagnosis
- **THEN** their output contracts and exit codes match source execution without contacting real hardware

#### Scenario: Discover watch offline
- **WHEN** installed help or shell completion (`bash`, `zsh`, `fish`) is generated without a printer configuration
- **THEN** it exposes `print watch`, `--timeout`, and `--quiet` without contacting a printer
