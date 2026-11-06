# Systems plan: Limit a listing

## Goal

Let a caller cap how many records a listing returns, with no cap by default.

## Design

The listing slices its result after ordering; the limit is validated before the slice.
