---
id: dec-011
title: Memory-first budget allocation with ADR soft cap for hook injection
status: superseded
superseded_by: dec-023
category: architectural
date: 2026-04-04
summary: ADR context injected into SubagentStart hook using memory-first budget allocation with a 2,000-char soft cap for ADRs
tags: [memory, adr, hooks, budget, injection]
made_by: agent
agent_type: systems-architect
pipeline_tier: standard
affected_files: [hooks/inject_memory.py, memory-mcp/tests/test_inject_memory.py]
---

## Context

The SubagentStart hook (`inject_memory.py`) injects memory context into every spawned agent within an 8,000-character budget. Architecture Decision Records (ADRs) in `.ai-state/decisions/` contain valuable decision context that agents should also receive automatically. The question is how to share the budget between memory entries and ADR summaries without breaking existing behavior.

## Decision

Use memory-first budget allocation: memory output is built first against the full budget (preserving backward compatibility), then ADRs fill the remaining space. A soft cap (`ADR_SOFT_CAP = 2000` chars) prevents ADR content from growing unboundedly when both the budget is ample and ADR count is high. The soft cap is a trimming threshold, not a hard ceiling -- when remaining budget exceeds the soft cap and total ADR content is under the soft cap, all ADRs are included without truncation.

ADR summaries are read from `DECISIONS_INDEX.md` (not individual ADR files) for performance and simplicity. The index table is parsed with string splitting on `|` (no regex, no new imports). Only `accepted` and `proposed` ADRs are injected; `superseded` and `rejected` are filtered out.

## Considered Options

### Option 1: Split budget (fixed allocation)
Reserve 6,000 chars for memory and 2,000 for ADRs. Simple and predictable but wastes allocation when one side is small (e.g., 2 memory entries and 10 ADRs would waste ~5,500 chars of memory allocation).

### Option 2: ADR-first allocation
Give ADRs priority, memory fills the remainder. Would break backward compatibility -- existing memory output could shrink when ADRs are added.

### Option 3: Memory-first with soft cap (chosen)
Memory gets first priority, ADRs fill remaining space with a soft cap. Preserves backward compatibility. The soft cap is tunable. Both sources degrade gracefully.

## Consequences

**Positive:**
- Zero impact on existing memory injection behavior
- ADRs are additive -- they appear only when budget allows
- Soft cap is a single constant, easy to tune as usage patterns emerge
- Independence: memory works without ADRs, ADRs work without memory

**Negative:**
- If memory grows very large (50+ high-importance entries filling most of the budget), ADR content gets squeezed
- The soft cap value (2,000) is an educated guess based on current 10-ADR state; may need adjustment as ADR count grows
