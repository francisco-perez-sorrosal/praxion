---
id: dec-draft-c66a19a6
title: Git-hook install observes the repository's hook configuration and composes with it, taking over core.hooksPath locally rather than integrating through a tracked file
status: proposed
category: architectural
date: 2026-09-02
summary: A new scripts/install_git_hooks.py becomes the single hook-install/repair implementation, with onboarding Phase 4 and upgrade_project_pins.sh as callers. It honours core.hooksPath by installing a wrapper directory in the git common dir that delegates to the observed value, and chains with an occupied .git/hooks slot instead of displacing it. Exit codes propagate for pre-commit and are swallowed for post-hooks.
tags: [git-hooks, hooks-path, husky, lefthook, pre-commit-framework, onboarding, upgrade, team-repo, chaining]
made_by: agent
agent_type: systems-architect
branch: worktree-sidecar-placement
pipeline_tier: full
affected_files:
  - scripts/install_git_hooks.py
  - scripts/assets/praxion-hook-wrapper.sh.tmpl
  - scripts/upgrade_project_pins.sh
  - skills/onboard-project/references/phases-core.md
  - skills/onboard-project/references/detection.md
  - docs/onboarding.md
dissent: "Silently taking ownership of core.hooksPath is a repository-level configuration takeover the team never consented to, and although it is per-clone and invisible to them, it means any teammate debugging why husky reports a path it did not set will find Praxion's fingerprints in a repository that is supposed to be Praxion-agnostic - the exact property the whole design is built to preserve."
---

## Context

Praxion's hook install has two verified defects, both invisible from inside the
install and both fatal on precisely the repositories this work targets.

**No `core.hooksPath` awareness.** An exhaustive grep across `*.py`, `*.sh` and
`*.md` returns zero matches for `core.hooksPath`. Phase 4's predicate reads
`readlink .git/hooks/<name>` and nothing else. If a repository has already
redirected `core.hooksPath` — the mechanism husky and lefthook use, and one
common `pre-commit`-framework configuration — Praxion installs into a directory
git never consults. Onboarding reports success, the files exist, they are
executable, and no hook ever fires. Neither the install nor a subsequent
`/sentinel` audit checks the value, so the failure is silent in both directions.

**No composition with an occupied slot.** Phase 4's conflict handling is binary:
back the existing hook up to `<name>.pre-praxion` and warn. A team already
running `pre-commit`-framework hooks has its gate **displaced** — moved aside and
left inert — rather than composed with. That is a worse outcome than not
installing at all, because the team's gate silently stops running.

Both are independent of the sidecar work and affect every team-repo onboarding
today. They become load-bearing under sidecar placement, where the local hook
chain is Praxion's *only* enforcement surface in the project repository.

`dec-355` established that reconciliation logic belongs in the script layer under
test, with commands and skills as thin callers. This decision applies that
directly.

## Decision

A new `scripts/install_git_hooks.py` becomes the single implementation of
"install, heal, report on, or remove Praxion's git hooks in this repository".
Onboarding Phase 4 and `upgrade_project_pins.sh` become callers; neither keeps
its own copy of the logic.

**It observes before it writes.** Two orthogonal observations drive a small,
enumerated state machine:

- `core.hooksPath` is `Unset`, a `PraxionWrapper`, a `Foreign` directory, or
  `Unresolvable`.
- Each hook slot is `Absent`, a `PraxionSymlink`, a `PraxionWrapperFile`, or
  `ForeignOccupied`.

**Actions:**

1. `Unset` with an empty slot — install today's symlink or inline script.
   Byte-identical to current behaviour, which is the point: the ~all projects
   that have no hook manager see no diff.
2. `Unset` with an occupied slot — preserve the occupant at
   `<name>.pre-praxion` (never overwriting an existing backup) and install a
   **wrapper file** that runs the occupant first and Praxion's step second.
3. `Foreign(d)` — create `<git-common-dir>/praxion-hooks/`, record `d` as the
   delegate, install wrappers there, and set `core.hooksPath` to the wrapper
   directory. The wrapper directory lives in the **common** directory because
   `core.hooksPath` is repo-local config shared by every worktree.
4. `PraxionWrapper` — refresh wrapper bodies; change no configuration.
5. `Unresolvable` — refuse, warn once naming the observed value, write nothing.

**Exit-code policy is per hook class, not global.** For `pre-commit` the
delegate runs **first** and its non-zero exit aborts the commit with its own
code, without running Praxion's gates: the team's gate stays authoritative and
its failure can never be masked. For `post-merge` / `post-commit` /
`post-checkout` the delegate's failure is reported and the chain continues,
exiting 0 — preserving `finalize_chain.sh`'s established non-blocking contract,
which exists because a hook cannot abort a completed git operation.

**The delegate is stored raw and resolved per worktree.** Git resolves a
relative `core.hooksPath` against the current working tree's root, so freezing
it to an absolute path at install time would make a linked worktree run the main
checkout's hooks. The wrapper resolves the stored value at run time.

**Two slot shapes are kept deliberately.** A symlink where no chaining is
needed, a wrapper file where it is, distinguished by a
`# praxion-hook-wrapper v1` first-line marker so the staleness predicate in
`upgrade_project_pins.sh` classifies structurally rather than heuristically.

**Praxion's own self-install is out of scope.** `install_claude.sh` keeps its
existing path: Praxion's checkout has `core.hooksPath` unset, three finalize
symlinks, and a `pre-commit`-framework dispatcher installed by
`pre-commit install`. Converging the self-install onto this script would place
the highest-blast-radius change on the least valuable case.

## Considered Options

### A — Status quo, plus a warning when `core.hooksPath` is set

Pros: trivial; no takeover of anything.

Cons: leaves the operator with a broken factory and a message. Under sidecar
placement the hooks are the only enforcement surface, so "warn and continue" is
"ship nothing and say so".

### B — Register inside the team's hook manager

Add a `repo: local` entry to `.pre-commit-config.yaml`, or drop a file into
`.husky/`.

Pros: the polite, idiomatic answer, and what most tools would choose. No
configuration takeover; the team's manager stays in charge.

Cons: **every file it writes is tracked.** `.pre-commit-config.yaml` and
`.husky/` are committed and teammate-visible, which defeats the premise
outright. It also requires a per-manager adapter — pre-commit, husky, lefthook,
and whatever comes next — each with its own schema and its own idempotency
problem.

### C — Observe, then compose, by taking over `core.hooksPath` locally (chosen)

Pros: works with every manager without knowing any of their schemas, because it
composes at git's own extension point rather than at each tool's. Writes nothing
tracked. The team's hooks keep running, first. Fully reversible.

Cons: Praxion owns a configuration value the team's tooling also writes, which
forces a self-heal to exist. Two slot shapes rather than one. A teammate
inspecting `core.hooksPath` on the operator's machine sees an unfamiliar value.

### D — Always install the wrapper, in every repository

Pros: one uniform shape, one predicate, the smallest state space.

Cons: rewrites hook wiring in every already-onboarded project, including
Praxion's own, to serve a case most of them do not have. A large diff and a real
regression surface bought for internal tidiness.

## Consequences

**Positive.** Praxion's hooks fire in husky, lefthook and `pre-commit`-framework
repositories. A team's existing gate keeps running rather than being quietly
displaced — a defect that has been shipping. Hook install becomes one tested
implementation instead of prose in a skill plus a shell fragment in an upgrade
script. `--status` makes a silently-inert install diagnosable, which was
impossible before. `--uninstall` makes Praxion's presence in a team repository
fully reversible, which matters for a design premised on being unobtrusive.

**Negative.** Praxion now writes a repository-local git config value it does not
exclusively own, which is what creates the drift the self-heal repairs. Two slot
shapes must both be classified correctly by the staleness predicate, and a
misclassification either re-points a healthy hook or leaves a stale one. The
per-hook-class exit-code policy is easy to get backwards and needs a test per
class. Existing onboarded projects receive the chaining behaviour only through
the Phase 4 content-aware top-up table, which must gain a row or the fix never
reaches them.

## Disconfirmation

**Falsifier.** If a repository is found where taking over `core.hooksPath`
breaks the team's own tooling in a way `--uninstall` cannot cleanly reverse — a
manager that asserts the value in CI, or one that rewrites it on every git
operation rather than on install — then composing at git's extension point is
the wrong seam and option B's per-manager adapters, tracked files and all,
becomes the honest answer for that manager.

**Steelmanned runner-up.** Option B is right if one believes the team's hook
manager should remain the single authority over what runs on commit. Under that
view Praxion is a *participant* in the team's toolchain, not a layer above it,
and a participant registers through the published extension point even at the
cost of a tracked file — which the operator could propose as an ordinary pull
request the team can accept or reject on its merits. That is a more honest
social contract than a configuration takeover the team never sees. It loses
because the operator explicitly does not want to ask, and a tracked file is a
request; but if the goal were ever restated as "adopt Praxion with the team's
knowledge", option B would be strictly better than this decision.

**Reversal trigger.** A third slot shape becoming necessary, or a second hook
manager requiring manager-specific handling inside the wrapper, would mean the
"compose at git's extension point" abstraction has leaked and per-manager
adapters should be reconsidered.
