---
id: dec-282
title: Praxion-only issue-autofix workflow; reusable-hub extraction deferred
status: accepted
category: architectural
date: 2026-07-24
summary: >-
  The P5 issue-autofix workflow is a Praxion-only direct workflow (on: issues),
  not a hub reusable workflow — because only Praxion receives ecosystem-feedback
  issues about its own shipped artifacts; hub extraction is a deferred, bounded
  incremental step consistent with dec-273's centralize-only-what-the-fleet-needs
  reasoning.
tags: [ci-cd, autofix, github-actions, issues-event, self-healing-loop, praxion-only, distribution, incremental-evolution]
made_by: agent
agent_type: systems-architect
pipeline_tier: standard
branch: feat-self-healing-p5
affected_files:
  - .github/workflows/issue-autofix.yml
affected_reqs: [REQ-01, REQ-15, REQ-16]
dissent: >-
  A reusable hub now would amortize the security-critical injection/sanitization
  logic across a future fleet in one audited place and avoid a later extraction
  refactor — if any managed project ever needs inbound issue-triage autofix.
---

## Context

P5 (Self-Healing Loop, Subsystem C, brief §6) closes the loop by auto-fixing
Praxion's own `ecosystem-feedback`-labeled defect issues. Its two sibling
subsystems ship as **hub reusable workflows + SHA-pinned per-repo callers**
(`reusable-ci-autofix.yml` P1/`dec-273`, `reusable-cross-model-review.yml` P2)
precisely because *every managed repo* needs CI-autofix and cross-model review.
The question for P5: does issue-autofix follow the same hub+caller distribution
shape, or is it a Praxion-only direct workflow?

The defining fact: `ecosystem-feedback` issues report defects in **Praxion's own
shipped artifacts** (hooks, canonical blocks, agents, scripts, skills), filed by
the P4 sidecar *from* managed projects *into* the Praxion repo. Managed projects
are the *source* of these reports, not consumers of an issue-triage workflow.
There is no second consumer for issue-autofix in v1.

## Decision

Ship P5 as a **Praxion-only direct workflow** at `.github/workflows/issue-autofix.yml`
with `on: issues, types: [labeled]`. Do **not** create a `reusable-issue-autofix.yml`
hub or a caller template. Reuse P1's *step bodies* (budget gate, non-agent
untrusted-text fetch/sanitize, sensitive-path tripwire) verbatim so the security
machinery is byte-for-byte the audited P1 logic even though the distribution
shape (direct workflow, not hub+caller) differs. Defer hub extraction until a
second consumer concretely appears — at which point it is a bounded, deliberate
refactor.

This is **consistent with `dec-273`'s reasoning**, not a contradiction: `dec-273`
centralizes in a hub what the *fleet* consumes; it does not mandate a hub for a
single-repo concern. Applying the hub pattern here would be premature
generalization (`Incremental Evolution`: don't build for a future consumer that
does not exist).

## Considered Options

### Option 1 — Praxion-only direct workflow (adopted)

- **Pros:** minimal surface (one file); no caller/policy indirection; no
  cross-org `secrets:` mapping ceremony for a single-repo workflow; fastest to
  ship and audit; security machinery still identical to P1 (reused step bodies).
- **Cons:** if a second consumer appears, the logic must be extracted then
  (a deliberate refactor); a small pattern divergence from P1/P2's hub+caller
  shape.

### Option 2 — New hub reusable workflow + per-repo caller (reusable-now)

- **Pros:** one audited home for the injection/sanitization logic across a
  hypothetical future fleet; no later extraction; maximal consistency with
  P1/P2's shape.
- **Cons:** generalizes for a consumer that does not exist in v1; adds
  workflow_call indirection, an explicit cross-org `secrets:` contract, a caller
  template, and onboarding-install work — all cost, no v1 benefit; a larger,
  slower-to-audit privileged surface for zero current fleet value.

## Consequences

- **Positive:** smallest possible privileged surface for a security-critical
  workflow; ships and audits fastest; no premature abstraction; the security
  machinery is the already-audited P1 logic.
- **Negative:** a future managed-project issue-triage need incurs an extraction
  refactor — the same "deliberate, blast-radius-controlled change" cost model
  `dec-273` already accepts for per-repo pin bumps.
- **Neutral:** P5 still consumes the P2 hub for review of its `issue-autofix/*`
  PRs (P2's `agent-prs` scope already matches that prefix — no P5 change), so
  the *review* half of the loop is already fleet-shared; only the *triage/fix*
  half is Praxion-local.

## Disconfirmation

- **Falsifier:** a managed project concretely needs inbound issue-triage autofix
  in the near term (making the "only Praxion consumes this" premise false), or
  the extraction refactor later proves materially more expensive than building
  the hub now would have been.
- **Steelmanned runner-up (reusable-now):** the logic P5 carries is *exactly* the
  security-critical class `dec-273` argued belongs in one audited hub —
  untrusted-text sanitization, prompt-injection posture, least-privilege scoping.
  Building the hub now means that class of logic lives in a single reviewed place
  from day one, the extraction refactor is never paid, and P5 conforms to the
  P1/P2 pattern a reader already knows. The marginal cost of `on: workflow_call`
  + a thin caller is small relative to the consistency and future-amortization it
  buys; "no second consumer yet" is a *timing* argument, and hubs are cheapest to
  establish before the first divergent copy exists.
- **Reversal trigger:** the first concrete second consumer of issue-triage
  autofix — extract `reusable-issue-autofix.yml` from the Praxion-only workflow
  at that point (a mechanical refactor, since the step bodies are already the
  reusable P1 forms).
- **Activation:** design-synthesis lens sweep — no. The decision is reversible
  (extraction is a bounded later step), single-axis, and well-grounded by
  `dec-273`'s precedent; honest-uncertainty gate does not fire at elevated
  stakes. Tier-A Disconfirmation authored above per the always-on obligation for
  `category: architectural`.
