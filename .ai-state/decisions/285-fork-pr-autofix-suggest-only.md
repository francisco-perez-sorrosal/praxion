---
id: dec-285
title: Fork-PR CI autofix is suggest-only with inverted privilege — never a commit to an untrusted head
status: accepted
category: architectural
date: 2026-07-25
summary: The fork_prs surface posts a suggested-patch comment and never commits; its job holds contents:read (no write), pull_request_target stays banned, and any fork-file inspection uses a base-at-root + isolated pr-head checkout the agent may read but never execute.
tags: [ci-cd, autofix, github-actions, workflow-run, fork-prs, trust-boundary, suggest-only, inverted-privilege, security, prompt-injection, self-healing-loop]
made_by: agent
agent_type: systems-architect
branch: worktree-pr-dependabot-autofix
pipeline_tier: standard
affected_files:
  - .github/workflows/reusable-ci-autofix.yml
  - .github/autofix-policy.yml
  - tests/test_ci_autofix_hub_invariants.py
affected_reqs: [REQ-08, REQ-10, REQ-11]
re_affirms: dec-277
dissent: A fix-commit-to-fork-head surface (with the contributor's maintainer-edit opt-in) would close the loop for forks too; it is rejected because writing to an untrusted head from a privileged workflow_run context is exactly the pwn-request pattern GitHub's Security Lab warns against, and the residual risk dwarfs the convenience.
---

## Context

Fork PRs originate from untrusted repositories. A `workflow_run` workflow chained off a fork PR's CI run
executes with the base repo's **full** read-write token and secrets (RESEARCH_FINDINGS Q1 [V]) — which
is exactly why checking out and acting on untrusted fork content from that context is dangerous. GitHub's
Security Lab documents `pull_request_target` + untrusted checkout as a repository-compromise vector and
prescribes the untrusted-`pull_request` → privileged-`workflow_run` two-workflow split this hub already
uses. The `fork_prs` policy surface defaults to `suggest`.

Fork PR branches live in the fork, so `github.event.workflow_run.pull_requests[]` is empty for them
(RESEARCH_FINDINGS Q4 [S]) — the PR number must be resolved another way.

Activation: fired — signals: stakes(security) + honest-uncertainty; lens set = Developer, Test,
Operations, Security, Simplicity, Testability; convergence = stable. Tier-B considered and declined
(reuses the P2 inverted-privilege pattern; reversible via policy `off`).

## Decision

The `autofix-fork` job is **suggest-only** and runs with **inverted privilege** — `contents: read`
(NO write) + `pull-requests: write` + `actions: read` + `id-token: write`, mirroring the P2 reviewer
(`dec-277`). It resolves the PR number via `gh api /repos/{repo}/commits/{head_sha}/pulls`, fetches and
sanitizes the failure logs in a non-agent step, and — only when a concrete patch requires reading fork
files — checks out the fork head into an isolated `path: pr-head` subdirectory with the base repo at the
workspace root. The agent's allowlist is **read-only**: `Read`/`Glob`/`Grep` + `gh pr comment` only, no
`Edit`/`Write`, no git, no Bash-exec; `--add-dir pr-head` grants read access, never execution. The agent
posts a suggested patch as a PR comment and **never commits, never merges, never `cd`/executes anything
from `pr-head`**. `pull_request_target` stays banned.

## Considered Options

### Suggest-only, inverted privilege (CHOSEN)
- Pros: no write to untrusted heads; the privileged job holds no `contents: write`, so even a
  compromised agent step cannot alter the base repo; contributors still get actionable guidance; reuses
  the audited P2 reviewer privilege profile.
- Cons: a human must apply the suggestion (the fork loop is not auto-closed).

### Fix-commit to the fork head (rejected)
- Pros: closes the loop for forks too.
- Cons: writing to an untrusted head from a full-token `workflow_run` context is the pwn-request pattern;
  requires `contents: write` the job otherwise never needs; residual compromise risk dwarfs the
  convenience.

### Log-only comment, no fork checkout (simpler variant)
- Pros: zero fork content touched at all.
- Cons: cannot produce a concrete patch when the fix needs to reference fork files. Resolution: prefer
  log-only, escalate to the isolated read-only `pr-head` checkout only when a concrete patch needs it.

## Consequences

**Positive:** the strongest trust-boundary posture (no write path to untrusted code); reuses a proven
privilege profile; the suggested-patch comment is human-reviewed by construction, so no tripwire is
needed for forks.

**Negative / costs:** fork PRs are not auto-fixed (by design); PR-number resolution needs the extra
`gh api commits/.../pulls` call; the isolated-checkout recipe adds a read-only-but-careful step whose
safety rests on the allowlist truly excluding all execution of `pr-head`.

## Disconfirmation

- **Falsifier:** if a fork-PR autofix run is ever observed executing code from `pr-head` or the fork job
  is ever found holding `contents: write`, the containment premise is broken and the surface must be
  disabled until re-hardened.
- **Steelmanned runner-up (Dialectical Inquiry):** the fix-commit-to-fork-head option is not absurd —
  GitHub's maintainer-can-edit default already lets base maintainers push to a fork PR head, so "the base
  repo writing to the fork head" is a sanctioned operation in principle, and doing it from a
  contents:write job would genuinely close the fork loop. The reason it still loses: the *agent*
  producing that write is driven by untrusted fork content read as data, and the blast radius of a single
  injection success (arbitrary commit to a branch that a maintainer may fast-merge) is unbounded compared
  to a comment. The asymmetry of consequences — not the mechanism's legitimacy — decides it.
- **Reversal trigger:** if a future GitHub primitive lets a job write *only* to a specific fork PR head
  under a scoped, non-secret token (eliminating the full-token exposure), revisit fix-commit-to-fork.
  Absent that, suggest-only stands.

## Prior Decision

Re-affirms `dec-277` (Claude fixes / Cursor reviews — the inverted-privilege, non-generative gate): the
fork surface adopts the same "privileged context, deliberately no write-code permission" profile,
applied here to a suggest-only fixer rather than a review gate.
