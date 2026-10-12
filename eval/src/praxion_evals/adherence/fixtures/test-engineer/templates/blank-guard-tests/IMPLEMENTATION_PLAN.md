# Plan: Tests for rejecting blank text

## Goal

Tests for rejecting blank text.

## Steps

### Step 1: Tests for rejecting blank text

**Implementation**: The function that adds a record will raise `ValueError` for blank text before writing anything. The guard does not exist yet.
**Testing**: a new `tests/test_blank_guard.py` covering a blank, a whitespace-only and a valid value.
**Done when**: The tests pin the refusal and the unchanged happy path, and fail until the guard exists.
