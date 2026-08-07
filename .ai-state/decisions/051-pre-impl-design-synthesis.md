---
id: dec-051
title: Pre-implementation design-synthesis capability (H1-wide)
status: accepted
category: architectural
date: 2026-04-17
summary: Add an activation-gated pre-impl design-synthesis reference file composed from existing skills, formalize REQ-ID stability as the mechanical convergence signal, and wire pointers from promethean, researcher, systems-architect, and refactoring — with zero always-loaded delta.
tags: [design-synthesis, pre-impl, progressive-disclosure, behavioral-contract, sdd, refactoring, activation-gate]
made_by: agent
agent_type: systems-architect
pipeline_tier: full
affected_files:
  - skills/software-planning/references/design-synthesis.md
  - skills/software-planning/SKILL.md
  - skills/spec-driven-development/SKILL.md
  - skills/refactoring/SKILL.md
  - agents/promethean.md
  - agents/researcher.md
  - agents/systems-architect.md
affected_reqs:
  - REQ-DDL-01
  - REQ-DDL-02
  - REQ-DDL-03
  - REQ-DDL-04
  - REQ-DDL-05
  - REQ-DDL-06
  - REQ-DDL-07
  - REQ-DDL-08
  - REQ-DDL-09
  - REQ-DDL-10
  - REQ-DDL-11
  - REQ-DDL-12
  - REQ-DDL-13
  - REQ-DDL-14
  - REQ-DDL-15
---

## Context

Praxion's self-healing loop is post-implementation only (verifier + sentinel). Pre-implementation has no explicit surface for composing competing proposals, running cross-lens critique, or recording convergence signals — yet the ingredients are scattered across `promethean` Phase 5, `researcher` Phase 4, `systems-architect` Phase 7 / Phase 9, `context-engineer` shadowing, and the `refactoring` skill's four pillars. The user asked whether a "design-dialectic" capability should be added.

The research (`RESEARCH_FINDINGS.md §§1/5/6/7/10/15`) surveyed six candidate shapes (dialectic, adversarial collaboration, tournament, constitutional AI, single-agent extended-thinking, multi-agent research) and the empirical literature. The literature is **not supportive of multi-agent debate for open-ended design synthesis**: at equal token budget, single-agent extended-thinking + scaffolding (rules, constraints, behavioral contracts) matches or beats multi-agent debate on reasoning tasks, while Anthropic's own multi-agent research wins correlate with token spend rather than topology (Budget-Aware Evaluation EMNLP 2024; Collaborative LLM Agents for C4 Software Architecture 2025). Praxion already has the scaffolding — the behavioral contract, SDD specs, existing security/performance/simplicity skills — but lacks an *activated composition surface* for pre-impl stages.

The context-review (`CONTEXT_REVIEW.md §§1/5/9`) verified the placement question as a progressive-disclosure / always-loaded-budget problem and recommended `H1 = Option 1 + Option 4's REQ-ID-stability formalization` with seven red flags the architect must avoid. `dec-050` (2026-04-17) raised the always-loaded budget ceiling to 25,000 tokens while explicitly warning that "raising the cap sends a 'more is OK' signal unless the reframing is internalized" — this ADR is the first authored under that reframed regime, and must justify its footprint on attention-relevance grounds, not headroom.

## Decision

**H1-wide** — a single consolidated design with three named sub-decisions:

### D1 — Capability

Add one new progressive-disclosure reference file: `skills/software-planning/references/design-synthesis.md` (~150–250 lines, on-demand only). It is **a composition layer, not a knowledge layer** — every lens it invokes points at an existing Praxion artifact (`skills/context-security-review`, `skills/performance-architecture`, `rules/swe/agent-behavioral-contract.md` Simplicity First, `agents/test-engineer.md` testability lens). It is registered in `skills/software-planning/SKILL.md`'s Satellite files list and cross-linked from `skills/refactoring/SKILL.md`'s `## Decision Framework`.

Four pointer edits wire it into the pipeline without adding always-loaded content:

| Stage | Agent file | Phase | Role |
|---|---|---|---|
| S1 Ideation | `agents/promethean.md` | Phase 5 | Pre-shortlist three-lens pass when impact-to-effort spread is narrow |
| S2 Research | `agents/researcher.md` | Phase 4 | Option-axis coverage critic when options < 3 |
| S3 Architecture (primary) | `agents/systems-architect.md` | Phase 7 | Full lens sweep before `### Decision` block |
| S3 Architecture (extended review) | `agents/systems-architect.md` | Phase 9 | Extend Dev/Test/Ops with Security/Performance/Simplicity/Testability |
| S5 Refactoring | `skills/refactoring/SKILL.md` | `## Decision Framework` | Cross-link for 2+ valid decompositions |

**Zero always-loaded delta.** The reference loads only when the architect (or promethean/researcher) follows a pointer. Agent-prompt additions are single-sentence pointers, not restated methodology.

### D2 — Activation Triggers

Activation is governed by a 5-dimension formula; tier is a prerequisite gate, not the sole activator:

```
activate_synthesis(task) =
    tier ∈ {Standard, Full}
  AND (
        blast_radius ≥ 5_files  OR  spans ≥ 2_subsystems
     OR reversibility == "one-way-door"
     OR novelty == "no-precedent"
     OR stakes ∈ {security, user-visible-breaking}
     )
  AND uncertainty == "multiple_plausible_paths"
```

The final `AND uncertainty == "multiple_plausible_paths"` clause is an **honest-uncertainty gate**: if the architect cannot name ≥2 plausible paths, synthesis will generate strawmen. The gate forces disclosure of whether there is a real choice, aligning with the behavioral contract's Register Objection.

### D3 — Convergence Signals

Four mechanical signals — **no LLM-as-judge confidence scalars**:

1. **REQ-ID stability** across ≥2 design sweeps (primary signal; formalized in `skills/spec-driven-development/SKILL.md` as a new `## Convergence via REQ-ID Stability` section, cross-linked from `design-synthesis.md`).
2. **Risk-budget satisfaction** — every High-likelihood × High-impact risk has a concrete mitigation or is explicitly accepted.
3. **Blast-radius bound** — chosen design's blast radius ≤ the budget from Phase 1 calibration.
4. **User acceptance** — final gate at `SYSTEMS_PLAN.md` review.

REQ-ID stability is the load-bearing insight: when multiple design sweeps produce the same REQ set, synthesis has converged on the *what*; the remaining trade-off is *how* (Phase 7's job). Stability is traceable, spec-grounded, and mechanically checkable by the verifier across ADR revisions — properties confidence scalars lack (`skills/agent-evals/SKILL.md` explicitly warns against uncalibrated LLM-as-judge thresholds).

## Considered Options

Four options evaluated in `RESEARCH_FINDINGS.md §15`; cost-and-footprint comparison in `CONTEXT_REVIEW.md §2`. H1-wide (chosen) is a hybrid of Options 1 and 4.

### Option 1 — Reference file inside `software-planning` skill

One new reference file, zero always-loaded delta, precedent-matched invocation surface (the behavioral-contract rule → behavioral-contract reference; the coordination rule → agent-pipeline-details reference; the implementation-planner agent → agent-pipeline-details reference for reconciliation). Progressive-disclosure-optimal. **Gap**: no mechanically checkable convergence signal on its own.

### Option 2 — Standalone `design-synthesis` skill

Promotes to `skills/design-synthesis/` with SKILL.md + 2–3 reference files. Incurs ~150–250 tokens of always-loaded metadata and creates naming-overlap risk with `software-planning` (sentinel C07's skill analogue): triggering vocabulary ("design", "synthesis", "architecture", "trade-offs") overlaps enough that disambiguation suffers. Rejected — the architect is the only consumer, discoverability gain is marginal.

### Option 3 — `DESIGN_SYNTHESIS.md` intermediate doc + parallel lens-critic subagents

New `.ai-work/<slug>/DESIGN_SYNTHESIS.md` document type; three parallel lens critic subagents (security / performance / simplicity); fragment-based reconciliation. Cost 5–10× baseline architect call. Requires registration across five locations (intermediate-documents rule, coordination-protocol rule, architect, planner, sentinel), new DL-equivalent sentinel checks, high description-overlap risk with existing skills. Research scopes high-activation decisions to <30% of ADRs — paying the carrying cost for a gate that fires 1 in 5 times violates Praxion's token-budget-first principle. Rejected.

### Option 4 — Reinforce-what-exists-only

No new artifacts; only tighten architect's Phase 7/9 prompts and formalize REQ-ID stability in SDD. Cheapest (~1.2× baseline). **Gap**: produces no *loadable capability* — the architect has nowhere to go when activation fires beyond inline prompt text, limiting the pattern's ability to evolve or be applied outside the architect agent.

### H1-wide (chosen) — Option 1 + Option 4's REQ-ID-stability formalization

Option 1's surgical footprint (one reference file, zero always-loaded delta, precedent-matched) combined with Option 4's mechanical convergence signal (REQ-ID stability formalized in SDD). Near-zero incremental cost over Option 1 alone. A one-line cross-link from `skills/refactoring/SKILL.md` (`H4` from context-review §4) covers the S5 refactoring gap the research identified without creating new artifacts.

## Consequences

### Positive

- **Zero always-loaded delta.** The surface that matters at session start is unchanged. Sentinel T02 headroom after `dec-050` (~9.5K tokens) is not consumed by this capability.
- **Precedent-matched invocation.** Pointers from agent prompts to `software-planning/references/*.md` anchors already exist (`rules/swe/agent-behavioral-contract.md:12`, `rules/swe/swe-agent-coordination-protocol.md:161`, `agents/implementation-planner.md:325`). The new reference follows the same pattern.
- **Composition, not duplication.** Lenses point at the skills that already own them. Sentinel T06 (redundancy) risk is minimal.
- **Mechanical convergence signal.** REQ-ID stability is verifier-checkable and spec-grounded — aligns with SDD's traceability model and closes the gap where Option 1 alone would preach a signal SDD did not define.
- **Graceful evolution.** If the reference outgrows ~5K tokens or the methodology is adopted outside the SWE pipeline (e.g., roadmap work that is not already covered by `roadmap-cartographer`), escalation to a standalone skill (Option 2) is a supersession ADR away — H3 in context-review §4 documents this explicit future path.
- **Aligns with `dec-050`'s reframe.** Every always-loaded token must earn its attention share; this work adds nothing to that surface and explicitly chooses composition over a new skill.

### Negative

- **Low visibility of the synthesis process.** Readers of `SYSTEMS_PLAN.md` see the outcome (the chosen design, the ADR's `Considered Options`), not the intermediate lens findings. If auditability of the deliberation becomes a requirement, H2 in context-review §4 (Option 1 default + Option 3 ceremony for security-critical / one-way-door decisions) is the escalation path — via supersession, not silent upgrade.
- **Dependency on lens-prompt quality.** The reference is a pointer layer; the lens bodies are owned by existing skills. If `performance-architecture` or `context-security-review` has gaps, the synthesis sweep inherits them. Mitigated by REQ-DDL-08 ("zero invented lenses") making the dependency explicit rather than hidden.
- **Activation gate requires architect judgment.** The 5-dimension formula has qualitative components (novelty, uncertainty). Over- or under-firing is possible until the project has observed 5–10 activations.
- **One consolidated ADR loses supersession granularity.** If activation triggers change later (D2) but the capability (D1) stays, the whole ADR must be superseded or amended. Accepted trade-off per the lean-mode design.

### Neutral

- `dec-047` (cross-reference validator) will catch anchor drift between `design-synthesis.md` and the SDD REQ-ID-stability section — no new sentinel check needed.
- `dec-050` (budget revision) remains in force; this ADR consumes no budget it provides.
- `dec-043` (behavioral contract layer) remains in force; the reference file extends Simplicity First / Register Objection into pre-impl without redefining them.

### Follow-ups (non-blocking)

- After 5–10 Standard/Full pipelines, measure activation-firing rate from `.ai-state/calibration_log.md` and ADR bodies. If firing rate < 20% or > 80%, revisit the 5-dimension formula in a supersession ADR.
- Sentinel T02 still encodes the 15,000-token ceiling (context-review §7). `dec-050` raised it to 25,000. This is independent drift, flagged here as an observation; a separate lightweight task should update `agents/sentinel.md:141`.
- If `performance-architecture` skill or `test-engineer` testability lens is missing or thin at implementation time, the planner records the gap in `LEARNINGS.md` and opens a follow-up ADR rather than inventing lens bodies inside `design-synthesis.md`.
- Consider a skill-genesis review after the first 3 activations to capture patterns worth extracting into the reference or back into the owning skills.
