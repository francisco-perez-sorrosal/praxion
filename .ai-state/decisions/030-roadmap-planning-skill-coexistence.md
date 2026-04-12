---
id: dec-030
title: Existing `roadmap-planning` skill coexists with new `roadmap-synthesis` skill
status: accepted
category: architectural
date: 2026-04-12
summary: 'Preserve `roadmap-planning` scope (prioritization + sequencing); introduce `roadmap-synthesis` for audit-to-candidate synthesis; cartographer composes both via `skills:` frontmatter'
tags: [architecture, roadmap, skills, coexistence, boundaries]
made_by: agent
agent_type: systems-architect
pipeline_tier: standard
affected_files:
  - skills/roadmap-planning/SKILL.md
  - skills/roadmap-synthesis/
---

## Context

The existing `skills/roadmap-planning/` skill is 259 lines of `SKILL.md` plus ~603 lines across three references (`prioritization-frameworks.md`, `dependency-mapping.md`, `roadmap-formats.md`). Its scope is narrowly defined (`SKILL.md:17`): *"Transform unstructured ideas into prioritized, sequenced plans"* — input is an existing `IDEA_LEDGER`, output is a ranked and sequenced roadmap. The skill is prioritization-first: RICE/MoSCoW/WSJF/Kano/ICE frameworks, dependency mapping, Now-Next-Later formats, dependency critical path.

SPIRIT requires something the existing skill does not provide: an audit-synthesis phase that *discovers* strengths, weaknesses, improvement opportunities, deprecations, and redefinitions *before* any ranking happens. The six-dimension lens (Automation, Coordinator awareness, Quality, Evolution, Pragmatism, Curiosity) is an evaluation framework absent from the current skill's references.

Three composition models:

- **Absorb.** Grow `roadmap-planning` to also include audit-synthesis, six-dimension lens, and template machinery.
- **Deprecate.** Replace `roadmap-planning` with a new comprehensive skill.
- **Coexist.** Introduce a second skill (`roadmap-synthesis`) scoped to audit-to-candidate synthesis; preserve `roadmap-planning` for prioritization mechanics.

## Decision

Coexist. Preserve `skills/roadmap-planning/` unchanged in scope. Introduce `skills/roadmap-synthesis/` scoped to:

- Audit methodology (6-lens parallel fan-out)
- Six-dimension SPIRIT evaluation lens (with paradigm-specific sub-questions)
- Paradigm detection (deterministic vs agentic)
- Grounding protocol (every claim cites evidence)
- Multi-angle reframing procedure
- `ROADMAP.md` template asset matching the 9-section exemplar shape

The `roadmap-cartographer` agent composes both skills via `skills: [roadmap-synthesis, roadmap-planning]` frontmatter. Phases 1–5 and 7 activate `roadmap-synthesis`; Phase 6 (Prioritize & Sequence) delegates to `roadmap-planning`'s framework selector and Now-Next-Later formatting.

Trigger-phrase disjointness is enforced at the `description:` level:

- `roadmap-synthesis` vocabulary: "ultra-in-depth project analysis", "spring cleaning roadmap", "project state of the union", "six-dimension audit", "evaluate project across multiple lenses", "strengths, weaknesses, deprecations roadmap"
- `roadmap-planning` vocabulary: "prioritize", "backlog", "RICE", "MoSCoW", "WSJF", "Kano", "sequencing", "Now-Next-Later", "roadmap format"

A minor clarifying edit to `roadmap-planning`'s `description` may be needed to sharpen the disjoint — the implementer decides based on the context-engineer Phase 2 review.

## Considered Options

### Option 1 — Absorb into `roadmap-planning`

Grow the existing skill to include audit-synthesis + six-dimension lens + new template.
**Pros:** single skill covers the full workflow; single entry point for users; no two-skill coordination.
**Cons:** mixes two distinct responsibilities (prioritization mechanics + audit synthesis); SKILL.md would grow past the 500-line target; breaking change for anything that already depends on the skill's current scope; destroys a clean boundary.

### Option 2 — Deprecate `roadmap-planning`

Replace with a new comprehensive skill.
**Pros:** single skill; fully redesigned for the SPIRIT; no trigger-phrase collision.
**Cons:** destroys working content (867 lines across SKILL.md + references); regression risk for any downstream consumer; unnecessary rewrite — the prioritization content is directly reusable.

### Option 3 — Coexist (chosen)

Keep both skills; cartographer composes them.
**Pros:** clear bounded contexts; mechanical reuse of 867 lines of proven content; separation of concerns (synthesis vs mechanics); upgrade path (either skill can evolve independently).
**Cons:** two skills named `roadmap-*` raises trigger-phrase collision risk; composition discipline required from cartographer; minor `description` edit may be needed on the existing skill.

## Consequences

**Positive:**

- `roadmap-planning`'s 867 lines of prioritization machinery preserved and reused.
- `roadmap-synthesis` can iterate independently on audit methodology without destabilizing prioritization.
- Trigger-phrase disjointness keeps both discoverable for their respective use cases (incremental ledger-driven roadmapping vs spring-cleaning audit-driven roadmapping).
- Cartographer's `skills:` frontmatter demonstrates the canonical skill-composition pattern.

**Negative:**

- Two skills with overlapping-looking names; users might expect one to do both jobs.
- Implementer must verify trigger disjointness in practice (context-engineer Phase 2 validates via simulated phrasings).
- Any future refactor that merges the two will be an explicit supersession decision.

**Operational:**

- `skills/roadmap-synthesis/` created by implementer per plan decomposition.
- `skills/roadmap-planning/SKILL.md` unchanged unless context-engineer Phase 2 flags a description sharpening.
- Cross-reference link added: `roadmap-synthesis/SKILL.md` names `roadmap-planning` as its Phase-6 delegate; `roadmap-planning/SKILL.md` optionally names `roadmap-synthesis` as its upstream for audit-driven roadmaps.
