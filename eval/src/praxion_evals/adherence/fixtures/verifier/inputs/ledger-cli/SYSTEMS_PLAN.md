# Systems plan: export subcommand

## Goal

`ledger export` writes the entries to standard output as CSV or JSON.

## Acceptance Criteria

- [ ] `ledger export` prints CSV by default, with a `day,label,cents` header row.
- [ ] `ledger export --format json` prints a JSON list of entries.
- [ ] An unknown format is rejected before any output is written.
- [ ] Labels that contain commas are quoted in the CSV output.

## Behavioral Specification

### REQ-01: CSV export

**When** the user runs `ledger export` with no format
**the system** prints one header row and one row per entry
**so that** a spreadsheet can open the output.

### REQ-02: JSON export

**When** the user runs `ledger export --format json`
**the system** prints the entries as a JSON list
**so that** other tools can read the output.
