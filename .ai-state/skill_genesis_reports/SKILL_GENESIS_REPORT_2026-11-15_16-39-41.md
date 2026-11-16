---
schema_version: 1
report_id: skill-genesis-2026-11-15_16-39-41
generated_at: 2026-11-15T16:39:41Z
task_slug: skill-genesis-2026-11-15
agent_version: skill-genesis@89e70d55
invocation_args: { since: null, scope: null, sources: /Users/fperez/dev/praxion/.ai-work/_harvest, batch: "1 of 11", dry_run: false }
review_status: pending
disposition_count: { pending: 4, approved: 0, rejected: 0, refined: 0, deferred: 0 }
---

# Skill Genesis Report — 2026-11-15 16:39:41

## Summary

1 queue source (`step-loop-driver`), 32 learning items extracted, 4 proposals, 28 deduplicated or skipped. The source was harvested by earlier runs (the 2026-10-11 and 2026-10-31 reports cite it, and the repository now carries most of its lessons), so only items with no artifact home were proposed. Review status: pending.

## Learning Sources Consumed

| Source | Path | Items Extracted | Status |
|---|---|---|---|
| Queue source LEARNINGS.md | `.ai-work/_harvest/step-loop-driver/LEARNINGS.md` | 30 | Read (lines 1-60 and 146-253; the Decisions block, lines 60-145, sampled by heading only: ADR-bound decisions already live in `.ai-state/decisions/`) |
| Queue source VERIFICATION_REPORT.md | `.ai-work/_harvest/step-loop-driver/VERIFICATION_REPORT.md` | 4 (overlap LEARNINGS "Merge" block) | Read (WARN findings and merge block; headings of the rest) |
| Queue source CONSULT_*.md | `.ai-work/_harvest/step-loop-driver/` | 0 | Not found |
| Other files in the directory (LEARNINGS_step-schema-harvest.md, HANDOFF*.md, etc.) | same | 0 | Not read (outside the contract) |
| SENTINEL / IDEA_LEDGER | `.ai-state/` | 0 | Not consulted (queue mode; ledger used only as a dedup guard) |
| Earlier reports of this run | `.ai-state/skill_genesis_reports/` | n/a | Pending: 2026-11-05_21-28-47 (headings read; no overlap with proposals below) |
| Calibration log Retrospective cells | `.ai-state/calibration_log.md` | 0 | Not consulted (the source predates the cells in scope) |

## Triage Results

| # | Item | Source | Decision | Rationale |
|---|---|---|---|---|
| 1 | Constructor invariant tightened in one step breaks a test only another step's `Check:` runs | LEARNINGS Gotchas [implementer] | Skill (update) | Not in repo (searched `skills/`, `agents/`, `rules/`); Proposal 1 |
| 2 | Purity test pinned an import allow-list; adding a pure import broke it, step stopped at CONFLICT | LEARNINGS Gotchas [implementer] | Skill (update) | Same class as 1; folded into Proposal 1 |
| 3 | Source-reading meta-tests fail the mutation sensor's first clean run | LEARNINGS Gotchas [implementer] | CLAUDE.md (scripts) | `scripts/CLAUDE.md:103` carries only the parent-counting variant; Proposal 4 |
| 4 | A deferred increment leaves a crash path; name the stop its absence causes | VERIFICATION_REPORT merge block, F-W1/td-346 | Skill (update) | Not in repo (grep for absence/crash wording found nothing); Proposal 2 |
| 5 | Delegation's suggested test command must run in the user's shell; unmatched zsh glob aborts | VERIFICATION_REPORT merge block | Skill (update) | Not shipped (only user memory); Proposal 3 |
| 6 | Caller holding the answer must pass `base_ref` to every consumer | VERIFICATION_REPORT; LEARNINGS Step 33 | Skip | Present: `skills/software-planning/references/decomposition-guide.md:41` |
| 7 | A split must amend acceptance criteria and footprints, not only footprints | VERIFICATION_REPORT; LEARNINGS Step 32 | Skip | Present: `coordination-details.md:299` |
| 8 | Footprint is bounded or declared, never both; log names only bounded criteria | LEARNINGS Step 32 | Skip | Present: `skills/spec-driven-development/references/footprint-criteria.md` |
| 9 | Detached run inherits SIGINT ignored; reset in child | LEARNINGS Step 31 | Skip | Present: `skills/test/SKILL.md:24` |
| 10 | Block reader folded a non-step heading's `Result:` into the previous step | LEARNINGS AC-13 / Step 34 | Skip | Present: `agent-pipeline-details.md:328` (Blocks) |
| 11 | Each red node owned by exactly one step; verify the partition by script | LEARNINGS Patterns | Skip | Present: `coordination-details.md`, `agents/implementation-planner.md` |
| 12 | Worktree guard refuses commands by text (`git` substring, `\| sh -e`) | LEARNINGS Gotchas, Step 33 | Skip | Present: `docs/claude-code-limitations.md:11` |
| 13 | Literal pathspecs; pre-staged rows refused; killed `git commit` leaves hooks running | LEARNINGS Step 16 | Skip | Driver-specific; `skills/step-loop/references/stop-recoveries.md` carries the stop |
| 14 | Composer fork-point resolved the older merge-base | LEARNINGS Handoff composition, Step 33 | Skip | Fixed in code (td-345 resolved); no reusable rule beyond item 6 |
| 15 | Replay through the driver in a scratch clone when no live spawn is available; label as replay | LEARNINGS AC-13 | Skip | One occurrence, driver-specific; seedling, wait for a second |
| 16 | New importer of the observation-log reader must be a declared consumer | LEARNINGS Step 17 | Skip | Enforced by a failing test whose message names the registry |
| 17 | Light review second `revise` escalated to user; non-interactive, so orchestrator decided and recorded | LEARNINGS Technical Debt | Skip | Covered by the self-gate convention in user memory; project-specific |
| 18 | Two-step pair ordering: reviewed/heavy step first, resume same agent | LEARNINGS Patterns | Skip | Planning detail of this plan; one occurrence |
| 19 | Ruff 100-column expansion makes a line ceiling a formatting budget | LEARNINGS Gotchas | Skip | Pipeline-specific; no recurrence signal |
| 20 | Prompt text must avoid `opus`/`sonnet`/`haiku` substrings | LEARNINGS Gotchas | Skip | Driver acceptance detail |
| 21-32 | Design assumptions, ADR-bound decisions (dec-draft-*), sizes, step interface seams, line budgets, td rows | LEARNINGS (various) | Skip | Recorded in ADRs / ledger / code; transient or too narrow |

## Discipline-Gap Signals

None recorded.

## Proposals

### Proposal 1: Tightening a contract, check every test that pins it, not only the step's `Check:`

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: sapling
- **Scope**: narrow
- **Priority**: P1 (next-cycle)
- **Source(s)**: `.ai-work/_harvest/step-loop-driver/LEARNINGS.md` Gotchas: "A constructor invariant tightened in one step breaks a test another step's `Check:` runs" (step 7 `Attempt` refusing a blank replan vs `test_step_verdict.py`, surfaced one step late); "The moved `Files:` reader's purity test pins an import allow-list" (step stopped at `[CONFLICT]`).
- **Description**: Add a short item beside the shared-resolver rule in the decomposition guide: when a step tightens a constructor check, an import set, or any contract other code pins, the planner or implementer greps every test that constructs the type or pins the module, including suites outside the step's `Check:` and `Files:`, and adds them to `Check:` or `Files:`. Add one line: a purity test should forbid I/O modules rather than allow-list the pure ones, so a new pure import does not break it.
- **Rationale**: Two independent occurrences in one pipeline, each costing a step (one late failure, one `[CONFLICT]` stop). The sibling rule at `decomposition-guide.md:41` covers new consumers of a resolver but not a tightened contract, so the gap is real.
- **Estimated scope**: one paragraph in an existing reference
- **Overlap check**: `skills/software-planning/references/decomposition-guide.md:41` (new consumers of a shared resolver; adjacent, different failure). Searched `skills/`, `agents/`, `rules/` for "constructor invariant", "purity test", "allow-list": no match.
- **Recommended delegation**: context-engineer (review scope) then implementer (content)
- **Suggested artifact path**: `skills/software-planning/references/decomposition-guide.md`

### Proposal 2: A deferred increment names the stop its absence causes

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: seedling
- **Scope**: narrow
- **Priority**: P2 (someday)
- **Source(s)**: `VERIFICATION_REPORT.md` § Merge to LEARNINGS.md and F-W1 (td-346): a review-marked step crashed `next` with `ValueError` because the renderer and `record` for the review path moved to the follow-up.
- **Description**: Extend the split paragraph in `coordination-details.md` (the one that moves acceptance criteria): when an increment moves to a follow-up, list the code path its absence leaves reachable and make it stop with a named cause (fail closed with a message), or record it as a declared limit, instead of leaving an internal error.
- **Rationale**: The split paragraph already makes the deferral visible to the verifier; this closes the runtime half. One occurrence, hence seedling, but the verifier flagged it as a general pattern.
- **Estimated scope**: one sentence in an existing section
- **Overlap check**: `skills/software-planning/references/coordination-details.md:299` (deferred acceptance criteria, footprints, `Files:`); no mention of the crash path. Searched `skills/`, `agents/`, `rules/`, `docs/` for "absence causes", "crash path": no match.
- **Recommended delegation**: context-engineer (review scope) then implementer (content)
- **Suggested artifact path**: `skills/software-planning/references/coordination-details.md`

### Proposal 3: A delegated test command lists files explicitly (zsh aborts on an unmatched glob)

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: seedling
- **Scope**: narrow
- **Priority**: P2 (someday)
- **Source(s)**: `VERIFICATION_REPORT.md` § Merge to LEARNINGS.md: a delegation's `scripts/test_step_loop*.py` matched nothing and zsh aborted the whole command with `no matches found`.
- **Description**: Add to the delegation checklist guidance that a test command handed to another agent names test files explicitly or uses a runner argument that tolerates no match, because the user's shell is zsh and an unmatched glob aborts the command.
- **Rationale**: Cheap to state, avoids a wasted agent turn. Only user memory (`feedback_zsh_param_expansion_no_word_split.md`) carries the zsh-glob family; no shipped artifact does.
- **Estimated scope**: one line
- **Overlap check**: searched `skills/`, `agents/`, `rules/`, `docs/` for "no matches found", "unmatched glob", "list test files explicitly": only `skills/agentic-interface-design/references/tool-design-for-models.md:30`, unrelated. `docs/claude-code-limitations.md:11` covers the worktree guard, not zsh globs.
- **Recommended delegation**: context-engineer (review scope) then implementer (content)
- **Suggested artifact path**: `skills/software-planning/references/coordination-details.md` (§ Delegation Checklists)

### Proposal 4: Source-reading meta-tests fail the mutation sensor's baseline

- **Disposition**: pending
- **Type**: claude.md (subdirectory `scripts/CLAUDE.md`)
- **Maturity**: sapling
- **Scope**: narrow
- **Priority**: P2 (someday)
- **Source(s)**: `LEARNINGS.md` Gotchas: "Source-reading meta-tests break the mutation sensor" (a test reading the module's own text for import allow-list, line ceiling or function size fails the sensor's first clean run because mutmut rewrites the module with trampolines; `run-failed`).
- **Description**: Extend the `mutation_sensor.py` bullet in `scripts/CLAUDE.md` (which already warns about parent-counting fixtures) with the second baseline-breaking shape: a test that reads the module's own source. Remedy: check size and imports by hand and by ruff/mypy, and keep such tests out of any suite a `mutation: on` step runs.
- **Rationale**: Same failure family and same diagnosis trap ("looks like a tooling fault") as the bullet already there. Folded here rather than a new artifact; Proposal 6 of the pending 2026-11-05 report is about survivor dispositions, a different point.
- **Estimated scope**: CLAUDE.md edit (about two lines)
- **Overlap check**: `scripts/CLAUDE.md:103` (parent-counting only). Pending 2026-11-05 Proposal 6 (mutation dispositions): adjacent, no overlap.
- **Recommended delegation**: user (claude.md), context-engineer to confirm placement
- **Suggested artifact path**: `scripts/CLAUDE.md`

## Recommended Delegations

| Proposal | Delegation Path | Notes |
|---|---|---|
| 1 | context-engineer then implementer | Reference update; keep next to decomposition-guide line 41 |
| 2 | context-engineer then implementer | One sentence in the split paragraph |
| 3 | context-engineer then implementer | Could merge with Proposal 2 in one edit pass on `coordination-details.md` |
| 4 | user / context-engineer | Subdirectory CLAUDE.md edit; check token impact is nil (on-demand file) |

## Disposition Log

<!-- Populated by /skill-genesis-review. Empty on report creation. -->

| Timestamp | Proposal | Disposition | Notes |
|---|---|---|---|
| _(empty — pending review)_ | | | |

## Recommended Next Steps

- Run `/skill-genesis-review` to disposition the 4 pending proposals.
- Proposals 2 and 3 touch the same file and may be dispositioned together.
- Remaining batches (2 to 11) of this run should check this report's headings before proposing an overlapping lesson.
