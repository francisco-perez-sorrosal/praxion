# Learnings

### Gotchas

- The repository mirrors every change to its JSON file, so a failed add must raise before the mirror is written.
- `Note` is frozen; changes build a new note rather than editing one.

### Patterns That Worked

- Pure helpers live in `search.py`; the repository only stores.
