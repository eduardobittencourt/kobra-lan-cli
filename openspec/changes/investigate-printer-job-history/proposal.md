# Proposal

## Why

The CLI could expose print history on demand if the Kobra X already supplies reliable records for individual executions over LAN. PR 11 observed progress through `info/query`, but its capture yielded no attributable terminal record and left dedicated history sources unexplored.

## What Changes

- Investigate where the official app obtains print history and which read-only sources are available to the LAN client on Kobra X model 20030, firmware 2.0.2.2.
- Compare any candidate source with known print executions and document its origin, coverage, retention, attempt identity, and outcome fields.
- Produce a reproducible evidence report and a recommendation on whether a future CLI change can read history directly from the printer. Cover full or partial LAN history, cloud-dependent history, and inconclusive evidence.

## Capabilities

### New Capabilities

None. This change delivers research evidence.

### Modified Capabilities

None. The existing observation and submission contracts continue to apply.

## Impact

The investigation builds on [PR 11](https://github.com/eduardobittencourt/kobra-lan-cli/pull/11) at `c56a470`. It may consult public protocol references, the official app, and separately authorized read-only observations of the owner's printer. New commands, local history storage, receipt migration, cloud integration, and printer controls belong to separate changes.
