# Spec Delta

## MODIFIED Requirements

### Requirement: Published and packaged compatibility matrix
The project SHALL maintain `docs/compatibility.md` separating implemented, offline-validated, and hardware-observed evidence across models, firmwares, slicers, topologies, slots, materials, preparation flags, CLI operations, and host platforms, indexed from docs and checked in packaging. Host-platform rows SHALL distinguish Linux `amd64` and macOS `arm64` offline CI and read-only LAN evidence from untested mutating runs, unqualified platforms, and unpublished channels.

#### Scenario: Compatibility matrix distinguishes evidence tiers
- **WHEN** an operator reads `docs/compatibility.md`
- **THEN** every row (including materials, slot-mapping classes, preparation flags, `printer discover`, camera commands, and macOS `arm64` host platform) separates implementation status, offline test coverage, and live hardware evidence without inferring support for untested materials, untested preparation combinations, mutating macOS runs, non-Next slicers, external ACE units, or unpublished distribution channels

#### Scenario: New module and documentation stay synchronized with packaging allowlists
- **WHEN** Python sdist/wheel and Debian package allowlist checks inspect the repository and built archives
- **THEN** all shipped modules and `docs/compatibility.md` remain synchronized with the allowlists and all relative Markdown links resolve within shipped documentation
