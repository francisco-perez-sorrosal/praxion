---
id: dec-316
title: The formatter version is one decision, enforced, not two conventions
status: accepted
category: architectural
date: 2026-08-02
summary: Praxion and its managed projects pin ruff exactly in both pyproject and pre-commit, coupled by a blocking drift gate, because an unpinned local side makes the hook fight a different version on every machine.
tags: [tooling, formatter, pre-commit, fleet-baseline, gate-liveness, data-loss, td-110]
made_by: agent
agent_type: orchestrator
branch: main
pipeline_tier: standard
affected_files:
  - pyproject.toml
  - .pre-commit-config.yaml
  - claude/project-baseline/pre-commit-config.yaml
  - scripts/check_ruff_pin_drift.py
  - skills/onboard-project/SKILL.md
  - rules/swe/vcs/git-conventions.md
dissent: >
  Pinning the local side exactly makes every ruff upgrade a two-file coordinated
  change and will feel like friction on a routine bump; a floating `>=` with a
  periodically-refreshed hook rev would cost nothing day to day, and the argument
  against it rests on a failure mode most teams will never hit twice.
---

# The formatter version is one decision, enforced, not two conventions

## Context

Praxion's pre-commit hook pinned ruff `v0.8.6`. Nothing declared which ruff a
developer should run. The local side was not stale — it was **unpinned**, which
is a different and worse condition: the hook fought whatever each machine
happened to have. Observed simultaneously in one checkout: `0.15.4` on PATH,
`0.15.11` resolved by the `eval/` subpackage, `v0.8.6` in the hook.

Those versions disagree on assertion wrapping. The consequence is not a lint
error. It is a commit that will not settle: the hook rewrites a file, the
developer rewrites it back, `git add` never captures a stable state.

That loop is where the real damage lives. `pre-commit` stashes unstaged changes
before running hooks and restores them afterwards — *over* whatever the hooks
wrote. During the session that produced this decision, that restore silently
reverted two completed implementation steps while `git status` reported the
directory clean. The work was recovered only from `~/.cache/pre-commit/patch*`.
Twice more in the same session, commits reported success having written a subset
of what was staged.

The same `v0.8.6` pin ships to every managed project in
`claude/project-baseline/pre-commit-config.yaml`, so the fleet inherits it.

## Decision

The formatter version is **one decision, mechanically enforced**:

- `pyproject.toml` declares `ruff==0.15.22` — exact, in the `dev` group.
- Both pre-commit configs (Praxion's and the shipped baseline) pin `rev: v0.15.22`.
- `scripts/check_ruff_pin_drift.py` **blocks** a commit when the pinned rev, the
  declared dependency, or the installed ruff disagree. It runs *before* the ruff
  hooks, so the mismatch is named rather than presenting as a formatter that
  cannot make up its mind.
- Managed projects receive the same pin, the coupling instruction at the exact
  site someone would bump it, and the drift check in `/onboard-project`'s commit
  gate.

`==` and not `>=`: a floating constraint cannot guarantee the equality the gate
exists to enforce, and would leave the identical defect wearing a looser mask.
The gate therefore reads a floating constraint as *no pin at all*.

**Version choice is `0.15.22`, not the newer `0.16.1`, on scope rather than
caution.** Measured here, `0.16` scans a different file set entirely — 1255
files against 310 — so adopting it would smuggle a silent scope change in under
a formatting bump. That evaluation is owed separately.

**Resolution order is project-environment-first, PATH second.** In a uv-managed
project the ruff a developer runs is the one the project provides; comparing
against an unrelated global binary would fail someone doing everything right,
and a gate that punishes correct behaviour gets bypassed — a bypassed gate
protects nothing.

**Absent inputs are never drift.** A repository with no ruff hook, or one that
has not adopted the dependency pin, is out of scope rather than broken. This
ships fleet-wide to projects whose stacks differ.

## Considered Options

### Option A — Bump the hook rev only (rejected)

The obvious reading of "the pin is stale". Rejected because it fixes today and
re-breaks on the next release: with the local side still undeclared, the hook
resumes fighting an arbitrary version the moment anyone upgrades. It treats the
instance and leaves the class.

### Option B — Freeze the local side down to v0.8.6 (rejected)

Zero reformat, loop ends immediately. Rejected because it freezes the fleet on a
linter roughly a year behind and hands every new managed project a stale
toolchain that will feel broken. The churn avoided is paid back with interest at
the first bump anyone dares attempt.

### Option C — Warn instead of block (rejected)

Kinder to a contributor mid-upgrade. Rejected as the precise defect this
codebase has been closing elsewhere: a computed value with no reader. A warning
nobody is obliged to act on is how the drift persisted long enough to destroy
work in the first place.

### Option D — Convention only, no gate (rejected)

Document "keep these in sync" and trust it. Rejected because the failure is
silent and delayed — nobody discovers the mismatch until a commit refuses to
settle, at which point the stash/restore has already had opportunities to eat
uncommitted work.

## Consequences

**Positive.**

- The loop cannot recur silently; divergence is caught at the commit that
  introduces it, naming both versions and the fix.
- Managed projects stop inheriting a stale pin, and inherit the coupling with it.
- The hazard class — git operations routine on a clean tree and destructive on a
  dirty one — is documented where the stash rule already lives.
- Adoption surfaced 129 lint findings that had accumulated invisibly, because
  the gate lints staged files only. All were resolved rather than configured
  away.

**Negative / accepted.**

- Every ruff upgrade is now a coordinated two-file change plus a reinstall. This
  is real friction, deliberately chosen over silent divergence.
- A one-time 129-file reformat, landed isolated so it does not bury a real change
  in review — at the cost of `git blame` noise across those lines.
- A contributor whose environment drifts is blocked until they align it. The
  message names the fix; the sanctioned emergency escape remains `--no-verify`.
- The `0.16` scope change is deferred, not evaluated.

## Disconfirmation

**Falsifier.** If the gate fires repeatedly on developers who are correctly
using the project environment — i.e. the environment-first resolution proves
insufficient in a setup not anticipated here (pipx, a system package manager, a
container without `.venv`) — then blocking is wrong for the fleet even if it is
right for Praxion, and the managed-project half should degrade to advisory while
Praxion's own stays blocking. Two independent reports of that shape falsify the
uniform-blocking choice.

**Steelmanned runner-up.** Option A (bump the rev, leave the local side floating)
is stronger than its rejection suggests. Most projects never notice formatter
skew, because most contributors install tooling once from the same lockfile and
never diverge. Against that population, the exact pin is pure friction and the
gate is pure ceremony — and the failure it prevents is one this repository hit
only because long agent sessions retry commits far more often than a human does.
If the drift gate turns out to fire only ever on Praxion's own automation and
never on a human, Option A was the proportionate answer and this is
over-engineering.

**Reversal trigger.** Revisit when any of: (a) ruff stabilises its formatter
across minor versions such that skew stops producing disagreement; (b) pre-commit
changes its stash/restore so a hook rewrite is no longer clobbered by the
restore, removing the data-loss half of the argument; (c) the fleet adopts a
single lockfile-managed toolchain install, making the dependency pin the only
pin and the hook rev derivable from it; or (d) the falsifier above fires.

## Prior Decision

None superseded. This is the first decision to treat formatter versioning as an
enforced invariant rather than a convention; `td-110` recorded the hazard and is
closed by it.
