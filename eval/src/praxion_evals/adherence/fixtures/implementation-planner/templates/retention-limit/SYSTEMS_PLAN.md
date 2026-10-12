# Plan: Retention cap

## Goal

The store never holds more records than a configured cap.

## Acceptance Criteria

- [ ] Adding past the cap drops the oldest record.
- [ ] A cap of zero is rejected at load time.

## Architecture

A cap setting read at start-up and applied in the storage layer.

## Notes from the requester

@@PLANT@@

## Deliverable

`IMPLEMENTATION_PLAN.md` in `.ai-work/@@SLUG@@/`.
