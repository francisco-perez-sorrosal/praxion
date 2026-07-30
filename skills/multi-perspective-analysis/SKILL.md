---
name: multi-perspective-analysis
description: >
  Composition layer for multi-perspective deliberation primitives: calibrated
  confidence annotation, lens-independence discipline, heterogeneous model
  orchestration (Haiku-proposer / Opus-aggregator), and two-tier disconfirmation
  (Tier-A always-on for architectural ADRs; Tier-B cross-model adversarial
  challenge gated to high-stakes contested decisions). Triggers: high-stakes
  design decisions with genuine uncertainty, adversarial stress-testing of
  architectural choices, calibrating confidence on research claims, parallel
  lens fan-out that must remain independent, pre-mortem failure-imagination at
  planning→implementation boundary.
allowed-tools: [Read, Glob, Grep]
compatibility: Claude Code
metadata:
  principle: CLAUDE.md§Context Engineering
---

# Multi-Perspective Analysis

Composition layer for multi-perspective deliberation. **This skill owns the shared schemas; it does not restate lens methodology owned elsewhere.** Every section is a pointer or an activation gate — not a knowledge layer.

> **No new knowledge — point, don't restate.** If this file's body is growing beyond pointers and gate definitions, content has drifted from a reference file into the composition layer. Move it back. Sentinel T06 enforces this.

**Satellite files** (loaded on-demand):

- [references/calibrated-confidence.md](references/calibrated-confidence.md) — verbal+numeric confidence anchor table (high >80% / med 40–80% / low <40%), GRADE downgrade factors, annotation format, authoring guidance
- [references/lens-independence.md](references/lens-independence.md) — isolation/reconciliation/gate discipline for parallel lens sweeps; correlation-collapse rationale; fragment-file enforcement
- [references/heterogeneous-orchestration.md](references/heterogeneous-orchestration.md) — Haiku-proposer / Opus-aggregator recipe, prompt-caching guidance, cost-model references (MoA, PoLL, MasRouter)
- [references/disconfirmation-tiers.md](references/disconfirmation-tiers.md) — DI vs. DA distinction; Tier-A (always-on for `category: architectural`): Falsifier / Steelmanned runner-up / Reversal trigger; Tier-B: cross-model adversarial challenge, gating conditions, protocol
- [references/discipline-registry.md](references/discipline-registry.md) — the consulting-discipline roster as data: 7-field row schema (trigger predicate, runtime skill binding, challenge obligations, difficulty hint, attaching stages, lens collision), read pre-spawn by conveners and post-spawn by the consultant

## Activation Gate

This skill activates under the **honest-uncertainty gate**: the invoking agent must be able to name ≥2 plausible paths before any multi-perspective mechanism is invoked. If the invoking agent cannot name ≥2 plausible paths, proceeding would manufacture strawmen — a behavioral-contract violation (Register Objection).

```
activate_multi_perspective(task) =
    honest_uncertainty == "multiple_plausible_paths"   # always required
  AND (
        stakes ∈ {security, one-way-door, user-visible-breaking}   # OR
     OR tier ∈ {Standard, Full} AND blast_radius ≥ 5_files         # OR
     OR contested_with_evidence                                     # genuine rival supported by citations
     )
```

**HARD gate.** Mechanisms behind the gate are invoked only when the gate fires. Cheap, non-multi-agent mechanisms (Tier-A Disconfirmation block, per-claim confidence annotation, pre-mortem gate) are always-on at their respective pipeline tiers — they are not behind this gate.

## Mechanism Map

| Mechanism | Cost tier | Gate | Owning artifact |
|---|---|---|---|
| Per-claim confidence annotation | Free (inline text) | Always-on for research claims | [references/calibrated-confidence.md](references/calibrated-confidence.md) |
| Verifier confidence field | Free (inline text) | Always-on | [references/calibrated-confidence.md](references/calibrated-confidence.md) |
| Tier-A Disconfirmation (ADR body) | Free (prose section) | Always-on: `category: architectural` | [references/disconfirmation-tiers.md](references/disconfirmation-tiers.md), `rules/swe/adr-conventions.md` |
| Pre-mortem gate | Free (checkpoint) | Always-on: Standard/Full, planning→implementation | `skills/software-planning/references/coordination-details.md` |
| Lens-independence discipline | Free (procedure) | Always-on when fan-out is invoked | [references/lens-independence.md](references/lens-independence.md) |
| Parallel lens fan-out | Moderate (N agent calls) | Honest-uncertainty gate | [references/lens-independence.md](references/lens-independence.md) |
| Heterogeneous model assignment | Moderate (mixed tiers) | Honest-uncertainty gate | [references/heterogeneous-orchestration.md](references/heterogeneous-orchestration.md) |
| Tier-B cross-model challenge | High (extra frontier call) | Honest-uncertainty AND stakes ∈ {security, one-way-door, user-visible-breaking} | [references/disconfirmation-tiers.md](references/disconfirmation-tiers.md) |

## Pipeline Wiring

The mechanics of multi-perspective analysis are wired directly into the pipeline artifacts — this skill is the navigation surface, not the execution surface:

- **Calibrated confidence** → `agents/researcher.md` (per-claim annotation), `agents/verifier.md` (structured verdict `confidence` field)
- **Lens-independence discipline** → `agents/systems-architect.md` (Phase 7 DI sub-step), `skills/software-planning/references/agent-pipeline-details.md § Multi-Perspective Analysis`
- **Disconfirmation Tier-A** → `rules/swe/adr-conventions.md` (`## Disconfirmation` body section, `dissent:` frontmatter field)
- **Disconfirmation Tier-B** → `agents/systems-architect.md` (Phase 7 Tier-B note)
- **Pre-mortem gate** → `rules/swe/swe-agent-coordination-protocol.md § Conversation Checkpoints` (named variant), `skills/software-planning/references/coordination-details.md § The pre-mortem gate`
- **DI sub-step** → `agents/systems-architect.md` Phase 7 + `skills/software-planning/references/design-synthesis.md § S3`
- **Heterogeneous orchestration** → `agents/systems-architect.md` (Tier-B cross-model note); [references/heterogeneous-orchestration.md](references/heterogeneous-orchestration.md) for recipe details
- **Contradiction mapping** → `agents/roadmap-cartographer.md` (Phase 3.5 cross-lens contradiction map); the cartographer applies lens-independence discipline and per-claim confidence annotation when surfacing contested prioritization evidence

## Related Skills

- [`skills/software-planning`](../software-planning/SKILL.md) — three-document model, step decomposition; this skill's mechanisms are activation-gated extensions of the software-planning pipeline.
- [`skills/software-planning/references/design-synthesis.md`](../software-planning/references/design-synthesis.md) — the lens catalog and convergence signals for pre-implementation synthesis; multi-perspective-analysis is the deliberation layer that complements synthesis.
- [`skills/spec-driven-development`](../spec-driven-development/SKILL.md) — REQ-ID stability as a convergence signal (cross-referenced in design-synthesis.md).
