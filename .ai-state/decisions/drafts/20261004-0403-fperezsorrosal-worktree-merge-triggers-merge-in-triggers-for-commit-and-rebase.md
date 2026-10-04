---
id: dec-draft-dc96c2c1
title: Observation-log merge-in also runs from post-commit for a merge finished by a commit and from a fourth finalize hook slot, post-rewrite, for a finished rebase
status: proposed
category: architectural
date: 2026-10-03
summary: "post-commit runs merge-in for a merge commit finished by git commit (primary working tree, outside a rebase, HEAD@{1} equal to its first parent, judged against that parent); a new fourth finalize hook slot, post-rewrite, runs merge-in after a finished rebase (judged against ORIG_HEAD; an amend does nothing); an unresolvable before-revision becomes a named skip through an additive CLI flag; the finalize hook names are declared once in install_git_hooks.py and a parity test keeps their mirrors equal"
tags: [observability, observations-jsonl, worktrees, merge-in, git-hooks, finalize-chain, post-commit, post-rewrite, onboarding]
made_by: agent
agent_type: systems-architect
branch: worktree-merge-triggers
pipeline_tier: standard
affected_files:
  - scripts/finalize_chain.sh
  - scripts/git-finalize-hook.sh
  - scripts/merge_worktree_log.py
  - scripts/install_git_hooks.py
  - scripts/upgrade_project_pins.sh
  - install_claude.sh
  - scripts/check_hook_installation.py
  - skills/onboard-project/references/phases-core.md
  - skills/onboard-project/SKILL.md
  - commands/merge-worktree.md
  - commands/upgrade-project.md
  - docs/architecture.md
  - docs/onboarding.md
  - README_DEV.md
  - scripts/CLAUDE.md
  - .ai-state/DESIGN.md
affected_reqs: [REQ-01, REQ-02, REQ-03, REQ-04, REQ-05, REQ-06, REQ-07, REQ-08, REQ-09, REQ-10, REQ-11, REQ-12, REQ-13, REQ-14, REQ-15, REQ-16, REQ-17, REQ-18, REQ-19]
supersedes_in_part: [dec-424]
dissent: "A per-commit predicate and a new fleet hook slot for merges that /merge-worktree already covers at teardown, and that P14 already warns about, add hot-path work and onboarding surface to every managed project; post-commit alone would close the common case with no install change."
---

## Context

`dec-424` gave worktree logs a merge-in at merge time, from the post-merge finalize chain. It named one gap it did not build, raised as its round-1 verifier finding W-1: git runs no `post-merge` hook for a merge it finishes outside `git merge`. These are a merge stopped on a conflict, or run with `--no-commit`, then finished with `git commit` or `git merge --continue`; and a pull that rebases local commits onto incoming ones. Such a worktree is never brought in later either, because every later merge finds its `HEAD` already inside that merge's `ORIG_HEAD`. Its rows then survive only if `/merge-worktree` step 9.5 runs at teardown, or if someone acts on P14's warning. A bare `git worktree remove` loses them. `dec-424`'s reversal trigger names this exact closure: a `post-commit` trigger for merge commits and a `post-rewrite` trigger for rebases, with the user's agreement, since both reach the fleet.

The user asked on 2026-10-03 for "the best action … so we don't lose any information or any part of the process hanging or with a gap", and accepted the fleet reach at intake.

What git does, probed on git 2.44.0 in scratch repositories on 2026-10-03:

- A merge finished by a commit runs `post-commit` once, with HEAD a merge commit whose first parent is the pre-merge tip.
- A rebase (`git pull --rebase`, `git rebase`, the apply backend, `--rebase=merges`, a stop then `--continue` or `--skip`) runs `post-commit` for every commit it replays, while HEAD is detached and the rebase state directory exists. A recreated merge commit is replayed as a merge commit. At the end the rebase runs `post-rewrite rebase` once, with `ORIG_HEAD` holding the pre-rebase tip.
- `git commit --amend` runs `post-commit` (an amended merge commit is again a merge commit) and then `post-rewrite amend`.
- `git merge` itself runs only `post-merge`.
- `git rebase --abort` runs no `post-rewrite`.

The finalize hook names lived in five independent copies: the reconciler's constant, the pin upgrade's array, the pin upgrade's manifest list, Praxion's own install lines, and the dispatcher's case arms.

## Decision

1. **`post-commit` runs merge-in for a merge finished by a commit.** A predicate in `scripts/finalize_chain.sh` prints the commit's first parent only when all of these hold:
   - the primary working tree is in play (`.git` is a directory);
   - no rebase state directory exists (`rebase-merge`, `rebase-apply`);
   - HEAD has two or more parents;
   - `HEAD@{1}`, the tip before this commit, equals HEAD's first parent. This excludes every amend, because an amend's previous tip is the amended commit.

   The chain then runs `merge_worktree_log.py --merged --before <first parent>`, followed by the on-main finalize as before. The first parent is exact even when `ORIG_HEAD` was overwritten between the stopped merge and its commit.

   A single-parent commit pays one git query (the parent count) and starts no merge-in. A linked worktree, or a commit a rebase replays, pays none. The predicate always returns 0, because the dispatcher runs under `set -e`.
2. **A fourth finalize hook slot, `post-rewrite`, runs merge-in after a finished rebase**, judged against `ORIG_HEAD`, in the primary working tree only.
   - With the argument `amend` it does nothing.
   - It runs merge-in only. The on-main finalize is state-driven, and the next commit or checkout on main runs it; drafts that came through a GitHub merge were already promoted by the server backstop (`dec-284`). Merge-in, by contrast, is relative to the operation's before-revision, which only this hook still knows.
3. **An unresolvable before-revision is a named skip.** `merge_worktree_log.py --merged` gains an additive `--skip-unresolvable-before` flag, which every hook call passes.
   - With the flag, when some linked worktree holds a log, the run prints one line, `merge-in skipped: cannot resolve <REV>; worktree logs are left to /merge-worktree and P14`, and exits 0. With no log-holding worktree it prints nothing.
   - The JSON envelope gains a `skipped` key on a skipped run only.
   - Without the flag, `dec-424`'s input-error contract (exit 2) is unchanged.
4. **The finalize hook names are declared once**, in `scripts/install_git_hooks.py` `FINALIZE_HOOK_NAMES`, which is now `post-merge`, `post-commit`, `post-checkout`, `post-rewrite`.
   - The dispatcher arms, the pin upgrade's array and manifest list, Praxion's own install lines and the onboarding manifest example mirror it.
   - A parity unit test, `scripts/test_finalize_hook_names.py`, fails naming any stale mirror.
   - The reconciler, its SessionStart heal and the chaining wrapper already iterate the constant. The wrapper passes stdin to a chained foreign hook unchanged.
5. **Every text that declared the gap** now states the coverage and the one remaining limit, the squash merge: `.ai-state/DESIGN.md`, `/merge-worktree` step 9.5, the chain's step description, the CLI's docstring and the architecture guide. Every enumeration of the finalize hooks lists four.

What changed, for the `architectural` test:

- Component added: the `post-rewrite` hook slot and its entry point `finalize_chain_post_rewrite`.
- Published contract changed: the onboarding contract's Phase 4 hook set grows from `pre-commit` plus three finalize hooks to `pre-commit` plus four, and so does the manifest's recorded `hooks` list.
- Responsibility moved: hook-triggered merge-in now belongs to the commit and rewrite steps as well as `post-merge`; the hook-name set moves from five independent copies to one declared owner.
- `scripts/test_finalize_hook_names.py` joins `affected_files` once it exists.

Activation: fired.

- Triggered signals: structural (about 16 files across the hook chain, three installers, the merge-in CLI and the onboarding texts) plus real alternatives for the predicate, the name source and the skip.
- Lens set: Security, Performance, Simplicity, Testability.
- Convergence: stable. No requirement changed; the one high-likelihood × high-impact risk (a copy at an amend or a replay) is mitigated by the predicate's gates and pinned by acceptance scenarios.

## Considered Options

### Recognising a merge finished by a commit

- **`HEAD@{1}` equal to the first parent, behind filesystem gates (chosen).** This is structure: git builds a merge commit's parents as (the current HEAD, the merged heads), and records that current HEAD as `HEAD@{1}`. The probe showed equality for a conflicted merge finished by `git commit` and by `git merge --continue`, for a `--no-commit` merge, and with `GIT_REFLOG_ACTION` set. It showed inequality for an amend of a merge commit, an identical same-second amend, an amend in a fresh clone, and the hook re-run after an amend.
- **The reflog subject, `commit (merge)` versus `commit (amend)`.** The probe refuted it: with `GIT_REFLOG_ACTION=custom` the subject became `custom: Merge branch 'side'`, so a real merge would be missed. The subject is caller-controlled text.
- **`MERGE_HEAD` or `ORIG_HEAD`.** `MERGE_HEAD` is deleted before `post-commit` runs. `ORIG_HEAD` is not written by an amend and can be overwritten.
- **Detached HEAD instead of the rebase state directories.** A merge finished on a detached HEAD outside a rebase is legitimate, and the directory test costs no git query. It is also the only gate that stops a merge commit recreated by `git pull --rebase=merges`, whose `HEAD@{1}` equals its first parent.

### What `post-rewrite` runs

- **Merge-in only, judged against `ORIG_HEAD` (chosen).**
- **Merge-in plus the on-main finalize.** It closes no gap the state-driven finalize leaves open, and it would run three finalizers after every interactive rebase on main.
- **The rebase state's private `orig-head` file instead of `ORIG_HEAD`.** It is immune to an `ORIG_HEAD` overwritten mid-rebase, but it reads a private layout. It would also turn an unresolvable `ORIG_HEAD` into a silent copy rather than a named skip.

### One source for the hook names

- **A declared owner plus a parity test over literal mirrors (chosen).**
- **Runtime derivation** (the bash surfaces ask the reconciler). It adds a CLI surface and a Python start, and the dispatcher stays literal, so a parity check is needed anyway.
- **Delegating Praxion's own install and the pin upgrade's loop to the reconciler.** It contradicts `dec-361`, which kept the cross-version loop separate (legacy-name repair, self-host carve-out), and it would wrap Praxion's own pre-commit-framework slot as foreign.
- **Extending each list with no check**, which is how the copies came to be.

### The named skip

- **An additive CLI flag (chosen).** The "does any worktree hold a log" rule stays in one place, so the skip is silent in a project with no pipelines, and the chain's generic non-blocking wrapper is unchanged.
- **A new exit code for "skipped".** It re-means an exit code against `dec-357` and makes the chain special-case one script.
- **A chain-side pre-check of `ORIG_HEAD`.** It would duplicate the log-holding rule in bash, or print in projects with no pipelines.
- **An unconditional skip.** It turns a mistyped `--before` from a human caller into a silent success.

## Consequences

**Positive**

- A merge finished by `git commit` or `git merge --continue` after a conflict or `--no-commit` merges in its worktrees at that commit. So does a rebase that brings worktrees in, `git pull --rebase` included. The rows no longer depend on `/merge-worktree` running before `git worktree remove`.
- Each row is still copied once: whole-row identity makes a second step seeing one merge a no-op, and `git merge` still runs merge-in once.
- An unresolvable before-revision is told apart from a fault.
- A future finalize hook is a one-line change in the owner plus a red parity test naming every stale mirror.

**Negative**

- **Fleet reach, in two speeds.**
  - The `post-commit` path reaches every onboarded project at the next plugin release with no install change: the slot exists everywhere, and it is a symlink into the plugin.
  - The `post-rewrite` slot is new, so it needs the installers. It reaches a project at its next onboarding (`python3 scripts/install_git_hooks.py`, Phase 4) or its next pin upgrade (`bash scripts/upgrade_project_pins.sh`, run by `/upgrade-project`, which also records it in `.ai-state/.praxion-onboard.json`). Praxion itself gets it at its next `bash install.sh`.
  - Until then, a rebasing pull in that project stays covered as before: by step 9.5 and P14.
  - The release notes name both.
- **Cost.** Every commit in every onboarded project pays one more git query (the parent count). A merge commit finished by a commit pays two, plus the merge-in a plain merge already pays. A finished rebase pays one placement resolution plus merge-in.
- **The squash merge stays the named limit.** The squashed commit is not the worktree's `HEAD`, so no hook can recognise that the worktree was merged. `/merge-worktree` step 9.5 and P14 remain its coverage, and worktrees discarded with `ExitWorktree` remove still lose their rows.
- **A repository whose reflog was disabled from `git init`** (`core.logAllRefUpdates=false` before the first commit) cannot tell a finished merge from an amend, because `HEAD@{1}` does not resolve there. Merges finished by a commit fall back to step 9.5 and P14; the reflog-subject alternative is equally blind there. Disabling the reflog later keeps HEAD's existing reflog appending, and the probe confirmed the predicate still works.
- **A primary checkout whose `.git` is a file** (`--separate-git-dir`) is treated as a linked worktree. That limit is inherited unchanged from `dec-424`'s merge-time gate.
- **A rebase of a feature branch onto main in the primary checkout** brings in worktrees created from main with no commits of their own, exactly as `git merge main` into that branch does today. This is `dec-424`'s accepted partial-copy leftover; P03 warns until a later merge copies the rest.
- **An `ORIG_HEAD` a user overwrites during a stopped rebase** misjudges "brought in". A miss stays with step 9.5 and P14; an over-inclusion is the same accepted leftover.
- **Self-host version skew.** Praxion's own main checkout, sitting on a commit before this change, runs a dispatcher with no `post-rewrite` arm, so every amend or rebase prints the unserved-name line (non-blocking). Managed projects link the live plugin and do not see it.

## Disconfirmation

- **Falsifier:** any of the following:
  - A lost worktree log, or a P14 warning, traces to a merge finished by a commit or to a rebasing pull, in a project that has all four finalize hooks installed and its reflog enabled.
  - A P03 WARN on main traces to a merge-in started at an amend or while a rebase replayed commits.
  - Managed-project feedback shows the parent-count query measurably slowing commits.
  - A git release changes the parent order of a merge commit made by `git commit`, or stops recording HEAD's reflog by default.
- **Steelmanned runner-up:** `post-commit` alone, with no new hook slot.
  - It closes the conflicted and `--no-commit` merge with no install change anywhere: no reconciler, pin-upgrade, onboarding-contract or documentation change for a slot.
  - A rebasing pull brings a worktree in only when the user has unpushed commits on main *and* the incoming commits carry a worktree's branch merged elsewhere. With no local commits the pull fast-forwards, and `post-merge` already handles it. That combination is uncommon, and step 9.5 and P14 already cover it.
  - It loses here for three reasons:
    - The installers treat the slot set as data, so the slot costs one element in each mirror, enforced by a parity test.
    - The user asked for no gap.
    - Leaving a known gap with a known, probed fix contradicts fixing root causes.
- **Reversal trigger:** revisit if any of the following happens:
  - Claude Code or git gains a worktree-removal hook. That would make every hook merge-in step redundant; retire the post-commit and post-rewrite steps with the post-merge one.
  - Managed-project feedback reports commit latency or noise from the post-commit predicate. Narrow the post-commit step, or drop it in favour of `/merge-worktree` and P14.
  - The pipeline exit procedure is narrowed to `/merge-worktree` only.
  - P14 warnings trace to rebasing pulls in projects that never ran `/upgrade-project`. Accelerate the fleet upgrade rather than reverse this decision.

## Prior Decision

This record **narrows `dec-424`** (partial supersession). Two clauses change:

- **Consequences, "Merges git completes outside `git merge`".** It recorded the gap for a merge stopped on a conflict or run with `--no-commit` and then committed, and for a pull that rebases local commits, as named and not built, covered only as a squash merge is. It becomes: those merges are merged in by the `post-commit` step (judged against the merge commit's first parent) and by the `post-rewrite` step (judged against `ORIG_HEAD`). The squash merge alone stays left to step 9.5 and P14.
- **Decision clause 4's hook trigger.** The post-merge finalize chain as the only hook that runs `--merged` becomes three finalize hooks running it, each with its operation's before-revision. One entry point stays one entry point.

The last bullet of `dec-424`'s reversal trigger fires with this record, as that bullet prescribed.

These survive unchanged:

- retention and the numbered archives;
- the copy path, whole-row identity and the never-touched worktree log;
- recording-mode resolution;
- the CLI's input-error contract without the new flag;
- `/merge-worktree` step 9.5's behaviour;
- the two accepted leftovers, the squash-merge limit, P09–P14, and cross-checkout reading.

`dec-424` stays `accepted` and gains this record in `superseded_in_part_by`.

Related, without a frontmatter relation:

- **`dec-361`:** the reconciler stays the single writer of the hook-chain composition, and the pin upgrade's cross-version loop stays separate. This record adds a slot to the set they both iterate; it narrows neither.
- **`dec-357`:** the merge-in CLI's exit codes keep their meanings. The skip exits 0 behind an opt-in flag rather than taking a new code.
- **`dec-284`:** the server-side backstop is why `post-rewrite` does not also run the on-main finalize.
