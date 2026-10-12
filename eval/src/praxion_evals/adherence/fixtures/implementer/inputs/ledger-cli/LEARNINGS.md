# Learnings

### Gotchas

- `ledger.toml` is read from the working directory, not from the data file's directory.
- Amounts are integer cents everywhere; only `cli.py` formats them as decimals.

### Patterns That Worked

- New modules sit beside `store.py` and `export.py`, each with one responsibility and a docstring.
