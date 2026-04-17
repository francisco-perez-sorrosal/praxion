# Pre-Implementation Design Synthesis

Progressive-disclosure reference for the activation-gated design-synthesis capability. Back to [SKILL.md](../SKILL.md).

## Purpose & Scope

Pre-implementation synthesis capability for S1 (ideation), S2 (research), S3 (architecture — Phase 7 primary and Phase 9 extended review), and S5 (refactoring with 2+ valid decompositions). This file is a **composition layer, not a knowledge layer**: every lens it invokes points at an existing Praxion artifact, and every convergence signal it names is mechanical. No new lenses are defined here, no confidence scalars are introduced, and no subagents are spawned. The reference loads on-demand when an invoking agent follows a pointer — it adds zero tokens to the always-loaded surface. Back-link: [../SKILL.md](../SKILL.md).

**What this file is not.** It is not a replacement for the owning lens artifacts, not a new agent phase, not a ceremony to run on every task, and not a place to record lens findings (those belong in `SYSTEMS_PLAN.md`, the ADR body, or the comparative matrix in `RESEARCH_FINDINGS.md`). It is a short, activation-gated orchestration surface that directs the invoking agent to *which* existing lenses to apply at *which* stage, and *how* to recognize convergence.

## When to Activate

Activation is governed by a **5-dimension formula**. The formula is the same at S1/S2/S3/S5; only the stage prerequisite differs per invocation (see [Stage-Specific Invocation](#stage-specific-invocation)).

```
activate_synthesis(task) =
    tier ∈ {Standard, Full}                                   # prerequisite gate
  AND (
        blast_radius ≥ 5_files  OR  spans ≥ 2_subsystems        # structural
     OR reversibility == "one-way-door"                          # risk
     OR novelty == "no-precedent"                                # exploration
     OR stakes ∈ {security, user-visible-breaking}               # criticality
     )
  AND uncertainty == "multiple_plausible_paths"                 # honest-uncertainty gate
```

The trailing `AND uncertainty == "multiple_plausible_paths"` is an **honest-uncertainty gate**: if the invoking agent cannot name ≥2 plausible paths, synthesis will generate strawmen to check a box. The gate forces disclosure of whether there is a real choice, aligning with the Register Objection behavior in `rules/swe/agent-behavioral-contract.md`.

### Fires vs. does not fire — examples

- **Fires**: Full-tier pipeline redesigning auth middleware — touches 7 files across auth and session subsystems, one-way-door (migration), security stakes, architect can name ≥2 plausible token-storage paths. All clauses satisfied.
- **Fires**: Standard-tier task introducing a new cache layer — 6 files, spans API and storage, novelty (no precedent in repo), architect weighs write-through vs. write-back. Structural + novelty + real choice.
- **Does not fire**: Standard-tier bug fix in a single module — blast_radius = 2, reversibility = reversible, no novelty, no elevated stakes. Structural clause fails.
- **Does not fire**: Full-tier refactor where the architect can only name one credible layout. Honest-uncertainty gate fails — proceeding would manufacture strawmen, violating the no-strawmen contract.
- **Does not fire**: Lightweight or Direct tier (prerequisite gate closed) regardless of other signals — those tiers do not carry the ADR/SYSTEMS_PLAN surface the convergence check depends on.

### Logging obligation

When activation fires at S1/S2/S3/S5, the invoking agent appends one row to `.ai-state/calibration_log.md` with the following format:

```
[timestamp, task-slug, stage, triggered-signals, lens-set-used, convergence-outcome]
```

Reuse the existing calibration log — do not create a new artifact. `triggered-signals` enumerates which clauses of the 5-dimension formula fired (e.g., `structural+stakes`). `convergence-outcome` is one of `stable`, `churned`, `re-swept`, or `user-override`.

### ADR obligation

When the architect writes a Phase 7 ADR for a Standard- or Full-tier trade-off, the ADR body **must** record an `Activation:` line. This is a single line that distinguishes "considered and declined" from "not considered":

- If activation fired: `Activation: fired — <triggered-signals>; lens set = <list>; convergence = <outcome>`.
- If activation did not fire: `Activation: no — <reason>` (e.g., `no — reversibility: trivially revertible; uncertainty: single plausible path`).

The line is load-bearing for the verifier's synthesis audit and for future readers reconstructing why a given decision did or did not go through synthesis.

## Lens Catalog

Each lens points at the Praxion artifact that owns it. **The reference never restates lens methodology** — consumers follow the pointer to the owning artifact and apply it there. This enforces the composition-not-knowledge contract and keeps sentinel T06 (redundancy) clean.

| Lens | Owning artifact |
|---|---|
| Security | [`skills/context-security-review/SKILL.md`](../../context-security-review/SKILL.md) |
| Performance | [`skills/performance-architecture/SKILL.md`](../../performance-architecture/SKILL.md) |
| Simplicity | [`rules/swe/agent-behavioral-contract.md`](../../../rules/swe/agent-behavioral-contract.md) (Simplicity First) + [`references/behavioral-contract.md`](behavioral-contract.md) |
| Testability | [`agents/test-engineer.md`](../../../agents/test-engineer.md) (Testability Feedback) |
| Blast-radius | [`skills/spec-driven-development/references/calibration-procedure.md`](../../spec-driven-development/references/calibration-procedure.md) |

**How to run a lens sweep.** For each option under consideration, open the owning artifact, apply its framework, and record the outcome as a one-line note on the option (or `n/a` when the lens does not discriminate). Do not paraphrase the lens body back into `SYSTEMS_PLAN.md` or the ADR — cite the artifact and keep the finding terse. The sweep is an orchestration, not a restatement; its output is a per-option lens-annotation table, not a lens tutorial.

**No new lenses.** If a future need arises for a lens not in this table, file an ADR supersession rather than editing this reference to introduce one. Inventing a lens here (a) duplicates knowledge better owned elsewhere, (b) trips sentinel T06, and (c) silently grows the composition layer into a knowledge layer — the exact failure mode this file was designed to prevent.



## Stage-Specific Invocation

Each subsection names the activation gate, lens set, and convergence outcome for that stage. The anchors below (`#s1-ideation`, `#s2-research`, `#s3-architecture`, `#s5-refactoring`) are stable and are the targets for pointers in `agents/promethean.md`, `agents/researcher.md`, `agents/systems-architect.md`, and `skills/refactoring/SKILL.md`.

### S1 Ideation

- **Invoking agent/phase**: `agents/promethean.md` Phase 5 (before `AskUserQuestion`).
- **Activation gate**: narrow impact-to-effort spread across candidates (no clear winner) OR explicit user ask.
- **Lens set**: Security + Simplicity + Testability — the "three-lens pre-shortlist pass." Performance is deferred to S2/S3 when concrete design exists to evaluate.
- **Convergence outcome**: user gate (unchanged from Phase 5's existing behavior) — the pre-shortlist pass narrows the slate presented to the user, but the user's accept/reject remains the S1 convergence signal.
- **What the sweep produces**: an annotated shortlist where each candidate carries a one-line note per lens (or "n/a" when the lens does not discriminate).

### S2 Research

- **Invoking agent/phase**: `agents/researcher.md` Phase 4, inside step 3 ("Build a comparison matrix").
- **Activation gate**: options < 3 OR architect later flags axis-coverage incomplete.
- **Lens set**: Security + Performance + Simplicity + Testability + any domain lenses the research brief names.
- **Convergence outcome**: cross-option delta stability — when re-running the matrix with added options or axes produces the same ranking, the research has converged. Finalize `RESEARCH_FINDINGS.md` only after stability holds across ≥1 re-sweep.
- **What the sweep produces**: an expanded comparative matrix with lens rows added; any option that scores "n/a" across every lens is a candidate for elimination.

### S3 Architecture

- **Invoking agent/phase**: `agents/systems-architect.md` — Phase 7 (primary) before the `### Decision` template, and Phase 9 (extended review) at the end of the Tier 1 self-review lens list.
- **Activation gate (Phase 7)**: full 5-dimension formula.
- **Activation gate (Phase 9)**: same formula, or user-requested Tier 2 extended review.
- **Lens set (Phase 7)**: Security + Performance + Simplicity + Testability — applied to each option under consideration.
- **Lens set (Phase 9)**: Dev + Test + Ops (baseline) + Security + Performance + Simplicity + Testability (extended), each citing an existing Praxion artifact (the owning skill or rule) rather than restating methodology.
- **Convergence outcome**: REQ-ID stability + risk-budget satisfaction + blast-radius bound + user acceptance (see [Convergence Signals](#convergence-signals)).
- **What the sweep produces**: ≥2 fleshed-out options under the Decision block (strawmen violate the honest-uncertainty gate) and an ADR body `Activation:` line per the [ADR obligation](#adr-obligation).

### S5 Refactoring

- **Invoking agent/phase**: the invoking agent follows the cross-link in `skills/refactoring/SKILL.md` `## Decision Framework`.
- **Activation gate**: 2+ valid module decompositions with no obvious winner on the four pillars (modularity, low coupling, high cohesion, pragmatic structure).
- **Lens set**: four pillars + blast-radius — score each decomposition against all five.
- **Convergence outcome**: pillar satisfaction + blast-radius bound — a decomposition "wins" when it strictly dominates on pillar scores AND stays within the blast-radius budget from Phase 1 calibration. Ties re-enter the sweep with an added lens (e.g., testability) or escalate to user acceptance.
- **What the sweep produces**: a pillar-by-decomposition scoring table recorded alongside the refactoring plan.

## Convergence Signals

Synthesis converges on four **mechanical** signals — observable, traceable, and verifier-checkable across ADR revisions. No LLM-as-judge confidence scalars are used — they are uncalibrated and not mechanically checkable.

1. **REQ-ID stability across ≥2 design sweeps.** When multiple pre-implementation sweeps produce the same REQ set, the design has converged on the *what*; Phase 7 then decides only the *how* (implementation trade-off). Formalized in [`spec-driven-development/SKILL.md#convergence-via-req-id-stability`](../../spec-driven-development/SKILL.md#convergence-via-req-id-stability). Churn across sweeps means REQs are leaking implementation detail — re-draft REQs before re-sweeping.
2. **Risk-budget satisfaction.** Every High-likelihood × High-impact risk in the `SYSTEMS_PLAN.md` Risk Assessment has a concrete mitigation or is explicitly accepted with a rationale. An unmitigated high-high risk is a blocker — synthesis has not converged.
3. **Blast-radius bound.** The chosen design's blast radius is less than or equal to the budget set by the Phase 1 tier calibration. A design that exceeds the budget either re-scopes the work or escalates the tier — it does not silently expand.
4. **User acceptance.** Final convergence gate at `SYSTEMS_PLAN.md` review. User acceptance is necessary but not sufficient — it follows the three mechanical signals, not in place of them.

**Signal ordering.** Check 1 → 2 → 3 → 4 in order. If REQ-IDs are still churning (signal 1 fails), the risk budget is premature — the "what" is not yet stable, so arguing about "how" mitigations wastes cycles. If the risk budget fails (signal 2), blast-radius is irrelevant because the design itself is not acceptable. User acceptance (signal 4) is the last gate, not the first — it ratifies the three mechanical signals, it does not substitute for them.

**Prohibited.** LLM-as-judge confidence scalars (e.g., `judge_threshold ≥ 0.80`) are **not** convergence signals for design synthesis. They are uncalibrated (see `skills/agent-evals/SKILL.md`), not spec-grounded, and not mechanically checkable. A numeric "confidence" value in an ADR body violates the mechanical-signals contract and is a signal to return to the four mechanical signals above.

## Cost Envelope

Design synthesis must stay within the following budget tiers, derived from `RESEARCH_FINDINGS.md §9`:

- **≤3× baseline** for routine Standard-tier activations — the typical fired case.
- **≤6× baseline** for high-stakes activations (security, one-way-door, user-visible-breaking) where deeper sweeps are justified.
- **≤10× baseline** for genuinely novel work with no precedent — the ceiling, not the default.

"Baseline" is the architect/researcher/promethean cost for the same stage without synthesis. Exceeding the envelope is a signal to re-scope (narrow the option set, drop a lens that is not discriminating) rather than a license to keep spending. Observed overruns should surface in `LEARNINGS.md` for post-pipeline review.

Envelope observations accumulate in `.ai-state/calibration_log.md` via the [Logging obligation](#logging-obligation) rows. After 5–10 fired activations, trend the cost-vs-outcome distribution: if routine activations regularly approach the 3× ceiling without discriminating signals, the formula is firing too broadly; if novel activations stay well under 10× with clean convergence, the envelope itself is worth revisiting in a supersession ADR.

## Anti-Patterns

- **Do not invent new lenses in this file.** Every lens must cite an owning artifact from the [Lens Catalog](#lens-catalog). Adding a new lens body here duplicates knowledge, trips sentinel T06, and breaks the composition-not-knowledge contract. If a lens is genuinely missing, file an ADR supersession and add it to the owning skill, not here.
- **Do not use LLM-as-judge confidence scalars.** Scalars are uncalibrated and not mechanically checkable. Use the four mechanical convergence signals.
- **Do not spawn lens-critic subagents.** Research §15 evaluated and rejected the parallel-subagent-fan-out shape (Option 3) at 5–10× baseline cost for <30% activation rate. Synthesis is a single-agent sweep across existing-skill pointers, not a multi-agent debate.
- **Do not promote this reference to a standalone skill without evidence of outgrowth.** The H3 escalation path (context-review §4) exists, but requires observed need — either this reference exceeding ~5K tokens in active use, or adoption outside the SWE pipeline. Premature promotion pays the always-loaded metadata tax for a discoverability gain that is not yet real.

## References

- [`../SKILL.md`](../SKILL.md) — parent skill.
- [`../../spec-driven-development/SKILL.md#convergence-via-req-id-stability`](../../spec-driven-development/SKILL.md#convergence-via-req-id-stability) — REQ-ID stability formalization.
- [`../../refactoring/SKILL.md`](../../refactoring/SKILL.md) — S5 invocation site (`## Decision Framework`).
- [`../../../agents/promethean.md`](../../../agents/promethean.md) — S1 invocation site (Phase 5).
- [`../../../agents/researcher.md`](../../../agents/researcher.md) — S2 invocation site (Phase 4).
- [`../../../agents/systems-architect.md`](../../../agents/systems-architect.md) — S3 invocation site (Phase 7 primary, Phase 9 extended review).
