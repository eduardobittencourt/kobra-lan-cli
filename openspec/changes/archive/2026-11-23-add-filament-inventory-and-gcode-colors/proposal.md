# Proposal

## Why

Before `kobra-lan` can support multicolor `print plan` and `print start` (whether for a single object with layered color changes or multiple differently colored objects on one build plate), operators and agents need read-only visibility into both sides of the color-mapping equation: what filaments and colors are currently loaded in the printer's onboard four-slot box, and what colors, materials, and tool indices a sliced G-code requires. Today, `multiColorBox / getInfo` is only queried internally during `print plan`, and `gcode inspect` omits `paint_info`, tool-change indices (`T<n>`), and filament weights, leaving users blind to slot inventory and multicolor G-code metadata until submission preflight.

## What Changes

- Add a read-only `slots list` command scoped to the selected printer (`--printer`, `--config`, or saved default) that opens one pinned MQTT session, verifies fresh Kobra X model `20030` / firmware `2.0.2.2` identity (without requiring the printer to be idle), queries `multiColorBox / getInfo`, and returns sanitized, deterministic inventory for the onboard four-slot box (`id == -1`, slots `1..4`) including human slot number, firmware `ams_index` (`0..3`), status code/label, start availability, material type, and normalized RGB/hex color.
- Extend offline `gcode inspect <file> [--name <remote-name>]` to parse and surface filament and color metadata observed in real Anycubic Slicer Next (`2.0.0.6`) single- and multi-color G-codes:
  - Validate all `; paint_info = [...]` declarations across the file (Anycubic Slicer Next emits it in both the header and trailing config blocks), verify agreement when repeated, and expose ordered filament entries (`paint_index`, `material_type`, `color_rgb`, `color_hex`, and optional per-index `filament_used_g`), supporting non-contiguous `paint_index` values (e.g., `[1, 3]` or `[2]`).
  - Report sorted unique `T<n>` tool indices, `paint_info_present`, `filament_count`, `multicolor`, nullable `total_filament_used_g`, and `single_filament_start_compatible` so callers can distinguish currently startable single-filament `paint_index: 0` files from multicolor or non-zero-index files before planning.
  - Preserve full backward compatibility for existing `gcode inspect` JSON fields, byte immutability, offline operation, and `files upload` (including synthetic fixtures that omit `; paint_info =` and valid multicolor Kobra X G-codes).
- Expose `slots list` in the canonical command tree, installed help, offline bash/zsh/fish shell completion, packaging module allowlists/probes (`scripts/check_python.py`, `scripts/build_deb.py`, `scripts/accept_deb.py`), and English documentation (`README.md`, `docs/usage.md`, `ROADMAP.md`, `debian/kobra-lan.1`).

## Capabilities

### New Capabilities
- `filament-inventory`: Read-only inspection of the qualified Kobra X onboard four-slot filament box (`slots list`) over one pinned MQTT session without requiring idle state or writing local/device state.

### Modified Capabilities
- `reviewed-job-submission`: Extend local `gcode inspect` to parse and report Anycubic Slicer Next `paint_info` entries, tool-change indices (`T<n>`), optional filament weight summaries, multicolor flags, and single-filament start compatibility while preserving existing fields, byte immutability, and upload acceptance.
- `cli-interface`: Add `slots list` to the canonical command tree, group help, offline bash/zsh/fish completion, and installed documentation.

## Impact

- New shared module `kobra_lan/filaments.py` (for G-code `paint_info`/tool/weight parsing and onboard `multiColorBox / getInfo` sanitization) reused by `kobra_lan/upload.py`, `kobra_lan/start.py`, and `kobra_lan/cli.py`.
- Updates to `kobra_lan/cli.py`, `kobra_lan/upload.py`, `kobra_lan/start.py`, and packaging module/CLI probes in `scripts/check_python.py`, `scripts/build_deb.py`, and `scripts/accept_deb.py`.
- Adds offline unit tests (`tests/test_filaments.py`) and updates `tests/test_cli.py`, `tests/test_client.py`, `tests/test_completions.py`, and `tests/test_start.py` using synthetic transports and G-code fixtures (covering single-color, multi-object multicolor, non-contiguous `paint_index`, mixed-material, duplicate/conflicting `paint_info`, and absent `paint_info`).
- Updates `README.md`, `docs/usage.md`, `ROADMAP.md`, and `debian/kobra-lan.1`.
- Multicolor `print plan` / `print start` slot mapping, external ACE Pro units (`id != -1` or multi-box responses), slot editing/filament feeding controls, and hardware qualification of slot 3 / multicolor starts remain out of scope for this change and belong to the subsequent multicolor-start change.
