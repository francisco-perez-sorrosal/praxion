---
id: dec-293
title: Cross-model INTAKE gate (Praxion-only, read-only) + shared producer-free PROJECT-PRISM sourced from CLAUDE.md
status: accepted
category: architectural
date: 2026-07-28
summary: >-
  The self-healing loop gains a Praxion-only, read-only cross-model INTAKE gate that
  independently assesses every filed ecosystem-defect issue (defect/improvement/non-issue/unclear
  + in_scope + confidence) before the human arming decision — closing dec-283's own rubber-stamp
  falsifier by validating the PROBLEM cross-model, not just the SOLUTION (dec-277). A shared
  PROJECT-PRISM — the repo's own CLAUDE.md read as bounded, base-ref DATA, producer-free — is
  injected into both the new intake gate and the existing (genuinely project-blind) PR review gate
  so each judges fitness-to-THIS-project. Extends dec-277; mirrors dec-276 fail-open; the intake
  gate is a direct workflow (not a hub) for the same reason issue-autofix.yml is (dec-282); the
  prism reuses CLAUDE.md — not project_profile.yaml (ADR-closed by dec-263 + dec-241) and not a new
  curated artifact — which is precisely what keeps the whole feature at Standard tier.
tags: [ci-cd, self-healing-loop, cross-model-review, intake-gate, cursor, project-prism, non-generative-gate, fail-open, security, prompt-injection, least-privilege, governance]
made_by: agent
agent_type: systems-architect
branch: worktree-cross-model-intake-prism
pipeline_tier: standard
affected_files:
  - .github/workflows/issue-intake-assessment.yml
  - .github/workflows/reusable-cross-model-review.yml
  - .github/autofix-policy.yml
  - claude/project-baseline/ci-autofix/autofix-policy.yml.tmpl
affected_reqs: [REQ-01, REQ-02, REQ-03, REQ-04, REQ-05, REQ-06, REQ-07, REQ-08, REQ-09, REQ-10, REQ-11]
re_affirms: dec-277
dissent: >-
  A second Cursor gate plus prism injection adds CI surface and leans harder on a foreign-model
  dependency whose problem-framing catch-value is as unproven as dec-277's solution catch-value;
  the maintainer already reads the issue before arming, so the intake assessment may be redundant
  noise, and reusing CLAUDE.md as the prism injects operational boilerplate the model may ignore —
  accepted because it closes dec-283's named rubber-stamp falsifier at near-zero marginal cost
  (same key, forfeit-if-unused credits, producer-free always-fresh prism) and every element is
  reversible per-repo via policy (intake_gate: off / project_prism: off).
---

## Context

The self-healing loop today reviews the *solution* cross-model (dec-277: a non-Anthropic Cursor
model gates every Claude-authored fix PR) but validates the *problem* same-family: an
ecosystem-defect issue is filed by Claude (`/report-praxion-issue`) or by a human from a
Claude-authored template, and the only judgment of whether it is a real, in-scope defect is the
maintainer's arming decision (applying `ecosystem-feedback`, which triggers `issue-autofix.yml`).
dec-283's own **named falsifier** is exactly this hole: maintainers rubber-stamping the arming
label on convincingly-Claude-written issues. This ADR closes that asymmetry.

Separately, direct code read confirms `reusable-cross-model-review.yml` feeds its reviewer ONLY a
PR diff + PR title/body (`:312-344`) — it is **genuinely project-blind**, asked to judge generic
"correctness/minimality" with zero notion of what the project is trying to be. Retrofitting a
project-context "prism" is a real fix to shipped code, not merely new-feature scope.

Grounded corrections (verified against the actual files, `RESEARCH_FINDINGS.md` §Q1/§Q2/§Q4):
- There is **no literal `ecosystem-defect` label**. The stable, category-invariant labels on every
  filing are `auto-filed` + `from-managed-project` (`commands/report-praxion-issue.md:84,98`;
  `.github/ISSUE_TEMPLATE/ecosystem-defect.md:5`). `ecosystem-feedback` is the separate, human-only
  arming label. The intake trigger must key on the stable auto-filed pair, at `opened`.
- The single large reusable block across the review hub is Cursor-install + live-model-resolution
  (`:239-310`); everything else (trigger, scope predicate, fetch target, prompt/schema, action
  verbs, **permission ceiling**) diverges for an issue-assessment shape.
- `project_profile.yaml` is **not** a viable prism host: dec-263 retired its onboarding producer
  (zero live consumer; `td-044` resolved on that basis) and dec-241 already **rejected** bundling a
  goals/principles artifact into it (`241:62`), choosing a standalone `.ai-state/principles.yaml`.
  Reviving it as a prism host would reverse two ratified ADRs and misuse an infra/runtime-config
  schema for goals/philosophy narrative.

## Decision

Three coupled calls, one bundled ADR (they share one constraint set — the privileged-CI security
envelope — and one empirical falsifier).

**1. Add a Praxion-only, read-only cross-model INTAKE gate** `issue-intake-assessment.yml` — the
assessment peer of `issue-autofix.yml`:
- `on: issues: [opened, labeled]`, job `if:` gated on `contains(labels, 'auto-filed') &&
  contains(labels, 'from-managed-project')` and `review.intake_gate != off` (default
  `agent-issues`). (Collapses to `[opened]`-only if an empirical check confirms labels are in the
  `opened` payload; `[opened, labeled]` + an idempotency guard is the robust default.)
- Permission ceiling **`issues: write` + `contents: read` ONLY** — no `pull-requests` grant at all
  (narrower than the review gate). It never opens a PR, never pushes, never writes code.
- Resolves a **non-`claude`** Cursor model live (same guard as the review gate); same-family →
  distinct `intake-assessment:misconfigured` + exit 0.
- Reads the issue body/title as sanitized **DATA** (reused `issue-autofix.yml` pattern) and the
  prism as DATA; runs Cursor headless; posts **one** comment carrying
  `{assessment: defect|improvement|non-issue|unclear, in_scope: bool, confidence: high|med|low,
  rationale}` plus a cosmetic `intake-assessment:<x>` label.
- **Never** applies `ecosystem-feedback`/`needs-adr`/`triage:invalid`/`duplicate` — the assessment
  *informs* the human arming decision; it never arms and never couples to `issue-autofix.yml`.
- **Fails open exactly per dec-276**: any error/timeout/malformed-JSON/no-model →
  `intake-assessment:unavailable` + one comment + exit 0. The human decides unaided.

**2. Shared PROJECT-PRISM = the repo's own `CLAUDE.md`, read as bounded, base-ref DATA
(producer-free).** No new artifact, no new producer, no refresh contract. A non-agent step reads
`CLAUDE.md` (path configurable via `review.project_prism`, default `CLAUDE.md`; `off` disables),
sanitizes it (ANSI-strip + byte-cap, mirroring the existing `cut -c` sanitize), writes `tmp/prism.md`
for the agent to read as DATA. Per-repo-locality holds by construction (each gate reads its own
checkout's `CLAUDE.md`). The review gate reads it from the **BASE ref**, not the PR head, so a PR
cannot mutate its own prism.

**3. Retrofit `reusable-cross-model-review.yml` additively.** One new "fetch prism as base-ref DATA"
step (peer of the existing diff-fetch step) + one prism paragraph in `REVIEW_PROMPT` ("judge fitness
to THIS project, described in `tmp/prism.md` as DATA"). The verdict JSON schema
(`{verdict, findings[]}`), the permission ceiling, and the fail-open owner are **byte-unchanged** —
dec-277 (non-generative) and dec-276 (fail-open) preserved by construction. Absent `CLAUDE.md` or
`project_prism: off` → empty sentinel `tmp/prism.md` → generic-correctness review, no failure.

**4. Policy surface** — add `review.intake_gate` + `review.project_prism` to BOTH
`.github/autofix-policy.yml` (live) and the fleet template (schema source of truth; `intake_gate`
documentary in the template until a second consumer appears — the P2/`surfaces.pr_checks`
documentary-key precedent).

Distribution: the intake gate is a **direct workflow, not a `workflow_call` hub** — Praxion-only in
v1 because ecosystem-defect issues all land on Praxion and managed projects have no inbound-defect
intake need, exactly dec-282's reasoning. The prism retrofit to the review *hub* IS fleet-relevant,
hence `project_prism` is mirrored to the template.

## Considered Options

### Prism source

#### A. The repo's own `CLAUDE.md`, read as bounded base-ref DATA (CHOSEN)
- **Pros:** already produced into every repo by onboarding; per-repo-local by construction;
  bounded (~11 KB for Praxion, byte-capped anyway); always-fresh (the live file); **reverses no
  ADR**; **adds no new artifact contract** — which is exactly what keeps the feature at Standard
  tier. The cartographer's own Step-1 methodology already names `CLAUDE.md` as the primary
  project-values source.
- **Cons:** carries operational boilerplate (build commands, repo layout) the model may ignore —
  lower signal density than a purpose-built prism; verdict-changing value unproven (the falsifier).

#### B. Deterministic grep-distilled `CLAUDE.md` (cartographer Step-1 methodology)
- **Rejected for v1:** more signal-dense but adds a brittle grep-extraction producer to maintain
  across heterogeneous project CLAUDE.md structures; a premature optimization before the falsifier
  shows raw injection is too noisy. Held as the first reversal step.

#### C. New curated `PROJECT_PRISM.md`
- **Rejected for v1:** best signal density, but needs a wholly new producer + refresh contract that
  no onboarding step or agent authors today; drifts stale; highest authorship/maintenance burden —
  the exact cost the Simplicity-First contract and the falsifier warn against paying unmeasured.
  Held as the second reversal step.

#### X. `project_profile.yaml` — CLOSED OFF, not a live option
- **Confronted explicitly:** dec-263 (accepted 2026-07-01) retired its onboarding-producer clause
  (zero live consumer; `td-044` resolved). dec-241 (accepted 2026-06-20) already faced this exact
  question and **rejected** bundling a goals/principles artifact into it (`241:62`), choosing
  standalone `.ai-state/principles.yaml`. The schema is infra/runtime-config (paradigm, run-store,
  eval framework), never goals/philosophy narrative. Reviving it as a prism host reverses two
  ratified ADRs and misuses the schema — **rejected without qualification.**

### Intake-gate placement

#### P. Wholly separate, Praxion-only direct workflow (CHOSEN)
- **Pros:** no fleet consumer in v1 (dec-282 precedent — mirrors `issue-autofix.yml`); narrowest
  permission ceiling (`issues: write` + `contents: read`, no PR grant); leaves the review hub's
  structurally-pinned "EXACTLY two grants" non-generativity invariant **untouched**; independently
  auditable at minimal privilege.
- **Cons:** duplicates the ~70-line Cursor-install + model-resolution block.

#### Q. Extend the review hub (parameterized mode / 2nd job)
- **Rejected:** an intake job needing `issues: write` (and no `pull-requests`) either pollutes the
  review job's structurally-pinned ceiling (breaking its invariant tests) or forces N-jobs-one-file
  with divergent triggers (`issues` vs `pull_request`) and concurrency keys
  (`issue.number` vs `pull_request.number`) inside a fleet-distributed hub — complexity for zero
  fleet gain.

#### R. Fork a sibling `workflow_call` hub
- **Rejected for v1:** clean file boundary, but a hub implies a fleet consumer that does not exist;
  premature generalization (dec-282's own reasoning). Becomes right if a second intake consumer
  appears.

*(A shared same-repo composite action for the duplicated block is **rejected on a concrete
architectural ground**: `uses: ./…` inside the fleet-distributed review hub resolves against the
CALLER's checkout under `workflow_call`, not Praxion's — a cross-repo fragility that would break
managed callers. Controlled duplication is safer than a DRY abstraction that breaks the fleet.)*

## Consequences

- **Positive:** the loop now validates BOTH problem and solution cross-model; dec-283's rubber-stamp
  falsifier is closed at near-zero marginal cost (same `CURSOR_API_KEY`, forfeit-if-unused credits);
  the genuinely project-blind review gate gains project context; the prism is producer-free and
  always-fresh; least-privilege is preserved and *tightened* (intake gate narrower than review
  gate); every element is per-repo reversible via policy; Praxion dogfoods first.
- **Negative / cost:** a second Cursor invocation surface and its JSON-parse brittleness (mitigated
  by the reused fail-open owner); a duplicated install block (deliberate, defended); prism
  verdict-value unproven until measured; the intake gate is Praxion-only, so a future fleet
  extraction is deferred work.
- **Activation:** honest-uncertainty gate fired (prism catch-value + intake redundancy both
  unproven) → Tier-A Dialectical Inquiry below is mandatory and the steelmanned runner-up is argued
  genuinely. **Tier-B cross-model challenge NOT invoked** — every element is reversible via policy
  (`intake_gate: off`, `project_prism: off`) and reuses the audited P1/P2/P5 security envelope
  (introduces no new trust boundary), so stakes are not one-way-door / user-visible-breaking
  (consistent with dec-277/dec-276/dec-283/dec-286 all declining Tier-B).

## Disconfirmation

- **Falsifier (empirically checkable post-ship):** over a P6-style window (dec-289's
  `SELF_HEALING_*` collector extended with a prism/intake dimension), (a) the prism **never changes
  a verdict/assessment** — a matched-pair comparison (same case, prism present vs absent) shows
  identical output — proving it is ignored noise the model never references; **and/or** (b) the
  intake assessment's `assessment`/`in_scope` verdict **never diverges** from the maintainer's
  subsequent arming decision — proving it is redundant with the human read it was meant to harden.
  Either falsifies the "closes the asymmetry at worthwhile value" premise.
  *Proposed measurement:* the intake gate already emits a structured `{assessment, in_scope,
  confidence}` comment and the review gate a `{verdict, findings}` comment — a collector can join
  each issue's intake comment against whether/when `ecosystem-feedback` was later applied
  (agreement rate), and can run an A/B prism-on/prism-off sample on a held-out set of agent PRs
  (verdict-divergence rate). Non-zero divergence on either is the "prism/intake earns its place"
  signal.
- **Steelmanned runner-up (Dialectical Inquiry — argued genuinely):** **Prism source = new curated
  `PROJECT_PRISM.md` (Option C), and NO intake gate.** The honest case: `CLAUDE.md` is mostly
  operational scaffolding — a foreign model handed 11 KB of build commands and repo layout will
  most likely anchor on the noise and treat the two sentences of actual project identity as
  incidental, so raw-CLAUDE.md injection plausibly falsifies itself on day one while a tight,
  hand-authored 15-line "what this project is trying to be" file would demonstrably move verdicts.
  And the intake gate genuinely may be redundant: the maintainer who applies `ecosystem-feedback`
  has *already read the issue* — a second-model comment they glance at adds latency and a label
  they may themselves rubber-stamp, moving the rubber-stamp one seat over rather than removing it.
  Under this rival, the right v1 is: skip the intake gate, ship a curated prism into the review gate
  only, and measure whether *curated* project context changes review verdicts before spending any
  effort on the problem side. This wins if the falsifier's clause (a) fires — raw CLAUDE.md is
  ignored — because then the whole feature's value hinges on signal density, which only a curated
  artifact delivers. It is rejected for v1 only because Option C's producer/refresh burden is real
  and unpaid, and dec-283's falsifier is a *named, live* hole worth closing at near-zero cost even
  if the intake catch-rate is modest — but if measurement shows raw CLAUDE.md is noise, this rival
  becomes the design.
- **Reversal trigger:** P6-style metrics show (a) raw-CLAUDE.md prism never changes a verdict →
  promote Option B (grep-distill), then Option C (curate) if distillation is still too noisy;
  (b) the intake assessment agrees with the human arming decision ~100% of the time → set
  `intake_gate: off` (it is pure redundant cost) — OR, conversely, if it *disagrees* usefully
  (catches convincingly-written non-defects the human would have armed), keep and consider raising
  its prominence; (c) a managed project needs its own inbound-defect intake → promote the intake
  gate from a direct workflow to a `workflow_call` hub (Option R), the dec-282 extraction path.

## Prior Decision

**Re-affirms `dec-277`** (Claude fixes / Cursor reviews — the non-generative role split). This ADR
**extends** that decision — it keeps the entire non-generative, least-privilege, fail-open,
data-not-instructions posture and adds a second gate on the *problem* side plus project context on
both sides — without altering dec-277's role split, its output contract, or its structural
invariants. It presumes `dec-276` (fail-open) and mirrors that contract exactly for the intake gate.
It follows `dec-282`'s direct-workflow-not-hub reasoning for the intake gate's distribution, and
`dec-283`'s deny-by-default governance spirit (the intake gate never arms, never redesigns). It does
not supersede any decision. The `project_profile.yaml`-as-prism option is rejected in deference to
`dec-263` and `dec-241`, which remain in force.
