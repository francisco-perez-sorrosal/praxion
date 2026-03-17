# roadmap-planning

Roadmap planning, feature prioritization, and backlog management for technical projects. Transforms promethean's unstructured ideas into prioritized, dependency-aware, sequenced roadmaps that feed into spec-driven-development.

## When to Use

- Prioritizing features or ideas from an IDEA_LEDGER into a sequenced plan
- Building a Now-Next-Later (or other format) roadmap from a backlog of candidates
- Mapping dependencies between features to identify critical paths and parallel work
- Selecting a prioritization framework (RICE, MoSCoW, WSJF, Kano, ICE) for the current context
- Deciding what to build next based on structured scoring rather than gut feel
- Refining an existing roadmap after new ideas arrive or priorities shift

## Activation

Load explicitly with `roadmap-planning` or reference prioritization, roadmap, backlog management, dependency mapping, or feature sequencing. Composes with `spec-driven-development` downstream (roadmap items become behavioral specs) and consumes `promethean` output upstream.

## Skill Contents

| File | Purpose |
|------|---------|
| `SKILL.md` | Core skill: pipeline integration, prioritization framework selector, dependency mapping workflow, roadmap production, backlog refinement, artifact templates |
| `README.md` | This file -- overview and usage guide |
| `references/prioritization-frameworks.md` | RICE, MoSCoW, WSJF, Kano, ICE detailed mechanics with worked examples and selection matrix |
| `references/dependency-mapping.md` | Dependency types, graph construction, critical path identification, sequencing strategies, parallelism assessment |
| `references/roadmap-formats.md` | Now-Next-Later, timeline-based, theme-based, outcome-based templates with format selection criteria |

## Quick Start

1. **Gather input**: read the latest `IDEA_LEDGER_*.md` from `.ai-state/` and any pending `IDEA_PROPOSAL.md`
2. **Select framework**: use the decision table in SKILL.md (ICE for speed, RICE for rigor)
3. **Score and rank**: apply the framework to each candidate item
4. **Map dependencies**: identify blocking and enhancing relationships between items
5. **Sequence**: produce a Now-Next-Later roadmap (or other format) respecting dependency constraints
6. **Write artifacts**: output `ROADMAP.md` (and optionally `BACKLOG.md`) to `.ai-work/`
7. **Hand off**: "Now" items flow to the systems-architect or researcher for specification

## Related Skills

- [`software-planning`](../software-planning/) -- three-document planning model for implementation step decomposition (downstream)
- [`spec-driven-development`](../spec-driven-development/) -- behavioral specifications with REQ traceability (downstream)
