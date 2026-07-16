---
id: dec-263
title: Retire the onboarding-producer expectation for the future-designed agentic-eval artifacts
status: accepted
category: architectural
date: 2026-07-01
summary: Neither project_profile.yaml nor eval_ledger/EVAL_LOG.md gets a /onboard-project producer; both are produced only by the (deferred) agentic-eval archetype feature. Retires dec-219's Phase 8f-output clause; re-affirms dec-231's deferral and dec-217's lazy-run design.
tags: [tech-debt, td-044, project-profile, eval-ledger, onboarding, dead-seam, gate-liveness, agentic-eval, deferral]
made_by: agent
agent_type: systems-architect
branch: main
pipeline_tier: lightweight
affected_files:
  - commands/onboard-project.md
  - skills/software-planning/references/artifact-inventory.md
  - skills/agent-evals/references/run-ledger-schema.md
  - .ai-state/decisions/219-project-profile-yaml-schema.md
supersedes: dec-219
re_affirms: dec-231
re_affirmed_by: [dec-268]
dissent: If the agentic-eval archetype loop lands soon, a minimal Phase 8f stub now would have saved re-opening this; retiring an almost-ready seam risks it being rebuilt from scratch rather than resumed.
---

## Context

td-044 flags two `future-designed` artifacts — `project_profile.yaml` and
`eval_ledger/EVAL_LOG.md` — as producer-less "dead seams": their archetype-detection +
agentic-eval scaffold is designed (schema `skills/agent-evals/references/run-ledger-schema.md`;
lifecycle `skills/software-planning/references/artifact-inventory.md`) but never wired into
`/onboard-project`. The row's two close paths are (a) wire the producers into onboarding, or
(b) formally retire the scaffold via ADR.

Direct verification refines the premise — the two artifacts are **not** symmetric:

- **`project_profile.yaml`**: dec-219 designed it as a *Phase 8f onboarding output*. Grep confirms
  **no Phase 8f exists** in `commands/onboard-project.md` (phases stop at 8/8b/8c/8d/8e), so the
  producer expectation dangles. Every consumer is fallback-to-live-detection prose:
  `project-principles.md` states outright *"project_profile.yaml has no active producer today...
  When project_profile.yaml gains a producer, the resolver gains one branch"*; the run-ledger
  schema's absent-behavior mandates live detection. **Zero active runtime consumer.** Its one
  consuming feature — the `project_profile.yaml`-keyed agentic eval-lens — is already deferred by
  dec-231.
- **`eval_ledger/EVAL_LOG.md`**: the inventory already documents it as *"created lazily by the
  first kept run, not at onboard."* It has **built readers** (dashboard eval panel per dec-223,
  `/scores` command) that tolerate absence, and a designed lazy-run writer (the project's eval
  loop). "No onboarding producer" is **by design**, not debt. (Note: `/eval-praxion` writes a
  *different* file, `.ai-state/praxion_eval_reports/PRAXION_EVAL_LOG.md` — Praxion's own self-eval
  log — not this managed-project ledger.)

## Decision

**Retire the onboarding-producer expectation (close path b), asymmetrically. Neither artifact is
produced by `/onboard-project`; both are outputs of the (deferred) agentic-eval archetype feature
when/if it lands.**

- `project_profile.yaml`: **retire dec-219's "Phase 8f output" clause.** Onboarding will not emit
  it. The artifact stays `future-designed`; its producer moves from onboarding to the agentic-eval
  archetype feature (dec-216 R1+R2). dec-219's *schema and `.ai-state/` location* decision remains
  in force — only the producer-mechanism clause is superseded.
- `eval_ledger/EVAL_LOG.md`: **no change.** Its lazy-run producer + absence-tolerant readers are
  already correct; re-affirm dec-217. It was never a dead seam.

**Named re-open trigger:** implementing the deferred agentic-eval archetype loop (the dec-216
R1+R2 detection work). That feature — not onboarding — carries the producers for both artifacts.
Until then, onboarding stays untouched (Simplicity First: the debt is a dangling *expectation*,
not missing code).

## Considered Options

### A — Wire the producers into `/onboard-project` (add Phase 8f + eval-loop scaffold)
- Pros: closes the seam by construction; every managed project gets a populated profile/ledger.
- Cons: requires building the entire archetype-detection + eval-loop feature (dec-216 provisional,
  dec-231 deferred) to satisfy one ledger row — sunk-cost-driven scope explosion. It would emit a
  `project_profile.yaml` that **no live consumer reads** (the eval-lens is deferred), producing the
  inverse gate-liveness anti-pattern: a producer with no live consumer. Violates Simplicity First
  and Register Objection.

### B — Retire the onboarding-producer expectation via ADR (CHOSEN)
- Pros: closes the debt honestly without shipping a large deferred feature; onboarding stays lean;
  the "named producer for every consumer" clause is satisfied cleanly (no consumer currently needs
  either artifact; both fall back to live detection / absence-tolerance). The producer is correctly
  relocated to the feature that owns it, behind a named trigger.
- Cons: when the agentic-eval feature lands, its author must remember to add the producers (mitigated
  by the run-ledger schema + inventory pointers and the named trigger recorded here).

### C — Retire both symmetrically as a single "dead seam"
- Pros: simplest narrative.
- Cons: **factually wrong for `eval_ledger/EVAL_LOG.md`**, which has built readers and a by-design
  lazy producer. Retiring it as dead would misrepresent a working forward-designed reader surface
  and could invite deleting the (correct) dashboard/`/scores` consumers.

## Consequences

- **Positive:** debt closed with zero new onboarding surface; the two artifacts get an honest,
  differentiated lifecycle record; a future feature author has a named trigger and a single place
  (this ADR) explaining why onboarding does not produce them.
- **Negative / constraint:** dec-219 must be marked as partially superseded (Phase 8f clause only;
  schema/location stands) so it no longer dangles an unbuilt producer claim — handled as a
  follow-up edit, not in this pass.
- **Gate-liveness:** both artifacts now satisfy "no live consumer ⇒ no producer obligation"; the
  producer obligation re-attaches only when the agentic-eval feature (its real consumer path) is
  built.

## Disconfirmation

- **Falsifier:** a *built, non-fallback* consumer of `project_profile.yaml` (a tool/agent that
  errors or misbehaves when it is absent, rather than falling back to live detection) would prove
  the seam is live and retirement wrong. None exists today.
- **Steelmanned runner-up (Option A):** the archetype-detection scaffold is designed down to the
  schema and a paradigm-detection reference (dec-216); a thin Phase 8f that writes the profile from
  already-designed detection is arguably low-cost and would make the eval-lens "just work" the day
  dec-231 is un-deferred. If the feature is imminent, wiring now avoids a rebuild-from-scratch.
- **Reversal trigger:** revisit when the deferred agentic-eval archetype loop (dec-231 / dec-216
  R1+R2) is scheduled for implementation — at that point the producer wiring is in-scope for that
  feature and this retirement is superseded by the feature's own producer decision.

## Prior Decision

This ADR **partially supersedes dec-219**: it retires only the *"Phase 8f output"* producer clause
(project_profile.yaml is no longer expected from onboarding). dec-219's substantive decision — that
`project_profile.yaml` is the machine-consumable archetype + run-store record, living in
`.ai-state/`, with the given schema — **remains in force**. It **re-affirms dec-231** (the
consuming eval-lens stays deferred, which is precisely why the producer must not be wired) and
**re-affirms dec-217** (the `eval_ledger/EVAL_LOG.md` lazy-run design is correct and unchanged).
