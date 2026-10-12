# ledger-cli

A small command-line bookkeeping tool. Entries live in a JSON file; the
`add`, `list` and `export` subcommands read and write it.

## Configuration

`ledger.toml` in the working directory sets the data file and the default
currency. Without it the tool uses `ledger.json` and `EUR`.

## Layout

- `src/ledger/config.py`: reads `ledger.toml`
- `src/ledger/store.py`: loads and saves entries
- `src/ledger/export.py`: renders entries as CSV or JSON
- `src/ledger/cli.py`: argument parsing and dispatch
