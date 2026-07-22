---
id: dec-draft-85e6d0dc
title: workflow_run-triggered Claude autofixer opens fix PRs, never pushes to main
status: accepted
category: architectural
date: 2026-07-22
summary: Praxion's shipped CI autofixer reacts to workflow_run failures on main, diagnoses from sanitized logs read as data, and opens a ci-autofix/ fix PR (never a direct push), with layered loop prevention and a sensitive-path tripwire.
tags: [ci-cd, autofix, github-actions, workflow-run, security, prompt-injection, self-healing-loop, claude-code-action, budget-cap]
made_by: agent
agent_type: orchestrator
branch: main
pipeline_tier: direct
affected_files:
  - .github/workflows/ci-autofix.yml
dissent: "workflow_run's decoupled payload forces a second fetch for PR/run context that pull_request_target would supply inline — accepted for the privilege-separation win and the fork-PR blast-radius reduction."
---

## Context

Praxion shipped a first-iteration CI autofixer (`.github/workflows/ci-autofix.yml`) as
the seed of the self-healing loop (brief `self-healing-loop-implementation-brief.md`
§1). It was committed before this ADR existed; this is a backfill that records the
load-bearing decisions embodied in the workflow and the P0 hardening applied on
2026-07-22. The design sits on a privileged surface — an agent with `contents: write`
and `pull-requests: write` reacting to CI failures — so its trigger choice, its
loop-prevention layering, and its prompt-injection posture are all architectural.

At authoring time the workflow carried a "KNOWN UNVERIFIED ASSUMPTION" that
`claude-code-action` accepts `workflow_run`. P0 verified this against raw source at the
exact pinned SHA (`51ea8ea`): `src/github/context.ts` lists `workflow_run` in
`AUTOMATION_EVENT_NAMES` with a real `case` handler; `push` is absent (hence its hard
error). The assumption is resolved in our favor — no `repository_dispatch` bridge is
needed.

## Decision

React to `workflow_run` failures of the watched workflows (`Test`, `Architecture`) on
`main`; have Claude (Opus, SHA-pinned `claude-code-action@51ea8ea`) diagnose the root
cause from **sanitized failure logs read as data** and open a `ci-autofix/<slug>` **pull
request** — never a direct push to `main`, never a modification of unrelated files. A
transient flake yields a GitHub issue instead of a PR. Loop prevention is **layered**,
not single-mechanism:

1. the workflow is excluded from its own `workflows:` watch list;
2. `if:` gates on `conclusion == 'failure'` **and** `head_branch == 'main'` (fix-PR runs
   have `head_branch = ci-autofix/*`, so the workflow never reacts to its own output);
3. an open-PR dedup step skips diagnosis when a `ci-autofix/` PR is already open;
4. `concurrency: ci-autofix` serializes runs so two agents never race;
5. **(P0 hardening)** a daily run-budget cap (`max_runs_per_day`, hardcoded 5 at P0,
   policy-sourced at P1) bounds the fix→fail-differently spend loop.

A sensitive-path tripwire converts any PR touching `.github/`, `scripts/`, or `hooks/`
to a draft with a prominent human-review warning. `track_progress` is never set
(claude-code-action bug #860 silently grants all write tools). Status is posted by plain
`gh` steps, not the action's tracking comments.

## Considered Options

### A. `workflow_run` failure → diagnose → open fix PR (chosen)
- **Pros:** `workflow_run` runs in the base-repo context with the base secrets, and
  GitHub explicitly recommends it over `pull_request_target` for privilege separation;
  the PR routes every fix back through `Test`/`Architecture` and a human merge gate;
  never touching `main` directly makes a wrong fix a reviewable artifact, not an outage.
- **Cons:** the `workflow_run` payload is decoupled from PR/run detail, so the agent must
  re-fetch run metadata (`gh run view`) — a second hop `pull_request_target` avoids.

### B. `pull_request_target` reacting to check failures
- **Pros:** richer PR context inline; one event.
- **Cons:** the canonical privileged-trigger footgun — untrusted fork head code one
  mis-checkout away from base secrets; GitHub's own guidance prefers `workflow_run`.
  Rejected. (`pull_request_target` is banned project-wide for this loop.)

### C. Direct commit to `main` on failure
- **Pros:** fastest path to green.
- **Cons:** a direct commit re-triggers the failing workflow, and a wrong "fix" loops
  indefinitely; no CI validation of the fix; no human gate. Rejected outright.

### D. `push` + `repository_dispatch` bridge
- **Pros:** works even if `workflow_run` were unsupported.
- **Cons:** unnecessary — P0 verified `workflow_run` is natively supported at the pinned
  SHA. Rejected as the primary design; retained only as a documented fallback in the
  workflow comment for a hypothetical future action version that drops the event.

## Consequences

- **Positive:** every automated fix is an independently CI-validated, human-mergeable PR;
  the privileged surface is minimized (least-privilege job permissions, SHA-pinned
  action, no `track_progress`); CI-log injection is contained by the non-agent
  fetch-and-sanitize step feeding the agent data, not instructions; the budget cap makes
  runaway spend a bounded, visible stop.
- **Negative / cost:** the agent must re-fetch run/PR context (extra `gh` calls); the
  daily cap can silently suppress a legitimate late-in-day failure (surfaced via
  `::notice::`, acceptable for a guardrail); the whole surface adds one more privileged
  workflow to audit.
- **Forward links:** this fixer is caller #1 of the hub `reusable-ci-autofix.yml` (P1);
  every `ci-autofix/` PR it opens will be reviewed by the cross-model gate (P2,
  `reusable-cross-model-review.yml`) before human merge — the fixer authors, a
  non-Anthropic model reviews.

## Disconfirmation

- **Falsifier:** a future `claude-code-action` version silently drops `workflow_run`
  support (re-run the P0 raw-source event check on every SHA bump), **or** the fix PRs
  prove net-negative over P6's 60–90-day window (agent noise / rebase churn outweighs
  time-to-green wins, gate catch-rate ≈ 0).
- **Steelmanned runner-up:** a `pull_request_target`-based reactor supplies PR + diff
  context in a single privileged event, removing the re-fetch hop and enabling
  same-run inline review — it wins *if* the two-hop `workflow_run` context-fetch proves
  materially lossy for diagnosis **and** fork-PR blast radius is mitigated by other means
  (e.g. an allowlist of trusted actors). The evidence today favors privilege separation.
- **Reversal trigger:** `claude-code-action` ships a first-class "on check-suite failure"
  trigger for the GitHub App that runs less-privileged than `workflow_run`, or GitHub
  removes the base-secret exposure that motivates the `workflow_run` preference.
