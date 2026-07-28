---
id: dec-287
title: Fleet-install the cross-model review gate — onboard 8e.8 installs the caller gated on policy; /new-project unchanged (defer contract); closes dec-278
status: accepted
category: architectural
date: 2026-07-27
summary: /onboard-project sub-step 8e.8 is flipped to install the cross-model-review.yml caller alongside ci-autofix.yml, gated on policy review.cross_model_gate != off, under the same file-existence idempotency guard, printing (never injecting) gh secret set CURSOR_API_KEY. The stale autofix-policy.yml.tmpl comments (pr_checks/dependabot/fork_prs) are corrected to LIVE. /new-project gains no install logic — its existing defer-to-/onboard-project handoff covers the new caller (dec-274 pattern, re-affirmed by dec-278). Closes dec-278's deferral of P2 fleet rollout.
tags: [ci-cd, self-healing-loop, cross-model-review, cursor, onboarding, fleet-rollout, secrets, new-project, defer]
made_by: agent
agent_type: systems-architect
branch: worktree-p3b-fleet-install
pipeline_tier: standard
affected_files:
  - commands/onboard-project.md
  - claude/project-baseline/ci-autofix/autofix-policy.yml.tmpl
  - commands/new-project.md
affected_reqs: [REQ-01, REQ-02, REQ-03, REQ-04, REQ-06, REQ-07, REQ-08]
re_affirms: dec-274
dissent: "Rolling a second vendor's secret requirement (CURSOR_API_KEY) into every managed onboard — even print-only and policy-gated — is the exact cost dec-278 deferred pending a Praxion dogfooding signal; installing it now for the whole fleet trusts that the dogfood signal is favorable, which this pass asserts rather than measures."
---

## Context

`dec-278` (P2) built and dogfooded the cross-model review gate on Praxion itself but
explicitly **deferred** wiring `/onboard-project` / `/new-project` to install the review
caller for managed repos — "a follow-on task, scheduled after Praxion's own dogfooding
produces a first real signal." P3b is that follow-on. The realized
`cross-model-review.yml.tmpl` caller already ships in `claude/project-baseline/ci-autofix/`
(P2 built it; the policy-template-schema suite is green); sub-step 8e.8 currently installs
only `ci-autofix.yml` + `autofix-policy.yml` and carries the line "Do **not** install the
P2 `cross-model-review.yml.tmpl` stub — deferred."

Two adjacent facts are now stale in the shipped surfaces: (1) 8e.8's deferral line, and
(2) `autofix-policy.yml.tmpl`'s comments marking `surfaces.pr_checks` / `dependabot` /
`fork_prs` as "P3 — reserved, not yet read by the hub" — P3a made those surfaces **live**.

Activation: honest-uncertainty gate **not fired** — the install follows the established,
test-covered 8e.8 file-existence-idempotent pattern and the `dec-274` defer-for-new-project
precedent; there is no genuine second design in contention. The Tier-A Disconfirmation
block below is nonetheless authored (always-on for `category: architectural`, because this
is a fleet trust-boundary rollout: a second vendor's secret enters every onboard).

## Decision

1. **8e.8 installs the cross-model caller, policy-gated.** When
   `.github/workflows/cross-model-review.yml` is absent **and** policy
   `review.cross_model_gate != off`, render `cross-model-review.yml.tmpl` (fill
   `{{PRAXION_HUB}}` + the same resolved `{{HUB_SHA}}` used for the fixer caller, strip the
   doc-comment header) and write it — under the same never-overwrite guard as the fixer
   caller. `{{HUB_SHA}}` resolves to a real 40-hex commit; abort on any surviving `{{`.
2. **Print, never inject, `CURSOR_API_KEY`.** When the cross-model caller is installed,
   print `gh secret set CURSOR_API_KEY` as a one-time operator step (the existing 8e.8
   parenthetical is promoted to an unconditional print when the caller is installed).
3. **Correct the policy-template comments.** `surfaces.pr_checks` / `dependabot` /
   `fork_prs` are documented as **live** surfaces the hub reads — inline rationale only,
   citing no `dec-NNN` (shipped-artifact isolation).
4. **Record the caller set in the onboard manifest** `artifacts` object (a flat key,
   e.g. `ci_autofix`), so the install footprint is discoverable and the upgrade reconciler
   can preserve it.
5. **`/new-project` gains no install logic.** Its exit handoff already defers all of
   Phase 8e to a subsequent `/onboard-project` run; that handoff now covers the cross-model
   install with no code change. This preserves the single-install-path convention and the
   existing regression guard (`test_new_project_gains_no_duplicate_install_logic`).

## Considered Options

### A. Flip 8e.8 to install the cross-model caller (policy-gated) + /new-project unchanged (chosen)
- **Pros:** mirrors the fixer-caller install exactly (same guard, same render path, same
  print-not-inject); policy gate lets a project opt out; matches `dec-274`'s defer pattern
  for `/new-project` (re-affirmed by `dec-278`); closes `dec-278`'s deferral now that the
  dogfood exists.
- **Cons:** asserts the dogfood signal is favorable rather than measuring it (dissent).

### B. Also add explicit install logic to /new-project (rejected)
- **Pros:** a literal reading of "mirror in /new-project."
- **Cons:** contradicts `dec-274`/`dec-278`; duplicates a security-sensitive install
  across two command files as a byte-identical same-step dependency; turns the existing
  regression guard red. The defer handoff already delivers the mirror.

### C. Install the cross-model caller unconditionally (ignore the policy gate) (rejected)
- **Pros:** simplest install.
- **Cons:** forces a second vendor's secret requirement on projects that set
  `cross_model_gate: off` — the opposite of the opt-out the policy field exists to provide.

## Consequences

**Positive:** managed projects gain the review gate by installing a thin, policy-gated
caller; the shipped policy template stops lying about P3a surface status; the onboarding
pair stays single-install-path consistent; `dec-278`'s open follow-on is closed.

**Negative / cost:** every onboard that keeps the gate on now prints a second secret step
and, unset, the review job fails **open** (per `dec-276`) so the absence is non-blocking
but silent; the favorable-dogfood assumption is asserted, not measured (dissent + reversal
trigger).

## Disconfirmation

- **Falsifier:** if managed projects that adopt the gate see a materially high
  false-positive rate (the cross-model reviewer requests changes on sound fixes) or find
  the `CURSOR_API_KEY` requirement a routine onboarding blocker, then rolling the gate to
  the whole fleet by default was premature and 8e.8 should default `cross_model_gate: off`
  (opt-in) rather than `agent-prs`.
- **Steelmanned runner-up:** keep the gate **opt-in at onboard** (install the caller but
  default the policy to `cross_model_gate: off`, requiring a deliberate flip). This is the
  more conservative rollout — it delivers the machinery without imposing the second-vendor
  secret until a project asks. It is the right answer if the dogfood signal is mixed; it
  was not chosen because the policy template already ships `agent-prs` as its default
  (P2), the gate fails open (`dec-276`) so an unset secret is harmless, and closing
  `dec-278` means actually enabling the gate the fleet, not just shipping dormant files.
- **Reversal trigger:** a measured high false-positive rate or repeated operator friction
  over the `CURSOR_API_KEY` step promotes the opt-in default (runner-up) from steelman to
  decision; conversely, a clean dogfood corpus confirms the current default.

## Prior Decision

Re-affirms `dec-274` (P1): "/new-project mirrors the install via its existing
defer-to-/onboard-project handoff — no new-project code change," now applied to P2's review
gate exactly as `dec-278`'s own Prior Decision anticipated. Closes the deferral recorded in
`dec-278` (P2 fleet rollout): `dec-278` stays `accepted` and historically correct — it
deferred pending a dogfood signal; this ADR executes that follow-on now the signal exists.
Builds on `dec-273` (distribution model) and `dec-277`/`dec-276` (the gate's role split +
fail-open), unchanged.
