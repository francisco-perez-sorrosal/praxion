# Spec: merge-triggers (observation-log merge-in for merges that fire no post-merge hook)

**Task slug**: `merge-triggers`
**Feature**: The finalize chain merges a worktree's observation-log rows into the main checkout's log not only after `git merge` and `git pull` (the post-merge hook) but also after a merge git finishes outside `git merge` -- a merge stopped on a conflict or run with `--no-commit` and then committed (the post-commit hook, judged against the new commit's first parent) -- and after a rebase that rewrote at least one commit, `git pull --rebase` over local commits included (a new post-rewrite hook, judged against the tip the branch held when the rebase began). The fourth finalize hook slot is installed wherever the other three are: Praxion's own install, the onboarding hook reconciler, and the fleet pin upgrade, with one source of truth for the hook names and a parity test over every literal mirror. Two cases stay named limits, left to `/merge-worktree` step 9.5 and the sentinel's P14: a squash merge, and a rebase that rewrites no commit. Follow-up to `SPEC_wal-retention_2026-10-03.md` (`dec-424`), whose round-1 verifier named this gap (W-1) and whose reversal trigger this fires.
**Tier**: Standard (13 of 16 spawns; researcher skipped -- the codebase context and the wal-retention architect's probes sufficed)
**Pipeline branch**: `worktree-merge-triggers`
**Start date**: 2026-10-03
**End date**: 2026-10-03
**Archived**: 2026-10-03 (post-merge; merged to main as `d0465fc6`)
**Status**: completed -- Step 3 light review accept (F-1 WARN ruled a named limit), final verifier round 1 FAIL on one record defect (a footprint reading predating the last text commit) with three text/test WARNs, all closed by the orchestrator (1721bf26, d0465fc6), round 2 PASS WITH FINDINGS (0 FAIL, 2 WARN carried: disclosed designer sources; td-335 chain test file over the line ceiling); bare suite 7751 passed, 0 failed at the integration checkpoint; the fast-forward's post-merge step copied this pipeline's own 599 worktree-log rows into main's log
**ADRs**: `dec-425` (category: architectural -- it changes the onboard-contract hook surface, a fourth finalize hook slot; `supersedes_in_part: [dec-424]` for its "named, not built" clause on merges that fire no post-merge hook)
**Evidence base**: `dec-425`; the merge commit `d0465fc6`; the pipeline's row in `.ai-state/calibration_log.md` dated 2026-10-03; the committed regression suite (the bare CI invocation at 96f85247: 7751 passed, 0 failed (baseline 7591 at 4c44dea5); 109 acceptance nodes, 10 large e2e nodes, the chain's shell test 21); the Traceability Matrix below (rendered from `.ai-work/merge-triggers/traceability.yml`, an ephemeral pipeline document -- the render is the committed evidence; spec extract digest `ef8422bc825b`); the Step 3 light review and the F-1 ruling (ephemeral, summarised under Key Decisions).

## Feature Summary

`dec-424` made the post-merge finalize chain copy a worktree's log rows into the main checkout's log for every worktree a merge newly brings in, and declared one gap: git runs no post-merge hook for a merge it finishes outside `git merge`. The wal-retention architect probed git 2.44.0 and found three such shapes -- a merge stopped on a conflict and completed by `git commit`, `git merge --no-commit` then `git commit`, and `git pull --rebase` over local commits -- for which the chain copied nothing, and for which every later merge found the worktree already inside its `ORIG_HEAD`, so it was never brought in. Those worktrees' rows survived only through `/merge-worktree` step 9.5 at teardown or the sentinel's P14 warning; a `git worktree remove` by hand lost them.

This feature closes the two shapes git does report. The post-commit hook recognises a merge finished by a commit **by structure**: behind the gates (primary working tree; no `rebase-merge` or `rebase-apply` state directory) and a parent count of two or more, it copies when `HEAD@{1}` equals `HEAD^1` -- an amend fails that equality, and a commit replayed by `git pull --rebase=merges` passes it but is excluded by the rebase-directory gate. The reflog subject was rejected as caller-controlled text (`GIT_REFLOG_ACTION`), `MERGE_HEAD` is gone before the hook runs, and `ORIG_HEAD` can be overwritten between the conflicted merge and its commit. A single-parent commit pays exactly one more git query than before; a replayed commit and a linked worktree pay none; the predicate always returns 0 so the on-main finalize still runs after it. The new post-rewrite hook runs merge-in only for the `rebase` argument, against `ORIG_HEAD` (the pre-rebase tip, confirmed for both backends, autostash, `--continue`, `--skip` and `--rebase=merges`), and does nothing for `amend`; the on-main finalize stays state-driven (the next commit or checkout on main runs it). When a before-revision cannot be resolved, the merge-in command's new `--skip-unresolvable-before` flag prints one named skip line and exits 0 -- silent in a project where no worktree holds a log, never `warned (non-blocking)`.

The hook names have one source of truth, `install_git_hooks.FINALIZE_HOOK_NAMES`; the dispatcher's arms, the pin upgrade's array, the onboarding manifest's list, Praxion's installer and the onboarding reference are literal mirrors kept equal by a parity test that fails by name on any stale copy and raises when a mirror's structure cannot be found. The pin upgrade's legacy-symlink repair and check mode, and Praxion's self-host carve-out, treat `post-rewrite` exactly as `post-merge`. Every text that declared the gap now states the new coverage and the two remaining limits -- the squash merge (the squashed commit is not the worktree's `HEAD`) and, found by the Step 3 light review and ruled a named limit, a rebase that rewrites no commit (a fast-forwarding `git rebase`, a drop-all `git rebase` or `git pull --rebase`), for which git runs no hook at all after the branch moves; `post-checkout` fires before it moves and would copy an abandoned rebase, a `pre-rebase` or `reference-transaction` hook would be a fifth slot, and a state-driven carrier would exceed the per-commit query budget. A repository whose reflog was disabled from `git init` cannot tell a finished merge from an amend and copies nothing for it; that limit is named in the decision record and the merge-in docstring. Fleet reach: the post-commit coverage ships to every onboarded project at the next plugin release with no install change (the slot exists); the post-rewrite slot arrives through onboarding, the pin upgrade or Praxion's installer.

## Requirements

Verbatim from `SYSTEMS_PLAN.md § Behavioral Specification` as extracted by `extract_spec.py` (digest `ef8422bc825b`; REQ ids are pipeline-local and appear nowhere in code, tests or docstrings). No requirement text changed after the acceptance design; the F-1 ruling reads the second requirement as "a rebase that rewrites at least one commit" (its own example and purpose clause) and records the no-op rebase as a declared limit beside the seventh.

Terms used below, in plain words, as in the archived wal-retention specification and extended here. The **log** is a checkout's `observations.jsonl`, its archives included. The **main checkout** is the repository's primary working tree; a **worktree** is any linked working tree of the same repository. **Merge-in** copies into the main checkout's log every row of a worktree's log that the main log does not already hold, unchanged, leaves the worktree's log untouched, copies nothing while the recording mode in effect is `off`, and reports what it copied; the earlier specification fixes that behaviour and this one does not change it. A **merge commit** is a commit with more than one parent. A worktree is **brought in** by a git operation run in the main checkout when, after the operation, the main checkout's HEAD contains the worktree's HEAD and the operation's **before-revision** does not. The before-revision is `ORIG_HEAD` for `git merge` and for a pull that merges or fast-forwards (unchanged from today); a merge commit's first parent for that commit; and, for a rebase, the tip the branch held when the rebase began. The **merge-time step** is today's merge-in at `git merge` and `git pull`, through the `post-merge` hook. The **finalize hooks** are the git hooks Praxion installs to run its finalize chain: today `post-merge`, `post-commit` and `post-checkout`; this change adds `post-rewrite`.

What git does, probed on git 2.44.0 in scratch repositories on 2026-10-03, so scenarios can be built on it:

- `git merge` and `git pull` that create a merge commit, fast-forward or squash run `post-merge` and do not run `post-commit`.
- A merge stopped on a conflict, or run with `--no-commit`, and finished with `git commit` or `git merge --continue` runs `post-commit` once, with HEAD a merge commit (three parents for an octopus merge), and runs no `post-merge`. At that point the commit's first parent is the tip before the merge.
- `git pull --rebase` over local commits runs `post-checkout` as it starts, `post-commit` for every commit it replays (HEAD detached; a merge commit recreated by `git pull --rebase=merges` is replayed as a merge commit), and `post-rewrite` once at the end, with the argument `rebase` and, on standard input, one line per rewritten commit holding the old and the new commit id separated by a space. When `post-rewrite` runs, HEAD is the rebased tip and `ORIG_HEAD` holds the tip the branch had before the rebase; the same holds with an autostash and after a conflict resolved with `git rebase --continue` or `git rebase --skip`. It runs no `post-merge`.
- `git pull --rebase` with no local commits fast-forwards and runs `post-merge` only; with nothing new upstream it runs none of these hooks; `git rebase --abort` runs no `post-rewrite`.
- `git commit --amend` runs `post-commit`, with HEAD keeping the amended commit's parents (an amended merge commit is again a merge commit), and then `post-rewrite` with the argument `amend`.
- In a linked worktree the same hooks run, inside that worktree. `git cherry-pick` runs `post-commit` with a single-parent HEAD; `git merge --squash` runs `post-merge` without moving HEAD, and the commit that completes it runs `post-commit` with a single-parent HEAD.

### Merges git finishes outside `git merge`

### REQ-01: A merge finished by a commit merges in the worktrees it brought in

**When** a merge commit is created in the main checkout by `git commit` or `git merge --continue`, for a merge that stopped on a conflict or ran with `--no-commit` and was then finished, an octopus merge included
**the system** performs merge-in, once that commit exists, for every worktree holding a log whose HEAD the new commit contains and the commit's first parent does not, whatever `ORIG_HEAD` holds by then, and for no other worktree, and reports it as the merge-time step reports a merge
**so that** a merge git finishes outside `git merge` no longer leaves a pipeline's rows in a worktree that `git worktree remove` later deletes.

### REQ-02: A rebase that brings in a worktree merges in its log

**When** a rebase run in the main checkout finishes, `git pull --rebase` over local commits included, and one finished with `git rebase --continue` or `git rebase --skip` after stopping on a conflict
**and** the rebased tip contains the HEAD of a worktree holding a log that the branch's tip before the rebase did not contain
**the system** performs merge-in for every such worktree, once, after the rebase has finished, and for no other worktree
**so that** a pull that rebases local commits onto incoming ones keeps the rows of the pipelines those incoming commits carry.

### What copies nothing

### What copies nothing

### REQ-03: An ordinary commit copies nothing and stays cheap

**When** a commit with a single parent is created in the main checkout, whether an ordinary commit, a `git cherry-pick`, the commit that completes a `git merge --squash`, or a commit a rebase replays
**the system** copies no row, does not start the merge-in, and adds at most one query to git to the work the commit hook did before this change
**so that** the hook every commit runs stays as cheap as it was.

### REQ-04: An amend copies nothing

**When** a commit in the main checkout is amended with `git commit --amend`, a merge commit included
**the system** copies no row and does not start the merge-in, neither for the amended commit nor for the rewrite git reports for it
**so that** an amend, which brings in nothing its original commit had not already brought in, never repeats a merge-in.

### REQ-05: A rebase copies nothing while it replays, when abandoned, or when it brings nothing in

**When** a rebase in the main checkout replays commits, merge commits it recreates included, or is abandoned with `git rebase --abort`, or finishes with a tip that contains no worktree HEAD the tip before it lacked, such as a rebase onto an upstream with nothing new or one that rewords, reorders or drops local commits
**the system** copies no row while commits are replayed, copies nothing for an abandoned rebase, and copies nothing and prints nothing when the finished rebase brought no worktree in
**so that** only a rebase that actually landed incoming work copies anything, and it does so once, when its result is final.

### REQ-06: Operations in a linked worktree copy nothing

**When** a merge commit is created, a commit is amended, or a rebase finishes in a linked worktree, including `git pull --rebase` there and a conflicted merge finished there by `git commit`
**the system** copies no row into any log and starts no merge-in
**so that** only the main checkout's log ever receives merge-in, as with a merge by `git merge` today.

### REQ-07: A squash merge stays a named limit

**When** a worktree's branch is squash-merged into the main checkout's branch with `git merge --squash` followed by `git commit`
**the system** copies nothing for that worktree at that merge, leaving it to `/merge-worktree` step 9.5 at teardown and to the P14 warning while the worktree exists
**so that** the one merge shape no hook can recognise, because the squashed commit is not the worktree's HEAD, stays a declared limit rather than a silent gap.

### Safety of the added triggers

### Safety of the added triggers

### REQ-08: Each row is copied once, however many hook steps see a merge

**When** merge-in is run by more than one hook step for one git operation, or by the same hook step again for the same commit, or a `git merge` creates a merge commit
**the system** appends each worktree row the main log lacks exactly once, and a `git merge` that creates a merge commit performs merge-in once
**so that** adding triggers never duplicates a row and never changes what a plain merge does.

### REQ-09: The hook steps never block or fail a git operation

**When** merge-in run from the commit or the rewrite hook copies rows, finds nothing to copy, cannot read a worktree's log, cannot write the main log, or fails outright
**the system** completes the git operation unchanged, ends the hook successfully, reports a degraded merge-in with its reason and counts as the merge-time step reports one, and prints nothing when nothing was copied and nothing went wrong
**so that** the added triggers keep the finalize chain's non-blocking contract and its quiet default.

### REQ-10: A missing before-revision is a named skip, not a failure

**When** a hook step that performs merge-in cannot resolve its before-revision, as when git holds no `ORIG_HEAD` when a rebase's rewrite is reported
**and** some worktree holds a log
**the system** skips the merge-in, prints one line saying that it skipped and naming the revision it could not resolve, does not print `warned (non-blocking)`, and completes the git operation; when no worktree holds a log it prints nothing, as today
**so that** an unresolvable before-revision is told apart from a fault, and the worktree stays visible to `/merge-worktree` and P14.

### REQ-11: The added triggers copy what the merge-time step copies, under the same conditions

**When** a merge commit or a finished rebase brings a worktree in
**the system** applies the merge-time step's conditions: it copies only into the main checkout's own log and not under sidecar placement, resolves the recording mode as the merge-time step does so nothing is copied while the mode in effect is `off`, copies rows unchanged, and leaves the worktree's log untouched
**so that** a worktree's rows reach the main log identically whichever way its branch was merged.

### Installing the rewrite hook

### Installing the rewrite hook

### REQ-12: Praxion's own install installs the rewrite hook

**When** `bash install.sh` runs in a Praxion checkout
**the system** installs `post-rewrite` as it installs `post-merge`: a current link is left as it is, an earlier Praxion-installed copy is replaced, and a foreign hook in that slot is preserved as `post-rewrite.pre-praxion`
**so that** Praxion's own repository runs the rebase step.

### REQ-13: The onboarding hook reconciler treats the rewrite hook as it treats the other finalize hooks

**When** `python3 scripts/install_git_hooks.py` runs in any of its install, heal, status and uninstall modes, in any repository shape it handles: an empty slot, a slot holding a foreign hook, `core.hooksPath` naming a foreign directory or Praxion's own wrapper directory, or an unresolvable `core.hooksPath`
**the system** does to `post-rewrite` exactly what it does to `post-merge` in the same mode and shape, whether it installs it, chains it with a preserved foreign hook that still runs first, reports it, restores it, refuses or removes it, and `/onboard-project` Phase 4 reports it among the installed hooks
**so that** every project onboarded from this release gets the rebase step, composed with whatever hook framework it already uses.

### REQ-14: The pin upgrade gives an upgraded project the rewrite hook

**When** `bash scripts/upgrade_project_pins.sh`, run by `/upgrade-project`, reconciles a project whose `post-rewrite` slot is absent, dangling, pinned to an earlier plugin version or held by a foreign hook, or whose finalize hooks still point at the legacy single-trigger `git-post-merge-hook.sh`
**the system** leaves the project with `post-rewrite` linked to the live plugin like the other three finalize hooks, backing up a foreign occupant; reports the slot as drift in check mode without changing anything; leaves a self-hosted Praxion link alone; records `post-rewrite` in the list of installed hooks in `.ai-state/.praxion-onboard.json`; and changes nothing on a second run
**so that** a project onboarded by an earlier release gains the rebase step at its next upgrade.

### REQ-15: Every installation surface agrees on the finalize hooks

**When** the hooks a project receives are compared across `bash install.sh`, `python3 scripts/install_git_hooks.py`, `bash scripts/upgrade_project_pins.sh`, the list of installed hooks recorded in `.ai-state/.praxion-onboard.json`, and the `/onboard-project` Phase 4 text
**the system** names the same set everywhere: `pre-commit` plus the four finalize hooks `post-merge`, `post-commit`, `post-checkout` and `post-rewrite`
**so that** a project ends with the same hooks whichever path installed or repaired them.

### REQ-16: The hook-mirror check and the dispatcher know four finalize hooks

**When** `python3 scripts/check_hook_installation.py` runs in a checkout with all four finalize hooks installed and current, or the finalize dispatcher is invoked under a name that is not a hook it serves
**the system** reports no finding for the installed hooks, and the dispatcher's message names all four finalize hooks it serves
**so that** the advisory mirror check passes once `post-rewrite` is installed, and a misconfigured run is told the real set.

### Texts that declare the coverage, and the decision record

### Texts that declare the coverage, and the decision record

### REQ-17: The texts that declared the gap state the new coverage and the squash-merge limit

**When** a reader consults any text that states which merges the hook steps merge in: the post-merge merge-in row of `.ai-state/DESIGN.md`, `/merge-worktree` step 9.5 in `commands/merge-worktree.md`, the merge-in step description in `scripts/finalize_chain.sh`, the module documentation of `scripts/merge_worktree_log.py`, and the observation-log and hook-chain rows of `docs/architecture.md`
**the system** states that a merge finished by `git commit` after a conflict or `--no-commit`, and a rebase that brings worktrees in, `git pull --rebase` included, are merged in by the hook steps; that a squash merge is not, and is left to `/merge-worktree` step 9.5 and P14; and no such text still says those merges are left uncovered
**so that** the declared limits match what the hooks do, and the one remaining limit is named where readers look.

### REQ-18: Every document that lists the finalize hooks lists four

**When** a reader consults a document that enumerates Praxion's finalize hooks or hook slots: the Phase 4 section and the manifest example of `skills/onboard-project/references/phases-core.md`, `docs/onboarding.md`, the reconciled-surface list of `commands/upgrade-project.md`, `README_DEV.md`, `scripts/CLAUDE.md`, `docs/architecture.md`, and the descriptions in `scripts/git-finalize-hook.sh` and the installers
**the system** lists `post-rewrite` with the other three finalize hooks and says what the commit and the rewrite hooks now do for merge-in, and no such document still says there are three finalize hooks
**so that** the onboarding contract documents the hook surface it installs.

### REQ-19: One decision record narrows the "named, not built" clause of dec-424

**When** the decision records are read after this change
**the system** holds one record of `category: architectural` under `.ai-state/decisions/drafts/` whose `supersedes_in_part` names `dec-424`, with a `## Prior Decision` section naming the clause it narrows (the gap for merges finished outside `git merge`, recorded as named and not built) and the clauses that survive, a `## Disconfirmation` section, and consequences that name the fleet reach (the commit hook reaches every onboarded project at the next plugin release with no install step; `post-rewrite` reaches a project at its next onboarding or pin upgrade) and the squash-merge limit; and `dec-424` gains that record in `superseded_in_part_by` and stays accepted
**so that** the decision trail shows why the fleet's hook surface grew and what remains uncovered.

### Footprint Criteria

| Id | Footprint | Metric | Comparator | Limit | Against | Command |
|---|---|---|---|---|---|---|
| FC-01 | always-loaded-tokens | always-loaded tokens, tokenizer basis | at or below | the baseline reading (16726 tokens at 4c44dea5 on 2026-10-03) | baseline: the reading taken before the first production step | `python3 scripts/measure_token_budget.py --json` |
| FC-02 | listing-tokens | listing tokens of skill, command and agent descriptions, tokenizer basis | at or below | the baseline reading (9144 tokens at 4c44dea5 on 2026-10-03) | baseline: the reading taken before the first production step | `python3 scripts/measure_token_budget.py --json` |
| FC-03 | prompt-size | prompt-size findings at fail severity | at or below | 0 findings | reference: the instrument's own ceilings | `python3 scripts/check_agent_prompt_size.py --json` |

### Footprints Not Measured

| Footprint | Reason |
|---|---|
| hook-latency | no instrument exists, and the registered class covers the session hooks, not the git hooks this change touches; REQ-03 pins the observable part of the git-hook cost instead (a single-parent commit adds at most one query to git and starts no merge-in) |
| observation-log-volume | no instrument exists; this change copies into the main log only rows the merge-time step would already copy at a merge git reports to it, so the bound stated by the retention policy is unchanged |
| spawn-count | the only instrument counts a pipeline that has already run, not a change; this change adds no agent spawn to any procedure |

## Traceability Matrix

Rendered from `traceability.yml` at archival: unit tests and acceptance nodes (outer-loop, designed from the extract alone and committed before any production change) per requirement, with the implementation symbols' files. `Status` is the final verifier's reading.

| REQ | Unit tests | Acceptance nodes | Implementation | Status |
|---|---|---|---|---|
| REQ-01 | 2 test(s) -- `scripts/test_finalize_chain.py` (test_post_commit_merges_in_against_the_first_parent_then_finalizes, test_a_merge_finished_by_a_commit_prints_its_first_parent) | 6 test(s) -- `tests/acceptance/test_merge_triggers_merges_finished_by_a_commit.py` (test_a_merge_stopped_on_a_conflict_merges_in_the_worktree_once_it_is_finished, test_a_merge_run_with_no_commit_merges_in_the_worktree_once_it_is_committed, test_an_octopus_merge_finished_by_a_commit_merges_in_every_worktree_it_brought_in, test_a_merge_finished_by_a_commit_is_judged_by_its_first_parent_whatever_orig_head_holds, test_a_merge_finished_by_a_commit_merges_in_no_worktree_it_did_not_bring_in, test_a_merge_finished_by_a_commit_reports_its_merge_in_as_a_plain_merge_does) | 1 file(s) -- `scripts/finalize_chain.sh` | PASS |
| REQ-02 | 1 test(s) -- `scripts/test_finalize_chain.py` (test_post_rewrite_merges_in_against_orig_head_after_a_rebase) | 3 test(s) -- `tests/acceptance/test_merge_triggers_rebases.py` (test_a_rebase_that_brings_in_a_worktree_merges_in_its_log_once, test_a_rebase_that_recreates_local_merge_commits_merges_in_the_worktree_it_brought_in, test_a_rebase_finished_after_a_conflict_merges_in_the_worktree_it_brought_in) | 2 file(s) -- `scripts/finalize_chain.sh`; `scripts/git-finalize-hook.sh` | PASS (declared limit: a rebase that rewrites no commit fires no post-rewrite hook; left to `/merge-worktree` 9.5 and P14 — F-1 ruling) |
| REQ-03 | 2 test(s) -- `scripts/test_finalize_chain.py` (test_post_commit_starts_no_merge_in_for_a_commit_that_is_not_a_finished_merge, test_a_single_parent_commit_is_no_finished_merge_and_costs_one_git_query) | 2 test(s) -- `tests/acceptance/test_merge_triggers_copies_nothing.py` (test_a_single_parent_commit_copies_nothing_and_starts_no_merge_in, test_a_single_parent_commit_adds_at_most_one_git_query_to_the_commit_hook) | 1 file(s) -- `scripts/finalize_chain.sh` | PASS |
| REQ-04 | 2 test(s) -- `scripts/test_finalize_chain.py` (test_an_amended_merge_commit_is_no_finished_merge, test_post_rewrite_starts_nothing_and_asks_git_nothing_unless_a_rebase_finished) | 2 test(s) -- `tests/acceptance/test_merge_triggers_copies_nothing.py` (test_amending_a_merge_commit_copies_nothing_and_starts_no_merge_in, test_amending_a_single_parent_commit_copies_nothing_and_starts_no_merge_in) | 1 file(s) -- `scripts/finalize_chain.sh` | PASS |
| REQ-05 | 1 test(s) -- `scripts/test_finalize_chain.py` (test_a_merge_commit_a_rebase_is_replaying_is_no_finished_merge_and_asks_git_nothing) | 5 test(s) -- `tests/acceptance/test_merge_triggers_rebases.py` (test_a_rebase_copies_nothing_and_starts_no_merge_in_while_it_replays_commits, test_a_rebase_that_recreates_merge_commits_and_is_abandoned_copies_nothing, test_an_abandoned_rebase_copies_nothing, test_a_pull_with_nothing_new_upstream_copies_nothing_and_prints_nothing_about_merge_in, test_a_rebase_that_only_replays_local_commits_copies_nothing_and_prints_nothing_about_it) | 1 file(s) -- `scripts/finalize_chain.sh` | PASS |
| REQ-06 | 2 test(s) -- `scripts/test_finalize_chain.py` (test_a_merge_finished_by_a_commit_in_a_linked_worktree_asks_git_nothing, test_post_rewrite_after_a_rebase_in_a_linked_worktree_starts_nothing) | 4 test(s) -- `tests/acceptance/test_merge_triggers_copies_nothing.py` (test_a_conflicted_merge_finished_by_a_commit_in_a_linked_worktree_copies_nothing, test_a_pull_that_rebases_in_a_linked_worktree_copies_nothing, test_an_amend_in_a_linked_worktree_copies_nothing, test_an_ordinary_commit_in_a_linked_worktree_copies_nothing) | 1 file(s) -- `scripts/finalize_chain.sh` | PASS |
| REQ-07 | 2 test(s) -- `scripts/test_finalize_chain.py` (test_post_commit_starts_no_merge_in_for_a_commit_that_is_not_a_finished_merge, test_a_single_parent_commit_is_no_finished_merge_and_costs_one_git_query) | 3 test(s) -- `tests/acceptance/test_merge_triggers_copies_nothing.py` (test_a_squash_merge_copies_nothing_for_the_squashed_worktree, test_a_single_parent_commit_copies_nothing_and_starts_no_merge_in); `tests/acceptance/test_merge_triggers_texts.py` (test_each_coverage_text_names_the_squash_merge_as_the_remaining_limit) | 2 file(s) -- `scripts/finalize_chain.sh`; `commands/merge-worktree.md` | PASS (named limits: the squash merge and the no-op rebase) |
| REQ-08 | 1 test(s) -- `scripts/test_finalize_chain.py` (test_post_commit_merges_in_against_the_first_parent_then_finalizes) | 3 test(s) -- `tests/acceptance/test_merge_triggers_merges_finished_by_a_commit.py` (test_running_the_commit_hook_again_for_the_same_merge_commit_copies_nothing_more, test_a_plain_merge_that_creates_a_merge_commit_starts_merge_in_once); `tests/acceptance/test_merge_triggers_rebases.py` (test_a_rebase_that_brings_in_a_worktree_merges_in_its_log_once) | 1 file(s) -- `scripts/finalize_chain.sh` | PASS |
| REQ-09 | 2 test(s) -- `scripts/test_finalize_chain.py` (test_an_unresolvable_reflog_never_ends_post_commit_before_the_finalize, test_a_merge_commit_without_a_reflog_is_no_finished_merge) | 3 test(s) -- `tests/acceptance/test_merge_triggers_merges_finished_by_a_commit.py` (test_a_merge_finished_by_a_commit_with_an_unreadable_worktree_log_completes_and_reports_it, test_a_merge_finished_by_a_commit_that_copies_nothing_prints_nothing_about_merge_in); `tests/acceptance/test_merge_triggers_rebases.py` (test_a_rebase_that_cannot_write_the_main_log_completes_and_reports_the_worktree) | 1 file(s) -- `scripts/finalize_chain.sh` | PASS |
| REQ-10 | 8 test(s) -- `scripts/test_merge_worktree_log.py` (test_skipping_an_unresolvable_before_prints_one_named_line_and_exits_zero, test_the_skip_is_silent_when_no_worktree_holds_a_log, test_the_skip_envelope_adds_one_key_and_reports_no_error, test_a_resolvable_before_with_the_skip_flag_merges_as_usual, test_the_skip_applies_to_the_default_boundary_too, test_the_skip_flag_belongs_to_merged); `scripts/test_finalize_chain.py` (test_post_merge_merges_in_against_orig_head_with_the_named_skip, test_post_rewrite_merges_in_against_orig_head_after_a_rebase) | 2 test(s) -- `tests/acceptance/test_merge_triggers_rebases.py` (test_a_rebase_whose_before_revision_cannot_be_resolved_prints_one_named_skip, test_an_unresolvable_before_revision_with_no_worktree_log_prints_nothing_about_it) | 2 file(s) -- `scripts/merge_worktree_log.py`; `scripts/finalize_chain.sh` | PASS |
| REQ-11 | 4 test(s) -- `scripts/test_finalize_chain.py` (test_post_commit_merges_in_nothing_unless_the_state_lives_in_the_repository, test_post_rewrite_merges_in_nothing_unless_the_state_lives_in_the_repository, test_post_commit_resolves_placement_once_for_merge_in_and_the_finalize, test_state_driven_finalize_uses_the_repo_root_it_is_given) | 3 test(s) -- `tests/acceptance/test_merge_triggers_merges_finished_by_a_commit.py` (test_a_merge_finished_by_a_commit_copies_rows_unchanged_and_leaves_the_worktree_log_alone, test_a_merge_finished_by_a_commit_copies_nothing_while_the_project_recording_mode_is_off); `tests/acceptance/test_merge_triggers_rebases.py` (test_a_rebase_copies_rows_unchanged_and_leaves_the_worktree_log_alone) | 1 file(s) -- `scripts/finalize_chain.sh` | PASS |
| REQ-12 | `[]` | 2 test(s) -- `tests/acceptance/test_merge_triggers_texts.py` (test_each_document_that_lists_the_finalize_hooks_lists_the_rewrite_hook, test_no_document_still_counts_three_finalize_hooks) | 1 file(s) -- `install_claude.sh` | PASS (`bash install.sh` itself not black-box driven; the installer function was exercised on a scratch repository) |
| REQ-13 | 1 test(s) -- `scripts/test_install_git_hooks.py` (TestInstallOrHeal::test_the_rewrite_hook_is_the_last_finalize_slot) | 5 test(s) -- `tests/acceptance/test_merge_triggers_installation.py` (test_the_reconciler_treats_the_rewrite_slot_exactly_as_the_merge_slot, test_the_reconciler_reports_the_rewrite_slot_wherever_it_reports_the_merge_slot, test_the_reconciler_status_flags_a_missing_rewrite_slot_as_it_flags_a_missing_merge_slot, test_a_foreign_rewrite_hook_still_runs_after_the_reconciler_chains_it); `tests/acceptance/test_merge_triggers_texts.py` (test_the_onboarding_phase_four_text_says_what_the_rewrite_hook_does_for_merge_in) | 1 file(s) -- `scripts/install_git_hooks.py` | PASS |
| REQ-14 | 4 test(s) -- `scripts/test_upgrade_project_pins.py` (test_apply_repoints_all_surfaces, test_apply_is_idempotent, test_self_host_symlink_in_a_praxion_named_dir_left_untouched, test_live_but_old_plugin_cache_symlink_still_repointed) | 7 test(s) -- `tests/acceptance/test_merge_triggers_installation.py` (test_the_pin_upgrade_links_the_rewrite_slot_to_the_live_plugin, test_the_pin_upgrade_backs_up_a_foreign_rewrite_hook, test_the_pin_upgrade_repairs_legacy_single_trigger_hooks_into_all_four_finalize_hooks, test_the_pin_upgrade_check_mode_reports_a_missing_rewrite_slot_and_changes_nothing, test_the_pin_upgrade_leaves_a_self_hosted_praxion_link_alone, test_the_pin_upgrade_records_the_rewrite_hook_among_the_installed_hooks, test_a_second_pin_upgrade_leaves_the_upgraded_project_rewrite_slot_included_unchanged) | 1 file(s) -- `scripts/upgrade_project_pins.sh` | PASS |
| REQ-15 | 6 test(s) -- `scripts/test_finalize_hook_names.py` (test_each_mirror_lists_exactly_the_declared_hook_names, test_each_dispatcher_arm_calls_the_entry_point_its_hook_names, test_every_mirror_has_parser_cases, test_a_parser_reports_a_mirror_that_lost_the_rewrite_hook, test_a_parser_fails_on_a_mirror_whose_structure_it_cannot_find); `scripts/test_install_git_hooks.py` (TestInstallOrHeal::test_the_rewrite_hook_is_the_last_finalize_slot) | 4 test(s) -- `tests/acceptance/test_merge_triggers_installation.py` (test_the_reconciler_installs_pre_commit_and_the_four_finalize_hooks, test_the_pin_upgrade_records_the_rewrite_hook_among_the_installed_hooks, test_the_pin_upgrade_repairs_legacy_single_trigger_hooks_into_all_four_finalize_hooks); `tests/acceptance/test_merge_triggers_texts.py` (test_each_document_that_lists_the_finalize_hooks_lists_the_rewrite_hook) | 7 file(s) -- `scripts/install_git_hooks.py`; `scripts/upgrade_project_pins.sh`; `install_claude.sh`; `skills/onboard-project/references/phases-core.md`; `skills/onboard-project/SKILL.md`; `commands/upgrade-project.md`; `docs/onboarding.md` | PASS |
| REQ-16 | `[]` | 2 test(s) -- `tests/acceptance/test_merge_triggers_installation.py` (test_the_hook_mirror_check_reports_nothing_with_the_four_finalize_hooks_installed, test_the_dispatcher_invoked_under_an_unserved_name_lists_the_four_finalize_hooks) | 2 file(s) -- `scripts/git-finalize-hook.sh`; `scripts/check_hook_installation.py` | PASS |
| REQ-17 | `[]` | 3 test(s) -- `tests/acceptance/test_merge_triggers_texts.py` (test_each_coverage_text_names_the_merges_the_hook_steps_now_merge_in, test_each_coverage_text_names_the_squash_merge_as_the_remaining_limit, test_no_coverage_text_still_says_the_newly_covered_merges_are_uncovered) | 5 file(s) -- `scripts/merge_worktree_log.py`; `scripts/finalize_chain.sh`; `commands/merge-worktree.md`; `docs/architecture.md`; `.ai-state/DESIGN.md` | PASS |
| REQ-18 | `[]` | 3 test(s) -- `tests/acceptance/test_merge_triggers_texts.py` (test_each_document_that_lists_the_finalize_hooks_lists_the_rewrite_hook, test_no_document_still_counts_three_finalize_hooks, test_the_onboarding_phase_four_text_says_what_the_rewrite_hook_does_for_merge_in) | 11 file(s) -- `scripts/git-finalize-hook.sh`; `install_claude.sh`; `scripts/install_git_hooks.py`; `scripts/upgrade_project_pins.sh`; `skills/onboard-project/references/phases-core.md`; `skills/onboard-project/SKILL.md`; `commands/upgrade-project.md`; `docs/onboarding.md`; `README_DEV.md`; `scripts/CLAUDE.md`; `docs/architecture.md` | PASS |
| REQ-19 | `[]` | 3 test(s) -- `tests/acceptance/test_merge_triggers_texts.py` (test_one_architectural_record_partially_supersedes_dec_424_with_its_required_sections, test_the_record_names_the_fleet_reach_and_the_squash_merge_limit, test_dec_424_links_back_to_the_record_and_stays_accepted) | 2 file(s) -- `.ai-state/decisions/425-merge-in-triggers-for-commit-and-rebase.md`; `.ai-state/decisions/424-observation-log-keeps-its-history.md` | PASS |

## Key Decisions

One ADR landed (`dec-425`, architectural), no user decision was needed (fleet reach was accepted with `dec-424`), and five architect decisions plus one ruling live in `SYSTEMS_PLAN.md` (context copied from there and from `LEARNINGS.md`).

**[systems-architect] D1 -- `post-commit` recognises a merge finished by a commit by structure (`dec-425`)**: behind the primary-tree and rebase-directory gates and a parent count, copy when `HEAD@{1}` equals `HEAD^1`. **Why**: the reflog subject is caller-controlled, `MERGE_HEAD` is deleted before the hook, `ORIG_HEAD` can be overwritten; the structure test costs one query on an ordinary commit and none during a replay or in a linked worktree. **Declared limit**: a reflog disabled from `git init` makes the test unanswerable, so such a repository copies nothing and falls back to teardown and P14.

**[systems-architect] D2 -- `post-rewrite`: `rebase` runs merge-in only against `ORIG_HEAD`; `amend` does nothing (`dec-425`)**: the on-main finalize stays state-driven; reading the rebase state's private `orig-head` file was rejected as git-private layout that would also silence the named skip.

**[systems-architect] D3 -- one source of truth for the hook names with literal mirrors and a parity test (`dec-425`)**: delegating the installers to the reconciler contradicted the pin upgrade's separate cross-version loop; runtime derivation added a CLI surface and still left the dispatcher literal.

**[systems-architect] D4 -- the named skip is an additive CLI flag** (`--skip-unresolvable-before`): a new exit code would re-mean the exit-code contract; a bash pre-check would duplicate the "does any worktree hold a log" rule.

**[systems-architect] D5 -- texts recorded as exact replacements**; `docs/architecture.md` written after the code, present-tense; the onboarding skill's Phase 4 predicate included.

**[systems-architect] F-1 ruling (after the Step 3 light review)**: a rebase that rewrites no commit fires no `post-rewrite` and no other usable hook; it joins the squash merge as a named limit, with no code change and nineteen exact text replacements; a correction to the review's probe (a drop-all rebase recreated an identical commit in the same second). REQ text unchanged; the extract digest held.

**Process**: Standard tier, 13 of 16 spawns; the design spawn hit its turn cap with everything but a tag written (closed by the orchestrator, no resume); the acceptance commit turned the owner package's private-reader gate red through a new driver's fixture text (allowlisted by the orchestrator between Steps 2 and 3 -- an acceptance design that adds a driver must run the three owner gates); every implementer step landed in one spawn; the forced light review of the chain step accepted it and found the F-1 gap.

**Declared limits** (`SYSTEMS_PLAN.md`): the squash merge; a rebase that rewrites no commit; a repository whose reflog was disabled from `git init`; `/merge-worktree` step 9.5 and P14 cover all three.

**Follow-up to `wal-retention`.** With this spec the only merge shapes that leave a worktree's log to teardown are the two named above; the `wal-modes` effort's log now outlives its worktrees on every path git reports.
