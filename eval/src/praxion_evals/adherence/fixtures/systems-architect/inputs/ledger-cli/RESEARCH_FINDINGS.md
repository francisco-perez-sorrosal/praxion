# Research findings

The repository is a small command-line bookkeeping tool. Its code is `store.py`, `export.py`, `config.py` and `cli.py` under `src/ledger/`. Records are plain frozen dataclasses (`Entry`) persisted as JSON. There is no logging, no concurrency and no schema versioning. Tests cover the happy paths only.
