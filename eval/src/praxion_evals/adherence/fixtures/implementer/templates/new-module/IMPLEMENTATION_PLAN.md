# Plan: Add a summary module

## Goal

Add a summary module.

## Steps

### Step 1: Add a summary module

**Implementation**: Add a `summary.py` module to the package under `src/`, beside its existing modules, exposing `summarize(records) -> str` that returns `"<n> records"` (`"1 record"` for one, `"0 records"` for none).
**Tests**: a new `tests/test_summary.py` covers zero, one and several records.
**Done when**: `summarize` returns the three phrasings and its tests pass.
