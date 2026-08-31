---
id: dec-290
title: Normalize every non-fix fixer terminal state to an idempotent decline
status: accepted
category: behavioral
date: 2026-07-28
summary: continue-on-error on the fixer agent step plus a non-agent finalize step converts crash/timeout/ambiguous-exit into a clean autofix:declined decline that exits 0
tags: [ci, self-healing, autofix, idempotency, dependabot]
made_by: agent
agent_type: systems-architect
branch: worktree-autofix-fixer-hardening
pipeline_tier: standard
affected_files:
  - .github/workflows/reusable-ci-autofix.yml
  - tests/test_ci_autofix_hub_contract.py
dissent: A masked agent crash surfaces as a green "declined" job, not a red X — an operator watching for red misses a genuine infra failure.
---

## Context

The `autofix-same-repo-pr` job in `reusable-ci-autofix.yml` fix-commits to same-repo human and Dependabot PR branches. Its decline path assumes the fixer agent either commits a fix or explicitly declines (posts a root-cause comment + applies the `autofix:declined` label). A live dogfood (Dependabot PR #48, run 30331896966, 2026-07-28) hit a third, unhandled terminal state: the agent step exited non-zero on `--max-turns 30` exhaustion (`subtype: error_max_turns`, `num_turns 31`). With no `always()` on the downstream steps, the job crashed red having applied **no label and posted no comment** — leaving the PR stranded, and defeating the declined-label idempotency gate (line ~543), so a re-trigger would spend another 30 turns from scratch.

The steps after the agent were guarded `if: steps.budget.outputs.proceed == 'true'` (implicit `success()`), so a failed agent step skips the push step and fails the job before the label is ever written.

## Decision

Make **every** non-fix terminal state of the fixer converge to a single idempotent decline:

1. Add `continue-on-error: true` to the fixer agent step so its non-zero exit records `steps.fixer.outcome == 'failure'` without failing the job (`steps.fixer.conclusion` becomes `success`).
2. Add one **non-agent** `run:` step, `Finalize terminal state (decline if no fix)`, guarded `if: always() && steps.budget.outputs.proceed == 'true'`, placed after the existing stamp-and-push step. Decision tree, using only GitHub-native / single-read signals:
   - HEAD advanced past the recorded `pre_agent_head` → a fix exists → the push step owns it → no-op.
   - `autofix:declined` already present (agent self-declined or a prior run) → idempotent no-op. Read fails **closed** on a `gh` error (skip, do not blind-write).
   - Otherwise (no fix, no label — crash, timeout, or an ambiguous exit-0-with-nothing) → post a bounded, fixed-template root-cause comment (naming the abnormal exit when `steps.fixer.outcome == 'failure'`), apply `autofix:declined`, exit 0.

The job then exits 0 on a clean decline, and the existing gate suppresses any re-trigger cheaply before the agent runs. Scope is confined to `autofix-same-repo-pr`; the main `autofix` job (opens a fresh PR, no declined-label idempotency gate, self-limited by the daily budget) and the suggest-only `autofix-fork` job are unchanged.

## Considered Options

### Option 1 — `continue-on-error` + non-agent finalize step (chosen)

- Pros: GitHub-native failure capture; `steps.fixer.outcome` is a reliable crash signal independent of the action's private output schema; reuses in-job context (`pre_agent_head`, PR number); one line + one step; declining on *ambiguous success* hardens beyond the one observed crash.
- Cons: the push step also runs on the crash path (harmless — already no-ops on no-commit); a real crash now reads as a decline rather than a red job.

### Option 2 — a separate `if: failure()` dependent job

- Pros: keeps the fixer job's red status honest.
- Cons: loses in-job `steps.fixer.outcome`/HEAD/pre-agent context; must re-resolve the PR and re-checkout; more surface for less clarity.

### Option 3 — shell-trap the agent (`|| true`)

- Rejected: the fixer is a `uses:` action, not a `run:` step — there is no shell to trap its exit.

## Consequences

- Positive: no PR is left stranded; idempotency holds across re-triggers (the declined label gates the gate); any future degenerate terminal state (not just `error_max_turns`) also converges to a clean decline; blast radius is one line + one non-agent step; trivial revert.
- Positive: preserves every existing safety control — no push to the default branch, no auto-merge, sensitive-path tripwire still fires, agent allowlist unchanged, privilege ceiling unchanged, `allowed_bots: dependabot[bot]` unchanged.
- Negative: a green autofix job can now mean "declined," so operators must read the comment/label to distinguish "fixed" from "declined." Mitigated by the queryable label and the comment body; daily-budget/attempt-cap telemetry still records spend.
- Negative: benign double-comment possible if the agent commented but failed to label; the label write makes the next run idempotent regardless.

## Disconfirmation

- **Falsifier**: a live dogfood where, after this change, a max-turns exhaustion still leaves the job red, or leaves the PR without an `autofix:declined` label, or a re-trigger spends a second agent run — any of these disproves the decision.
- **Steelmanned runner-up**: Option 2 (separate `if: failure()` job) keeps the fixer job's red status truthful, which matters if operators rely on red X's as the primary "a human must look" signal; a green-on-decline job could let a systematic agent-infra failure hide. The counter is that the declined label + comment is a *better* signal than a bare red X (it is deduped and carries a root cause), and the daily-budget telemetry still exposes repeated declines.
- **Reversal trigger**: if post-ship observation shows operators routinely miss agent-infra failures because the job is green, revisit — either emit a distinct label (`autofix:errored` vs `autofix:declined`) or fail the job while still writing the label.

## Prior Decision

Re-affirms the intent of dec-281 (label application as the arming/idempotency gate) and dec-286 (single fix-commit job owns the security envelope) without superseding either — this ADR closes an unhandled terminal state those decisions did not enumerate.
