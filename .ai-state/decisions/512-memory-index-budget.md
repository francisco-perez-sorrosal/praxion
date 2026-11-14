---
id: dec-512
draft_id: dec-draft-5a8b73b0
title: "Memory index budget: one declared ceiling owned by the audit"
status: accepted
category: behavioral
date: 2026-11-12
summary: "The memory index audit and its write-time guard warn above 5,000 bytes or 40 lines, one value owned by the audit module, replacing the four-fifths-of-load-limit warning"
tags: [memory, gate, budget, hooks]
made_by: agent
agent_type: systems-architect
branch: feat/memory-to-artifacts
pipeline_tier: full
affected_files: [scripts/check_memory_index.py, hooks/guard_memory_index.py]
affected_reqs: [REQ-01, REQ-02]
---

## Context

The project memory index loads into every session and spawn (first 200 lines or 25KB, Claude Code memory documentation, read 2026-11-12). The audit warned only past four fifths of that limit (160 lines or 20,000 bytes), so the index grew from 12.2 KB to 17.6 KB with no warning. The entries that belong there (live status and preferences) fit in 12 lines and 1,698 bytes.

## Decision

`scripts/check_memory_index.py` declares one budget, `IndexSize(lines=40, bytes=5_000)`, beside the load limit `IndexSize(lines=200, bytes=25_000)`, and owns the only literal of each. The audit reports one warning for an index above the budget and within the load limit; the four-fifths share is removed. A pure `budget_warning(before, after)` warns when a write leaves the index above the budget, within the load limit and larger than before; `hooks/guard_memory_index.py` calls it when it has nothing to refuse and returns the warning as `additionalContext` on an allowed write. One budget applies to every index both tools judge.

## Considered Options

### A share of the load limit (status quo)
Pro: no new number. Con: it warned nobody at 17.6 KB; a loss cliff is the wrong reference for a cost paid on every spawn.

### A separate constant in the guard
Pro: the hook stands alone. Con: two literals of one budget drift.

### One declared value owned by the audit (chosen)
Pro: one owner, the guard imports it as it already imports the audit's rules. Con: one budget for every project's index, so `--all` warns on indexes outside this project.

## Consequences

Positive: regrowth is seen at a fifth of the load limit, at the write and in the audit; refusals are unchanged. Negative: two other local projects' indexes (15.6 KB and 11.8 KB) draw the warning under `--all`; the hook warning reaches marketplace sessions only after a release.
