---
schema_version: 1
report_id: skill-genesis-2026-11-15_16-42-24
generated_at: 2026-11-15T16:42:24Z
task_slug: skill-genesis-2026-11-15
agent_version: skill-genesis@89e70d55
invocation_args: { since: null, scope: null, sources: /Users/fperez/dev/praxion/.ai-work/_harvest, batch: "2 of 11", dry_run: false }
review_status: pending
disposition_count: { pending: 3, approved: 0, rejected: 0, refined: 0, deferred: 0 }
---

# Skill Genesis Report — 2026-11-15 16:42:24

## Summary

2 queue sources (`step-loop-dogfood`, `step-schema`), 38 learning items extracted, 3 proposals, 35 deduplicated or skipped. Both pipelines were built into the repository (the driver, the reconciler, the iteration ledger, the request counter) and most of their lessons now live in code, ADRs, `scripts/CLAUDE.md` or the planning references. Only items with no artifact home were proposed. Review status: pending.

## Learning Sources Consumed

| Source | Path | Items Extracted | Status |
|---|---|---|---|
| Queue source LEARNINGS.md | `.ai-work/_harvest/step-loop-dogfood/LEARNINGS.md` | 19 | Read in full |
| Queue source VERIFICATION_REPORT.md | `.ai-work/_harvest/step-loop-dogfood/VERIFICATION_REPORT.md` | 2 | Read (WARN list, behavioral findings, merge block; headings of the rest) |
| Queue source LEARNINGS.md | `.ai-work/_harvest/step-schema/LEARNINGS.md` | 15 | Read in full |
| Queue source VERIFICATION_REPORT.md | `.ai-work/_harvest/step-schema/VERIFICATION_REPORT.md` | 2 | Read (WARN list and merge block; headings of the rest, including the two re-verification rounds) |
| Queue source CONSULT_*.md | both directories | 0 | Not found |
| Other files in the directories (HANDOFF*, PROMPT_*, SYSTEMS_PLAN, RESEARCH_*, logs) | same | 0 | Not read (outside the contract) |
| SENTINEL / IDEA_LEDGER / calibration log | `.ai-state/` | 0 | Not consulted (queue mode) |
| Earlier reports of this run | `.ai-state/skill_genesis_reports/SKILL_GENESIS_REPORT_2026-11-15_16-39-41.md` | n/a | Read in full; pending 2026-11-05 and 2026-10-10 headings and mutation rows checked |

## Triage Results

| # | Item | Source | Decision | Rationale |
|---|---|---|---|---|
| 1 | Shared `Files:` leave a later step with no attributable file; the reconciler reads it `unknown` | step-schema LEARNINGS Gotchas [planner] | Skill (update) | Not in repo (searched `skills/software-planning/`, `agents/implementation-planner.md`); Proposal 1 |
| 2 | Equivalent mutants cluster at defaults (`encoding=` on ASCII, keyword equal to the default); remedy | step-schema LEARNINGS Gotchas [implementer] | Skill (update) | `python-testing.md:235` has the class, not the cluster; Proposal 2 |
| 3 | Removing a test dropped the only assertion on key names, opening 6 survivors; substring match let a message mutant live | step-schema LEARNINGS Technical Debt [implementer] | Skill (update) | Folded into Proposal 2 |
| 4 | Write tool turned a ` ` escape in a source string into the raw character | step-loop-dogfood LEARNINGS Gotchas, step 5 | Skill/doc (seedling) | Not in repo (searched `docs/claude-code-limitations.md`, `scripts/CLAUDE.md`); Proposal 3 |
| 5 | Mutation sensor's flat sandbox refuses a target that imports `hooks/` (`run-failed`) | step-schema LEARNINGS Technical Debt | Skip | Present: `scripts/CLAUDE.md:102`; `decomposition-guide.md:148` (`not-flat-layout`); td-338 |
| 6 | Derived scope mixes `fitness/tests` and `tests`; 29 collection errors | step-schema LEARNINGS Gotchas | Skip | Fixed in code (td-337 resolved) |
| 7 | Same-basename test files in two directories: `import file mismatch` | step-schema LEARNINGS Gotchas | Skip | One file was renamed (`scripts/test_iteration_ledger.py` is gone); pytest-generic |
| 8 | Worktree guard refuses commands whose text names the VCS tool, even in heredocs | both LEARNINGS | Skip | Present: `docs/claude-code-limitations.md:11` (prior report item 12) |
| 9 | `Check:` runs without a shell (no `&&`, env prefix or glob); a second `Check:` label line makes the step unreadable | step-loop-dogfood LEARNINGS [planner] | Skip | Present: `document-templates.md:83` and `:77` |
| 10 | Id-citation checker flags `Step <digit>` in test data; build labels from a constant | both LEARNINGS | Skip | Present: `rules/swe/id-citation-discipline.md` (ignore marker, exempt paths); the checker's own message names the house form |
| 11 | Green results block over 1024 bytes (driver wrote full output into the block) | both VERIFICATION | Skip | Ledgered td-353; the shape gate reports it |
| 12 | Baseline read against today's cap rewrites an older regime (`maxTurns` 80 to 100) | step-schema VERIFICATION merge block | Skip | Fixed in code (`_PRIOR_MAX_TURNS`); one occurrence, instrument-specific |
| 13 | Check-first moves the truncation shape: a stopped agent with files done needs a resume naming the check | step-schema VERIFICATION merge block | Skip | Built in `_step_verdict._name_the_check`; recorded in `scripts/CLAUDE.md` |
| 14 | Two readers of one `Result:` line drifted; one shared reader | step-schema rework | Skip | Built (`_loop_fields.latest_result`); the one-definition principle is already in `software-design-principles` |
| 15 | Planner skeleton `Write` overwrote the architect's `LEARNINGS.md` | step-schema LEARNINGS Gotchas [planner] | Skip | Covered: `agents/implementation-planner.md:46` says to check for existing documents first |
| 16 | Facade split: ruff isort explodes `as` re-exports; use one import and `__all__`; derive base names from the base commit | step-loop-dogfood LEARNINGS step 3 | Skip | Known idiom; one occurrence; consumers-before-move overlaps pending items in this run |
| 17 | Draft prose against the scenarios' own predicates before the step; ownership script over `--collect-only`; `pending=` from the baseline red set | both LEARNINGS Patterns | Skip | Present or one occurrence (prior report item 11; `document-templates.md` `pending=`) |
| 18 | Driver `then`/`resume` drop the caller's `--base-ref`; `record` exits 1 after recording when the handoff composer refuses a hand-written `HANDOFF.md` | step-loop-dogfood VERIFICATION W-B1, W-B3 | Skip | td-351, td-352 (driver defects, ledgered); prior report item 6 for the principle |
| 19 | Orchestrator context stayed flat only inside the driven band; enter it earlier | step-loop-dogfood LEARNINGS Close | Skip | One pipeline, a sequencing judgement bound to the self-modification boundary; wait for a second reading |
| 20 | Nested `claude -p --plugin-dir <worktree>` shows a hook's injected context in the subagent transcript | step-loop-dogfood LEARNINGS Step 9 | Skip | Present: `docs/lean-spawn-how-to.md`; the reading is recorded in the dated Status note of the reminder record |
| 21-38 | Design decisions (dec-draft-*), assumptions, pending/floor counts, step sizes, line ceilings, import allow-lists, hook-group shape, traceability nesting, doc-manifest regeneration, td rows, spawn tallies | both LEARNINGS | Skip | Recorded in ADRs, the ledger or code; transient or too narrow |

## Discipline-Gap Signals

None recorded.

## Proposals

### Proposal 1: Each implementer step keeps one `Files:` entry no earlier step declares

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: sapling
- **Scope**: narrow
- **Priority**: P1 (next-cycle)
- **Source(s)**: `.ai-work/_harvest/step-schema/LEARNINGS.md` Gotchas [implementation-planner]: "Shared `Files:` make a later step unattributable" (the reconciler's `attributable()` subtracts files an earlier step declares, so a step whose files are all shared reads `unknown`; the plan gave steps 5, 6, 7 and 10 each a test file of their own).
- **Description**: Add one rule to the planner-facing decomposition guidance: when several steps touch the same files, give every implementer step at least one file no earlier step declares (usually its own test file), because the recovery reconciler judges completion by the step's attributable `Files:` and otherwise reads `unknown`, which routes to a human. Name the check: run the reconciler over the plan before the first spawn and treat an `unknown` on an implementer step as a plan defect.
- **Rationale**: The reconciler is shipped and its `unknown` verdict stops auto-resume, so a planner who shares files across steps silently disables recovery for them. The information lives only in a code docstring and one pipeline's notes. One pipeline, but the mechanism is structural, not incidental.
- **Estimated scope**: one paragraph in an existing reference
- **Overlap check**: `scripts/CLAUDE.md:14` describes `attributable` Files and the `unknown` verdict for readers of the script, not for the planner. Searched `skills/software-planning/`, `agents/implementation-planner.md` for "attributable", "no earlier step", "shared Files": no planner-facing mention. Adjacent: `decomposition-guide.md:62` (parallel-group golden bad-case), different failure.
- **Recommended delegation**: context-engineer (review scope) then implementer (content)
- **Suggested artifact path**: `skills/software-planning/references/decomposition-guide.md`

### Proposal 2: Survivors that are equivalent cluster at defaults; removing a test can open a gap

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: sapling
- **Scope**: narrow
- **Priority**: P2 (someday)
- **Source(s)**: `step-schema/LEARNINGS.md` Gotchas [implementer] "Equivalent mutants cluster at defaults" (`encoding="utf-8"` on ASCII data; a keyword whose value equals the dataclass default; remedy: write `.encode()` and read `.decode()`, rely on the default once the validator proved it, giving `survivors=0` over 256 mutants); Technical Debt [implementer] "Removing a test can open a mutation gap" (deleting a shim-only test dropped the only assertion on the verdict dict's key names, 6 survivors in `make_verdict`; a substring match on an error message let a message mutant survive, so use an anchored match).
- **Description**: Under "Reading survivors" in the testing-strategy Python reference, name the two concrete equivalent clusters (a redundant `encoding=` on ASCII, a keyword equal to its default) with the remedy of removing the redundancy, not arguing it. Add one line: after deleting or merging a test, re-run the sensor on the module it covered, and assert error messages with an anchored match.
- **Rationale**: The existing text names equivalent mutants in the abstract; an implementer meeting the cluster spends a retry arguing dispositions that code removal ends. Cheap and concrete.
- **Estimated scope**: two to three lines in an existing section
- **Overlap check**: `skills/testing-strategy/references/python-testing.md:235-238` (the abstract class). Pending 2026-11-05 Proposal 6 edits the next paragraph (record survivor ids, clear stale bytecode); disposition both together to avoid conflicting edits. Deferred 2026-10-10 Proposal 3 (subprocess and env boundaries) is a different point.
- **Recommended delegation**: context-engineer (review scope) then implementer (content)
- **Suggested artifact path**: `skills/testing-strategy/references/python-testing.md`

### Proposal 3: Check test files for raw U+2028/U+2029 after any Write

- **Disposition**: pending
- **Type**: skill (update); fallback `docs/claude-code-limitations.md` candidate row
- **Maturity**: seedling
- **Scope**: narrow
- **Priority**: P2 (someday)
- **Source(s)**: `step-loop-dogfood/LEARNINGS.md` Gotchas [implementer] "Tooling (step 5)": the Write tool turned a ` ` escape typed in a Python source string into the raw character; restored to the escape form with a script.
- **Description**: One line for authors of tests and fixtures that carry line-separator characters: write the escape by a method that cannot be normalized (Edit or a scratch script), then grep the file for the raw characters. If a second occurrence confirms it, move it to the limitations catalog with an upstream issue and a ledger row, which that file requires.
- **Rationale**: The failure is silent (the test still passes against the wrong input) and the transcript reader and its tests exist precisely because these separators occur in real transcripts. One occurrence, so seedling; the behavior was observed once and not reproduced here.
- **Estimated scope**: one line
- **Overlap check**: none. Searched `docs/claude-code-limitations.md`, `scripts/CLAUDE.md`, `skills/testing-strategy/` for "U+2028", "raw character", "Write tool": only code and tests that handle the separators.
- **Recommended delegation**: context-engineer (placement) then implementer
- **Suggested artifact path**: `skills/testing-strategy/references/python-testing.md` (alternative: `docs/claude-code-limitations.md`)

## Recommended Delegations

| Proposal | Delegation Path | Notes |
|---|---|---|
| 1 | context-engineer then implementer | Reference paragraph; keep beside the `Files:` guidance |
| 2 | context-engineer then implementer | Same file as pending 2026-11-05 Proposal 6; one edit pass |
| 3 | context-engineer then implementer | Seedling; may be deferred until a second occurrence |

## Disposition Log

<!-- Populated by /skill-genesis-review. Empty on report creation. -->

| Timestamp | Proposal | Disposition | Notes |
|---|---|---|---|
| _(empty — pending review)_ | | | |

## Recommended Next Steps

- Run `/skill-genesis-review` to disposition the 3 pending proposals.
- Proposals 2 and 3 touch `python-testing.md`; disposition them with pending 2026-11-05 Proposal 6 together.
- Remaining batches (3 to 11) should check this report's headings before proposing an overlapping lesson.
