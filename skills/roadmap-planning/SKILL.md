---
name: roadmap-planning
description: Roadmap planning, feature prioritization, and backlog management for
  technical projects. Covers prioritization frameworks (RICE, MoSCoW, WSJF, Kano,
  ICE), dependency mapping between features, roadmap visualization formats (now-next-later,
  timeline, theme-based, outcome-based), and capacity-based planning. Integrates with
  promethean's IDEA_LEDGER output to produce prioritized backlogs that flow into
  spec-driven-development. Use when prioritizing features, building a product roadmap,
  managing a backlog, sequencing work across releases, release planning, backlog
  grooming, mapping feature dependencies, or deciding what to build next.
compatibility: Claude Code
allowed-tools: [Read, Write, Edit, Glob, Grep, Bash]
---

# Roadmap Planning

Transform unstructured ideas into prioritized, sequenced plans. Sits between ideation (promethean) and specification (spec-driven-development) in the pipeline: promethean generates ideas; this skill organizes them into a roadmap; SDD turns roadmap items into behavioral specs.

**Satellite files** (loaded on-demand):

- [references/prioritization-frameworks.md](references/prioritization-frameworks.md) -- RICE, MoSCoW, WSJF, Kano, ICE scoring with worked examples and selection criteria
- [references/dependency-mapping.md](references/dependency-mapping.md) -- feature dependency graphs, critical path identification, sequencing strategies
- [references/roadmap-formats.md](references/roadmap-formats.md) -- now-next-later, timeline-based, theme-based, outcome-based roadmap templates

## Pipeline Position

```text
promethean                 roadmap-planning              spec-driven-development
IDEA_LEDGER_*.md  ──►  ROADMAP.md + BACKLOG.md  ──►  SYSTEMS_PLAN.md (per item)
(ideas)                (prioritized sequence)          (behavioral spec)
```

The promethean produces ideas with impact/effort assessments. Consume those assessments, apply structured prioritization, map dependencies, and produce a sequenced roadmap. Individual roadmap items then flow into SDD for behavioral specification when they reach the "Now" horizon.

## Core Workflow

### 1. Gather Input

Collect candidate items from available sources:

- **IDEA_LEDGER**: Read the latest `.ai-state/IDEA_LEDGER_*.md`. Extract pending ideas with their impact/effort ratings
- **IDEA_PROPOSAL**: Check `.ai-work/<task-slug>/IDEA_PROPOSAL.md` for newly validated ideas not yet in the ledger
- **User input**: Accept ad-hoc items the user wants on the roadmap
- **Sentinel findings**: Review `.ai-state/SENTINEL_REPORT_*.md` for ecosystem health issues that warrant roadmap slots

### 2. Select Prioritization Framework

Choose a framework based on context. Use this decision table:

| Context | Recommended Framework | Why |
|---------|----------------------|-----|
| Mature product with usage data | **RICE** | Quantitative; leverages real reach/impact numbers |
| Fixed scope with clear constraints | **MoSCoW** | Binary classification; forces hard trade-offs |
| Flow-based work with cost-of-delay pressure | **WSJF** | Optimizes economic throughput; penalizes delay |
| User-facing features needing satisfaction analysis | **Kano** | Distinguishes basic needs from delighters |
| Early-stage or rapid triage | **ICE** | Fast; minimal data required |
| Small backlog (< 10 items) | **Simple rank** | Direct comparison; frameworks add overhead |

When uncertain, default to **ICE** for speed or **RICE** for rigor. For this ecosystem's typical workload (skills, agents, rules, commands), **ICE** or **simple rank** usually suffice.

--> See [references/prioritization-frameworks.md](references/prioritization-frameworks.md) for detailed mechanics, scoring scales, and worked examples.

### 3. Score and Rank

Apply the selected framework to each candidate item:

1. Score each item using the framework's dimensions
2. Calculate the composite score
3. Rank items by score (highest first)
4. Review the ranking for obvious misalignments -- scores are inputs to judgment, not replacements for it

**Scoring with IDEA_LEDGER data**: The promethean's impact/effort assessments map directly to framework inputs. Impact maps to RICE Impact or ICE Impact. Effort maps to RICE Effort or WSJF Job Size. Confidence requires a separate assessment.

### 4. Map Dependencies

Before sequencing, identify dependencies between items:

1. For each item, ask: "What must exist before this can be built?"
2. Mark blocking dependencies (hard) vs. enhancement dependencies (soft)
3. Identify the critical path -- the longest chain of hard dependencies
4. Flag items with no dependencies as parallelizable

--> See [references/dependency-mapping.md](references/dependency-mapping.md) for dependency notation, graph construction, and critical path identification.

### 5. Sequence into Roadmap

Combine priority scores with dependency constraints to produce a sequenced roadmap:

1. **Select a roadmap format** based on planning context (see decision table below)
2. **Place items** respecting dependency order -- no item appears before its dependencies
3. **Balance capacity** -- each time horizon should contain a feasible amount of work
4. **Mark decision points** -- where the roadmap depends on spike outcomes or external factors

| Planning Context | Recommended Format | Why |
|-----------------|-------------------|-----|
| Uncertain timelines, evolving scope | **Now-Next-Later** | No dates; communicates intent without false precision |
| Committed delivery dates, external stakeholders | **Timeline** | Date-anchored; suitable for coordination |
| Strategic alignment needed | **Theme-based** | Groups work by strategic objective |
| OKR/goal-driven organization | **Outcome-based** | Maps features to measurable outcomes |

For this ecosystem, **Now-Next-Later** is the default format -- timelines are rarely fixed, and scope evolves continuously.

--> See [references/roadmap-formats.md](references/roadmap-formats.md) for templates and examples of each format.

### 6. Produce Artifacts

Write the roadmap and backlog to `.ai-work/<task-slug>/`:

**ROADMAP.md** -- the sequenced plan:

```markdown
# Roadmap: [Project or Area Name]

**Created**: [ISO 8601 timestamp]
**Framework**: [prioritization framework used]
**Format**: [now-next-later | timeline | theme | outcome]
**Source**: IDEA_LEDGER_[timestamp].md

## Now (Active / In Progress)

### [Item title]
- **Priority score**: [score]
- **Dependencies**: [none | list of blocking items]
- **Effort**: [small | medium | large]
- **Next step**: [researcher | systems-architect | implementer]

## Next (Validated / Ready to Start)

### [Item title]
- **Priority score**: [score]
- **Dependencies**: [list]
- **Effort**: [estimate]
- **Blocked by**: [items that must complete first]

## Later (Candidates / Needs Discovery)

### [Item title]
- **Priority score**: [score]
- **Open questions**: [what needs resolution before this moves to Next]

## Dependency Graph

[Markdown representation of item dependencies]

## Decision Log

- [Date]: [What was decided and why]
```

**BACKLOG.md** -- the flat prioritized list (optional, for when a detailed backlog is needed):

```markdown
# Backlog: [Project or Area Name]

**Created**: [ISO 8601 timestamp]
**Framework**: [framework used]
**Items**: [count]

| Rank | Item | Score | Effort | Dependencies | Status |
|------|------|-------|--------|--------------|--------|
| 1 | [title] | [score] | [S/M/L] | [none/list] | Now |
| 2 | [title] | [score] | [S/M/L] | [list] | Next |
| ... | ... | ... | ... | ... | ... |
```

### 7. Connect to Downstream Pipeline

When a "Now" item is ready for implementation:

1. **If scope is clear**: hand off to the systems-architect for behavioral specification via SDD
2. **If unknowns exist**: hand off to the researcher first, then systems-architect
3. **Update the roadmap**: mark the item as "In Progress" and note which pipeline agent owns it
4. **After completion**: move the item to a "Done" section or remove it; update the idea ledger

## Backlog Refinement

Roadmaps are living documents. Refine periodically:

- **Review cadence**: revisit the roadmap when new ideas arrive (promethean run), when items complete, or when priorities shift
- **Re-score**: apply the prioritization framework to new items and re-rank the full list
- **Promote/demote**: move items between Now/Next/Later based on updated scores and dependencies
- **Prune**: remove items that are no longer relevant; note them in the decision log with rationale
- **Capacity check**: ensure "Now" contains a feasible workload -- if overloaded, demote lowest-priority items to "Next"

## Integration with Existing Pipeline

### Promethean (upstream)

The promethean's `IDEA_LEDGER_*.md` is the primary input. Each pending idea has:

- **Title and description**: what the idea is
- **Impact/Effort**: from Phase 4 assessment (maps to framework scoring dimensions)
- **Dependencies**: from Phase 4 analysis
- **Category**: skill / command / agent / rule / other

The roadmap planning skill does NOT replace the promethean's ideation. It takes the promethean's output and applies structured prioritization, dependency analysis, and sequencing that the promethean does not perform.

### Spec-Driven Development (downstream)

When a roadmap item reaches "Now" and is ready for implementation:

1. The item becomes input to the systems-architect, which produces a `SYSTEMS_PLAN.md` with acceptance criteria
2. The item's title and description seed the plan's Goal section
3. Acceptance criteria defined during roadmap refinement inform REQ IDs in the behavioral spec
4. The dependency graph informs implementation ordering

### Software Planning (downstream)

After SDD produces a behavioral spec, the software-planning skill decomposes it into implementation steps. The roadmap's effort estimates and dependency information flow into the planner's step decomposition.

### Sentinel (input)

Sentinel reports provide ecosystem health context. Critical or important findings may warrant roadmap items for remediation. Include these as candidates during the Gather Input phase, but classify them separately -- maintenance items compete on priority alongside feature work.

## Effort Estimation

Use relative sizing, not absolute time:

| Size | Signal | Typical Scope |
|------|--------|---------------|
| **Small** | Single skill/agent/rule, clear scope, no dependencies | Hours of work |
| **Medium** | 2-3 artifacts, some architectural decisions, 1-2 dependencies | Days of work |
| **Large** | 4+ artifacts, cross-cutting concerns, multiple dependencies | Weeks of work |

Resist the urge to estimate in hours or days. Relative sizing communicates uncertainty honestly and avoids false precision. If pressed for dates, convert using historical throughput (items completed per time period), not bottom-up hour estimates.

## Anti-Patterns

- **Roadmap as promise**: treat the roadmap as a plan, not a commitment. "Later" items may never happen
- **Score worship**: prioritization scores inform decisions; they do not make them. Override scores when judgment warrants it
- **Dependency denial**: skipping dependency analysis leads to blocked work mid-implementation
- **Stale roadmap**: a roadmap last updated months ago is worse than no roadmap -- it misleads
- **Kitchen sink**: every idea does not belong on the roadmap. Prune aggressively
- **Framework mismatch**: using WSJF for a 5-item personal backlog adds ceremony without value

## Quick Reference

**Typical workflow**:
1. Read latest `IDEA_LEDGER_*.md` and `SENTINEL_REPORT_*.md`
2. Select prioritization framework (ICE for speed, RICE for rigor)
3. Score and rank candidates
4. Map dependencies between items
5. Sequence into Now / Next / Later roadmap
6. Write `ROADMAP.md` to `.ai-work/<task-slug>/`
7. Hand off "Now" items to systems-architect or researcher

**Key artifacts**:

| Artifact | Location | Lifecycle |
|----------|----------|-----------|
| ROADMAP.md | `.ai-work/<task-slug>/` | Session-persistent; updated as items move |
| BACKLOG.md | `.ai-work/<task-slug>/` | Optional; flat prioritized list |
| IDEA_LEDGER_*.md | `.ai-state/` | Permanent; promethean-maintained |
| IDEA_PROPOSAL.md | `.ai-work/<task-slug>/` | Ephemeral; consumed during Gather Input |

**Related skills**:

- [software-planning](../software-planning/SKILL.md) -- three-document planning model for implementation
- [spec-driven-development](../spec-driven-development/SKILL.md) -- behavioral specifications with REQ traceability
