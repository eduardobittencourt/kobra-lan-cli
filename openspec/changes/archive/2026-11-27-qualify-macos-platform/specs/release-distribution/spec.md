# Spec Delta

## ADDED Requirements

### Requirement: Qualified macOS Python installation and CI acceptance
The project SHALL qualify macOS (`arm64`) for Python `>=3.11` source and wheel/venv installs without altering Debian `.deb` contracts or claiming PyPI/Homebrew availability. macOS CI SHALL run locked offline unit tests, launcher syntax checks, native `zsh` completion checks, and outside-checkout archive/wheel acceptance. `./kobra-lan` SHALL resolve symlinks portably and use `python3` from `PATH` (fallback `/usr/bin/python3`).

#### Scenario: macOS CI offline unit and wheel installation acceptance
- **WHEN** the package-checks workflow runs on macOS (`arm64`)
- **THEN** the locked offline unit suite (including native `zsh` completion verification), `sh -n kobra-lan`, and outside-checkout sdist/wheel build and runtime-locked installation probes pass with zero network printer access

#### Scenario: Portable source checkout launcher on Linux and macOS
- **WHEN** `./kobra-lan` is invoked directly or through a symlink on macOS or Linux with Python `>=3.11` on `PATH`
- **THEN** it resolves the repository directory without GNU-only flags and executes `kobra_lan.cli` using the resolved `python3` interpreter while Debian's packaged `/usr/bin/kobra-lan` continues to target `/usr/bin/python3`

## MODIFIED Requirements

### Requirement: Installation and release instructions
Documentation SHALL explain version selection, tag creation, local builds, release recovery, checksum verification, `.deb` install/upgrade/removal, macOS `arm64` Python/wheel/venv installation, and development-symlink PATH precedence. It SHALL distinguish downloadable `.deb` assets, local macOS Python installs, and future channels (PyPI, Homebrew, hosted apt), keeping live setup migration separate.

#### Scenario: Existing checkout installation
- **WHEN** an operator follows package installation instructions with a user-local kobra-lan symlink already present
- **THEN** the instructions explain how to identify the selected executable and deliberately switch installations without deleting credentials or markers

#### Scenario: macOS source or wheel installation guidance
- **WHEN** a macOS user consults the installation documentation
- **THEN** the documentation provides concrete Python `>=3.11` venv/wheel/source setup steps, notes optional `ffmpeg` for `camera snapshot`, and states that Homebrew and PyPI channels are not yet published
