---
schema_version: 1
report_id: skill-genesis-2026-10-11_00-56-42
generated_at: 2026-10-11T00:56:42
task_slug: skill-genesis-2026-10-11
agent_version: skill-genesis@7a7dc04d
invocation_args: { since: null, scope: null, sources: .ai-work/_harvest-commands-to-skills, batch: "1 of 1", dry_run: false }
review_status: pending
disposition_count: { pending: 6, approved: 0, rejected: 0, refined: 0, deferred: 0 }
---

# Skill Genesis Report — 2026-10-11 00:56:42

## Summary

2 queue sources analyzed (LEARNINGS.md and VERIFICATION_REPORT.md of `commands-to-skills`), 31 items extracted, 6 proposals generated, 25 deduplicated or skipped (already in memory, in an existing skill, fixed in code, or one-off). Review status: pending.

## Learning Sources Consumed

| Source | Path | Items Extracted | Status |
|---|---|---|---|
| LEARNINGS.md (queue) | `.ai-work/_harvest-commands-to-skills/commands-to-skills/LEARNINGS.md` | 27 | Read |
| VERIFICATION_REPORT.md (queue, round 3) | `.ai-work/_harvest-commands-to-skills/commands-to-skills/VERIFICATION_REPORT.md` | 4 | Read |
| CONSULT_*.md | same directory | 0 | Not found |
| Latest SENTINEL_REPORT_*.md | `.ai-state/sentinel_reports/` | 0 | Not consulted (not needed for this slug) |
| Latest IDEA_LEDGER | `.ai-state/idea_ledgers/IDEA_LEDGER.md` | 0 | Not read for overlap (no feature ideation here) |
| ADRs | `.ai-state/decisions/` | 0 | The slug's own decisions are drafts, already recorded |
| Calibration log Retrospective cells | `.ai-state/calibration_log.md` | 0 | Not used (queue mode) |
| Sibling pending report | `SKILL_GENESIS_REPORT_2026-10-10_00-49-38.md` | n/a | Headings grepped; Proposal 5 (retired-identifier sweep) is adjacent but distinct |

## Triage Results

| # | Item | Source | Decision | Rationale |
|---|---|---|---|---|
| 1 | Legacy sweep selects by what the retired producer wrote (marker header, full release history), not by what exists now | LEARNINGS orchestrator; VR W-08/09/12 | Skill (update) | Recurs three times in one pipeline; no existing artifact |
| 2 | Probe a fixture against real producer output, not a stand-in | VR "Merge to LEARNINGS" | Skill (update) | Folded into Proposal 1 |
| 3 | `Files:` entries: full repo-relative path, bare directory, no glob/trailing slash | LEARNINGS orchestrator (x3), planner | Skill (update) | Only in project memory, which does not ship |
| 4 | Check floor from subtraction can be one too high; re-run once | LEARNINGS orchestrator | Skill (update) | Folded into Proposal 2 |
| 5 | Deletion step consequences land in files owned by done steps; needs a pending owner | LEARNINGS orchestrator | Skill (update) | Folded into Proposal 2 |
| 6 | Orchestrator-resolved Spec Question recorded in ACCEPTANCE_TESTS.md at edit time | LEARNINGS orchestrator | Skill (update) | Verifier failed commit-order audit on the record gap alone |
| 7 | A rework that changes a decision must revisit its draft ADR | LEARNINGS orchestrator; VR W-13 | Skill (update) | Folded into Proposal 3 |
| 8 | Description edit needs its diet row (`apply_skill_description_diet.py --check`) | LEARNINGS orchestrator | Skill (update) | No artifact mentions the diet table |
| 9 | Shell state must live in one fenced block of a skill body | LEARNINGS implementer Step 7 | Skill (update) | Not in `user-invoked-skills.md` |
| 10 | Outer-loop before-state fixture needs a declared-deps edge from its model source | LEARNINGS orchestrator | Skill (update) | Sapling; one occurrence |
| 11 | `pre-commit run --all-files` is not a per-change gate; baseline it | LEARNINGS orchestrator | Skill (update) | Seedling |
| 12 | `Files:` globs never commit; recovery with `git apply --include` | LEARNINGS orchestrator | Skip (dup) | Memory `feedback_step_loop_files_globs_never_match`; value carried by Proposal 2 |
| 13 | Pre-staged index rides a plain commit | LEARNINGS orchestrator | Skip (dup) | Memory `feedback_prestaged_deletion_rides_next_pathspec_commit` |
| 14 | Gate fix must be committed, not merely in the tree (pre-commit stashes) | LEARNINGS orchestrator | Skip (dup) | Memory `feedback_precommit_config_unstaged_blocks_commit` |
| 15 | Worktree guard refuses heredocs naming git and `$VAR` | LEARNINGS implementer | Skip (dup) | Memory `feedback_worktree_guard_command_text_heuristics` |
| 16 | Step-loop gate could not read vitest; session-exit orphan; golden-rule gate `.mmd` | LEARNINGS orchestrator | Skip | Fixed in code with tests |
| 17 | Refreshable block is unconditional (hackathon block) | LEARNINGS orchestrator | Skip | Tracked as td-403 for the architect |
| 18 | `check_token_ratchet.py --check` rewrites the day's sample | LEARNINGS orchestrator | Skip | Narrow; in the plan pre-mortem |
| 19 | Plan-time proof with the real readers (`parse_plan_steps`, ownership map) | LEARNINGS planner | Skip | Pattern already practiced; single source |
| 20 | Remaining items (decisions, step-local notes, prose carriers, flaky test, `check_paths_syntax` base failure, `AGENTS.md` render, DRC-08 summary, Codex arg line, etc.) | both | Skip | Transient, step-local, or captured in ADR drafts and td rows |

## Discipline-Gap Signals

None recorded.

## Proposals

### Proposal 1: refactoring (or software-planning) — retiring a producer: sweep what it wrote, proven against its real output

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: mature
- **Scope**: medium
- **Priority**: P1 (next-cycle)
- **Source(s)**: LEARNINGS "Derive a sweep's name set from history" and "A legacy sweep selects by what was written" (orchestrator); VERIFICATION_REPORT round 3 W-08, W-09, W-12, "Merge to LEARNINGS" candidates 1 and 3; td-406..td-408
- **Description**: A reference section for pipelines that delete or replace an artifact family which a shipped installer or exporter wrote into users' projects. It states that the cleanup selector must (a) take its name set from the union over every release that ran the producer (`git log --all --name-only`, `ls-tree` per tag), (b) require a content marker the producer prepended (header first line) rather than a name match or "a skill of that name exists now", (c) treat exemption lists as named members with what they carry, never a shape, and (d) be probed by running the retired producer into a tmp dir and feeding its real output to the sweep (user-authored lookalikes must survive).
- **Rationale**: Three successive review rounds each found a narrower selector was still wrong (107 names deleting user files, then no marker, then eight orphan stems from earlier releases). The lesson is generic to any retirement with an on-disk legacy surface and nothing in skills currently encodes it.
- **Estimated scope**: one reference file plus a pointer in SKILL.md
- **Overlap check**: sibling pending Proposal 5 (retired-identifier sweep over templates and rule text) covers in-repo prose, not user-side artifacts; `refactoring` skill has no legacy-cleanup guidance
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `skills/refactoring/references/retiring-a-written-surface.md`

### Proposal 2: step-loop / implementation-planner — plan hygiene for the driver's `Files:`, `Check:` and ownership

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: mature
- **Scope**: medium
- **Priority**: P0 (this-cycle)
- **Source(s)**: LEARNINGS orchestrator "A glob in `Files:` is never committed", "A `Files:` entry without its directory", "A Check floor computed at plan time can be one too high"; planner gotcha "use globs" (since corrected); implementer Step 14 retry notes
- **Description**: A short plan-authoring checklist: `Files:` entries are full repo-relative literal paths; a tree is its bare directory (directories expand), never a glob or trailing slash; `verify_plan.py` proves node ownership, not path existence, so check paths yourself; a deletion step's side effects in files owned by done steps need a pending owner (amend a later step); a `pass>=` floor derived by subtraction is re-run once against the tree.
- **Rationale**: The planner's own gotcha ("use globs") was wrong for the driver, and the same defect stopped Step 14 with a disturbed tree and left Step 10 uncommitted. The knowledge lives only in project memory, which does not ship with the plugin, so other projects' planners repeat it.
- **Estimated scope**: SKILL.md section or one reference in step-loop, plus a pointer in the planner's plan-format guidance
- **Overlap check**: memory `feedback_step_loop_files_globs_never_match` (not shipped); `skills/step-loop/SKILL.md` has no `Files:` guidance
- **Recommended delegation**: context-engineer then implementer
- **Suggested artifact path**: `skills/step-loop/references/plan-files-and-checks.md`

### Proposal 3: software-planning coordination — records follow the edit during in-place rework

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: sapling
- **Scope**: narrow
- **Priority**: P1 (next-cycle)
- **Source(s)**: LEARNINGS "A rework that changes a decision must revisit its draft ADR", "An acceptance-driver edit needs its Spec Question in ACCEPTANCE_TESTS.md"; VERIFICATION_REPORT W-11, W-13, W-10 residual, "Merge to LEARNINGS" candidate 2
- **Description**: Add to the rework/in-place-fix procedure a same-round checklist: (a) an orchestrator-resolved Spec Question is written into the designer's ACCEPTANCE_TESTS.md first (REQ, raiser, ambiguity, resolution, regenerated digest, `Resolved in:` sha, marked for ratification); (b) when a fix changes what was decided, edit the draft ADR Decision and summary, and sweep every draft describing the mechanism; (c) flip ledger rows with their fix shas.
- **Rationale**: The verifier failed the commit-order audit on a record gap alone, and a draft ADR was about to finalize describing a selector the code never shipped, through two rounds. Each is cheap at edit time and costly at audit.
- **Estimated scope**: edit to an existing section of `coordination-details.md`
- **Overlap check**: `coordination-details.md` covers Spec Question semantics and the Sources Read audit, not the orchestrator-resolved recording or draft ADR re-sync
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `skills/software-planning/references/coordination-details.md`

### Proposal 4: skill-crafting — a description edit must run the diet check; a procedure's shell state lives in one block

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: sapling
- **Scope**: narrow
- **Priority**: P1 (next-cycle)
- **Source(s)**: LEARNINGS "A description edit needs its diet row in the same change" (Step 18); implementer "Step 7 revise r1: a procedure's shell state must live in one fenced block"
- **Description**: Two gotchas. (1) Changing a `SKILL.md` `description` makes `apply_skill_description_diet.py --check` report DRIFT; include that check in the Done-when of any step whose Files include a SKILL.md. (2) Shell variables do not persist between Bash tool calls, so a user-invoked skill that resolves a value in one block and consumes it in another passes an empty value (the dashboard launcher fell back to the cwd); put resolve-and-use in one fenced block and state the rule in prose.
- **Rationale**: Both defects passed all gates except a late full run or a light review; the acceptance harness joined the blocks and could not see the second. They are exactly the non-obvious failure points the skill says gotchas are for.
- **Estimated scope**: two gotcha bullets in `references/user-invoked-skills.md` and the checklist or Step 5 of SKILL.md
- **Overlap check**: `user-invoked-skills.md` covers arguments and invocation modes only; no mention of the diet table or block-scoped shell state
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `skills/skill-crafting/references/user-invoked-skills.md`

### Proposal 5: testing-strategy — outer-loop before-state fixtures need a declared-deps edge and an identity-file Read-only

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: seedling
- **Scope**: narrow
- **Priority**: P2 (someday)
- **Source(s)**: LEARNINGS "A previous pipeline's frozen before-state outlives its change" (SQ-06); implementer Step 8 Spec Question (frozen selection names a deleted test)
- **Description**: A frozen before-state fixture (architecture model, selection list) guards "nothing lost", which a deliberate removal violates; the derived scope never selected its test because the driver reads the model via a directory export. Record: give such a fixture a declared-deps edge from its source, list the model-identity file in the Read-only of any step that removes a modelled component, and filter frozen selections to files that still exist.
- **Rationale**: Reds appeared only in the final full run; one occurrence so far, so kept as a seedling to watch.
- **Estimated scope**: one paragraph in the acceptance-test guidance
- **Overlap check**: memory `feedback_acceptance_tests_no_git_history` (fixture freezing) is adjacent, not the same
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `skills/testing-strategy/SKILL.md` (or a reference)

### Proposal 6: spec-driven-development calibration — baseline `pre-commit run --all-files` before demanding it clean

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: seedling
- **Scope**: narrow
- **Priority**: P2 (someday)
- **Source(s)**: LEARNINGS "`pre-commit run --all-files` is not a per-change gate"; VERIFICATION_REPORT W-06 (td-405)
- **Description**: A spec clause requiring `--all-files` clean needs a baseline reading before the first change, as the pytest baseline has. On the final tree the hooks rewrote 32 untouched files and tripped on deliberately malformed fixtures while CI (changed files) stayed green. Record the pre-existing result and restore rewrites via `git restore` after checking the touched-file set.
- **Rationale**: Hit once and already tracked as a hygiene row; worth a line only if it recurs.
- **Estimated scope**: one bullet
- **Overlap check**: none found
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `skills/spec-driven-development/references/calibration-procedure.md`

## Recommended Delegations

| Proposal | Delegation Path | Notes |
|---|---|---|
| 1 | context-engineer | New reference; load skill-crafting |
| 2 | context-engineer then implementer | Verify `Files:` driver semantics against `_step_loop_gate.py` before writing |
| 3 | context-engineer | Edit existing coordination-details section |
| 4 | context-engineer | Two gotcha bullets |
| 5 | context-engineer | Defer until a second occurrence |
| 6 | context-engineer | Defer until a second occurrence |

## Disposition Log

<!-- Populated by /skill-genesis-review. Empty on report creation. -->

| Timestamp | Proposal | Disposition | Notes |
|---|---|---|---|
| _(empty — pending review)_ | | | |

## Recommended Next Steps

- Run `/skill-genesis-review` to disposition the 6 pending proposals.
- After approval, invoke `context-engineer` for skills/rules; the agent will pick up the recommended delegations table.
- Re-run `/skill-genesis` after the next pipeline completes if `LEARNINGS.md` accumulates further items.
