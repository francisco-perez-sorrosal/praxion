---
id: dec-232
title: Dialectical Inquiry + two-tier Disconfirmation replaces an ACH matrix for ADR deliberation
status: accepted
category: architectural
date: 2026-06-18
summary: ADR deliberation uses a gated Dialectical-Inquiry sub-step + an always-on Tier-A Disconfirmation block + a gated Tier-B cross-model challenge; the full ACH matrix is not adopted.
tags: [adr, dialectical-inquiry, disconfirmation, devils-advocacy, cross-model, storm-integration]
made_by: agent
agent_type: systems-architect
branch: worktree-storm-integration
pipeline_tier: full
affected_files:
  - agents/systems-architect.md
  - rules/swe/adr-conventions.md
  - skills/software-planning/references/adr-authoring-protocols.md
  - skills/software-planning/references/design-synthesis.md
affected_reqs: [REQ-03, REQ-04, REQ-05]
supersedes_in_part:
  - dec-231
dissent: "A reader who wants exhaustive option enumeration may argue DI (one genuine rival) is narrower than an ACH matrix (all plausible hypotheses scored by disconfirmation). Held minority view: revisit if decisions with >2 genuinely-live options recur and DI's single-rival framing demonstrably loses coverage."
---

## Context

The storm-integration scope originally listed an ACH (Analysis of Competing Hypotheses) matrix as a candidate for ADR deliberation. The research base (SAT §1–2, AI_DEBATE, DECISION §2) is decisive on two points: (1) ACH is moderately evidenced but sparsely validated and degrades to "ACH theater" when hypotheses are too similar or evidence is sparse; (2) assigned devil's advocacy degrades to performance ("DA-as-theater") — critics tick the box then rejoin consensus. Meanwhile Dialectical Inquiry (Schweiger AMJ 1986/1989) beats consensus and edges DA on assumption surfacing, and Huang (ICLR 2024) shows intrinsic self-correction of reasoning is illusory without an external oracle — the only reliable disconfirmation of reasoning comes from a *different* model.

## Decision

Replace ACH with a three-part scheme:

1. **DI sub-step** (gated: honest-uncertainty gate AND `category: architectural`) in systems-architect Phase 7 — argue a *genuine rival design*, not an assigned-contrarian critique. Completes the existing `design-synthesis.md` lens sweep.
2. **Tier-A Disconfirmation block** (always-on for `category: architectural` ADRs) — ~5 lines attacking the CHOSEN option: Falsifier / Steelmanned runner-up / Reversal trigger. New `dissent:` frontmatter field.
3. **Tier-B cross-model adversarial challenge** (gated to high-stakes/contested: honest-uncertainty fires AND stakes ∈ {security, one-way-door, user-visible-breaking}) — a different-model agent whose sole job is to refute the decision. This is the external oracle that makes disconfirmation effective.

## Considered Options

### Option 1 — ACH matrix
- Pro: structured exhaustive enumeration; disconfirm-weak-options reverses confirmation bias.
- Con: sparse validation; "ACH theater"; 20–60 min ceremony per decision; matrix subjectivity provides structure but not objectivity.

### Option 2 — DI + Tier-A always-on + Tier-B gated (CHOSEN)
- Pro: DI beats consensus and avoids DA-theater (each side genuinely defends its own design); Tier-A is cheap honest disconfirmation of the chosen option (Toulmin Rebuttal/Qualifier + steelmanning); Tier-B supplies the cross-model external oracle that escapes Huang's self-correction-illusion regime; all heavyweight pieces gated.
- Con: DI surfaces one rival, not an exhaustive hypothesis set; can still be performed shallowly if the honest-uncertainty gate is gamed.

## Consequences

- Positive: cheaper, better-evidenced, theater-resistant, oracle-grounded; reuses the existing activation formula and named-variant patterns; the `dissent:` field makes minority views machine-queryable (Disagree-and-Commit).
- Negative: no structured matrix for option-heavy decisions; Tier-B adds a cross-model call (cost) — mitigated by gating.

## Prior Decision

Supersedes the deferral ADR (dec-231) only on the ACH-matrix clause: that ADR defers the full ACH matrix; this ADR explains *why* the replacement (DI + Disconfirmation) is the chosen mechanism. The two are consistent — the matrix is deferred because this scheme covers the need.

## Disconfirmation (Tier A)

- **Falsifier**: Wrong if architectural decisions routinely have ≥3 genuinely-live options where scoring each against disconfirming evidence (ACH) would change the outcome and DI's single-rival framing misses the winner.
- **Steelmanned runner-up (ACH)**: ACH's matrix forces enumeration of *all* plausible hypotheses and disconfirmation-first scoring, which is structurally more resistant to anchoring on a favorite than DI's "argue one rival." For decisions with many competing technical hypotheses (e.g., choosing among 5 storage engines), the matrix's completeness is a real advantage DI lacks.
- **Reversal trigger**: Reintroduce ACH (as a gated heavyweight mode in the skill) if recurring decisions exhibit >2 live options AND post-hoc review shows DI missed a winning option that ACH-style disconfirmation would have surfaced.

**Activation:** fired — signals: criticality (changes ADR contract) + reversibility (one-way-door on the ADR schema field); lens set = Simplicity + Testability + the SAT/DECISION evidence base; convergence = stable across SAT, AI_DEBATE, DECISION, EVIDENCE (four independent research fragments converge on DI>DA, external-oracle, steelmanning).
