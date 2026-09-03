---
id: dec-draft-48d81c8a
title: DS-1's existing-only placement gate (exit 2) is authoritative over INTERFACE_DESIGN.md D10
status: proposed
category: implementation
date: 2026-09-02
summary: Step 14 implements SYSTEMS_PLAN.md DS-1's placement x mode legality (sidecar legal only under mode existing, exit 2) rather than INTERFACE_DESIGN.md D10's new-and-existing/exit-3 variant.
tags: [sidecar-placement, onboarding, conflict-resolution]
made_by: agent
agent_type: implementation-planner
pipeline_tier: full
branch: worktree-sidecar-placement
affected_files:
  - scripts/onboard-project
affected_reqs: [REQ-14]
---

## Context

Two independently-authored specialist documents in this pipeline specify
different legality rules for `--placement sidecar`. `SYSTEMS_PLAN.md` DS-1
(the systems-architect's Representation Design Pass output) models
`OnboardingPlan = InRepo{mode} | Sidecar{config}`, where `Sidecar` carries no
mode field and is structurally legal **only when the resolved mode is
`existing`**; the enforcer is a single gate at `scripts/onboard-project`'s
argument-parsing boundary, exiting `2` (usage error) and naming the legal
combination. `INTERFACE_DESIGN.md` D10 (the interface-designer's own decision,
authored under lens-independence — it deliberately did not read
`SYSTEMS_PLAN.md`) specifies `--placement sidecar` as valid in **both `new`
and `existing`** modes, refused with exit `3` (refused-on-safety-grounds) in
`hackathon`/`promote`. Step 14 (`scripts/onboard-project`'s placement flag
parsing) must implement exactly one of these two rules; implementing both
would leave the CLI's own contract self-contradictory.

## Decision

Step 14 implements `SYSTEMS_PLAN.md` DS-1 exactly: `--placement sidecar` is
legal only when the resolved mode is `existing`; any other mode
(`new`, `hackathon`, `promote`) exits `2` (`$EXIT_USAGE`), naming the legal
combination.

## Considered Options

### Option A — Implement `INTERFACE_DESIGN.md` D10 as written

`sidecar` legal in `new` and `existing`; exit `3` on `hackathon`/`promote`.

- **Pros**: matches the interface-designer's already-drafted `--help` text,
  error table (R5), and onboarding-surface documentation in
  `INTERFACE_DESIGN.md §5.1`/`§2.1`.
- **Cons**: directly contradicts `SYSTEMS_PLAN.md` DS-1, which is the binding
  architectural output for this feature and carries its own Disconfirmation
  section (Falsifier / Steelmanned runner-up / Reversal trigger) explicitly
  reasoning through why `sidecar × new` is illegal today (a freshly-scaffolded
  project the operator just created and owns has no reason to hide Praxion
  from anyone) and naming the concrete future signal that would make it legal
  (a monorepo-sub-package scaffolding request). Overriding a data-structure
  design pass with an interface sketch authored without reading it would
  invert the pipeline's authority order.

### Option B — Implement `SYSTEMS_PLAN.md` DS-1 (chosen)

`sidecar` legal only in `existing`; exit `2` on every other mode.

- **Pros**: DS-1 is the architect's own Representation Design Pass output —
  the binding source for this decomposition per this pipeline's stage
  ordering (architecture before planning); its Disconfirmation section
  supplies the reasoning `INTERFACE_DESIGN.md` D10 does not carry (D10 states
  the rule without arguing for it, since the interface-designer's brief
  explicitly scoped mode-legality decisions to the architect); exit `2` is
  also the ecosystem-wide usage-error convention `INTERFACE_DESIGN.md` D1
  itself establishes for `praxion-sidecar`, so this choice does not even
  contradict the interface-designer's own exit-code philosophy — only D10's
  specific mode-legality claim.
- **Cons**: `INTERFACE_DESIGN.md §5.1`'s composition-rules table and `§2.1`'s
  R5 error message need a follow-up correction (Placement-by-mode row, R5's
  `<mode>` list) to stay consistent with the implemented behavior — flagged
  here for the doc-engineer/verifier rather than corrected in
  `INTERFACE_DESIGN.md` directly (that file is the interface-designer's
  frozen pipeline artifact, not one this plan edits).

### Option C — Implement both, gated by a flag

Ship D10's rule behind an opt-in flag, DS-1's as default.

- **Pros**: preserves both specialists' work.
- **Cons**: no user need justifies two competing placement×mode legality
  rules in one codebase (Simplicity First); doubles the test surface for a
  distinction with no demonstrated demand; DS-1's reversal trigger already
  names the exact future signal that would justify revisiting this — that
  signal has not occurred.

## Consequences

- **Positive**: `scripts/onboard-project`'s placement gate matches the
  architect's binding design and its documented reasoning; no
  self-contradictory legality rule ships.
- **Negative**: `INTERFACE_DESIGN.md`'s onboarding-surface prose (composition
  table, R5) is now stale on this one point relative to the implemented
  behavior — a documentation-only drift, not a behavioral one, and noted for
  the verifier to catch if `INTERFACE_DESIGN.md` is later treated as a
  standalone reference rather than a frozen pipeline artifact.
- **Risk accepted**: none — DS-1's own Disconfirmation section already
  reasons through the trade-off this decision inherits.

## Departure from the Plan

Not a supersession of any finalized ADR — this resolves an in-pipeline
conflict between two draft-stage specialist artifacts (`SYSTEMS_PLAN.md` and
`INTERFACE_DESIGN.md`) in favor of the architecturally-binding one, before
either reaches finalized ADR status.
