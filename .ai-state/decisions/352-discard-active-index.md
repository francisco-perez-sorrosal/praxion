---
id: dec-352
title: ACTIVE_INDEX.md is not built — the current-streamline filter already ships at query time
status: accepted
category: implementation
date: 2026-08-31
summary: 'A generated accepted+re-affirmation index would remove 5.5% of DECISIONS_INDEX.md while remaining an ungated ~41.6K-token read; query_adrs.py already defaults to the current streamline, so no ACTIVE_INDEX.md and no --index emission mode are built.'
tags: [adr, active-index, decisions-index, read-path, context-cost, query-tool, no-build]
made_by: agent
agent_type: systems-architect
branch: worktree-adr-living-view
pipeline_tier: standard
affected_files:
  - scripts/query_adrs.py
  - .ai-state/decisions/DECISIONS_INDEX.md
---

## Context

The adr-compaction spike ranked candidate (a) — a generated `ACTIVE_INDEX.md` holding only `accepted` + `re-affirmation` records — last among the pursued options, worth doing only *after* a still-current audit made `status` carry signal. The audit ran and reported the opposite: the corpus is ~93% still-current, so almost nothing would move into terminal status. The user asked for an explicit redundancy verdict against what `dec-347`'s query tool already serves, including the option of a `query_adrs.py --index` emission mode.

Measured on this corpus (347 finalized records): 328 in the current streamline, **19 terminal (5.5%)**. `DECISIONS_INDEX.md` is ~44K tokens; an active-only index projects to ~41.6K.

## Decision

**Do not build `ACTIVE_INDEX.md`, and do not add an `--index` emission mode to `scripts/query_adrs.py`.**

Three independent reasons, any one sufficient:

1. **The filter already ships at query time.** `query_adrs.py`'s `DEFAULT_STATUSES` is `{accepted, re-affirmation}`, with `--all` as the opt-out — `dec-347` delivered the "filter the list" capability as a query-time view. A materialized index is the same filter, stale between regenerations, and a fourth flat-glob consumer of `.ai-state/decisions/`.
2. **It fails at the job it would exist for.** As an *orientation* tier it would be a ~41.6K-token artifact — itself an ungated full read, the exact act the Discovery Protocol forbids. It removes 5.5% of a cost that is an order of magnitude over the threshold that matters.
3. **Orientation is answered elsewhere.** The checkpointed `DESIGN.md` (`dec-draft-c5d81484`) is the sanctioned answer to "what is the architecture now". Building both yields two orientation tiers, one of them 40× the tokens and answering a strictly worse question.

`query_adrs.py`'s existing contract — a selector is mandatory, there is no unfiltered mode — is a correct constraint, not a gap. Its output is bounded by the query, not by the corpus; an `--index` mode would give that property up.

## Considered Options

### A — Discard (chosen)
Pros: no new artifact, no new generation trigger, no fourth glob consumer; the capability already exists at zero token cost. Cons: gives up a git-diff-reviewable record of decisions leaving the streamline.

### B — Improve existing (`query_adrs.py --index`)
Pros: reuses the shipped tool rather than adding an artifact. Cons: output would be sized by the corpus rather than the query, inheriting exactly the failure mode that makes `DECISIONS_INDEX.md` forbidden reading.

### C — Build `ACTIVE_INDEX.md`
Pros: the active/terminal split becomes visible in git history. Cons: 5.5% yield against a measured 800%-over-threshold problem; staleness between regenerations; a new consumer to keep in sync with the finalize protocol.

## Consequences

Positive: the question is settled with numbers and is greppable (`query_adrs.py --grep "active index"`) rather than re-litigated each time the index's size is noticed. No new machinery.

Negative: the active/terminal split remains invisible to `ls` and to PR diffs — a reader learns a decision left the streamline only when some tool renders it. `dec-317` accepted the same trade-off when it rejected an archive directory; this decision is consistent with it.

**Reversal trigger**: if the terminal-status share ever exceeds ~25% of the corpus, the 5.5% arithmetic no longer holds and the question should be re-opened.
