---
id: dec-034
title: Zero-net always-loaded budget impact via prune of redundant ASCII Coordination Pipeline block
status: accepted
category: configuration
date: 2026-04-12
summary: 'Add cartographer Available Agents row + Delegation Checklist + proactive-use bullet (~570 chars); offset by pruning redundant ASCII Coordination Pipeline block (~430 chars) and consolidating proactive-use examples (~120 chars). Net ≤ 0'
tags: [token-budget, always-loaded, rules, offset, roadmap, prune]
made_by: agent
agent_type: systems-architect
pipeline_tier: standard
affected_files:
  - rules/swe/swe-agent-coordination-protocol.md
  - skills/software-planning/references/coordination-details.md
---

## Context

The always-loaded content budget is at **106% of ceiling** (56,164 / 52,500 chars as of 2026-04-12). SPIRIT dimension 2 (coordinator awareness) strongly favors a formal Available Agents table entry + Delegation Checklist + Proactive Agent Usage bullet for the new `roadmap-cartographer` agent. These additions would total ~570 chars of always-loaded content — a net regression under the current budget.

ROADMAP.md weakness W1 flags the budget pressure explicitly. Memory entry `always-loaded-budget-at-106pct-apr-2026` names the constraint: *any new always-loaded content must bundle a reclamation offset of equal or greater size in the same ADR.*

Pre-existing precedent (dec-022) extracts `coordination-details.md` from the coordination-protocol rule, with stub-sections retained in the rule pointing to the reference. The same pattern is available here.

Inspection of `rules/swe/swe-agent-coordination-protocol.md` reveals:

- An ASCII `### Coordination Pipeline` block (~430 chars) diagrams the same pipeline already described in (a) the Available Agents table, (b) the prose immediately above the ASCII block, and (c) the Mermaid component diagram in `.ai-state/ARCHITECTURE.md`.
- Two verbose Proactive Agent Usage examples (~120 chars combined in the overflow) that can be consolidated via a link to the `software-planning` skill.

## Decision

**Additions** (+~570 chars):

1. One row in the Available Agents table for `roadmap-cartographer`.
2. A Delegation Checklist block for `roadmap-cartographer` (3 bullets, mirroring existing agent checklists).
3. One bullet in the Proactive Agent Usage list describing roadmap-intent recognition.

**Reclamations** (−~550 chars):

1. Replace the ASCII `### Coordination Pipeline` block with a summary sentence + link to `coordination-details.md#coordination-pipeline-diagram` — matching dec-022's stub-section pattern. The Mermaid diagram in `.ai-state/ARCHITECTURE.md` preserves the visual; the coordination-details.md reference preserves the ASCII form for readers who want it.
2. Consolidate two verbose Proactive Agent Usage examples by linking to the `software-planning` skill's detailed examples.

**Net delta**: ≈ 0 chars (target: ≤ 0). The implementer measures actual char delta at commit time; if the measured delta exceeds +50 chars, the implementer escalates to the graceful-degradation path (see below).

**Graceful degradation**: if the offset proves infeasible at implementation time, the rule edits are skipped entirely. The cartographer still ships. Coordinator discovery then relies on:
- The `/roadmap` slash command (explicit)
- The cartographer's description-based semantic activation (when the coordinator recognizes roadmap intent)

This is a degraded but functional path — loses the formal delegation-table entry but preserves the capability itself.

## Considered Options

### Option 1 — No rule edits; rely solely on command + description

Skip the Available Agents row and Delegation Checklist.
**Pros:** zero budget impact; simpler implementation.
**Cons:** weakens SPIRIT dimension 2 (coordinator awareness) — the agent is not formally registered in the rule that governs delegation; coordinator must rely on implicit semantic activation for non-explicit invocations; new agent is less visible to anyone reading the delegation protocol.

### Option 2 — Accept net-positive budget impact

Add the ~570 chars without reclamation.
**Pros:** formal delegation-table entry; no rework on the existing rule.
**Cons:** violates the 106%-of-ceiling budget constraint; sets a precedent of additive-only growth; amplifies ROADMAP.md W1.

### Option 3 — Prune redundant content as offset (chosen)

Prune the ASCII Coordination Pipeline block + consolidate proactive-use examples; add the cartographer entries.
**Pros:** net ≤ 0 delta; the ASCII block is truly redundant (same info in Available Agents table + Mermaid diagram + prose); reclamation is reusable pattern; dec-022's stub-section approach preserves anchor stability; SPIRIT dim 2 fully served.
**Cons:** ASCII block removal is a user-visible change for readers who prefer inline ASCII over links; mitigated by the summary sentence + link pattern.

### Option 4 — Narrow `paths:` on an existing unconditional rule

Take the dec-028 approach on a different always-loaded rule to reclaim chars.
**Pros:** larger potential reclamation; might offset more than the addition.
**Cons:** changes unrelated rule behavior; couples this ADR to a rule-scoping decision that deserves its own analysis; scope creep.

## Consequences

**Positive:**

- SPIRIT dim 2 (coordinator awareness) served through three layers: command + delegation-table row + semantic activation.
- Token-budget discipline maintained at net ≤ 0.
- Reclamation pattern is reusable for future rule-affecting additions.
- dec-022's stub-section pattern reinforced.

**Negative:**

- ASCII readers lose the inline diagram; mitigated by the summary sentence + reference link.
- Implementation requires careful char accounting at commit time (AC-11 measures this explicitly).
- Graceful-degradation path is a reduced state; users who care about formal delegation-table visibility lose that in the degraded path.

**Operational:**

- Implementer edits `rules/swe/swe-agent-coordination-protocol.md` per the plan's step decomposition.
- `skills/software-planning/references/coordination-details.md` receives the moved ASCII pipeline diagram content under an appropriately anchored section.
- Char delta measured at commit via `wc -c` on before/after of always-loaded files.
- Verifier AC-11 confirms net delta ≤ 0 before marking the task complete.
- If degraded path is taken, AC-1 discovery testing verifies command + semantic activation still reliably fire.
