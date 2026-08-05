---
id: dec-077
title: Frontmatter `model:` is a capability floor; rule table is authoritative
status: accepted
category: architectural
date: 2026-04-25
summary: 'The 3 existing `model: opus` pins stay as capability floors (minimum tier); the rule table may route up via layer-2, never below'
tags: [model-routing, frontmatter, floor-semantic, agent-crafting, convention]
made_by: agent
agent_type: systems-architect
pipeline_tier: standard
affected_files:
  - agents/systems-architect.md
  - agents/promethean.md
  - agents/roadmap-cartographer.md
  - skills/agent-crafting/references/configuration.md
  - rules/swe/agent-model-routing.md
affected_reqs:
  - AC3
---

## Context

The hybrid routing mechanism (dec-078) introduces a central rule table as the tier authority. This creates tension with three existing `model: opus` frontmatter pins on `systems-architect`, `promethean`, and `roadmap-cartographer` — either the pins or the rule is the source of truth, but not both without creating drift. Claude Code's layer-2 per-spawn override (from the main orchestrator) beats layer-3 frontmatter mechanically, so the question is what *semantic* to attach to the pin.

The context-engineer shadow review (`CONTEXT_REVIEW.md §F4`) proposed a hybrid resolution: treat frontmatter as a **capability floor** — a declaration that "this agent must not route below tier X" — while the rule table remains authoritative and may route up via layer-2. This preserves local author intent (the pins survive copy-paste between projects) without creating a two-sources-of-truth drift.

## Decision

Adopt the **capability floor** semantic:

- Frontmatter `model: <alias>` on a Praxion agent declares the **minimum** tier that agent must run on.
- The central rule table is authoritative for tier assignments and may route an agent to its floor or higher via layer-2.
- The main orchestrator, when spawning an agent with a floor, **omits** the layer-2 override and lets the floor apply (the floor already matches the rule table's H tier for the 3 pinned agents — no conflict possible in v1).
- The other 10 agents omit `model:` (= `inherit`); the rule table alone governs them via layer-2.

Document the semantic in:

- The header of `rules/swe/agent-model-routing.md` (one sentence).
- `skills/agent-crafting/references/configuration.md` under the `model:` field entry (one-line note).

## Considered Options

### Option 1 — Frontmatter = policy (layer-3 authoritative)

- Pros: Declarative, local, greppable.
- Cons: Drifts against any central rule table; two sources of truth; cannot express task-sensitive routing.

### Option 2 — Remove frontmatter pins entirely

- Pros: Single source of truth in the rule table; audit-friendly.
- Cons: Loses local author intent; copy-pasted agents degrade to session default; no safety net if the orchestrator forgets to pass layer-2.

### Option 3 — Hybrid "capability floor" (selected)

- Pros: Rule table is the single authority for tiers; pins preserve local intent; copy-paste resilience — a relocated agent carries its floor and degrades gracefully; semantic aligns with Claude Code's layer-2-beats-layer-3 precedence.
- Cons: Authors must understand "floor" vs "ceiling" — a one-line documentation burden in `agent-crafting`.

## Consequences

**Positive:**

- Zero frontmatter changes in v1 (the 3 pins stay; the 10 non-pinned stay). Small blast radius.
- Copy-pasted agents carry a sensible minimum.
- Audit story: one canonical rule, with floors as local safeguards.

**Negative:**

- Authors may mis-read "floor" as "ceiling." Mitigated by the rule header + `agent-crafting` note.
- Drift between a floor and the rule table's tier remains possible if they are updated at different times (e.g., floor stays at `opus` while rule drops the agent to M). In v1 this cannot happen (all 3 pinned are H in the rule), but a future change could create it.

**Risks accepted:**

- Future drift. Boundary: any tier change for a pinned agent in the rule table must simultaneously update (or remove) the frontmatter floor; enforce by convention + PR review.

Credit: context-engineer shadow review (CONTEXT_REVIEW.md §F4) proposed this resolution; the architect accepts it as the cleanest answer to the local-vs-central tension.
