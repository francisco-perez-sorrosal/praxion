---
id: dec-061
title: ADR Finalize Protocol -- draft to NNN at merge-to-main
status: accepted
category: architectural
date: 2026-04-19
summary: A new `scripts/finalize_adrs.py` promotes draft ADRs under `.ai-state/decisions/drafts/` to `<NNN>-<slug>.md` at merge-to-main, rewrites cross-references in sibling ADRs/LEARNINGS/PLAN docs, regenerates the index, and is idempotent; invoked by post-merge hook and `/merge-worktree`.
tags:
  - concurrency
  - adrs
  - finalize
  - hooks
made_by: agent
agent_type: systems-architect
pipeline_tier: full
affected_files:
  - "scripts/finalize_adrs.py"
  - "scripts/git-finalize-hook.sh"
  - "scripts/reconcile_ai_state.py"
  - "commands/merge-worktree.md"
  - "rules/swe/adr-conventions.md"
  - "agents/sentinel.md"
---

## Context

Fragment-naming (dec-056) solves unstable identifiers at creation. The complementary question is when and how drafts become stable `<NNN>-<slug>.md` files. External research converged on "assign sequence at merge-to-main" -- the branchnews rename-at-PR pattern. Praxion already has a post-merge hook (`scripts/git-post-merge-hook.sh`) and a reconciler (`scripts/reconcile_ai_state.py`) -- the finalize step extends these existing primitives rather than introducing a new pipeline stage.

Cross-reference integrity is the sharp edge. When `dec-draft-abc123 supersedes dec-draft-def456` and both are finalized in the same merge, the finalize step must rewrite both directions across every file that could hold a `dec-draft-*` reference.

## Decision

A new script `scripts/finalize_adrs.py` (pure stdlib Python) implements the finalize protocol. Invocation modes:

- `--merged` (default, called by post-merge hook): detect drafts added in the just-merged commit via `git log --diff-filter=A --name-only <merge-base>..HEAD -- .ai-state/decisions/drafts/`; promote them.
- `--branch <name>`: manually promote drafts created by a specific branch.
- `--dry-run`: print planned changes without writing.

Promotion steps per draft, in order:

1. Assign the next sequential NNN by scanning `.ai-state/decisions/` for the highest existing `<NNN>-<slug>.md`, ignoring `drafts/`.
2. Extract the slug from the draft filename (last `-<slug>.md` component).
3. Rename `drafts/<fragment-filename>.md` to `<NNN>-<slug>.md`.
4. Rewrite frontmatter `id: dec-draft-<hash>` to `id: dec-NNN`.
5. Walk a bounded set of locations to rewrite the old `dec-draft-<hash>` to `dec-NNN`:
   - All ADR files in `.ai-state/decisions/` (drafts and finalized) -- `supersedes`, `superseded_by`, `re_affirms`, `re_affirmed_by` frontmatter and inline `[dec-draft-<hash>]` or bare `dec-draft-<hash>` body references.
   - All `LEARNINGS.md` files under `.ai-work/*/`.
   - All `SYSTEMS_PLAN.md` and `IMPLEMENTATION_PLAN.md` files under `.ai-work/*/`.
   - `.ai-state/SPEC_*.md` that match the current pipeline's task slug (detected from `.ai-work/` directory layout).
6. After all drafts in the current batch are promoted, run `python scripts/regenerate_adr_index.py` to update `DECISIONS_INDEX.md`.

Concurrency safety: the script acquires an advisory file lock on `.ai-state/decisions/drafts/.finalize.lock` via `fcntl.LOCK_EX` before any writes. The lock is released at exit. Pattern matches existing memory-mcp locking.

Idempotence: if `drafts/` is empty or all drafts in the current batch are already finalized, the script exits 0 with "nothing to do".

Invocation chain:

- `scripts/git-post-merge-hook.sh` gains one additional call after reconciliation: `python3 "$FINALIZE_SCRIPT" --merged 2>/dev/null || true`.
- `commands/merge-worktree.md` gains Step 6.5: run `python scripts/finalize_adrs.py --merged` to cover merges not triggered by the hook.
- `scripts/reconcile_ai_state.py::reconcile_adr_numbers()` gains a deprecation comment; it remains as a safety net for one release, then removed. A guard is added so the legacy renumber path skips when no `drafts/` directory changes are present in the merge.

## Considered Options

### 1. Finalize at merge via post-merge hook and `/merge-worktree` (chosen)

Extends existing primitives. Atomicity: a single batch of drafts promotes together, preserving cross-reference integrity. Recovery: failed finalize leaves drafts untouched; rerun is safe (idempotent).

### 2. Finalize on-demand only (via explicit command)

User-triggered `/finalize-adrs`. Rejected: violates the "zero-friction" design principle -- pipelines would complete with drafts still in `drafts/` until the user remembers to run the command.

### 3. Continuous numbering (assign NNN eagerly, renumber on conflict)

Current behavior. Rejected: causes the broken-cross-reference class of bugs the fragment scheme was designed to eliminate.

### 4. Finalize at `git commit` time (pre-commit hook)

Drafts would promote at each commit, not at merge. Rejected: pipelines frequently iterate on drafts pre-PR; finalizing too early defeats the fragment scheme's purpose and causes the same NNN collisions.

## Consequences

**Positive:**

- Cross-reference integrity preserved across all three concurrency modes.
- Idempotent and recoverable -- operator can re-run safely.
- Integrates with existing post-merge hook and `/merge-worktree` command -- no new invocation surface.
- `--dry-run` supports operator verification before merge.
- Advisory file lock prevents concurrent finalize races (low-frequency but consequential).

**Negative:**

- `finalize_adrs.py` is new code to maintain.
- Deprecation window for `reconcile_ai_state.py::reconcile_adr_numbers()` adds temporary complexity.
- Text rewriting is inherently brittle; bounded walk scope mitigates but does not eliminate risk.

**Risks:**

- Rewrite misses a location where a `dec-draft-<hash>` reference lives. Mitigation: bounded walk scope (see step 5), `--dry-run` flag, explicit test cases for each location type.
- Post-merge hook fails silently (shell `|| true`). Mitigation: `/merge-worktree` duplicates the finalize call, so manual merge flow is covered.
- Two post-merge hook invocations race (rare). Mitigation: file lock serializes them.
