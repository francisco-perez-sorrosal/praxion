---
id: dec-114
title: Split TECH_DEBT_LEDGER into active + resolved file pair
status: accepted
category: architectural
date: 2026-05-01
summary: Split the single TECH_DEBT_LEDGER.md into an active ledger (open/in-flight) and a sibling TECH_DEBT_RESOLVED.md (resolved/wontfix); the pair forms one logical namespace.
tags: [tech-debt, ledger, lifecycle, finalize, observability]
made_by: agent
agent_type: orchestrator
pipeline_tier: direct
affected_files:
  - .ai-state/TECH_DEBT_LEDGER.md
  - .ai-state/TECH_DEBT_RESOLVED.md
  - rules/swe/agent-intermediate-documents.md
  - scripts/finalize_tech_debt_ledger.py
  - scripts/test_finalize_tech_debt_ledger.py
  - agents/sentinel.md
re_affirmed_by:
  - dec-262
---

## Context

The pre-existing convention treated `.ai-state/TECH_DEBT_LEDGER.md` as a single, append-only Markdown table where rows are **never deleted** — resolved rows accumulate as a debt-fix audit trail. The `wontfix` status is a tombstone. Status updates happen in place via `status`, `resolved-by`, and `last-seen`. The `finalize_tech_debt_ledger.py` post-merge script collapses duplicate rows by `dedup_key` with status precedence (`resolved > in-flight > open > wontfix`).

Two pressures motivate revisiting that lifecycle:

1. **Cognitive load.** As resolved rows accumulate, the file grows and the "what's actively open?" question becomes an O(N) scan instead of O(active-rows). Consumer agents (systems-architect, implementation-planner, implementer, test-engineer, doc-engineer) read the ledger to filter by `owner-role` and pick actionable items; mixed open+resolved noise degrades that signal. The ratio is asymmetric over time — resolved rows accrue faster than they're created (one resolution per row, lifetime), so the resolved fraction trends toward dominance.
2. **No real coupling between active and resolved rows.** The dedup script needs to consult resolved rows only on **recurrence** (a new finding matching an old `dedup_key`). That's a rare event. The common-case reads (consumers picking work) and writes (producers filing new rows) operate exclusively on active rows.

The user raised the cognitive-load concern explicitly and asked for a structural fix that does not break the audit-trail invariant. The single-file convention's stated *purpose* is the audit trail; its *form* (one file) was descriptive of the original implementation, not load-bearing.

## Decision

Split the ledger into a two-file pair:

- **`.ai-state/TECH_DEBT_LEDGER.md`** — active rows only (`status ∈ {open, in-flight}`)
- **`.ai-state/TECH_DEBT_RESOLVED.md`** — terminal rows only (`status ∈ {resolved, wontfix}`)

The pair forms **one logical namespace**:

- `id` (`td-NNN`) is unique across both files; the next-NNN scan covers both
- `dedup_key` collisions are detected across both files (recurrence detection)
- ADR cross-references treat the pair as a single ledger; consumers may cite a `td-NNN` regardless of which file currently holds it

**Migration semantics.** When a row's status transitions to `resolved` or `wontfix`, the row is moved (cut + paste) from the active LEDGER to the RESOLVED file. The move is performed by `finalize_tech_debt_ledger.py` at post-merge, and may also be done in-commit by the agent or human authoring the resolution. The script is idempotent: running it on a settled state is a byte-equivalent no-op.

**Re-open semantics.** If a producer files a new active row whose `dedup_key` matches a row in the RESOLVED file, the resolved row is **moved back** to the active LEDGER with `status = open`, `last-seen` set to today, and a `notes` suffix `recurrence: re-opened YYYY-MM-DD` describing the recurrence event. The newly-filed row is collapsed into it (preserving the historical row's `id` and `first-seen`). This preserves the "this issue was resolved before, now back" audit trail.

**`dedup_key` recomputation on class change.** When a producer reclassifies a row (e.g., `other` → `token-budget`), the producer recomputes `dedup_key` from the new field set. The convention text gains an explicit note about this; the existing rule already says reclassification is allowed.

**Schema unchanged.** All 14 row fields + `dedup_key` retain their definitions and constraints. The `class` enum gains a new value `token-budget` for always-loaded headroom optimization (the existing `other` escape-hatch was accumulating four such rows; the rule's own "propose new class if `other` recurs" guidance fires).

## Considered Options

### Option A — Two-file pair with automated migration (chosen)

**Pros:**
- Active ledger stays focused — consumer reads are O(active-rows)
- Audit trail preserved (RESOLVED file is committed; git history intact)
- Recurrence detection still works via cross-file `dedup_key` matching
- Sentinel TD03 and TT03 (which read open rows for thresholds) can keep reading the active LEDGER alone — they get faster
- Aligns with the proven `decisions/<NNN>-<slug>.md` + `DECISIONS_INDEX.md` pattern: source-of-truth files + a derived/companion file

**Cons:**
- `finalize_tech_debt_ledger.py` grows in complexity (read both files, route by terminal status, handle re-open)
- TD05 status-update-discipline check must scan both files (it audits `resolved-by` completeness, which is a terminal-row concern)
- Two files to keep consistent for `id` and `dedup_key` uniqueness (mitigated: the finalize script enforces it)

### Option B — Single file + derived companion view

Keep `TECH_DEBT_LEDGER.md` as the single source of truth; add a generator script that produces `TECH_DEBT_RESOLVED.md` as a filtered, regenerated view (`status ∈ {resolved, wontfix}`).

**Rejected because** the active ledger keeps growing — the user's stated cognitive-load concern is unsolved. A derived view alongside an unbounded source-of-truth file does not shrink the file consumers actually read.

### Option C — Status-query script (read-only filter)

Provide a `scripts/show_open_tech_debt.py` that filters the ledger on demand without changing the file structure.

**Rejected because** consumer agents read the full file; a query script doesn't help the LLM-context cost of loading a noisy ledger. The cognitive-load problem applies to machine readers, not just human readers.

## Consequences

**Positive:**
- "What's open?" becomes O(active-rows) for both human and machine readers
- Resolved-row accumulation no longer degrades the active-debt signal as the ecosystem matures
- The split is structurally similar to the ADR `dec-NNN` + `DECISIONS_INDEX` pair already in production, so no new mental model
- Recurrence detection becomes more visible — the re-open transition is now an explicit row-move event, not a silent status flip in a long file

**Negative:**
- Two files to maintain consistency across; the finalize script absorbs that complexity
- Worktree concurrency: the post-merge dedupe must lock both files (advisory `fcntl` lock extended to a single shared lock file covering both); already covered by the existing lock-path pattern
- Existing tooling that reads `TECH_DEBT_LEDGER.md` only (e.g., older scripts) misses resolved rows; this is intentional but must be flagged in the rule update

**Operational:**
- Initial migration: `td-001` (already `resolved`) moves from LEDGER to a newly-created RESOLVED file as part of the same commit that lands this lifecycle change
- `class: token-budget` enum value lands in the same commit (side-quest already discussed; the four token-budget tech-debt rows being resolved next consume it)
- `agents/sentinel.md` TD05 updated to scan both files; TD03 and TT03 read only the active LEDGER (open rows are exclusively there); the existing CH and TT dimensions are unaffected

## Migration Note

Pre-existing rows with `status ∈ {resolved, wontfix}` migrate from LEDGER to RESOLVED in the same commit that lands this ADR. Today that is a single row (`td-001`). No backfill of historical rows is needed — they were already authored under the single-file convention, and their `dedup_key` values are stable across the move.
