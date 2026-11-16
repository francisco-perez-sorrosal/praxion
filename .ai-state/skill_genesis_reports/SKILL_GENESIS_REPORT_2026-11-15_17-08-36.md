---
schema_version: 1
report_id: skill-genesis-2026-11-15_17-08-36
generated_at: 2026-11-15T17:08:36
task_slug: skill-genesis-2026-11-15
agent_version: skill-genesis@89e70d55
invocation_args: { since: null, scope: null, sources: /Users/fperez/dev/praxion/.ai-work/_harvest, batch: "8 of 11", dry_run: false }
review_status: pending
disposition_count: { pending: 3, approved: 0, rejected: 0, refined: 0, deferred: 0 }
---

# Skill Genesis Report — 2026-11-15 17:08:36

## Summary

2 queue sources (`wal-retention`, `wal-modes-core`) analyzed, 19 learning items extracted, 3 proposals generated (all skill updates), 16 deduplicated or skipped. Both sources describe the same observation-log work (modes and owner package; retention, rotation and worktree merge-in), so most items were already carried by an artifact or by a pending proposal of an earlier report of this run. Review status: pending.

## Learning Sources Consumed

| Source | Path | Items Extracted | Status |
|---|---|---|---|
| Queue source: wal-retention | `.ai-work/_harvest/wal-retention/LEARNINGS.md`, `VERIFICATION_REPORT.md` | 11 | Read (LEARNINGS whole except lines 1-58, the Decisions block; VERIFICATION rounds 1-2 dispositions and recommendations) |
| Queue source: wal-modes-core | `.ai-work/_harvest/wal-modes-core/LEARNINGS.md`, `VERIFICATION_REPORT.md` | 8 | Read (LEARNINGS whole; VERIFICATION round-1 dispositions and new findings) |
| CONSULT_*.md fragments | both source directories | 0 | Not found |
| Latest SENTINEL_REPORT / IDEA_LEDGER / ADRs / calibration log | n/a | 0 | Not consulted (queue mode; the sources carry the learning) |
| Earlier reports of this run | `.ai-state/skill_genesis_reports/SKILL_GENESIS_REPORT_2026-11-15_*.md` (7) | n/a | Read (proposal titles and triage lines) |

## Triage Results

| # | Item | Source | Decision | Rationale |
|---|---|---|---|---|
| 1 | A `git add && git commit` in one Bash call passes the id-citation commit gate (hook fires before `git add` runs) | modes-core LEARNINGS | Skip | Fixed and documented: `scripts/CLAUDE.md:47` (`_commit_scope.py` adds paths a `git add` earlier in the same call stages) |
| 2 | `dispatch-reworks`: `claude --bg` in a `while read <<EOF` loop eats the heredoc; unnamespaced `/resume-rework`; session id taken from the wrong field | modes-core LEARNINGS | Skip | Fixed in code: `scripts/dispatch-reworks:265,321,340` (`/praxion:resume-rework`, `< /dev/null`); stdin idiom is general shell knowledge |
| 3 | Dual-import seam: patch the module object the hook imported, not `hooks.<pkg>.X` | modes-core LEARNINGS (correction 147) | Skip | Pending: 17-04-31 Proposal 2 |
| 4 | `Files:` entries disjoint across steps; the reconciler reads `Files:` only at line start / to end of line | retention LEARNINGS Gotchas, N-3 | Skip | Pending: earlier reports' `Files:` proposal; `scripts/CLAUDE.md:14` row |
| 5 | Take final footprint readings after the last commit touching a measured path | retention Step 15c, FAIL-1 | Skip | Present: `skills/spec-driven-development/references/footprint-criteria.md:54` |
| 6 | Write the report skeleton first so a capped verifier resumes | retention VERIFICATION | Skip | Present: `agents/verifier.md:23` (Write early, finish last) |
| 7 | All three implementers hit the 100-turn cap; two steps per spawn did not hold | modes-core Step 6 close-out; retention sizing | Skip | Present: `skills/software-planning/SKILL.md:140` (60% of window sizing) |
| 8 | Bound driver turned a "never blocks" scenario false-green (oracle holds on any repo with nothing to run) | retention Step 1 | Skip | Same class as pending 17-04-31 Proposal 2 (assert the scene before reading a verdict); noted there as an extra instance |
| 9 | Intake missed prompt readers/writers (`agents/`, `commands/`); grep them too | modes-core Gotchas | Skip | Present: `decomposition-guide.md:39` (grep with no include filter) |
| 10 | Post-merge hook firing matrix (conflicted merge, `--no-commit`, rebasing pull do not fire) | retention Assumptions | Skip | Pending: 16-51-16 Proposal 1 |
| 11 | A git-hook-run script does not see the project's `settings.json` `env` block; resolve the setting from the files, key by key | retention Step 8, 8b, 15a/15b, W-9 | Skill (update) | Proposal 1; not in repo (searched `skills/hook-crafting/SKILL.md`, `rules/swe`, `docs/*.md`) |
| 12 | Filesystem-fault tests: directory-where-file-should-be bites as root, chmod skips as root; git reports resolved paths (`/private/var`); "returned at once" pinned by call-count spy | retention Step 6, 15b | Skill (update) | Proposal 2; not in repo (searched `skills/testing-strategy`, `skills/python-development`, `agents/test-engineer.md`) |
| 13 | A claim that sibling consumers "already degrade" is probed with one fixture per consumer | retention B1/FAIL-2, Step 8b; modes-core WARN-2 | Skill (update) | Proposal 3; two pipelines; no match for the wording in `agents/`, `skills/`, `rules/` |
| 14 | A Step-1 characterization test pins code a later step deletes by design; the plan must name the retarget | modes-core close-out (plan defect) | Skip | One occurrence; same family as pending 16-39-41 Proposal 1 (check every test that pins a contract) |
| 15 | Acceptance sources cite output formats from `--help`/docstrings, not executed base output | retention W-11 | Skip | Advisory, no failure resulted; earlier reports of this run already carry the output-format theme |
| 16 | Canary-coverage meta-test wants a direct call by name; private-reader gate greps docstrings | retention Step 10 | Skip | Repo-specific; the gates' own failure messages say it |
| 17 | `row_time` returns a `UNTIMED` sentinel; never subtract from it; reader decodes `errors="replace"`; non-object JSON line is malformed | retention Step 3/5, modes-core Step 5 | Skip | Documented in `hooks/_observation_log/reader.py`; narrow |
| 18 | Decisions (Q3 `"0"` resolves to standard; owner package; helper_stop; no intermediate mode) | both Decisions Made | Skip | Recorded in ADRs |
| 19 | Upcast rule relabelled pre-`usage_source` real agents; a fault-injection fixture caught it | modes-core Step 7 | Skip | Narrow to this reader |

## Discipline-Gap Signals

None recorded.

## Proposals

### Proposal 1: A script a git hook starts does not see the project's `env` block

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: sapling
- **Scope**: narrow
- **Priority**: P1 (next-cycle)
- **Source(s)**: wal-retention `LEARNINGS.md` Step 8 ("the hook process sees the user's shell variables, not the project's `.claude/settings.json` `env` block, so a project that set the recording mode to `off` there still has contained worktree logs copied"), Step 8b (mode resolved from the process, else `settings.local.json` over `settings.json`), Step 15a/15b (W-9: per-key layering, `mode_source` names the layer); `VERIFICATION_REPORT.md` round 1 W-9 and round 2 closure.
- **Description**: Add one gotcha to `skills/hook-crafting/SKILL.md` beside the git-hook environment bullet: a script that a git hook or the finalize chain starts runs outside any Claude session, so a project setting made in `.claude/settings.json` `env` is absent from its environment. A script that must honour such a setting reads the settings files itself, resolves each key separately (process, then `settings.json`, then `settings.local.json`, the last layer that supplied the key wins), and reports which layer decided. Wholesale precedence ("the process wins if it defines either key") is the failure.
- **Rationale**: The defect shipped in design, was found by the forced review, then needed a ruling and a rework step (W-9); a fleet-reaching post-merge step depends on it. The existing bullet covers git's own variables only.
- **Estimated scope**: SKILL.md edit, one bullet
- **Overlap check**: `skills/hook-crafting/SKILL.md:70` (git environment variables, different subject); `rules/swe/gate-liveness.md:20` (prove a gate runs in the environment it guards, does not name settings); `docs/onboarding.md:86` (the key is written to `settings.json`). Pending 16-51-16 Proposal 1 is about recognising the git event, not configuration.
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `skills/hook-crafting/SKILL.md`

### Proposal 2: Filesystem-fault and speed-bound tests — bite as root, resolve both paths, count calls

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: sapling
- **Scope**: narrow
- **Priority**: P2 (someday)
- **Source(s)**: wal-retention `LEARNINGS.md` Step 6 Gotchas (macOS `/var` to `/private/var`: `git worktree list` prints the resolved path, so compare against `Path.resolve()`; unreadable-segment tests put a directory where a file should be so they bite for root; one chmod test skips for root), Step 15b (the "returned at once" claim pinned by a call-count spy on `archive_path`, not a timer; the old code called it ~20M times), Step 1 (chmod fixtures); `VERIFICATION_REPORT.md` round 1 W-2 (the far-copy tests never finished on the old code, 4 GB RSS) and round 2 (fixture teardown restores in reverse).
- **Description**: A short block in `skills/testing-strategy/references/python-testing.md`: (1) to force an unreadable path prefer a directory in place of a file (works as root), and where chmod is needed, skip under root explicitly and restore modes in reverse in teardown; (2) on macOS the temp directory is a symlink, so compare any path a tool printed (git, `os.getcwd`) with `Path.resolve()` of both sides; (3) pin "returns promptly / bounded work" with a call-count spy on the loop's inner function, never a timer, and make the old code fail it deterministically.
- **Rationale**: Three independent traps hit one pipeline; each is invisible on a developer machine until CI runs as root or on Linux, and the spy-over-timer rule extends the existing "no wall-clock dependencies" line with a concrete substitute.
- **Estimated scope**: one block in one reference page (about 10 lines)
- **Overlap check**: `skills/testing-strategy/SKILL.md:94,132` (no sleeps, no wall-clock dependencies; no substitute named); `python-testing.md` has no root, chmod or symlink content (searched `skills/testing-strategy`, `skills/python-development`, `agents/test-engineer.md`).
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `skills/testing-strategy/references/python-testing.md`

### Proposal 3: "The other consumers already handle it" is probed, one fixture per consumer

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: sapling
- **Scope**: narrow
- **Priority**: P1 (next-cycle)
- **Source(s)**: wal-retention `LEARNINGS.md` Final verification ("the Step 8b lane's claim that every reader 'already degrades' was an unsurfaced assumption (verifier B1) that scoped td-326 too narrowly"; verifier pattern 2: 'Already degrades' claims about sibling consumers must be probed: one chmod-000 fixture per consumer settled it) and Step 8b ("Not done: the other consumers of `SegmentListing.error`"); wal-modes-core `VERIFICATION_REPORT.md` round 1 WARN-2 (P03 read an unreadable log as clean; the lesser instances in `spawn_count`, `reconcile_pipeline_state`, `query_memory_write_evidence` were split to a ledger row).
- **Description**: Extend the Surface Assumptions deep dive in `skills/software-planning/references/behavioral-contract.md` with a worked case: when a change narrows a debt row, a requirement or a fix to "the others already handle this", the claim is evidence only after one probe per named consumer (a fixture that triggers the case and shows the consumer's output). An unprobed claim is written as an assumption and the row stays wide.
- **Rationale**: Two pipelines had a verifier turn the same unprobed sibling claim into a FAIL or a ledger row. Pending 16-58-47 Proposal 5 covers a tool's behavior written into a template or contract; a claim about other callers is a different object and needs its own sentence.
- **Estimated scope**: one paragraph in one reference page
- **Overlap check**: `agents/verifier.md:204` (the tag, no guidance on this case); pending 16-58-47 Proposal 5 (adjacent, may be merged by the reviewer); `decomposition-guide.md:39` enumerates consumers by grep but does not require probing them.
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `skills/software-planning/references/behavioral-contract.md`

## Recommended Delegations

| Proposal | Delegation Path | Notes |
|---|---|---|
| 1 | context-engineer | Skill update; load skill-crafting; keep to one bullet |
| 2 | context-engineer | Reference-page edit; keep under 10 lines |
| 3 | context-engineer | Reference-page edit; consider merging with 16-58-47 Proposal 5 at review |

## Disposition Log

<!-- Populated by /skill-genesis-review. Empty on report creation. -->

| Timestamp | Proposal | Disposition | Notes |
|---|---|---|---|
| _(empty — pending review)_ | | | |

## Recommended Next Steps

- Run `/skill-genesis-review` to disposition the 3 pending proposals.
- After approval, invoke `context-engineer` for the skill updates.
- Remaining batches of this run (9 to 11) may repeat the observation-log themes; deduplicate against this report.
