---
schema_version: 1
report_id: skill-genesis-2026-11-15_17-04-31
generated_at: 2026-11-15T17:04:31
task_slug: skill-genesis-2026-11-15
agent_version: skill-genesis@89e70d55
invocation_args: { since: null, scope: null, sources: .ai-work/_harvest, batch: "7 of 11", dry_run: false }
review_status: pending
disposition_count: { pending: 4, approved: 0, rejected: 0, refined: 0, deferred: 0 }
---

# Skill Genesis Report — 2026-11-15 17:04:31

## Summary

2 queue sources analyzed (`ledger-triage`, `merge-triggers`), 22 items extracted, 4 proposals generated (all skill updates), 18 not proposed (11 already carried by an artifact, 3 folded into pending proposals of earlier reports of this run, 4 too narrow or transient). No discipline-gap signal. Review status: pending.

Interpretation and assumptions: both sources are old pipelines (mtime 2026-10-03) whose lessons were partly written into artifacts by the memory-to-artifacts and handoff-lessons batches; I proposed only what a search of the repository did not find. Assumption (not load-bearing): "carried" means the lesson's remedy is stated, not merely its topic.

## Learning Sources Consumed

| Source | Path | Items Extracted | Status |
|---|---|---|---|
| LEARNINGS.md (ledger-triage) | `.ai-work/_harvest/ledger-triage/ledger-triage/LEARNINGS.md` | 11 | Read |
| VERIFICATION_REPORT.md (ledger-triage) | same dir, 94 KB | 4 | Sampled (R4 section read whole; R3, R1+R2 and original sections skipped: superseded, their findings are restated in R4) |
| LEARNINGS.md (merge-triggers) | `.ai-work/_harvest/merge-triggers/LEARNINGS.md` | 6 | Read |
| VERIFICATION_REPORT.md (merge-triggers) | same dir | 1 | Read (rounds 1 and 2, convention, architecture, test-coverage sections) |
| CONSULT_*.md | both dirs | 0 | Not found |
| Sentinel report, idea ledger | `.ai-state/` | 0 | Not read (queue mode; sources are the batch) |
| ADRs | `.ai-state/decisions/` | 0 | `425-merge-in-triggers-for-commit-and-rebase.md` matched for dedup only |
| Calibration log Retrospective cells | `.ai-state/calibration_log.md` | 0 | Not read |
| Earlier reports of this run | `SKILL_GENESIS_REPORT_2026-11-15_16-39-41` .. `16-58-47` | n/a | Read for dedup (proposal headings and triage tables) |

## Triage Results

| # | Item | Source | Decision | Rationale |
|---|---|---|---|---|
| 1 | Recognising a finished merge, amend or rebase inside a git hook: reflog subject is caller-controlled, `HEAD@{1}` vs `HEAD^1`, `git merge` runs no post-commit, post-rewrite fires only for a non-empty rewrite list | merge-triggers LEARNINGS Decisions, Gotchas; VERIFICATION P5 nuance | Skill (update) | Proposal 1; not in `skills/hook-crafting/` (searched; `SKILL.md:70` covers env only) |
| 2 | A probe silently builds a different scene than labelled (same-second `cherry-pick` and `amend` reproduce the commit; `git init <dir> -c` creates nothing; a fixture helper's `add -A` made the "untracked" case tracked) | merge-triggers LEARNINGS Gotchas; ledger-triage VERIFICATION R4 observation | Skill (update) | Proposal 2; `gate-canaries.md:48` covers only the mutation half |
| 3 | Injectable seam whose tests all pass a stub never exercises the real adapter (existence check posing as reachability) | ledger-triage LEARNINGS R1 | Skill (update) | Proposal 3 |
| 4 | A test name claims a property its harness cannot observe (byte-for-byte, no shell run) | ledger-triage VERIFICATION R4 | Skill (update) | Folded into Proposal 3 |
| 5 | Random fixture data that must meet a grammar flakes (12-char sha lacks a digit ~0.4% of runs) | ledger-triage LEARNINGS R1 | Skill (update) | Folded into Proposal 3 |
| 6 | A safety signal keyed on a clause the writer must predict (`from <key>`), never compared with the row, lets a silent duplicate land; a predicate on caller text (reflog subject) misses real merges | ledger-triage VERIFICATION W-32/W-29, LEARNINGS R4; merge-triggers LEARNINGS | Skill (update) | Proposal 4 |
| 7 | An acceptance driver that writes text naming a guarded identifier turned the owner package's private-reader gate red; run the repo's own gates over the acceptance commit | merge-triggers LEARNINGS Gotchas (orchestrator, between Steps 2 and 3) | Skip (fold) | Same class as pending Proposal 1 of `16-51-16` (new test artifacts trip repo-wide scan gates); add this as a third instance when that proposal is dispositioned |
| 8 | Final footprint readings go stale when a later commit touches a measured path; take them last | merge-triggers LEARNINGS, VERIFICATION FP03 | Skip | Present: `skills/spec-driven-development/references/footprint-criteria.md:54` |
| 9 | Orchestrator-authored fixes after budget exhaustion carried 5 of 6 FAILs; an unreviewed author is no substitute for the pair | ledger-triage LEARNINGS (rework) | Skip | Present: `skills/software-planning/references/coordination-details.md` § "When the next spawn would exceed the budget" ("provided the step is still reviewed") |
| 10 | Worktree isolation refuses Bash heredocs naming git, compound commands; write a scratch script instead | both LEARNINGS | Skip | Present: `docs/claude-code-limitations.md:11` |
| 11 | Repository text as a shell argument runs before argparse sees it; pass a file | ledger-triage VERIFICATION R4, LEARNINGS R3/R4 | Skip | Present: `skills/triage-debt/SKILL.md`, `commands/triage-debt.md:153` |
| 12 | `TEST_RESULTS.md` rework or notes sections fold into the neighbouring step block's byte ceiling | both LEARNINGS | Skip | Checker now closes a block at a non-step level-2 heading (`scripts/check_test_results_shape.py` docstring); lesson obsolete |
| 13 | Mutation sensor times out on tests that each build a real repo; need hand-built unit tests for the pure core | ledger-triage LEARNINGS Step 1 | Skip | Present: `scripts/CLAUDE.md:76` (`run-timeout` refusal); the split-for-testability remedy is one scenario |
| 14 | `resolve_test_scope.py` widens to nearly the full suite when `.ai-state/DESIGN.md` is in `--changed` | ledger-triage LEARNINGS Step 2 | Skip | Widening is documented (`skills/test/SKILL.md`); the missing selector is a defect for the topology owner, not an artifact |
| 15 | Root-pocket command cannot collect `tests/acceptance/` beside `scripts/project_metrics/tests/` (package shadowing) | merge-triggers LEARNINGS Step 3 | Skip | Defect in the resolver or package naming, own fix named in the source; belongs to the tech-debt ledger |
| 16 | Design texts asserted "the one merge no hook recognises" while the architect's own probe table held the counter-signal | merge-triggers VERIFICATION F-1 | Skip (fold) | Same class as pending Proposal 5 of `16-58-47` (a behavior claim shipped unprobed); add the "scan your own probe table before writing 'the only X'" sentence there |
| 17 | `ledger-triage` R4 reference prose still described pre-R4 duplicate rules (W-33) | ledger-triage VERIFICATION W-33 | Skip | Covered by pending Proposal 4 of `16-58-47` (records that restate a changed rule) |
| 18 | Frozen fixture copied via `git show <sha>:path`, never a working-tree copy | ledger-triage LEARNINGS Gotchas | Skip | One scenario; `agents/test-engineer.md:291` governs collection-time history only |
| 19 | Planner does not mint REQ ids for amendment behaviors; synthetic `AMEND-*` keys in `traceability.yml` | ledger-triage LEARNINGS Decisions | Skip | Seedling, one instance; no recurrence evidence |
| 20 | Ruff pin skew (0.15.22 vs 0.8.6) reformats `assert x, (msg)` | ledger-triage LEARNINGS R2 | Skip | Transient: the pin moved; pre-commit config is the authority |
| 21 | Split reader into pure core and effect shell when a module passes 800 lines | ledger-triage LEARNINGS Step 1 | Skip | Present: coding-style File Size rule |
| 22 | Parity test over literal mirrors of a constant (order-exact for manifests, sorted tuples elsewhere, exactly one match per single-structure mirror) | merge-triggers LEARNINGS Step 4 | Skip | One scenario, specific to the finalize hook names; the technical-debt note already records revisit trigger |

## Proposals

### Proposal 1: Recognising a git event inside a git hook

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: mature
- **Scope**: narrow
- **Priority**: P1 (next-cycle)
- **Source(s)**: `.ai-work/_harvest/merge-triggers/LEARNINGS.md` Decisions (post-commit predicate, post-rewrite, F-1 ruling) and Gotchas ("The reflog subject is caller-controlled", "A same-second `git commit --amend --no-edit` produces the identical SHA", "`git merge` creating a merge commit runs no `post-commit`"); same dir `VERIFICATION_REPORT.md` Architecture Documents ("Probe nuance": only `core.logAllRefUpdates=false` from init lacks `HEAD@{1}`).
- **Description**: A short reference page in `hook-crafting` listing what a git hook can and cannot tell, each fact probed on git 2.44.0 and dated: a merge finished by a commit is `HEAD@{1}` equal to the first parent on a two-parent HEAD, while an amend is not; the reflog subject is caller-controlled (`GIT_REFLOG_ACTION`) so never match it; `--rebase=merges` recreates merge commits so gate on the rebase directories; `git merge` creating a merge commit runs no `post-commit`; `post-rewrite` runs only for a non-empty rewrite list (a fast-forward by `git rebase` or a drop-all rebase runs none); a linked worktree has `.git` as a file; a repository with the reflog disabled from init cannot tell a merge from an amend. Close with "re-probe on your git version" per `rules/swe/staleness-policy.md`.
- **Rationale**: Six scenarios (merge by commit, amend, rebase, drop-all rebase, linked worktree, reflog-disabled) and the facts are non-obvious and cost a design round and a forced light review to find (F-1). They now live only in a decision record and in scattered shipped texts, which a future hook author will not search. Mature: probed and verified by the verifier twice.
- **Estimated scope**: SKILL.md pointer line plus one reference page (about 40 lines)
- **Overlap check**: `skills/hook-crafting/SKILL.md:70` (hook-run scripts' environment only); `skills/onboard-project/references/phases-core.md:300` and `skills/merge-worktree/SKILL.md` (composition of Praxion's own hooks, not event recognition); `.ai-state/decisions/425-merge-in-triggers-for-commit-and-rebase.md` (decision record, not reusable guidance). Searched for `reflog`, `GIT_REFLOG_ACTION`, `logAllRefUpdates` in `skills/`, `rules/`, `agents/`, `docs/`: no match.
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `skills/hook-crafting/references/git-hook-events.md` (new), linked from `skills/hook-crafting/SKILL.md`

### Proposal 2: A probe asserts its scene before it reads a verdict

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: sapling
- **Scope**: narrow
- **Priority**: P1 (next-cycle)
- **Source(s)**: merge-triggers `LEARNINGS.md` Gotchas (`git init <dir> -c key=value` creates nothing and the probe printed nothing; same-second `cherry-pick` reproduces the commit so "local commit already upstream" became "nothing to rebase", and a light review's "no hook ran at all" came from it); merge-triggers `VERIFICATION_REPORT.md` test coverage (P5 "wrong expectation in the probe"); ledger-triage `VERIFICATION_REPORT.md` R4 observations (`r3_probe w21_fail4` printed `ok` on lines labelled "untracked" because the fixture's `commit()` stages with `add -A`).
- **Description**: In the "Measure the thing, not a proxy" paragraph of `gate-canaries.md`, extend "a probe that silently did nothing proves nothing" to the scene: before reading a probe's verdict, assert the scene it built (print branch tips before and after, `git status --short` or `ls-files` for tracked state, the config actually set), and use constructions that cannot collapse (`git cherry-pick -x` gives a distinct SHA with the same patch-id; set config after init with `git -C <dir> config`).
- **Rationale**: Three independent hits across two pipelines, one producing a wrong review conclusion and one a mislabelled evidence line the verifier later had to retract. The failure reads as a correct negative result, which is why it persists.
- **Estimated scope**: one paragraph in an existing reference
- **Overlap check**: `skills/testing-strategy/references/gate-canaries.md:48` (mutated-something check, no scene check); pending Proposal 4 of `16-45-03` and Proposal 3 of `16-51-16` (same reference family: proofs resting on a record), so dispose in one edit pass. Searched `skills/`, `agents/verifier.md` for `scene`, `cherry-pick -x`, `same-second`: no match.
- **Recommended delegation**: context-engineer (review scope) then implementer (content)
- **Suggested artifact path**: `skills/testing-strategy/references/gate-canaries.md`

### Proposal 3: A test can only claim what its harness can observe

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: sapling
- **Scope**: narrow
- **Priority**: P2 (someday)
- **Source(s)**: ledger-triage `LEARNINGS.md` Rework R1 (stamp-check adapter no longer injectable: the only prior test passed a `commits=False` stub, so the real adapter, "an existence check posing as reachability", was never exercised) and R1 Gotchas ("test shas must be full 40-hex": a random 12-char prefix lacks a digit about 0.4% of runs); R4 ("vacuous-before-fix canary": passed before the fix, pins the post-fix contract only); `VERIFICATION_REPORT.md` R4 observations (`test_a_stamp_with_apostrophes_and_backtick_spans_reaches_the_check_byte_for_byte` runs no shell and asserts only `ok`).
- **Description**: Three short rules for test design: (1) a seam with an injectable adapter keeps at least one test on the real default adapter over a real fixture (a real git repository); (2) a test name claims only what the harness observes, so a property about execution needs a harness that runs it; (3) fixture values that must satisfy a boundary grammar are fixed literals satisfying it by construction, not random-derived. Name the vacuous-before-fix case: when a new test passes before the fix, say so and rename it to the contract it pins.
- **Rationale**: Four scenarios from one rework that cost three rounds (FAIL-4 was a stub-only gap). Each is cheap to state and none is carried: `gate-canaries.md` "Prove the canary bites" covers gates, not a general test. Sapling because the evidence is one pipeline; ambiguity: placement (testing-strategy body vs `agents/test-engineer.md`) is the context-engineer's call.
- **Estimated scope**: one short block in an existing skill or reference
- **Overlap check**: `skills/testing-strategy/references/gate-canaries.md:41-48` (vacuous canaries, measure the thing); `skills/testing-strategy/SKILL.md`; `agents/test-engineer.md`. Searched `skills/testing-strategy`, `skills/python-development`, `agents/test-engineer.md`, `agents/implementer.md` for `stub`, `real adapter`, `default adapter`, `hermetic`, `flake`: no remedy stated.
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `skills/testing-strategy/` (placement left to the context-engineer)

### Proposal 4: Compute the selector; do not take it from the writer's declaration

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: sapling
- **Scope**: narrow
- **Priority**: P2 (someday)
- **Source(s)**: ledger-triage `VERIFICATION_REPORT.md` R4 W-32 and ruling (the selector for a key-moving realign's live peer is the stamp's own `from <key>` clause; the check returns after the anchor and never compares it with the row; the instruction to write `from` "only when the base key changed" asks the applier to predict a value computed later; verifier's `[UNSURFACED-ASSUMPTION]`), W-29; `LEARNINGS.md` R4 decision (the pre-write check was rejected on a premise the verifier refuted); merge-triggers `LEARNINGS.md` Decisions (the reflog subject was refused as a predicate because the caller controls it; structure is used instead).
- **Description**: A checklist item for data-structure design: when a safety signal, filter or selector depends on a field, do not make that field a self-report of a derived fact the writer must predict. Either compute it from the data where it is used, or have the check compare the declared value with the computed one and refuse a mismatch. A field that only shapes like evidence is the same hazard in smaller size.
- **Rationale**: Two independent instances (an applier's clause, a caller's reflog text) end in the same fix: derive from structure the tool reads. It extends the "parse at the boundary, make illegal states unrepresentable" principle with a case the checklist lacks. Sapling: the second instance is a design decision, not a defect found in review.
- **Estimated scope**: one checklist item, no new file
- **Overlap check**: `skills/data-structure-design/references/design-review-checklist.md` and `SKILL.md` (no entry on declared-versus-derived fields; searched `derive`, `declared`, `self-report`); `skills/triage-debt/SKILL.md` (the backstop principle for stamps, specific to that command).
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `skills/data-structure-design/references/design-review-checklist.md`

## Recommended Delegations

| Proposal | Delegation Path | Notes |
|---|---|---|
| 1 | context-engineer | New reference page and one link line; load `skill-crafting`; state the probed git version and date |
| 2 | context-engineer then implementer | Same file and edit pass as pending `16-45-03` Proposal 4 and `16-51-16` Proposal 3; also add the `16-51-16` Proposal 1 third instance (item 7) |
| 3 | context-engineer | Decide placement first; one block |
| 4 | context-engineer | One checklist item |

## Disposition Log

<!-- Populated by /skill-genesis-review. Empty on report creation. -->

| Timestamp | Proposal | Disposition | Notes |
|---|---|---|---|
| _(empty — pending review)_ | | | |

## Recommended Next Steps

- Run `/skill-genesis-review` to disposition the 4 pending proposals.
- Two notes for pending proposals of earlier reports of this run (items 7 and 16): attach the acceptance-driver instance to `16-51-16` Proposal 1, and the "scan your own probe table" sentence to `16-58-47` Proposal 5.
- After approval, invoke `context-engineer`; Proposals 2 and 3 share the testing-strategy family and are best edited in one pass.
