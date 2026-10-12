# Plan: Cap how many records a listing returns

## Goal

Cap how many records a listing returns.

## Steps

### Step 1: Cap how many records a listing returns

**Implementation**: The function that returns the stored records takes an optional `limit` argument; with it, only the first `limit` records come back, and the default behaviour is unchanged.
**Tests**: extend the existing test module for that function with a limited and an unlimited case.
**Done when**: `limit` truncates the result, the default returns everything, and a negative `limit` raises `ValueError`.
