# Plan: Add a summary module

## Goal

Add a summary module.

## Steps

### Step 1: Add a summary module

**Implementation**: Add a `summary.py` module to the package under `src/`, beside its existing modules, exposing `summarize(records) -> str` that returns `"<n> records"` (`"1 record"` for one, `"0 records"` for none). Export `summarize` from the package's `__init__.py`, and add the module to the README's Layout list.
**Tests**: a new `tests/test_summary.py` imports `summarize` from the package itself and covers zero, one and several records.
**Done when**: `summarize` returns the three phrasings, the package exports it, the README lists the module, and its tests pass.
