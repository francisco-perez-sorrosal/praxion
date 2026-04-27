---
id: dec-draft-ef86f36f
title: Separate test scopes for canonical-blocks refactor — integration vs. unit
status: proposed
category: implementation
date: 2026-04-27
summary: Use two distinct test files for the canonical-blocks extraction — hooks/test_onboard_praxion_block.py (behavioral integration) and scripts/test_sync_canonical_blocks.py (sync engine unit tests).
tags:
  - testing
  - canonical-blocks
  - td-001
  - test-design
made_by: agent
agent_type: implementation-planner
pipeline_tier: standard
affected_files:
  - hooks/test_onboard_praxion_block.py
  - scripts/test_sync_canonical_blocks.py
  - scripts/sync_canonical_blocks.py
re_affirms:
supersedes:
---

## Context

The canonical-blocks extraction refactor (td-001) introduces two new test concerns:

1. **Behavioral integration tests** — verifying all four canonical blocks satisfy structural requirements in both command files (section presence, byte-identical mirror constraint, canonical-file byte-identity, token budget, shipped-artifact isolation, idempotency). The existing `hooks/test_onboard_praxion_block.py` already covers the §Praxion Process block with this style.

2. **Sync-engine unit tests** — verifying the `scripts/sync_canonical_blocks.py` engine: the block locator, `--check` / `--write` / `--dry-run` modes, exit codes, round-trip fidelity, idempotency, and edge cases (trailing newline, blank lines inside fence). These tests use synthetic fixture command files via `tmp_path`, not the real command files.

The systems-architect's Components section listed both `scripts/test_sync_canonical_blocks.py` and the extended `hooks/test_onboard_praxion_block.py` as separate files. The orchestrator's decomposition guidance collapsed them; this decision restores the separation.

## Decision

Two distinct test files serve separate scopes:

- **`hooks/test_onboard_praxion_block.py`** — extended to cover all four blocks parametrically. Behavioral integration tests read real `commands/*.md` files. These tests are the end-to-end regression guarantee for AC-05 and AC-06.
- **`scripts/test_sync_canonical_blocks.py`** — new file. Unit tests for the sync script engine against synthetic `tmp_path` fixtures. These tests verify the parser/locator logic and CLI contract independently of the real command files.

## Considered Options

### Option 1 — Single test file in `hooks/` (collapsed)

Extend `hooks/test_onboard_praxion_block.py` to include both behavioral and engine unit tests.

**Pros:** fewer files, single discovery location.

**Cons:** mixes behavioral integration tests (real files) with synthetic unit tests (tmp_path). Failure diagnosis is harder — a sync-engine parse bug surfaces identically to a real block extraction error. Test file grows to ~600+ lines, exceeding the 400-line soft ceiling from `coding-style.md`.

### Option 2 — Separate files (chosen)

`hooks/test_onboard_praxion_block.py` for behavioral; `scripts/test_sync_canonical_blocks.py` for engine unit.

**Pros:** clear scope boundary per test file. Failure messages distinguish "the canonical blocks in the real files are wrong" from "the sync script's locator logic is broken." Each file stays within size conventions. Mirrors the existing pattern: `scripts/test_finalize_adrs.py`, `scripts/test_render_claude_md.py` are colocated with their production scripts.

**Cons:** two test files to maintain instead of one.

## Consequences

**Positive:**
- Failure messages are scoped: `hooks/test_onboard_praxion_block.py` failures indicate block content / placement issues; `scripts/test_sync_canonical_blocks.py` failures indicate sync-engine logic bugs.
- Engine unit tests can be written before the real canonical files exist (synthetic fixtures), enabling the BDD/TDD parallel — test-engineer authors `scripts/test_sync_canonical_blocks.py` concurrently with the implementer writing the sync script.
- File size stays manageable for both test files.

**Negative:**
- Two files to maintain. Minor cost; both are colocated with their subjects.
