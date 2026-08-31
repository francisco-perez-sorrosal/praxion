---
id: dec-286
title: P3a CI-autofix extends to PR/Dependabot surfaces via N-jobs seam, fix-commit-to-PR-branch under P5 containment, commit-trailer attempt cap
status: accepted
category: architectural
date: 2026-07-25
summary: The main-only CI autofix hub gains PR-check and Dependabot fix-commit surfaces as new jobs (main job byte-unchanged); fixes commit to the PR's own branch under P5's structural no-git-reach containment; a commit-trailer attempt counter, an autofix:declined terminal label, per-branch concurrency, and a probe-main gate bound the loop; unfixable failures escalate without committing.
tags: [ci-cd, autofix, github-actions, workflow-run, self-healing-loop, dependabot, pr-checks, loop-prevention, security, prompt-injection, least-privilege, additive]
made_by: agent
agent_type: systems-architect
branch: worktree-pr-dependabot-autofix
pipeline_tier: standard
affected_files:
  - .github/workflows/reusable-ci-autofix.yml
  - .github/autofix-policy.yml
  - tests/test_ci_autofix_hub_contract.py
affected_reqs: [REQ-01, REQ-02, REQ-03, REQ-04, REQ-05, REQ-06, REQ-07, REQ-09, REQ-10, REQ-11, REQ-12, REQ-13, REQ-14]
re_affirms: dec-273
dissent: A single surface-aware job with computed conditionals (A1) would be DRYer and keep one hub abstraction; the N-jobs choice trades some boilerplate for a structural — not merely tested — no-regression guarantee, and that guarantee is the whole point of the additive constraint.
---

## Context

`reusable-ci-autofix.yml` is the fleet-distributed hub (`dec-273`) that today reacts only to
default-branch CI failures: its single `autofix` job gates on
`head_branch == default_branch`, and the policy reader consumes only `surfaces.main_branch`. The
`autofix-policy.yml` schema already reserves `pr_checks`, `dependabot`, `fork_prs`, and
`max_attempts_per_pr` as P3 fields "not yet read by the hub." P3a activates the first two same-repo
surfaces (fork is a separate trust boundary — see `dec-285`) **additively: the existing
main-branch fix-PR path must not regress.**

The per-repo caller (`ci-autofix.yml`) already fires on `workflow_run: [Test, Architecture] completed`
for **every** branch — the hub's job `if:` is the *only* thing filtering PR/Dependabot runs today — so
the extension is hub-only and Praxion (caller #1) dogfoods it automatically; the caller's existing
`permissions:` ceiling already accommodates the new jobs.

A fix commit on a PR's own branch re-triggers that PR's CI, which fires this same `workflow_run` chain
again — an **unbounded loop by construction** unless capped. The `ci-autofix/*`-branch-prefix dedup that
bounds the main path does not transfer (the fix lands on the PR's existing branch, not a new one). And
untrusted text (Dependabot metadata, CI logs) must never reach the agent's instruction channel.

Activation: fired — signals: stakes(security) + honest-uncertainty (≥2 plausible paths per axis);
lens set = Developer, Test, Operations, Security, Simplicity, Testability; convergence = stable.
Tier-B cross-model challenge considered and **declined**: the decision reuses the audited P1/P5 security
envelope, is reversible per-surface via policy (`off`), and invents no new trust boundary (fork stays
suggest-only in the sibling ADR) — Tier-A Dialectical Inquiry (below) is sufficient.

## Decision

1. **Seam = N-jobs-one-file (A2).** Leave the `autofix` job **byte-identical**; add `classify`
   (reads policy + `github.event` once, emits `surface` + per-surface outputs), `autofix-same-repo-pr`
   (handles both `pr_checks` and `dependabot` — Dependabot branches are same-repo), and (in the sibling
   ADR) `autofix-fork`. The no-regression guarantee is **structural**: the untouched main job's `if:`
   already excludes every new surface.
2. **Fix-commit privilege = P5's structural containment**, not P1's current main allowlist. A non-agent
   step checks out the PR head at its exact `head_sha`; the agent's allowlist has **no**
   `git checkout`/`git branch`/`git push` and no `gh pr merge`; a non-agent step pushes
   `git push origin HEAD:<head-branch>` **without `--force`** and treats any rejection (non-fast-forward
   *or* permission/read-only) as skip-and-flag. Committing to the default branch is structurally
   impossible; the Dependabot read-only-token edge fails closed reactively (no proactive detection
   exists — the predictor is undocumented [U]).
3. **Loop prevention = layered.** Primary breaker: an `Autofix-Attempt: N` **commit trailer** stamped by
   the non-agent commit step (never the agent, so it can't be missed) and read by a pre-agent gate;
   `>= max_attempts_per_pr` → decline. Terminal state: an `autofix:declined` label (checked by the
   idempotency gate) stops re-arming for unfixable/capped PRs. Backstops: per-branch concurrency
   (`group: ci-autofix-${{ github.event.workflow_run.head_branch }}`) + the per-surface daily budget.
   Dependabot adds a **probe-main gate** (decline if the default branch's latest run of the same
   workflow is also failing) and **deny-by-default unfixable classification** (post root-cause comment +
   `autofix:declined`, no commit). fix-COMMIT never merges; `@dependabot merge` does not exist and
   `@dependabot rebase` is deferred (its behavior is [U]; not made load-bearing).

## Considered Options

### Seam — A1: one job, per-surface computed conditionals
- Pros: DRYest; single hub abstraction.
- Cons: the main path's `if:`/prompt/allowlist become surface-conditional, making "main byte-stable,
  un-regressed" **un-provable**; a classifier bug risks main-branch prompt text leaking into a PR run.

### Seam — A2: one hub file, N jobs (CHOSEN)
- Pros: no-regression is structural (main job untouched); per-job least-privilege; each surface
  independently auditable; all surfaces arrive through the one existing trigger (no caller change).
- Cons: duplicated setup boilerplate (mitigated by `classify`); more jobs to read.

### Seam — A3: separate reusable-workflow files per surface
- Pros: cleanest file-level boundary, matching `issue-autofix.yml` vs `reusable-ci-autofix.yml`.
- Cons: every surface would need its own caller wrapper + `workflow_run` trigger, yet all fire on the
  same completion event — multiplies caller wiring and P3b's fleet-distribution surface for no gain.

### Attempt counter — B2 PR label / B3 external state (rejected)
- B2 needs pre-created numbered label sets and is clunky; B3 introduces external state to manage/commit,
  inconsistent with the codebase's git-native dedup mechanisms. B1 (commit-trailer) needs neither.

### Concurrency — shared `ci-autofix` group (runner-up)
- Strictly byte-stable but serializes all surfaces repo-wide; per-branch group is behavior-identical for
  main while letting different PRs fix in parallel.

## Consequences

**Positive:** additive with a machine-checkable no-regression proof (existing invariant suite stays
green); the whole same-repo fix-commit security envelope lives in one job (a control can't be applied to
one surface and forgotten on another); loop is bounded by state that travels with the PR; no new
dependency, no version bump, no caller change; Praxion dogfoods immediately.

**Negative / costs:** duplicated per-job setup; the budget now aggregates across surfaces (may need
`max_runs_per_day` bumped); one new operator prerequisite (`autofix:declined` label, degrades
gracefully); the concurrency group string changes (behavior-preserving deviation from strict
byte-stability — see D3 in `SYSTEMS_PLAN.md`).

## Disconfirmation

- **Falsifier:** if the live #35–38 dogfood shows the main-branch fix-PR path behaving differently than
  before P3a, or shows a fix-commit loop that the attempt-counter/`autofix:declined`/concurrency layers
  fail to bound, the "additive + bounded" premise is wrong and the seam or loop-prevention model must be
  reworked.
- **Steelmanned runner-up (Dialectical Inquiry):** A1 (one surface-aware job) is genuinely attractive —
  it keeps a single hub abstraction, avoids ~45 lines of duplicated setup, and GitHub Actions'
  `if:`-per-step is a first-class idiom, so "computed conditionals" is not inherently a smell. If the
  main path were *also* being rewritten this pass, A1's shared-step reuse would dominate. The deciding
  factor is narrow but decisive: the binding constraint is *proving* the main path did not change, and
  only leaving it literally untouched makes that proof structural rather than test-coverage-dependent —
  so A2 wins **for this pass**, and A1 would be the right answer for a future pass that legitimately
  reworks the main path.
- **Reversal trigger:** if a future change reworks the main-branch path anyway (dissolving the
  byte-stability constraint), or if the N-jobs boilerplate becomes a maintenance burden across 4+
  surfaces, revisit and consolidate toward A1. If per-branch concurrency ever causes a correctness
  surprise, fall back to the shared `ci-autofix` group.

## Prior Decision

Re-affirms `dec-273` (hub reusable-workflow distribution): this extension keeps all security-critical
logic centralized in the one audited hub and changes only WHICH surfaces the hub reacts to — it does not
alter the distribution model. Fleet rollout of these surfaces (templates + onboarding wiring) is
deferred to P3b, consistent with `dec-278`/`dec-274`.
