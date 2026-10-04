---
id: dec-424
draft_id: dec-draft-10dba96c
title: The observation log keeps its history — numbered archives behind the reader, worktree logs merged in at merge time, and a log-health family
status: accepted
category: architectural
date: 2026-10-03
summary: "Rotation keeps five numbered archives shifted by rename inside the writer's lock (count-bounded, 26-week target); a copy-path merge-in in the owner package appends a worktree's rows the main log lacks (whole-row identity) at /merge-worktree and from the post-merge finalize chain for every worktree that merge newly brings in; the spawn counter reads every checkout; sentinel family P09-P14 audits archives, rotation, segment integrity, helper share, recorded mode source and unmerged worktree logs"
tags: [observability, observations-jsonl, wal, retention, rotation, worktrees, merge-in, sentinel, log-health, spawn-budget, td-308]
made_by: agent
agent_type: systems-architect
branch: worktree-wal-retention
pipeline_tier: full
affected_files:
  - hooks/_observation_log/
  - scripts/spawn_count.py
  - scripts/reconcile_pipeline_state.py
  - scripts/project_metrics/collectors/cost_collector.py
  - scripts/project_metrics/collectors/cost_collector_read.py
  - scripts/check_agent_lifecycle_pairing.py
  - scripts/finalize_chain.sh
  - commands/merge-worktree.md
  - agents/sentinel.md
  - tests/test_sentinel_row_contract.py
  - .gitignore
  - scripts/onboard-project
  - scripts/upgrade_project_pins.sh
  - skills/onboard-project/references/phases-core.md
  - eval/src/praxion_evals/live/scenarios.py
  - scripts/merge_worktree_log.py
  - scripts/check_observation_log_health.py
affected_reqs: [REQ-01, REQ-02, REQ-03, REQ-04, REQ-05, REQ-06, REQ-07, REQ-08, REQ-09, REQ-10, REQ-11, REQ-12, REQ-13, REQ-14, REQ-15, REQ-16, REQ-17, REQ-18, REQ-19, REQ-20, REQ-21, REQ-22, REQ-23, REQ-24, REQ-25, REQ-26, REQ-27, REQ-28, REQ-29, REQ-30]
supersedes_in_part: [dec-250]
dissent: "A post-merge step that copies rows into every managed project's log on every pull is fleet-wide machinery for a problem only pipeline worktrees have; reading worktree logs where they live, plus an explicit copy at /merge-worktree, would serve Praxion without touching the fleet's git hooks."
---

## Context

`dec-401` gave the observation log one owner package and explicitly left three items to this pipeline: "retention and archives (the reader's `segments()` is the extension point for the following pipeline), worktree-log merge-in, and the log-health sentinel check." Measured on 2026-10-03:

- **Rotation destroys history.** `dec-250` keeps one archive: "the next rotation overwrites it." The `.1` holds 2026-08-07 → 2026-09-25, and everything earlier is gone. `dec-377`'s reversal trigger names this exact gap ("…or widen the local retention window").
- **Worktree rows vanish.** Ten worktrees held about 4,650 rows main's log never saw. `/merge-worktree` step 7 claims to reconcile `observations.jsonl`, but `reconcile_ai_state.py` acts only on git-conflicted paths and the log is gitignored, so the step is inert. Step 10 then deletes the worktree's log. The spawn counter reads only its own checkout, so a pipeline split across checkouts is under-charged (td-308).
- **Nothing checks the log's health.** The September defects (rows dropped from a subdirectory cwd, `dec-414`; hooks silently off) were found by accident. `dec-401` added `log_mode_source` to `session_start` rows for this check, with the instruction to remove the field if this pipeline does not consume it.
- **Hand-built archive paths remain** in the recovery reconciler and the cost collector, so `dec-401`'s single-owner invariant held only for the active file.

## Decision

1. **Retention is a policy module in the owner package**, `hooks/_observation_log/retention.py`: `SIZE_CAP_BYTES` (10 MiB, unchanged), `ARCHIVE_COUNT = 5`, `HISTORY_TARGET = 182 days`, and the only builder and parser of archive names (`<log>.<position>`, 1 = newest).
   - **Rotation (writer, inside the existing lock):** at the cap, find the lowest missing position in `1..N`. If there is one, shift the positions below it up by one; otherwise shift `N−1 → N`, dropping the oldest. Then rename active → 1. It only renames: no row is read or rewritten, and nothing is listed below the cap.
   - **A failed rename** leaves a gap that the next rotation fills.
   - **Retention is bounded by count only.** An age limit could only delete history earlier.
   - **Why five:** at measured growth, five archives hold about 35 weeks under `full` (7 weeks per segment) and about 70 under `standard`; both clear the 26-week target. The disk bound is 60 MiB plus one append per checkout.
2. **Discovery stays in `segments()`.** `reader.segment_listing()` scans for numbered archives, returns them oldest first and reports missing positions; `segments()` derives from it with its signature unchanged. *Bounded at Step 15a (W-2):* a missing position is reported only up to the policy's count. A surplus position, above the count, is still read as history and warned on by P09, but never opens a gap below it, so a backup named like `observations.jsonl.20261003` no longer yields millions of "missing" paths. The reconciler and the cost collector delete their hand-built `.1` paths and take segments from the reader. The reconciler's age window now bounds every segment by row time; it keeps a row of unreadable time only in the active log.
3. **Merge-in is a copy path in the owner package**, `hooks/_observation_log/merge_in.py`, with the CLI `scripts/merge_worktree_log.py` (`--worktree PATH | --merged`, exit 0 complete / 1 degraded / 2 input error).
   - **Copy.** It reads the worktree's segments raw and skips every row whose **identity** — a digest of the row's canonical JSON as stored, i.e. whole-row equality — is held by any main-log segment. It appends the rest through the writer's lock with per-row rotation. Copied rows are unchanged, so `project` and `log_mode` survive.
   - **Mode.** Only `off` suppresses the copy, because recording modes govern recording, not the copying of rows already recorded.
   - **Never touched.** The worktree's log is never written.
   - **Degraded runs.** If any main segment is unreadable, the run copies nothing and reports `degraded`, since duplicates cannot be ruled out.
4. **Two triggers, one entry point.**
   - `/merge-worktree` runs `--worktree` before teardown and keeps the worktree when the result is degraded, unless the user discards it.
   - The post-merge finalize chain (`finalize_chain_post_merge`) runs `--merged` in the primary working tree under in-repo placement. That covers every linked worktree **this merge brings in**: one that holds a log, whose `HEAD` is contained in the primary checkout's `HEAD`, and whose `HEAD` is not contained in `ORIG_HEAD`, the pre-merge tip `git merge` and `git pull` record. The step is non-blocking, like the rest of the chain. User decision SQ-1, 2026-10-03: ship it. *Narrowed at Step 8a* (light review F1): the first cut used `HEAD` alone. That also copied a worktree with no commits of its own, contained from the moment it was created, while its sessions ran, and P03 on main then reported their agents as never stopped. For an abandoned or squash-merged worktree that report is permanent.
   - Both entry points resolve the recording mode the way the project sets it: the process environment when it defines a mode key, else the main checkout's `.claude/settings.local.json` over `.claude/settings.json` `env`. A git hook does not see Claude Code's settings `env`, and onboarding writes `PRAXION_DISABLE_OBSERVABILITY` there (Step 8a, F5). *Amended at Step 15a (W-9):* the precedence is per key, the way Claude Code writes a settings `env` over the shell's. Each mode key comes from `.claude/settings.local.json`, else `.claude/settings.json`, else the process environment. A shell export of one key therefore no longer hides the project's setting of the other.
5. **Cross-checkout reading** comes from one package function, `checkouts.repository_checkouts()`, over `git worktree list`.
   - The spawn counter reads every checkout's segments, deduplicates by identity and orders rows by recorded time. It withholds, naming the path, on an unreadable segment (`wal-unreadable`), a missing position (`wal-gap`) or a failed listing (`checkouts-unlisted`). This closes td-308.
   - P03 and the reconciler also order by recorded time, because merge-in appends rows out of time order.
6. **A log-health family**, `scripts/check_observation_log_health.py`, adds rows P09–P14 to the sentinel's Pipeline Discipline dimension: archive coverage against the policy, rotation state, segment integrity (malformed lines, unreadable segments), helper share (information only), recorded mode source (consuming `log_mode_source`), and worktree logs unmerged past 14 days or unreadable (the unreadable case was added at Step 15a, FAIL-2). It skips with the three named substrate states. It is registered in the catalogue, the dispatch table and `EXTRACTED_CHECKS`, with a canary per id.
7. **Every archive is gitignored by glob** (`.ai-state/observations.jsonl.*`) in Praxion, the onboarding block and the upgrade path. The live eval treats every archive as a hook byproduct.

New components (the `architectural` falsifier):

- `hooks/_observation_log/retention.py`, `checkouts.py` and `merge_in.py`;
- `scripts/merge_worktree_log.py` and `scripts/check_observation_log_health.py`.

Responsibility moved: archive naming moves out of the writer and two consumers into `retention.py`. Published contracts changed: the shipped post-merge hook behaviour and the onboarding `.gitignore` block. The two new scripts join `affected_files` once they exist.

Activation: fired — structural (about 17 files across the hooks package, consumer scripts, the git hook chain, the sentinel prompt and onboarding), with real alternatives for archive naming, the merge-in key and the trigger. Lens set: Security, Performance, Simplicity, Testability. Convergence: stable. REQ-01..REQ-30 were unchanged by the design except for the two Spec-Question clarifications, REQ-07's active-log window and REQ-24's denominator, which are text amendments, not added or removed REQs.

## Considered Options

### Archive scheme

- **Numbered positions shifted by rename, count-bounded (chosen).** Keeps the existing `.1` as position 1, so the legacy archive becomes position 2 at the first rotation. Uses only renames, and at most N stats, only at the cap. A missing archive is detectable as a missing position. *Con:* up to N renames per rotation; a mid-shift fault leaves a gap that the next rotation fills.
- **Timestamped archive names.** One rename per rotation; pruning by directory listing. *Con:* there is no sequence, so a lost archive is indistinguishable from a quiet period, and pruning lists a directory under the lock.
- **One larger archive** (active appended to `.1`, head trimmed). *Con:* O(size) reading and rewriting under the lock, the shape `dec-250` already rejected.
- **Compressed archives.** *Con:* compressing 10 MiB under the lock; a possible later increment off the hot path.

### Merge-in key

- **Whole-row identity (chosen).** Exact, because rows are copied unchanged, and it cannot fold distinct events.
- **`reconcile_observations`' `timestamp|session_id|event_type|tool_name`.** *Con:* folds two `agent_start` rows of one session at the same instant (no `tool_name`) and two gate fires of one commit.

### Merge-in vs reading in place

- **Copy into the main log (chosen),** with the spawn counter also reading live worktrees in place.
- **Read every checkout in place, never copy.** *Con:* rows die with `git worktree remove`, which is the defect being fixed.

### Trigger

- **`/merge-worktree` plus a post-merge step over the worktrees that merge brings in (chosen at Step 8a).** Every linked worktree's `HEAD` is tested against the merge's after-tip (`HEAD`) and before-tip (`ORIG_HEAD`), and no branch name is parsed. That covers fast-forward merges, merge commits, pulls and pulled pull-request merge commits alike.
- **`/merge-worktree` plus a post-merge step over every contained worktree (first cut, refuted by the Step 8 light review, F1).** *Con:* a worktree with no commits of its own is contained while its sessions run. Its partial sessions reach main's log and P03 WARNs about live agents, permanently once that worktree is squash-merged or abandoned. It also re-read every kept worktree's log on every merge or pull.
  - *Rejected repairs:* copying only sessions with a `session_stop` row (written at every turn end, not session end, and it turns the REQ-11 acceptance nodes red); skipping logs younger than an age (a heuristic, also red on REQ-11); teaching P03 that rows of a live checkout are in flight (cross-checkout knowledge in a sentinel check, and no help after removal).
- **Post-merge detecting *the* merged branch by name from the reflog.** *Con:* the event detection the finalize chain abandoned, because it silently skipped non-merge paths.
- **A SessionStart sweep.** *Con:* a whole-log scan on every session start.
- **The command only.** *Con:* misses `git merge` and pull-request merges, which the pipeline exit procedure permits.

## Consequences

**Version skew (recorded, not fixable in code).** A hook process from an earlier plugin release (0.43.0/0.44.0) renames the active log onto `.1` under the same lock; while such a process writes beside a current one, it overwrites the newest archive, and the rotation-state check cannot see it. The window closes when every writer is on this release. Lowering the archive count later needs a migration of the positions above the new count.

**Accepted leftover (first): partial copy of a running session (Step 8a residual).** A merge taken while the merged worktree's own agents still run copies their starts without their stops. P03 on main WARNs until the next merge bringing in that worktree's later commit, or `/merge-worktree`, copies the rest. Praxion merges after verification, when the pipeline's agents have stopped.

**Accepted leftover (second): a worktree branched from `origin/main` (light review N1 residual).** A worktree branched from `origin/main` while the local main was behind is brought in by the next pull, commits or not; its running agents show as unstopped in P03 until a later merge copies the rest.

**Positive**

- History grows from about 7 weeks to 35–70 weeks with a fixed disk bound, and no rotation reads or rewrites a row.
- A pipeline's spawns, stops, costs and gate fires outlive its worktree. The spawn counter sees a split pipeline whole (td-308).
- Every history reader inherits the policy through `segments()`; no consumer builds an archive path.
- The log's health is audited every sentinel run. `log_mode_source` has its consumer, so `dec-401`'s field stays.

**Negative**

- **Fleet reach and cost.** Every onboarded project's `post-merge` hook (a symlink into the plugin) runs the merge-in step from the next plugin release; the release notes name it.
  - *Measured on the first cut* (Step 8 light review F4; median of 5 runs on Python 3.13, scratch repository with copies of this repository's logs):
    - 0.04 s with no worktrees;
    - 0.12 s with ten worktrees and no logs (one `git merge-base` per worktree, run before any log check);
    - 0.37 s steady state at today's sizes, because every kept worktree with a log forced a full main-log identity read on every merge or pull;
    - 1.08 s with the main log at full retention (six segments, 55 MB).
  - *Under the Step 8a rule:* a merge or pull costs one `git worktree list`, one stat and scan per linked worktree, and two `merge-base` calls per worktree holding a log. The main-log identity read happens only at the merge that brings a worktree in, about 1 s at full retention, once per pipeline.
- **Recording mode in a git hook (F5).** Only the project's settings layers are read (`.claude/settings.local.json` over `.claude/settings.json`), key by key over the process environment since Step 15a (W-9). User-scope and managed-policy `env` are not read, so a mode set only there is invisible to the hook. Rows keep the mode they were recorded under in every case.
- **Squash merges** leave the worktree's `HEAD` uncontained and are not merged in by the hook. `/merge-worktree` or P14's warning covers them. Worktrees discarded with `ExitWorktree` remove still lose their rows.
- **Merges git completes outside `git merge`** run no `post-merge` hook (probed on git 2.44.0). These are a merge stopped on a conflict, or run with `--no-commit`, and then finished with `git commit`; and a pull that rebases local commits onto the incoming ones. Such a worktree is not merged in at that merge. No later merge brings it in either, because its `HEAD` is already in that merge's `ORIG_HEAD`. It is covered as a squash merge is: `/merge-worktree` step 9.5 at teardown, P14's warning past the age limit, or `scripts/merge_worktree_log.py --worktree <path>` by hand. *Named at Step 15a (W-1).* A `post-commit` step for two-parent commits and a `post-rewrite` step for rebases would close it, but both reach every onboarded project's hooks, so they are the user's decision and are not built.
- **Merge-in's identity read is outside the writer's lock** (Step 15a, W-8, accepted with a ledger row). A hook rotation during the main-index read, or two concurrent merge-ins of one worktree, can append an already-held row once more. No row is ever lost. Identity-deduplicating readers and a re-run merge-in count the copy once; P03, P12 and P13 may not. Holding the writer's lock for the read would stall every hook for about a second at full retention.
- **Merged rows are distinguishable only by `project`.** `gate_fire` and `compaction` rows carry no `project`, so their origin is recoverable by session only.
- **`dec-400`'s residual window widens.** Legacy helper `agent_stop` rows and `pre-attribution` cost rows now leave after five rotations, not one. The reader's upcast and the cost collector's provenance classes already handle them; the residual counts simply persist longer.
- **New withhold reasons.** The spawn counter can now withhold because of another checkout's unreadable log; that is deliberate, since a silent partial count is the failure it exists to refuse.
- **Two checkout enumerations coexist.** The cost collector keeps its own crawl behind its documented patch seam; unifying the two is a follow-up.

## Disconfirmation

- **Falsifier:** any of the following:
  - P09's "archive count at the policy count, span below target" warning fires on Praxion's own log at `standard`: the count is wrong for real volume.
  - The post-merge step measurably slows a pull in a managed project, beyond about 2 s.
  - A spawn-count or P03 verdict over a real log differs between time-ordered and arrival-ordered rows after this change.
  - A merged row is ever counted twice by a consumer, outside the identity-read race named in the Consequences.
  - A P03 WARN on main traces to a partial copy the post-merge step took of a worktree's running session, outside the narrow residual named in the Consequences.
- **Steelmanned runner-up:** timestamped archives with no merge-in hook. Rotation becomes one rename, with no shift, no gap states and no partial-failure reasoning. Readers order by name. Merge-in happens only at `/merge-worktree`, which keeps the fleet's git hooks untouched. Praxion's own pipelines all exit through that command when the user remembers. Its weaknesses are real but bounded: a lost archive is undetectable, and a pipeline merged by `git merge` or a PR silently keeps its rows in a worktree that is later removed. If Praxion's exit procedure were narrowed to `/merge-worktree` only, the runner-up's fleet argument would win.
- **Reversal trigger:** revisit if any of the following happens:
  - Claude Code or git gains a worktree-removal hook, which would make the post-merge step redundant.
  - P09's span warning fires in two consecutive sentinel runs; raise `ARCHIVE_COUNT` or lower the target.
  - The managed-project feedback loop reports post-merge noise or latency from this step; narrow it to `/merge-worktree` and P14.
  - The pipeline exit procedure is narrowed to `/merge-worktree` only, at which point the hook step should be retired.
  - A lost worktree log or a P14 warning traces to a merge the hook did not see (a conflicted or `--no-commit` merge, or a rebasing pull). If so, add the `post-commit` trigger for two-parent commits (`--merged --before HEAD^1`) and the `post-rewrite` trigger for rebases (`--before ORIG_HEAD`), with the user's agreement, since both reach the fleet.

## Prior Decision

This ADR **narrows `dec-250`** (partial supersession). Two clauses change:

- Decision clause 1's "A single archived segment is kept; the next rotation overwrites it." It becomes "five numbered archives are kept; a rotation shifts them by rename and drops only the oldest."
- Decision clause 3's two-file read ("the active file **and** `observations.jsonl.1` when the segment's mtime is within the window"). It becomes every archive newest first while its mtime is inside the window, with the window applied to every segment by row time.

These survive unchanged: rotate-and-archive as a best-effort, `OSError`-swallowing rename **inside the append lock**; archives **gitignored** and outside every merge driver; and the reconciler's **windowed** read with its 7-day default. `dec-250` stays `accepted` and gains this record in `superseded_in_part_by`.

Related, without a frontmatter relation:

- **`dec-401`:** this record discharges its "Not in this decision" hand-off. It uses `segments()` as the extension point that record named, and it consumes `log_mode_source`. No clause of `dec-401` is narrowed: its single-owner and three-gate contracts are extended to the new modules.
- **`dec-377`:** the WAL stays out of git. This record is the "widen the local retention window" alternative its reversal trigger names, not a reversal.
- **`dec-413` and `dec-414`:** `project` still means the checkout that recorded the row, and merged rows keep it.
