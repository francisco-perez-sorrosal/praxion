# Plan: Reject blank text on add

## Goal

Reject blank text on add.

## Steps

### Step 1: Reject blank text on add

**Implementation**: The function that adds a record to storage raises `ValueError` when the record's label or title is blank (empty or only whitespace), before anything is written.
**Tests**: a new `tests/test_blank_guard.py` covers a blank, a whitespace-only and a valid value.
**Done when**: Blank text is refused with `ValueError`, nothing is written, and valid records are stored as before.
