---
id: dec-438
draft_id: dec-draft-c609547f
title: Praxion's architecture model projects sixteen focused views sized to the legibility thresholds; `index` is the System Context
status: accepted
category: implementation
date: 2026-10-04
summary: "Six views become sixteen: index (System Context, replaces context), components (Container), one Component view per layer (knowledge, orchestration, persistence, tooling), the forward pipeline in four slices drawn without the implicit pipeline frame (ideation to design, acceptance tests and plan, plan to build, verification), supporting_agents (shadow and gated) and independent_agents, the feedback_loops overview, challenge_loop_detail, and the numbered dynamic views cis_loop_detail and rework_loop_detail; every non-dynamic view carries one #c4_* level tag and every view passes the review checks (text at least 10 px at 960 px, aspect 0.5-2.5, at most nine arrows per element); the orchestrator's dispatch fan draws as one aggregated edge in the orchestration view; no element or relationship is removed. Amended at execution (2026-10-04) from the twelve views of the first draft."
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

Project sixteen views. Every non-dynamic view carries exactly one `#c4_*` level tag (`c4_system_context`, `c4_container` or `c4_component`); dynamic views carry none. Ids and titles are the ones declared in `docs/diagrams/architecture/src/architecture.c4`; the render appends the C4 type to the title.

| View | Title | Type | Contents |
|---|---|---|---|
| `index` | Praxion in its context | System Context | The developer, the six external systems (Claude Code, Claude Desktop, Cursor, GitHub, Arize Phoenix, Anthropic API) and Praxion; replaces `context` |
| `components` | Praxion's building blocks | Container | Praxion as a frame holding the four layers as boxes, with the developer and the six externals |
| `knowledge_components` | Knowledge layer | Component | Skills, rules, commands and agents; the installers that deploy them; the agent pipeline they shape (the commands-to-architect dispatch excluded) |
| `orchestration_components` | Orchestration layer | Component | The main agent, the agent pipeline as one element, hooks, `.ai-work/`, the Chronograph relay and `.ai-state/`; the 17 dispatches draw as one aggregated edge |
| `persistence_components` | Persistence layer | Component | Chronograph, `.ai-state/`, ADR fragments and the tech-debt ledger; Arize Phoenix; the scripts and the dashboard that finalize or read the stores |
| `tooling_components` | Tooling layer | Component | Installers, versioning, dashboard and eval framework, with the knowledge layer, `.ai-work/` and the Anthropic API they reach |
| `agent_pipeline` | Agent pipeline, ideation to design | Component | Promethean, researcher and systems architect with IDEA_PROPOSAL, RESEARCH_FINDINGS, SYSTEMS_PLAN and SPEC_EXTRACT |
| `agent_pipeline_plan` | Agent pipeline, acceptance tests and plan | Component | Systems architect, test engineer and implementation planner with SPEC_EXTRACT, ACCEPTANCE_TESTS, SYSTEMS_PLAN and IMPLEMENTATION_PLAN |
| `agent_pipeline_build` | Agent pipeline, plan to build | Component | Implementation planner, implementer, test engineer and doc engineer with IMPLEMENTATION_PLAN, WIP, TEST_RESULTS and LEARNINGS |
| `agent_pipeline_verify` | Agent pipeline, verification | Component | Verifier with WIP, TEST_RESULTS and VERIFICATION_REPORT |
| `supporting_agents` | Shadow and gated agents | Component | The main agent with the context engineer, discipline consultant, CI/CD engineer and roadmap cartographer, and CONTEXT_REVIEW |
| `independent_agents` | Independent and post-pipeline agents | Component | The main agent with sentinel, architect validator and skill genesis, LEARNINGS and the tech-debt ledger |
| `feedback_loops` | Feedback loops | Component | Researcher, systems architect, verifier, main agent and commands with RESEARCH_FINDINGS, SYSTEMS_PLAN, REWORK_MANIFEST and VERIFIER_FINDINGS; loop-tagged edges only |
| `challenge_loop_detail` | Challenge loop | Component | Interface designer, agentic transactions architect and systems architect with INTERFACE_DESIGN and TRANSACTIONS_DESIGN |
| `cis_loop_detail` | Continuous improvement signals loop | Dynamic | Seven numbered steps from the researcher's CIS section to the ledger row; the three ledger writers in one `parallel` block |
| `rework_loop_detail` | Rework loop | Dynamic | Eight numbered steps from the verifier's rework manifest to the architect re-entering the pipeline at the plan |

- The four forward-flow views `exclude praxion.orchestration.pipeline`, the implicit parent LikeC4 would otherwise draw as a frame around the agents; without the frame, ELK lays the agents and their documents out as one flow instead of routing every document arrow around a frame. The exclusion is view-level: the element and its relationships stay in the model.
- The orchestrator's dispatch fan draws as one aggregated edge in `orchestration_components`, as individual edges only in `supporting_agents` and `independent_agents`, whose subject is those dispatches, and nowhere else: `feedback_loops` excludes `orchestrator -> pipeline.*`, and the forward-flow views do not include the orchestrator.
- Dynamic steps mirror recorded relationships only; the renderer flags a step with no recorded pair.
- Read-only relationships take the `reads` kind and draw dashed in element views; in a dynamic view every step draws as the solid numbered-step line (dec-444).
- The renderer gates each view on its checks (`python3 scripts/regenerate_diagrams.py --check`).

**Amendment at execution (2026-10-04).** The first draft named twelve views and a split of `persistence_tooling_components` as its fallback. The legibility checks forced three splits, each recorded as an objection in the pipeline's `LEARNINGS.md`: `persistence_tooling_components` into `persistence_components` and `tooling_components` (the named fallback); `supporting_agents` into `supporting_agents` and `independent_agents` (seven sibling agents in one rank measured 1992 px wide, past the width at which 14 px edge labels still read at 10 px when the render is shown 960 px wide); the two forward-flow views into four (a frame of five agents beside six documents measured 1600-1900 px wide). The pipeline-frame exclusion above followed as the last model change before verification, once the four slices passed every check but still routed their document arrows around the frame. Every element and relationship of the model is unchanged.

## Considered Options

### Option 1: Restyle the six views as they are

**Pros:** no embed churn.
**Cons:** fails ratio, text height and fan-in by construction; leaves seven elements undrawn.

### Option 2: Restructure into focused views (chosen)

**Pros:** each view tells one story within the thresholds; every element is drawn.
**Cons:** sixteen embeds and dashboard cards instead of six; DESIGN.md §2 moves to `index.svg`.

## Consequences

**Positive:** legible renders; full coverage; numbered loop narratives.
**Negative:** more renders to curate; the dashboard order stays alphabetical (a reading-order list is ledger work).

## Prior Decision

**dec-183 (narrowed, not replaced).** Its first and third choices stand unchanged:
- per-agent first-class elements;
- agent-to-agent communication routed through document elements.

Its tagged-edge classification also stands. Narrowed: clause 2's enumeration of six named views and their L0/L1/L2 labels. The view set is now the sixteen above, with C4 type names in place of L-numbers. "Multiple focused views, one concept each" is affirmed.

Activation: no — uncertainty: a single plausible path once the legibility thresholds are fixed (restyling in place fails them mechanically).
