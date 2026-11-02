---
schema_version: 1
report_id: skill-genesis-2026-10-31_20-11-33
generated_at: 2026-10-31T20:11:33Z
task_slug: context-diet-resume
agent_version: skill-genesis@a3ba7469
invocation_args: { since: null, scope: null, sources: ".ai-work/_harvest-diet", batch: "5 of 5", dry_run: false }
review_status: complete
disposition_count: { pending: 0, approved: 0, rejected: 6, refined: 0, deferred: 0 }
---

# Skill Genesis Report — 2026-10-31 20:11:33

## Summary

Queue mode, batch 5 of 5: one source (`skill-crafting-refresh`, the td-391 pipeline, closed 2026-10-11). 19 learning items extracted from `LEARNINGS.md` and `VERIFICATION_REPORT.md`; 11 deduplicated or skipped, 6 proposals generated (2 of them extend pending proposals from earlier batches), 2 defects listed for ledger routing. Review status: pending.

Interpretation and assumptions: (1) the pipeline's product (the reworked `skill-crafting` skill, its validator, trigger evals) is already shipped, so only process learnings about *how the pipeline ran* are proposal candidates; (2) a learning whose fix is already a resolved ledger row (td-414, td-417, td-418) or already in the tree is a Skip, not a proposal; (3) `VERIFICATION_REPORT.md` was read for headings, verdict, REQ-25/26 and the recommendations, not line by line; its remaining content is the per-REQ table and is covered by the verifier's own merged learnings.

## Learning Sources Consumed

| Source | Path | Items Extracted | Status |
|---|---|---|---|
| LEARNINGS.md (queue source) | `.ai-work/_harvest-diet/skill-crafting-refresh/LEARNINGS.md` | 16 | Read |
| VERIFICATION_REPORT.md (queue source) | `.ai-work/_harvest-diet/skill-crafting-refresh/VERIFICATION_REPORT.md` | 3 | Read (headings, verdict, REQ-25/26, recommendations; per-REQ table not mined) |
| CONSULT_*.md | same directory | 0 | Not found |
| Latest SENTINEL_REPORT_*.md | not read this batch (ecosystem findings are not this source's subject) | 0 | Not consulted |
| ADRs | `.ai-state/decisions/450-repo-root-plugin-eval-suite.md` | 0 | 1 matched (verified W4 amendment landed) |
| Calibration log Retrospective cells | `.ai-state/calibration_log.md` | 0 | Not consulted (source pipeline's row is in the verification report) |
| Prior reports of this run | `SKILL_GENESIS_REPORT_2026-10-31_19-30-34.md`, `_19-33-49.md`, `_19-40-39.md`, `_19-45-58.md` | n/a | Read (proposal headings, for deduplication) |

`prior-report: no` on the source; `memory: yes` (`project_commands_to_skills.md` names td-391; four `feedback_skill_*` memories hold skill-crafting gotchas already shipped in `skills/skill-crafting/`).

## Triage Results

| # | Item | Source | Decision | Rationale |
|---|---|---|---|---|
| 1 | One code source for the frontmatter field set (`frontmatter_contract.py`) | LEARNINGS dec-draft-92a84d08 | Skip | Shipped and documented by the ADR and `schema.md`. |
| 2 | Reference-set restructure, entry page rebuild | LEARNINGS dec-draft-911fdeba | Skip | Product, now in the tree. |
| 3 | Plugin eval suite at repo-root `evals/`; list lines not a second table in `MEASUREMENTS.md`; `--no-publish`; `tool_used: Skill` graders excluded in two-arm runs | LEARNINGS decisions and constraints | Skip | In `evaluating-skills.md` lines 78-93 (verified), ADR 450. |
| 4 | Oversized plugin directory (>20,000 entries) scores 0 at exit 0; ADR draft said "zero-flag" | VERIFICATION W4, verifier learning | Skip / fold | Reference page and ADR 450 amended (verified). The *process* half is Proposal 4. |
| 5 | Warnings as a separate severity; `withheld` via the F07 row | LEARNINGS behavioral decisions | Skip | Shipped behaviour. |
| 6 | Planner: no `mutation:` tag on a layout the sensor refuses | LEARNINGS planner | Skip | Pending batch 1 Proposal 3. |
| 7 | Planner: every red node owned; step-loop node ownership; function-level `Read-only:` owns parametrized variants; shared node has one owner | LEARNINGS planner | Fold | Pending batch 1 Proposal 5 covers ownership; the page-rebuild ordering traps are new: Proposal 1. |
| 8 | A late removal step is a no-op if an earlier rewrite dropped its target text; catalog list set only after headings and markers exist (else `withheld` goes red) | LEARNINGS planner (items 29, 42) | Skill | Proposal 1. |
| 9 | Field-label line start parsed as that field; `Files:` admits only paths with `/` or `.`; `Check:` runs without a shell; plan parsed with the driver's own reader | LEARNINGS planner | Skip | Memories `feedback_step_loop_files_globs_never_match`, `feedback_plan_readonly_field_one_line`, `feedback_check_runs_without_a_shell`; plan-authoring home is pending batch 1 Proposals 2 and 5. |
| 10 | Driver orders entry-page topics by unanchored word patterns (`script` matches "Description"; `gotcha` pins the topic); a design heading failed its own plan rule; checklist item 6 conflicted with the pinned order | LEARNINGS gotcha, Step 12, verifier | Skill | Proposal 2; the driver defect itself is Defect 1. |
| 11 | Plan said "the way neighbours do, never `__file__` arithmetic"; no neighbour did | LEARNINGS test-engineer, Step 1 | Skill | Proposal 5. |
| 12 | Acceptance driver not importable as a package; load by path, register in `sys.modules` before `exec_module` | LEARNINGS test-engineer | Skill | Proposal 6. |
| 13 | `TEST_RESULTS.md` green section cap 1024 bytes; `Command:` names the Check | LEARNINGS implementer | Skip | The checker reports the ceiling and the fix itself (`check_test_results_shape.py`, "exceeds ceiling"). |
| 14 | `resolve_test_scope.py \| sh -e`: args after `sh -e` go to `sh`; `-e` stops at the first red pocket | LEARNINGS implementer | Skip | One-occurrence local gotcha; `test-selection.md` documents the `\| sh -e` form. Revisit if it recurs. |
| 15 | Step 11 re-verification of drift-prone docs (reload semantics, `Skill(...)` deny form) | LEARNINGS implementer | Skip | Landed in `plugin-and-troubleshooting.md`; dated markers carry it. |
| 16 | Marker must sit directly below the heading; a blank line turned F07 and two marker nodes red | LEARNINGS Step 12 | Skip | Already stated at `rules/swe/staleness-policy.md:14` ("no blank line between heading and marker"). |
| 17 | A skill that teaches a checklist fails it where the outer loop pins the order; an eval set sized from the probe floor is not three scenarios; a rewritten CLI must honour the `--help` contract it teaches; a guarded skip dropped more coverage than the guard needed | VERIFICATION F1, verifier learnings | Skill | Proposal 3 (one verifier self-application pass). Fixes themselves: td-417, td-418 resolved. |
| 18 | `NAME_PATTERN` ending in `$` accepts a trailing newline | LEARNINGS Step 6 review finding | Skip | Fixed in tree: `frontmatter_contract.py:79` uses `fullmatch`. |
| 19 | Closed input classes collide with the current-docs mandate | VERIFICATION W1 | Skip | td-419 open (rule amendment at three paired sites). |
| 20 | ADR draft kept a premise a live run disproved | verifier learning | Skill | Proposal 4 (extends pending batch 2 Proposal 3). |
| 21 | Baseline run detached while planning; plan rendered from data and parsed with the driver's reader | LEARNINGS patterns | Skip | Memory `feedback_detach_long_test_runs`; plan-parse practice is the planner's own and is covered by Proposal 1's last bullet only in passing. |
| 22 | Driver `--base-ref` must be the design-state commit when a deleted stub was added after the base | LEARNINGS | Skip | Memory `feedback_step_loop_base_ref_unmerged_parent` is the same family. |

## Discipline-Gap Signals

None recorded.

## Proposals

### Proposal 1: decomposition-guide — ordering traps when the plan rebuilds a documentation page under a read-only acceptance driver

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: sapling
- **Scope**: narrow
- **Priority**: P1 (next-cycle)
- **Source(s)**: `skill-crafting-refresh/LEARNINGS.md` Assumptions (planner: "a cataloged title that matches no heading is `withheld` and turns a guard node red; the catalog list is therefore set in Step 12"), Gotchas ("Steps 5 and 14 rewrite the sections that hold the two caveat sentences but must leave them verbatim for Step 19; a rewrite that drops them early would turn the late deletion step into a no-op with a green-before check"), Edge Cases ("a node that two steps both advance has one owner: the step after which it first reads green"; "Check for a guard-only step cannot be red before; its new unit test file is the floor"), Assumptions (page-wide parametrized nodes change count as files change).
- **Description**: Add to the planner's decomposition guidance a short block for plans that move or rewrite prose under a structural acceptance driver: (a) a deletion step is ordered after every rewrite of its section, and each earlier rewrite states in its brief that the target text stays verbatim, because a rewrite that drops it makes the deletion green before it runs; (b) a catalog or index of titles is set last, after the steps that create each heading and marker; (c) a page-wide parametrized node is owned by the step after which it first reads green, later steps re-run it in `Check:` without owning it, and its floor is stated as a lower bound; (d) a guard-only step's red-before is its own new unit test.
- **Rationale**: Each of the four points was found and handled by a planner who knew the driver; none is written down, and each failure is silent (a no-op step, a node that goes red one step late). Same family as pending batch 1 Proposal 5 but about documentation moves rather than code, so one block in the same guide serves both.
- **Estimated scope**: one subsection (about 15 lines) in an existing reference
- **Overlap check**: pending batch 1 Proposal 5 (guard ownership; extends it, merge the bullets at review) and pending 2026-10-11 plan-authoring proposal; `decomposition-guide.md` line 56 (contract-first step) is adjacent, not overlapping; memory `feedback_unproven_step_keeps_nodes_pending` (mechanism, not ordering).
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `skills/software-planning/references/decomposition-guide.md`

### Proposal 2: acceptance-design stage — read the driver's topic vocabulary before a spec applies a page's canon to itself, and before naming headings

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: sapling
- **Scope**: narrow
- **Priority**: P1 (next-cycle)
- **Source(s)**: `skill-crafting-refresh/LEARNINGS.md` Gotchas (entry-page driver orders topics by the first heading matching each pattern; an h3 containing "script" before the scripts section breaks the order), Step 12 (the design's own heading "Invocation Modes and the Description's Reader" had to be renamed because "Description" contains "script"), Verifier (a REQ that applies the page's canon to itself pinned the order against checklist item 6), Orchestrator dispositions ("page now opens with a failure list under a heading that avoids the word the read-only acceptance driver classifies as a topic").
- **Description**: In the acceptance-design stage text (and the architect's spec step that writes a self-application REQ), require: when a REQ makes a page obey its own canon and an outer-loop driver pins section order or topic by pattern, the architect and the test-engineer read the driver's patterns, list the headings the design intends, and run them through the patterns before the plan is written; any clash is settled then, as a recorded Spec Question, not at implementation or verification.
- **Rationale**: The clash cost a heading rename mid-implementation, a verifier FAIL on REQ-26 item 6, a rework row and an orchestrator workaround, all from patterns that were readable at design time. It is a specific case of the pending "record the spec question when the outer-loop change is made" rule, with a cheap mechanical preflight (match intended headings against the driver's patterns).
- **Estimated scope**: one paragraph in an existing reference
- **Overlap check**: pending batch 2 Proposal 1 (Spec Question recorded when the outer-loop change is made; this supplies the trigger at design time, merge); pending batch 4 Proposal 3 (orchestrator ruling quotes the REQ; same Spec Question path); `coordination-details.md#acceptance-design-stage` states the allowed inputs but not this preflight.
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `skills/software-planning/references/coordination-details.md` (acceptance-design stage)

### Proposal 3: verifier — a self-application pass for a change that teaches a convention

- **Disposition**: pending
- **Type**: skill (update) — agent definition
- **Maturity**: sapling
- **Scope**: narrow
- **Priority**: P1 (next-cycle)
- **Source(s)**: `skill-crafting-refresh/LEARNINGS.md` Verifier entries ("a skill that teaches a checklist fails its own checklist"; "a beyond-the-floor eval case is not three scenarios"; "a rewritten CLI must honour the contract its own skill teaches: probe `--help` on every bundled script the change touches"; "a guarded skip can cost more coverage than the guard needs"); `VERIFICATION_REPORT.md` REQ-26 table (items 6, 8, 9 failed or warned; results td-417, td-418).
- **Description**: In `agents/verifier.md`, add a short pass for any change whose product states a convention (a skill, rule or checker rewrite): apply the convention's own checklist to the change's artifacts and list each item with a verdict; run `--help` on every bundled script the change touches and confirm exit 0 and usage output; size the change's own eval or test set from the checklist's floor, not the probe's; and for a multi-part check that gained a skip reason, confirm the skip drops only the part whose input is missing.
- **Rationale**: Four findings in one verification, all of one kind: the artifact violates what it teaches. The verifier found them only because REQ-26 was in the spec; without that REQ, the pass would have missed them. A standing line in the verifier makes it independent of the spec carrying the REQ.
- **Estimated scope**: one numbered item under the verifier's convention-compliance phase
- **Overlap check**: pending batch 4 Proposal 1 (implementer and verifier name every mode of a governed function; same agent file, adjacent point, merge the edits); `skills/skill-crafting/SKILL.md` Checklist and `scripts-for-agents.md` teach authors the conventions but do not reach the verifier. None in `agents/verifier.md` (grep for self-application and `--help` empty).
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `agents/verifier.md`

### Proposal 4: software-planning — a live run that contradicts an ADR draft's premise amends the draft before finalize

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: seedling
- **Scope**: narrow
- **Priority**: P2 (someday)
- **Source(s)**: `skill-crafting-refresh/LEARNINGS.md` Verifier ("an ADR draft's 'zero-flag' consequence survived a live run that disproved it"); `VERIFICATION_REPORT.md` W4 (route: amend Consequences and Falsifier before finalize).
- **Description**: Extend the pending "refresh an ADR draft after a revision changes its decision" sentence with a second trigger: a live run, measurement or paid evaluation whose result contradicts a draft's stated consequence or falsifier obliges the author of that run (usually the orchestrator) to amend the draft in the same step that records the result, not at verification.
- **Rationale**: Same failure as batch 2 Proposal 3 (draft diverges from built reality, verifier finds it), reached by a different trigger. It costs one sentence in a place already being edited, so it is a rider, not an independent artifact. Seedling because one occurrence supports it.
- **Estimated scope**: one sentence added to the pending proposal's target
- **Overlap check**: pending batch 2 Proposal 3 (extends it; reviewer may fold and reject this one); `coordination-details.md:411` (a different trigger).
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `skills/software-planning/references/decomposition-guide.md` and `skills/software-planning/references/rework-manifest.md` (same paragraphs as batch 2 Proposal 3)

### Proposal 5: implementation-planner — a plan's claim about how neighbouring code does something names the file

- **Disposition**: pending
- **Type**: skill (update) — agent definition
- **Maturity**: seedling
- **Scope**: narrow
- **Priority**: P2 (someday)
- **Source(s)**: `skill-crafting-refresh/LEARNINGS.md` test-engineer Step 1 ("the plan said to resolve the repository root 'the way the neighbouring drivers do, never by `__file__` arithmetic', but no neighbour does that; all use `Path(__file__).resolve().parents[3]`"); Technical Debt ("Step 1 deviation ... the driver was switched to that convention before commit c15e8928").
- **Description**: In the planner's step-writing guidance, state that a step brief which tells the implementer to follow a convention "as neighbouring files do" cites one such file by path, found by search at plan time; a brief that cannot cite one states the convention directly or drops the claim.
- **Rationale**: An uncited neighbour convention is an unchecked assumption handed to an implementer as an instruction; here it was wrong, cost a deviation and a rework of the first step's commit. One occurrence, but the fix is a single line and matches the planner's existing duty to ground steps in the codebase.
- **Estimated scope**: one bullet in the planner's step-brief checklist
- **Overlap check**: none in `agents/implementation-planner.md` (grep for premise, neighbour and grounding found nothing relevant); behavioral contract "Surface Assumptions" is the general principle.
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `agents/implementation-planner.md`

### Proposal 6: test-engineer — probe an acceptance driver by file path, registered in `sys.modules`

- **Disposition**: pending
- **Type**: skill (update) — agent definition
- **Maturity**: seedling
- **Scope**: narrow
- **Priority**: P2 (someday)
- **Source(s)**: `skill-crafting-refresh/LEARNINGS.md` test-engineer Step 1 ("`tests.acceptance` is not importable as a package from a bare `python3` in this repo (`ModuleNotFoundError`); a probe script must load the driver by file path and register it in `sys.modules` before `exec_module`, or `@dataclass` raises `AttributeError: 'NoneType' ... __dict__`").
- **Description**: In the test-engineer's driver-authoring guidance, add the probe recipe: `importlib.util.spec_from_file_location`, `sys.modules[name] = module`, then `spec.loader.exec_module(module)`; and name the failure signatures (`ModuleNotFoundError` on the package path, a `@dataclass` `__dict__` error when the module is not registered first).
- **Rationale**: The two error messages point away from the cause, so an agent loses turns on them; the recipe is three lines. Narrow and from a single run, so seedling and P2.
- **Estimated scope**: 3 lines in an existing section
- **Overlap check**: `agents/test-engineer.md:138` says test files must be importable but does not cover probing a driver outside pytest; memory `feedback_acceptance_tests_no_git_history` is unrelated.
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `agents/test-engineer.md`

## Recommended Delegations

| Proposal | Delegation Path | Notes |
|---|---|---|
| 1 | context-engineer | Merge with batch 1 Proposal 5 into one block in `decomposition-guide.md` |
| 2 | context-engineer | Merge with batch 2 Proposal 1; sits in `coordination-details.md` |
| 3 | context-engineer | Same file as batch 4 Proposal 1 (`agents/verifier.md`); one edit pass |
| 4 | context-engineer | Rider on batch 2 Proposal 3; reject if that one is folded |
| 5 | context-engineer | One-line addition |
| 6 | context-engineer | Same file as batch 3 Proposal 5 (`agents/test-engineer.md`) |

## Defects and Deferred Fixes (for ledger routing; not artifact proposals)

Confirmed against the tree at `a3ba7469`. The ledger was not edited. td-412, td-413, td-416 (open) and td-414, td-415, td-417, td-418, td-419 (filed or resolved) already cover the rest of this source's deferred items.

1. **Acceptance driver topic patterns are unanchored substrings.** `tests/acceptance/drivers/skill_pages.py:38-47`: `ENTRY_TOPICS` maps "scripts designed for agents" to `r"script"` and "degrees of freedom and gotchas" to `r"freedom|gotcha|specificity"`, and `LAYOUT_TOPIC` to `r"layout|anatomy|structure|director|packag"`. `script` matches the headings "Description" and "Prescription"; `gotcha` pins any gotcha heading below invocation modes, so the entry page cannot lead with a gotchas section (checklist item 6). Evidence: the Step 12 heading rename and REQ-26 item 6 in the verification report; the shipped page works around it with "Where Skills Go Wrong by Default" (`skills/skill-crafting/SKILL.md:39`). Fix: word-boundary patterns (`\bscripts?\b`) and either relax the gotchas ordering or move it ahead of invocation modes; the driver is outer-loop, so it needs an orchestrator-mediated Spec Question. Suggested owner: test-engineer.
2. **`lens-fanout` user-only description spans 10 lines.** `skills/lens-fanout/SKILL.md:3-12` (`description: >`). Reproduced: `python3 skills/skill-crafting/scripts/validate.py skills/lens-fanout` prints `WARNINGS -- 1 warning(s): user-only skill's description spans 10 lines — write it on one line`. The planner scheduled a ledger row for it (LEARNINGS Technical Debt); none exists in the ledger or the resolved file. Fix: collapse to one line (the trigger terms are irrelevant for a user-only skill). Suggested owner: context-engineer; severity: suggested.

## Disposition Log

<!-- Populated by /skill-genesis-review. Empty on report creation. -->

| Timestamp | Proposal | Disposition | Notes |
|---|---|---|---|
| 2026-11-01T23:00:00Z | Proposal 1: ordering traps when rebuilding a doc page under a read-only driver | reject | below-bar: One pipeline, four prose points, no check |
| 2026-11-01T23:00:00Z | Proposal 2: read driver topic vocabulary before applying a page canon to itself | reject | duplicate: A trigger case of 2026-10-31_19-33-49 P1; single occurrence |
| 2026-11-01T23:00:00Z | Proposal 3: verifier self-application pass | reject | below-bar: One verification; adds to a 57 KB per-spawn agent; the spec carried the REQ that found it |
| 2026-11-01T23:00:00Z | Proposal 4: live run contradicting ADR draft amends the draft | reject | duplicate: Rider on 2026-10-31_19-33-49 P3, itself built |
| 2026-11-01T23:00:00Z | Proposal 5: plan claim about neighbouring code names the file | reject | below-bar: One occurrence |
| 2026-11-01T23:00:00Z | Proposal 6: probe acceptance driver by file path in sys.modules | reject | below-bar: One run, three-line recipe, narrow |

## Run-Level Summary (all five batches of the 2026-10-31 run)

| Batch | Report | Proposals | Defects listed |
|---|---|---|---|
| 1 | `SKILL_GENESIS_REPORT_2026-10-31_19-30-34.md` | 6 | yes (section at line 159) |
| 2 | `SKILL_GENESIS_REPORT_2026-10-31_19-33-49.md` | 7 | yes (section at line 185) |
| 3 | `SKILL_GENESIS_REPORT_2026-10-31_19-40-39.md` | 5 | yes (section at line 136) |
| 4 | `SKILL_GENESIS_REPORT_2026-10-31_19-45-58.md` | 5 | yes (section at line 155) |
| 5 | `SKILL_GENESIS_REPORT_2026-10-31_20-11-33.md` | 6 | 2 |
| **Total** | | **29** | |

Proposals that extend or share an edit site, to walk together in `/skill-genesis-review`:

- **Plan-authoring block in `decomposition-guide.md`**: batch 1 Proposal 5 (guard ownership, partition check, binding order) + batch 5 Proposal 1 (page-rebuild ordering) + batch 2 Proposal 3 and batch 5 Proposal 4 (ADR draft refresh on revision, and on a contradicting live run; the second is a rider). Also batch 1's older pending plan-authoring proposals (2026-10-11 Proposal 2).
- **Spec Question timing**: batch 2 Proposal 1 (record when the outer-loop change is made) + batch 4 Proposal 3 (ruling quotes the governing REQ) + batch 5 Proposal 2 (design-time driver-vocabulary preflight). Approve as one `coordination-details.md` edit.
- **`agents/verifier.md`**: batch 4 Proposal 1 (name every mode of a governed function) + batch 5 Proposal 3 (self-application pass). One edit pass.
- **`agents/test-engineer.md`**: batch 3 Proposal 5 (allowed inputs only) + batch 5 Proposal 6 (probe recipe).
- **`agents/implementation-planner.md`**: batch 1 Proposals 3 and 4 + batch 5 Proposal 5 (cite the neighbour).
- Priority spread of this batch: three P1 (1, 2, 3), three P2 (4, 5, 6); the three seedlings (4, 5, 6) are the first to reject if the review wants a short list.

## Recommended Next Steps

- Run `/skill-genesis-review` to disposition the 6 pending proposals of this report, walking the clusters above together with batches 1 to 4.
- Route the 2 defects to ledger rows (orchestrator, verifier, sentinel or architect-validator write; this agent does not).
- After approval, invoke `context-engineer` per the delegation table.
