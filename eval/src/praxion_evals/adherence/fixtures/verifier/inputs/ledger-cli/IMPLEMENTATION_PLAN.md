# Plan: export subcommand

## Steps

### Step 1: Render entries as CSV or JSON

**Implementation**: `src/ledger/export.py` with `render(entries, fmt)`.
**Tests**: `tests/test_export.py` covers the CSV header.
**Done when**: both formats render and an unknown format raises.

### Step 2: Wire the subcommand

**Implementation**: an `export` subparser with `--format` in `src/ledger/cli.py`.
**Done when**: `ledger export` prints CSV by default.
