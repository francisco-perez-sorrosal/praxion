---
id: dec-278
title: P2 build scope excludes onboard-project.md/new-project.md install wiring — fleet rollout deferred to a follow-on pass
status: accepted
category: implementation
date: 2026-07-23
summary: The P2 cross-model review gate implementation pass builds the hub, Praxion's own caller (dogfood), the realized caller template, and the annotated policy template — but does NOT wire `/onboard-project` or `/new-project` to install the review caller for managed (fleet) repos. Fleet rollout is a separate follow-on task once Praxion's own dogfooding has produced a live signal. Chosen over including the onboarding install in this pass, because SYSTEMS_PLAN.md's own Prerequisites section already separates "built" from "usefully fleet-adopted," and dec-274 set the precedent that onboarding-install wiring is properly its own scoped unit of work, not bundled into the gate's core build.
tags: [ci-cd, self-healing-loop, cross-model-review, cursor, onboarding, scope, planning, fleet-rollout]
made_by: agent
agent_type: implementation-planner
branch: feat-self-healing-p2
pipeline_tier: standard
affected_files:
  - commands/onboard-project.md
  - commands/new-project.md
affected_reqs: [REQ-12]
dissent: "SYSTEMS_PLAN.md's own Architecture > Components > Modified table lists commands/onboard-project.md + commands/new-project.md as in-scope artifacts (annotated '(P1-for-fleet, sequenced by planner)'), so deferring them is a real scope narrowing relative to the architect's own component inventory, not merely a reading of ambiguous text — accepted because the dispatching task brief's explicit deliverables list and AC1–AC13 both omit any onboarding-install acceptance criterion, and the Prerequisites section itself states fleet rollout 'additionally waits on P1's onboarding phase; Praxion dogfooding does not,' i.e. building and fleet-adopting are already framed as separable."
---

## Context

`SYSTEMS_PLAN.md`'s Architecture > Components > Modified table lists
`commands/onboard-project.md` + `commands/new-project.md` as an in-scope artifact for P2, annotated
"(P1-for-fleet, sequenced by planner)" — i.e. the systems-architect explicitly deferred the
sequencing decision (whether and when this pass touches those command files) to the
implementation-planner. Two independent signals point the same direction:

1. The dispatching task brief's "What the build produces" list and AC1–AC13 do not mention
   onboarding-command changes at all — only the hub, Praxion's own caller, the realized template,
   and the annotated policy template.
2. `SYSTEMS_PLAN.md`'s own Codebase Readiness > Prerequisites section states: "Fleet rollout of the
   gate additionally waits on P1's onboarding phase; Praxion dogfooding does not" — i.e. the
   architecture document itself treats "build the gate" and "fleet-install the gate" as separable
   milestones, with Praxion's own dogfooding (caller #1) requiring only the former.

This mirrors `dec-274` (P1): the P1 onboarding install landed only in `/onboard-project` Phase 8e,
with `/new-project` needing no duplicate logic because its existing generic exit-handoff already
defers Phase-8e-style baseline installs to a subsequent `/onboard-project` run. That precedent
established onboarding-install wiring as its own scoped unit of work, not bundled into the gate's
core build.

## Decision

**This implementation pass builds and dogfoods the P2 gate but does not wire `/onboard-project` or
`/new-project` to install it for managed (fleet) repos.** Concretely, in scope: the hub
(`reusable-cross-model-review.yml`), Praxion's own caller (`.github/workflows/cross-model-review.yml`,
caller #1), the realized `cross-model-review.yml.tmpl` caller template, the annotated
`autofix-policy.yml.tmpl` `review:` block, and structural + dogfooding-parity tests. Out of scope:
any change to `commands/onboard-project.md` or `commands/new-project.md`. Fleet rollout — installing
the review caller alongside the ci-autofix caller in managed repos, and printing the
`gh secret set CURSOR_API_KEY` instruction — is a follow-on task, scheduled after Praxion's own
dogfooding (this pass's closing live-verification step) produces a first real signal.

## Considered Options

### A. Defer onboarding-install wiring to a follow-on pass (chosen)
- **Pros:** matches the task brief's explicit deliverables and AC1–AC13 exactly; matches the
  architecture document's own build-vs-fleet-adopt separation; matches the `dec-274` precedent that
  onboarding-install is its own scoped unit; keeps this pass's step count and file surface aligned
  with a Standard-tier decomposition instead of ballooning toward Full; lets fleet rollout benefit
  from Praxion's own dogfooding signal before every managed repo receives a second vendor's secret
  requirement.
- **Cons:** the gate remains Praxion-only until the follow-on lands; a reader of
  `SYSTEMS_PLAN.md`'s Modified-components table alone would expect the command files to change in
  this pass, so the divergence must be surfaced (this ADR + the `LEARNINGS.md` entry serve that).

### B. Include onboarding-install wiring in this pass (rejected)
- **Pros:** completes every artifact `SYSTEMS_PLAN.md`'s Modified table names in one pass; no
  follow-on task needed.
- **Cons:** contradicts the task brief's explicit scope and AC list; conflates "build a
  well-tested gate" with "roll a second vendor's secret requirement out to every managed repo" —
  two decisions with very different risk profiles that deserve independent review; the P1 precedent
  (`dec-274`) already established the pattern of keeping onboarding-install as a separate step;
  bundling it here would also require byte-identical mirroring across two command files as a
  same-step dependency of a security-sensitive gate build, adding surface without a corresponding
  AC to verify it against.

## Consequences

- **Positive:** this pass's step count and file surface stay proportionate to its Standard tier;
  the fleet-rollout decision is left open for reconsideration once Praxion's own dogfood run
  (`REQ-12`) has produced real signal on gate reliability and false-positive rate, rather than being
  locked in sight-unseen; consistent with `dec-274`'s established separation.
- **Negative / cost:** managed projects do not receive the cross-model review gate until a
  follow-on task explicitly wires `/onboard-project` (and confirms whether `/new-project` needs
  anything beyond its existing defer-to-onboard-project handoff, per `dec-274`'s reasoning, which
  should apply unchanged here).
- **Activation:** honest-uncertainty gate not fired — this is a scope-boundary/sequencing call, not
  a technology or architecture trade-off; Tier-A/B disconfirmation is not required, but the
  divergence from `SYSTEMS_PLAN.md`'s literal Modified-components table is significant enough to
  warrant this ADR plus an explicit `LEARNINGS.md`/return-summary flag so the user can object before
  work proceeds.

## Prior Decision

Builds on `dec-274` (P1): "AC7 '/new-project mirrors the install' satisfied by existing defer
pattern, no new-project.md code change." That decision already established that onboarding-install
wiring for the self-healing loop's autofix machinery is a distinct, separately-scoped concern from
building the machinery itself. This ADR applies the same separation to P2's review-gate onboarding.
