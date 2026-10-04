---
id: dec-draft-c609547f
title: Praxion's architecture model projects twelve focused views sized to the legibility thresholds; `index` is the System Context
status: proposed
category: implementation
date: 2026-10-04
summary: "Six views become twelve: index (System Context, replaces context), components (Container), knowledge/orchestration/persistence-and-tooling component views, the forward pipeline split in two, supporting_agents, feedback_loops overview, numbered dynamic cis_loop_detail and rework_loop_detail, and challenge_loop_detail; each carries a #c4_* level tag, stays within 10 px at 960 px, ratio 0.5-2.5 and nine arrows per element; the orchestrator's 17 dispatches are demoted at view level; no element or relationship is removed."
tags: [diagrams, likec4, c4, views, architecture-model, legibility]
made_by: agent
agent_type: systems-architect
branch: worktree-likec4-diagram-craft
pipeline_tier: full
affected_files:
  - docs/diagrams/architecture/src/architecture.c4
  - docs/diagrams/architecture/src/_spec.c4
  - docs/diagrams/architecture/rendered/
  - docs/architecture.md
  - .ai-state/DESIGN.md
  - docs/diagrams/README.md
affected_reqs: [REQ-05, REQ-06, REQ-07, REQ-09, REQ-12, REQ-13]
supersedes_in_part: [dec-183]
---

## Context

The six views fail the legibility thresholds mechanically:
- `components` is a 4769 × 1403 strip (ratio 3.40, about 3 px text at 960 px);
- `agent_pipeline` and `feedback_loops` render text under 10 px;
- fan-in reaches 13.
- Seven elements appear in no view.
- LikeC4's automatic, untitled `index` view duplicates `context` and must still be rendered, because every model view needs a committed render.

## Decision

Project twelve views. Every non-dynamic view carries exactly one `#c4_*` level tag.

| View | Type | Contents |
|---|---|---|
| `index` | System Context | Developer, all six externals including Anthropic API, Praxion; replaces `context` |
| `components` | Container | Praxion frame with the four layers as boxes, plus externals |
| `knowledge_components` | Component | Knowledge layer |
| `orchestration_components` | Component | Orchestration layer; the 17 dispatches as one synthesized edge |
| `persistence_tooling_components` | Component | Persistence and tooling layers |
| `agent_pipeline` | Component | Forward flow, ideation to plan |
| `agent_pipeline_build` | Component | Forward flow, plan to verification |
| `supporting_agents` | Component | Shadow, gated and independent agents with their dispatch modes |
| `feedback_loops` | Component | CIS + rework overview, loop-tagged edges only |
| `cis_loop_detail` | Dynamic | Numbered steps |
| `rework_loop_detail` | Dynamic | Numbered steps |
| `challenge_loop_detail` | Component | Interface and transactions challenge loop |

- The orchestrator's dispatch fan is drawn only in the orchestration view, as one edge.
- Dynamic steps mirror recorded relationships only; the renderer flags a step with no recorded pair.
- Read-only relationships take the `reads` kind and are drawn dashed.
- The renderer gates each view on its checks. Named fallback: split `persistence_tooling_components`.

## Considered Options

### Option 1: Restyle the six views as they are

**Pros:** no embed churn.
**Cons:** fails ratio, text height and fan-in by construction; leaves seven elements undrawn.

### Option 2: Restructure into focused views (chosen)

**Pros:** each view tells one story within the thresholds; every element is drawn.
**Cons:** twice the dashboard cards and embeds; DESIGN.md §2 moves to `index.svg`.

## Consequences

**Positive:** legible renders; full coverage; numbered loop narratives.
**Negative:** more renders to curate; the dashboard order stays alphabetical (a reading-order list is ledger work).

## Prior Decision

**dec-183 (narrowed, not replaced).** Its first and third choices stand unchanged:
- per-agent first-class elements;
- agent-to-agent communication routed through document elements.

Its tagged-edge classification also stands. Narrowed: clause 2's enumeration of six named views and their L0/L1/L2 labels. The view set is now the twelve above, with C4 type names in place of L-numbers. "Multiple focused views, one concept each" is affirmed.

Activation: no — uncertainty: a single plausible path once the legibility thresholds are fixed (restyling in place fails them mechanically).
