# Spec Delta

## ADDED Requirements

### Requirement: Discover intentional reprint workflow
Installed help and documentation SHALL show `--reprint-from` on `print plan` and `print start`, explain where to find the prior local attempt reference and show how to review and explicitly execute a reprint. Offline bash, zsh and fish completion SHALL offer the flag on both commands.

#### Scenario: Installed CLI without printer configuration
- **WHEN** help is requested for `print plan` or `print start`, or shell completion is generated on a clean installation
- **THEN** the relevant help and completions expose the flag without network access or state writes

#### Scenario: Invalid predecessor reference
- **WHEN** `--reprint-from` is supplied with a malformed value in text or JSON mode
- **THEN** the CLI exits 2 before printer access or reservation and emits a safe error in the selected format
