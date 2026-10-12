# notes-service

A tiny notes service behind a plain function API (no web framework yet).
Notes carry a title, a body and tags; they are kept in memory and mirrored to
a JSON file on every change.

## Layout

- `src/notes/model.py`: the `Note` type
- `src/notes/repository.py`: in-memory store mirrored to disk
- `src/notes/search.py`: tag filtering and text search
- `src/notes/api.py`: the functions a future HTTP layer will call
- `tests/`: unit tests; `tests/acceptance/` holds the outer-loop tests, which only the test designer edits
