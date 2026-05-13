---
id: dec-170
title: Refactor auto_complete_install.py _link_rules() to per-file symlinking
status: accepted
category: implementation
date: 2026-05-13
summary: _link_rules() in auto_complete_install.py is refactored from directory-level to per-file symlinking to enable manifest-based hook-deliver filtering, matching the behavior of lib/install_shared.sh link_rules().
tags: [rules, installer, auto-complete, refactor, marketplace-install]
made_by: agent
agent_type: implementation-planner
branch: worktree-rules-reorg-blacklist
pipeline_tier: full
affected_files:
  - hooks/auto_complete_install.py
  - hooks/test_auto_complete_install.py
affected_reqs:
  - REQ-02
  - REQ-05
re_affirms: null
supersedes: null
---

## Context

`hooks/auto_complete_install.py:_link_rules()` (lines 166-181) iterates the top-level entries of `rules/` (e.g., `rules/swe/`, `rules/ml/`, `rules/writing/`) and symlinks each as a directory object into `~/.claude/rules/`. This is a directory-level symlinking approach.

`lib/install_shared.sh:link_rules()` iterates individual `.md` files recursively with `find`, creating per-file symlinks.

The systems-architect (`dec-167`) requires both functions to skip files with `install: hook-deliver` in the manifest. Directory-level skipping in `auto_complete_install.py` cannot achieve per-file granularity — it can only skip an entire top-level directory (e.g., skip all of `rules/swe/` to avoid `swe/memory-protocol.md`), which would also skip core rules in the same directory.

This divergence was not visible in the architect's analysis (which described both functions as "almost the same logic"). The planner discovered it during codebase verification (Phase 2).

## Decision

Refactor `_link_rules()` in `hooks/auto_complete_install.py` to per-file recursive symlinking, matching `lib/install_shared.sh:link_rules()`:

1. Use `pathlib.Path.rglob('*.md')` to walk all `.md` files recursively under `rules/`
2. Apply the same skip rules as `lib/install_shared.sh`: skip `README.md`, skip `*/references/*`
3. Read `rules/_manifest.yaml` from the plugin cache to determine which rule IDs have `install: hook-deliver`
4. Skip those files (create no symlink)
5. For remaining files, create per-file symlinks preserving relative directory structure under `~/.claude/rules/`
6. If manifest is missing, fall back to current behavior (link all — backward compat)

## Considered Options

### Option 1 — Directory-level filtering (skip top-level dirs)

Skip symlinking `rules/swe/` entirely if any file in it is hook-deliver.

**Pros:** Minimal change.
**Cons:** Would also skip core rules in the same directory (`agent-behavioral-contract.md` etc.). Completely unacceptable — violates AC-04 and AC-06.

### Option 2 — Per-file refactor (chosen)

Switch to per-file walking and symlinking, then apply per-file manifest filter.

**Pros:** Matches `lib/install_shared.sh` behavior exactly. Enables granular filtering. Testable at the file level.
**Cons:** More extensive change to `_link_rules()`. Required: existing test coverage must be updated. Justified by correctness requirement.

### Option 3 — Hybrid: keep directory links but walk directory to handle exceptions

Symlink top-level directory objects, but for dirs that contain any hook-deliver file, switch to per-file linking within that dir.

**Pros:** Minimal disruption for dirs with no hook-deliver files.
**Cons:** Complex conditional logic. Harder to test. Fragile — adding a hook-deliver file to a new directory requires the logic to detect it. Rejected on simplicity grounds.

## Consequences

**Positive:**
- `auto_complete_install.py` and `lib/install_shared.sh` now have equivalent file-level semantics.
- Per-file manifest filtering works correctly.
- Future rule additions only require manifest update; no installer code changes.

**Negative:**
- More extensive change to `_link_rules()` than the architect anticipated.
- Test file `hooks/test_auto_complete_install.py` requires new test cases for the filtering behavior.

**Operational:**
- Implemented in Step 11.
- Test cases added to `hooks/test_auto_complete_install.py` covering: hook-deliver file skipped; non-hook-deliver file linked; missing manifest falls back to link-all.
- The refactor uses `[Phase: Refactoring]` methodology: characterize current behavior via existing tests, then refactor, verify existing tests still pass, add new tests.

**Technical debt resolved:**
- The divergence between `_link_rules()` and `link_rules()` was pre-existing tech debt (two implementations of the same concern). This refactor eliminates it.

**Cross-cutting:**
- Depends on `dec-167` (hook-delivery mechanism) — that ADR mandates per-file filtering.
- Enables AC-05 (marketplace install produces functioning blacklist).
