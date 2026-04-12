---
id: dec-033
title: Lens content placement — skill reference file + template asset + SKILL.md summary
status: accepted
category: architectural
date: 2026-04-12
summary: 'Lens content (SPIRIT-exemplar sub-questions and lens-framework methodology) lives in `skills/roadmap-synthesis/references/lens-framework.md` (tier-4 procedural, on-demand) + `ROADMAP_TEMPLATE.md` asset (tier-5 structural echo) + SKILL.md summary (tier-3); zero always-loaded cost'
tags: [architecture, roadmap, skills, progressive-disclosure, token-budget]
made_by: agent
agent_type: systems-architect
pipeline_tier: standard
affected_files:
  - skills/roadmap-synthesis/references/lens-framework.md
  - skills/roadmap-synthesis/assets/ROADMAP_TEMPLATE.md
  - skills/roadmap-synthesis/SKILL.md
---

> **See also `dec-036`**: the *content* of the lens reference file was generalized from a hardcoded six-dimension SPIRIT set to a project-derived lens framework; SPIRIT is preserved as a first-class exemplar. The *placement* decision recorded here (reference file + template asset + SKILL.md summary) stands unchanged; only the file was renamed from `six-dimension-lens.md` to `lens-framework.md`.

## Context

SPIRIT enumerates six evaluation dimensions: Automation, Coordinator awareness, Quality (non-negotiable), Evolution, Pragmatism, Curiosity & Imagination. The roadmap-creation capability must apply these lenses during audit-to-synthesis; every generated roadmap must visibly address all six (AC-2 in `SYSTEMS_PLAN.md`).

Four candidate placement tiers for the lens content:

- **Tier 1 — Rule** (always-loaded, declarative constraint).
- **Tier 3 — SKILL.md body** (loaded on skill activation).
- **Tier 4 — Skill reference file** (loaded on-demand via `Read`).
- **Tier 5 — Template asset** (loaded on-demand via `Read`).
- **Agent prompt** (loaded inside the cartographer's spawned context only).

The dimensions are *procedural evaluation lenses* (each is a set of questions applied to the project, with paradigm-specific sub-questions for deterministic vs agentic projects) — not *declarative constraints* that must always be in context. Token budget is at 106% of ceiling (dec-034 adds offset-balanced content); any always-loaded addition is a net regression.

## Decision

Place the six-dimension lens at **two tiers simultaneously**:

1. **Primary: `skills/roadmap-synthesis/references/lens-framework.md`** (~200 lines, tier 4 on-demand). Full elaboration — for each dimension: definition, sub-questions for deterministic projects, sub-questions for agentic projects, evidence types accepted, failure signals, example findings. References `README.md#guiding-principles` and `ROADMAP.md#guiding-principles-for-execution` for the four Praxion principles rather than re-authoring.
2. **Structural echo: `skills/roadmap-synthesis/assets/ROADMAP_TEMPLATE.md`** (tier 5 on-demand). Template sections organized such that the six dimensions are visible through the roadmap's structure itself (What's Working, Weaknesses, Improvement Phases addressing each dimension, Quality Metrics, Guiding Principles).
3. **Summary table in `SKILL.md` body** (~15 lines, tier 3). Names each dimension with a one-line description and links to the full reference. Provides activation-time context without replicating the reference.

Zero content in rules or in the agent prompt body (beyond the one-line pointer to the skill).

## Considered Options

### Option A — Rule (always-loaded)

Put the six dimensions in a new or existing rule.
**Pros:** guaranteed load on every session; declarative style matches the SPIRIT's principle-like framing.
**Cons:** SPIRIT dimensions are *procedural evaluation lenses*, not declarative constraints — placing them in a rule miscasts the content. Also: 106%-of-ceiling budget forbids any net-positive always-loaded addition; offset would need to exceed the dec-034 plan. Rejected.

### Option B — Agent prompt body

Embed the full dimension content in the cartographer's prompt.
**Pros:** guaranteed inside the cartographer's context.
**Cons:** violates the 300-line agent-prompt ceiling (promethean is already at ~310); plugin self-containment failure for any downstream agent that wants to reuse the lens (agent-local content doesn't ship to downstream projects); duplicates effort if any other agent needs the same lens. Rejected.

### Option C — SKILL.md body only (tier 3)

Full dimension content inside `SKILL.md`.
**Pros:** single-file simplicity; loads on skill activation.
**Cons:** pushes SKILL.md past the ≤260-line target — SKILL.md must stay focused on workflow and pointers; detailed procedural content belongs in references.

### Option D — Reference file + asset + SKILL.md summary (chosen)

Tier 4 + tier 5 + tier 3 summary table.
**Pros:** zero always-loaded cost; dimensions fully elaborated with paradigm-specific sub-questions in the reference; template structurally echoes the dimensions; SKILL.md summary gives activation-time context without duplicating; evolution-friendly (update the reference, not always-loaded content); plugin-self-contained (skill content ships to downstream projects).
**Cons:** coordinator cannot see dimensions until the skill activates — mitigated by naming the dimensions in the skill `description` (reliably fires on roadmap intent).

## Consequences

**Positive:**

- Zero always-loaded cost; respects the 106%-of-ceiling budget constraint.
- Dimensions are fully elaborated with paradigm-specific sub-questions in the reference — serves both deterministic and agentic project evaluations.
- Evolution-friendly: when the 2026 agentic-coding landscape shifts, update the reference file, not always-loaded content.
- No duplication with `claude/config/CLAUDE.md` Principles, Praxion `CLAUDE.md` Guiding Principles, or `README.md`/`ROADMAP.md` principle anchors — the reference file points at them, not re-authors them.
- Template asset gives the cartographer a concrete structural scaffold; the six dimensions are visible through the roadmap's section headings.

**Negative:**

- Coordinator does not see the dimensions until the skill activates. The skill `description` must reliably fire on roadmap intent (validated in context-engineer Phase 2).
- Three places hold dimension content (reference, template, SKILL.md summary). Drift risk mitigated by: SKILL.md summary is a one-liner linking to the reference; template echoes structure only, not definitions.

**Operational:**

- `skills/roadmap-synthesis/references/lens-framework.md` created by implementer per plan.
- `skills/roadmap-synthesis/assets/ROADMAP_TEMPLATE.md` includes section comments citing the dimension each section addresses.
- `skills/roadmap-synthesis/SKILL.md` summary table (~15 lines) links to both.
- The four Praxion principles are *referenced* (cross-link), never duplicated.
