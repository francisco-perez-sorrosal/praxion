---
id: dec-draft-dd0da49a
title: multi-perspective-analysis skill — GO as a composition layer (Step-1 kill-switch verdict)
status: proposed
category: architectural
date: 2026-06-18
summary: Create skills/multi-perspective-analysis as a thin composition layer (pointers + shared schema definitions, mirroring design-synthesis.md), HARD-gated to high-stakes stages; not a knowledge layer, not embedded-per-agent.
tags: [skill, multi-perspective, composition-layer, heterogeneous-models, storm-integration, gating]
made_by: agent
agent_type: systems-architect
branch: worktree-storm-integration
pipeline_tier: full
affected_files:
  - skills/multi-perspective-analysis/SKILL.md
  - skills/multi-perspective-analysis/references/calibrated-confidence.md
  - skills/multi-perspective-analysis/references/lens-independence.md
  - skills/multi-perspective-analysis/references/heterogeneous-orchestration.md
  - skills/multi-perspective-analysis/references/disconfirmation-tiers.md
affected_reqs: [REQ-05, REQ-06, REQ-08, REQ-09]
dissent: "A reader applying maximal Simplicity-First may argue four agents sharing a structure is too thin to justify a whole skill, and the shared schemas could live in software-planning/references/ without a new skill. Held minority view: revisit if the skill's SKILL.md body never grows past the schema pointers it hosts at v1."
---

## Context

Item 6 carried an explicit STEP-1 / KILL-SWITCH instruction: first validate whether the candidate consumers (researcher, roadmap-cartographer, systems-architect, promethean) genuinely share enough structure to justify one skill — and if not, drop or reshape it and say so here, rather than force a hollow abstraction.

## Decision

GO — but as a **composition layer**, mirroring `skills/software-planning/references/design-synthesis.md`, not a knowledge layer and not embedded-per-agent.

Step-1 verdict: the candidate consumers DO share one load-bearing structure — *independent collection → reconciliation at a strong aggregator, gated by honest-uncertainty + cost*. The shared, drift-prone definitions (calibrated-confidence schema, lens-independence discipline, heterogeneous Haiku-proposer/Opus-aggregator orchestration + prompt caching, Tier-A/Tier-B disconfirmation) earn a single owning artifact. The per-consumer mechanics (cartographer Phase 3.5, researcher divergence pass, architect DI sub-step) stay in the consuming agents and CITE the skill.

## Considered Options

### Option 1 — No skill; embed mechanics directly in each consuming agent
- Pro: no new skill; maximally surgical.
- Con: the shared schemas (confidence, lens-independence, orchestration recipe, disconfirmation tiers) would be duplicated across ≥3 agents and drift — a Pragmatism + Balanced-Coupling violation (same knowledge in many places).

### Option 2 — Skill as a knowledge layer (lens tutorials, persona libraries, debate transcripts)
- Pro: rich, self-contained.
- Con: the hollow-abstraction trap the task warned against; trips sentinel T06 redundancy by restating methodology owned elsewhere; persona libraries are specifically counter-indicated (expert personas don't improve factual accuracy, arXiv:2512.05858).

### Option 3 — Thin composition layer mirroring design-synthesis.md (CHOSEN)
- Pro: single source of truth for shared schemas; no drift; HARD-gated cost; proven shape (design-synthesis.md precedent); points-not-restates keeps it a composition layer.
- Con: one more skill in the catalog (~1 line startup cost); composition layers can silently grow into knowledge layers.

## Consequences

- Positive: consuming agents stay lean and cite one schema; the skill is the home for the gating + heterogeneous-orchestration recipe; auto-registers via plugin glob.
- Negative: requires discipline to stay a composition layer — mitigated by copying design-synthesis.md's "No new knowledge — point, don't restate" guard clause verbatim.

## Disconfirmation (Tier A)

- **Falsifier**: Wrong if, at v1, the skill body holds nothing but pointers that could equally live as a single `software-planning/references/` file — i.e., the "skill" boundary buys no activation/gating benefit and only adds catalog surface.
- **Steelmanned runner-up (Option 1, embed-per-agent)**: With only ~3 active consumers and the schemas being short, a single shared reference under `software-planning/references/` (already a hosting precedent) plus per-agent citation avoids a new top-level skill entirely. The strongest case for Option 1 is that a skill's progressive-disclosure activation adds value only when a model needs to *discover* the capability on its own — and these consumers are hard-wired to cite it, so discovery is moot.
- **Reversal trigger**: Collapse the skill into `software-planning/references/` if after one or two pipelines the SKILL.md body has not grown beyond schema pointers AND no agent ever activates it by description (only by hard-coded citation).

**Activation:** fired — signals: novelty (new skill) + structural (5 new files); lens set = Simplicity + Balanced-Coupling + Testability; convergence = stable (the design-synthesis.md precedent settles the shape).
