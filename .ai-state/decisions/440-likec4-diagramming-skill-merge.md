---
id: dec-440
draft_id: dec-draft-971ab11d
title: Merge `likec4-querying` into one `likec4-diagramming` skill that owns authoring canon, review checks, render loop and the query rubric
status: accepted
category: architectural
date: 2026-10-04
summary: "Replace skills/likec4-querying with skills/likec4-diagramming (same path scope): body keeps the query rubric and adds the authoring loop and category rule; references hold the only copy of the review-check list and thresholds (review-checks.md), the graded style canon, authoring recipes, the one canonical regeneration statement and the MCP tool catalog; the path-scoped diagram rule links the check list one hop away and three agent prompts carry an in-place one-line directive."
tags: [skills, likec4, diagrams, guidance, progressive-disclosure, review-checks, context-engineering]
made_by: agent
agent_type: systems-architect
branch: worktree-likec4-diagram-craft
pipeline_tier: full
affected_files:
  - skills/likec4-diagramming/SKILL.md
  - skills/likec4-diagramming/references/review-checks.md
  - skills/likec4-diagramming/references/style-canon.md
  - skills/likec4-diagramming/references/likec4-authoring-recipes.md
  - skills/likec4-diagramming/references/render-and-regen.md
  - skills/likec4-diagramming/references/mcp-tool-recipes.md
  - skills/likec4-querying/SKILL.md
  - rules/writing/diagram-conventions.md
  - agents/systems-architect.md
  - agents/implementer.md
  - agents/doc-engineer.md
  - scripts/skill_description_diet.yaml
  - skills/README.md
affected_reqs: [REQ-14, REQ-17]
supersedes_in_part: [dec-109]
dissent: "A separate authoring skill would keep the query-only consumers (architect-validator, MCP lookups) free of the canon's tokens; merging makes every .c4 read pay for authoring guidance it may not need."
---

## Context

The diagramming practice must be codified so that an architect in any managed project meets the same bar. The review checks must sit within one link of the diagram rule.

`likec4-querying` (dec-109) is a query-only rubric. No agent, command or rule names it. Its tool count is stale (18 vs 20). The regeneration pipeline is restated in ten or more places, each stale differently.

Budgets bind tightly:
- The skill listing has 99 tokens of headroom.
- The systems-architect prompt is capped at 449 lines.
- The rule loads on every `docs/**` read.

The architect has no `Skill` tool, so guidance must also reach it in-situ.

## Decision

Rename and merge into **`skills/likec4-diagramming/`**, with the same `paths:` scope:

- **Body (≤ 150 lines):** the authoring loop (read `_spec.c4` → edit → `regenerate_diagrams.py --check` → fix → commit), the category rule and vocabularies, the view recipe, the twelve-row query rubric, kept, and gotchas.
- **References:**
  - `review-checks.md`: the check list `DRC-01`..`DRC-12` (format per `dec-443`), the **only** home of thresholds.
  - `style-canon.md`: graded canon, palette and shape semantics, anti-patterns, no numbers.
  - `likec4-authoring-recipes.md`.
  - `render-and-regen.md`: the **one** canonical pipeline statement.
  - `mcp-tool-recipes.md`: kept and updated to the live tool list.
- **Description:** ≤ 300 characters, carrying both trigger sets (measured 9,141 listing tokens against the 9,243 ceiling).
- **Rule:** stays the entry point, gains `**/*.c4`, keeps only declarative constraints plus a link to `review-checks.md`, and stays ≤ 9,000 bytes.
- **Prompts:** `systems-architect`, `implementer` and `doc-engineer` each get a one-line directive, edited in place with net 0 lines. It says to read `_spec.c4`, use the skill, and apply `review-checks.md`.
- **Pointers:** every other site points and never restates.

## Considered Options

### Option A: Extend `likec4-querying` in place

**Pros:** no rename; non-architectural.
**Cons:** the name misdescribes an authoring skill, and the skill stays unwired.

### Option B: Merge into `likec4-diagramming` (chosen)

**Pros:**
- One concern, the LikeC4 model lifecycle; `preview-view` fuses draft, preview and query.
- Tiny rename blast radius.
- One listing entry.

**Cons:** rename churn; a stale plugin cache until refresh.

### Option C: Sibling authoring skill

**Pros:** query consumers skip the canon.
**Cons:** the same `paths:` double-activate on every `.c4` read; double listing cost for no isolation gain.

## Consequences

**Positive:**
- Thresholds have one home.
- The pipeline has one statement.
- Agents without a `Skill` tool still get the bar through `_spec.c4`, the rule and the directive.

**Negative:**
- Every `.c4` read activates a larger skill body; references stay on demand.
- Consumers of the old name must move in the same commit (the diet-registry applier exits 2 on a missing skill file).

## Disconfirmation

- **Falsifier:** sessions that only query the model (architect-validator sweeps, MCP lookups) show material skill-activation cost with no authoring follow-up. The likec4-diagramming body stays in context without being consulted for authoring in most activations.
- **Steelmanned runner-up:** option C. Query and authoring have different consumers and change for different reasons: the MCP tool surface tracks LikeC4 releases, while the style canon tracks Praxion's taste. Separating them is Balanced Coupling, and `paths:` could be narrowed, so querying loads on `docs/architecture.md` while authoring loads on `.c4`.
- **Reversal trigger:** the falsifier fires (measured with `/skill-doctor`), or the two halves start changing on different cadences. Then split authoring back out with distinct `paths:`.

## Prior Decision

**dec-109 (narrowed, not replaced).** The query rubric, its MCP-vs-direct-read decision table and the per-tool recipe catalog stand and move into the merged skill unchanged in substance. Narrowed:
- the skill's **name and scope**: `likec4-querying` → `likec4-diagramming`, query-only → query plus authoring and review;
- the skill's line-count and file-layout clause: more references.

Activation: fired — structural + multiple plausible paths; lens set = Simplicity, Testability; convergence = stable.
