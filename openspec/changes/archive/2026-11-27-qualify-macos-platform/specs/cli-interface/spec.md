# Spec Delta

## MODIFIED Requirements

### Requirement: Offline shell completion
`completion <shell>` SHALL emit an installable script for bash, zsh or fish covering canonical commands, flags, choices, and local files without config, network, or state writes. Generated bash completion SHALL run cleanly on Bash 3.2 and Bash 4+ without Bash 4-only builtins, guarding optional `compopt`. Native `zsh` completion SHALL be verified in macOS CI alongside Linux bash checks. Dynamic printer-name discovery is outside this contract.

#### Scenario: Fresh installation completion
- **WHEN** completion is generated and sourced for a supported shell without configuration
- **THEN** canonical commands and options can be completed offline without contacting any printer

#### Scenario: Bash 3.2 and Bash 4+ compatibility
- **WHEN** generated `bash` completion is sourced and invoked under Bash 3.2 (without `mapfile` or `compopt`) or Bash 4+
- **THEN** root commands, nested subcommands, option flags, fixed choices, and file arguments complete without stderr errors, and `compopt -o filenames` is invoked when `compopt` is available

#### Scenario: Native zsh completion runtime validation
- **WHEN** macOS CI runs the offline suite with native `zsh`
- **THEN** generated `zsh` completion loads under `compinit` and completes canonical commands, flags, fixed choices, and file options offline without skipping
