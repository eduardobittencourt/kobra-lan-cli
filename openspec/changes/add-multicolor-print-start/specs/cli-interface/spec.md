# Spec Delta

## ADDED Requirements

### Requirement: Discover multicolor slot mapping
Installed help, English documentation, and offline bash/zsh/fish completions SHALL expose repeatable required `--slot-map PAINT_INDEX=SLOT` (and omit removed `--slot`) on `print plan` and `print start` without configuration, state writes, or printer access. Removed `--slot`, missing `--slot-map`, malformed syntax, out-of-range slots, or duplicate `paint_index` keys SHALL exit 2 (`invalid_arguments`) before target selection without echoing raw values.

#### Scenario: Discover --slot-map offline on clean installation
- **WHEN** `print plan --help`, `print start --help`, or `completion bash|zsh|fish` runs without a printer configuration or state directory
- **THEN** help and generated completions expose `--slot-map` and omit `--slot` on both `print plan` and `print start` with no network access and no state writes

#### Scenario: Removed --slot or invalid/hostile --slot-map fails safely before printer access
- **WHEN** `print plan` or `print start` receives removed `--slot`, omits `--slot-map`, or receives malformed `--slot-map` input (including a token-bearing URL, non-integer key/slot, slot outside `1..4`, or duplicate `paint_index`) in text or JSON mode
- **THEN** the CLI exits 2 (`invalid_arguments`) before target selection or printer access and emits one safe error without echoing the raw argument value
