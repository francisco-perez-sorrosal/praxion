# Plan: Tests for a listing limit

## Goal

Tests for a listing limit.

## Steps

### Step 1: Tests for a listing limit

**Implementation**: The listing function will take an optional `limit`; negative values raise `ValueError`. The parameter does not exist yet.
**Testing**: extend the existing test module for that function.
**Done when**: A limited, an unlimited and a negative case are covered and the new ones fail until the parameter exists.
