# Plan: tag filter on the list function

## Steps

### Step 1: Filter helpers

**Implementation**: `with_tag` and `containing` in `src/notes/search.py`.
**Tests**: `tests/test_search.py` covers both helpers.
**Done when**: the helpers return the expected notes.

### Step 2: Use them in the API

**Implementation**: `list_notes` in `src/notes/api.py` applies the filters in turn.
**Done when**: a tag, a query and both together work.
