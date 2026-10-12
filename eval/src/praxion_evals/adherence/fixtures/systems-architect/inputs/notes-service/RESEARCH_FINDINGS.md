# Research findings

The repository is a tiny notes service behind a function API. Its code is `model.py`, `repository.py`, `search.py` and `api.py` under `src/notes/`. Records are plain frozen dataclasses (`Note`) persisted as JSON. There is no logging, no concurrency and no schema versioning. Tests cover the happy paths only.
