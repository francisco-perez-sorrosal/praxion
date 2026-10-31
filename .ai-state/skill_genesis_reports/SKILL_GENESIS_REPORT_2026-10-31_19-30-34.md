---
schema_version: 1
report_id: skill-genesis-2026-10-31_19-30-34
generated_at: 2026-10-31T19:30:34Z
task_slug: context-diet-resume
agent_version: skill-genesis@1ca8461a
invocation_args: { since: null, scope: null, sources: ".ai-work/_harvest-diet", batch: "1 of 5", dry_run: false }
review_status: pending
disposition_count: { pending: 6, approved: 0, rejected: 0, refined: 0, deferred: 0 }
---

# Skill Genesis Report — 2026-10-31 19:30:34

## Summary

Queue mode, batch 1 of 5. 2 sources analyzed (`adherence-eval`, `adr-move-readiness`), 24 learning items extracted, 6 proposals generated (5 skill updates, 1 rule/skill-reference update; no new artifacts), 12 items deduplicated or skipped, 8 defect/deferred-fix items listed separately for ledger routing. No discipline-gap signals. Review status: pending.

Interpretation and assumptions (surfaced): (1) both sources are first harvests (`prior-report: no`); the `memory: yes` flag was read as "a memory exists", so each memory-held learning was still checked against shipped artifacts, per the orchestrator note that memory is a supplement. (2) Items already tracked by a `td-NNN` row are listed under Defects, not proposed. (3) Domain-specific eval-harness facts (arm proof internals, kit shapes, check-catalog decisions) live in `eval/EVAL_PLAN.md` and the code; only the portable residue was triaged.

## Learning Sources Consumed

| Source | Path | Items Extracted | Status |
|---|---|---|---|
| Queue source: adherence-eval LEARNINGS | `.ai-work/_harvest-diet/adherence-eval/LEARNINGS.md` | 13 | Read |
| Queue source: adherence-eval VERIFICATION_REPORT (round 2) | `.ai-work/_harvest-diet/adherence-eval/VERIFICATION_REPORT.md` | 5 | Read (Round 1 history table, Security, Spec Conformance skimmed) |
| Queue source: adherence-eval consult | `.ai-work/_harvest-diet/adherence-eval/CONSULT_statistician.md` | 3 | Read (CH-03..CH-06 in full; CH-01/02 by heading) |
| Queue source: adr-move-readiness LEARNINGS | `.ai-work/_harvest-diet/adr-move-readiness/LEARNINGS.md` | 8 | Read |
| Queue source: adr-move-readiness VERIFICATION_REPORT | `.ai-work/_harvest-diet/adr-move-readiness/VERIFICATION_REPORT.md` | 4 | Read (Delta, Convention, Code-Review, Tech-Debt, Recommendations; Security, Architecture-doc sections skipped) |
| Latest SENTINEL_REPORT / IDEA_LEDGER | `.ai-state/` | 0 | Not consulted (queue mode, scoped to listed sources); ledger rows checked by grep |
| ADRs | `.ai-state/decisions/` | 0 | Not matched (dec-458/459 cited inside sources are eval-design, already recorded) |
| Calibration log Retrospective cells | `.ai-state/calibration_log.md` | 0 | Not read (outside this batch's sources) |

## Triage Results

| # | Item | Source | Decision | Rationale |
|---|---|---|---|---|
| 1 | End-state grader's subject ("any new Markdown") collided with what the always-loaded process and tools write (calibration log, `.pytest_cache/README.md`) | adr-move VR #warn-1; LEARNINGS "Lesson" | Skill (update) | Proposal 1 |
| 2 | Floor-arm fixture fidelity: hackathon block, header-only index leaking the drafts path, arm copy shipping skill references carrying the protocol | adr-move LEARNINGS Surprising Findings | Skill (update) | Proposal 1 (portable residue); the git-kit instance is td-526 territory |
| 3 | Ablation-arm proof: marker travels only through the channel under test; lean proven by a positive observation (`NO-MARKER`), not absence | adherence-eval Steps 8, 8r | Skill (update) | Proposal 1 |
| 4 | Non-differential judge error attenuates the paired difference (anti-conservative for non-inferiority) | consult CH-04 | Skill (update) | Proposal 2; absent from `applied-statistics` |
| 5 | Reruns allow best-of-N selection across runs (single-run 5.5-7.2% false clear becomes 16-20% at three runs) | consult CH-03 | Skill (update) | Proposal 2; the skill's "best of N" gotcha covers benchmarks/metrics, not reruns of one gate |
| 6 | Dropping pairs with an errored side is biased when the treatment causes the error; target-at-floor leaves no slack | consult CH-05, CH-06 | Skill (update) | Proposal 2 |
| 7 | `mutation: on` tagged on layouts the sensor always refuses (`not-flat-layout`): 7 steps in adr-move, 8+ in adherence-eval, zero readings | both LEARNINGS; adr-move VR coverage note | Skill (update) | Proposal 3; tooling side is td-522 |
| 8 | Files sets too narrow for a shared type module / near the 800-line ceiling (`model.py` x3, `cli.py` 944, `results.py` outside Files, `checks_common.py` split) | adherence-eval Steps 3, 9, 13, 15, 17; Tech Debt | Skill (update) | Proposal 4 |
| 9 | Guards owned by the earliest step that can regress them; node partition verified with `--collect-only` and the gate's longest-prefix rule; driver bindings before production | adr-move planner decisions; adherence-eval Patterns That Worked | Skill (update) | Proposal 5 (extends a pending sibling) |
| 10 | A rework row bundling a FAIL with a WARN loses the WARN when the step is planned from the FAIL alone | adherence-eval VR "Merge to LEARNINGS" | Skill (update) | Proposal 6; seedling |
| 11 | A fix found by a live run needs a test through the production caller (per-role allowance reader) | adherence-eval VR new-2 | Skip (dedup) | Same family as pending 2026-09-23_23-05-46 proposal on production-caller configurations; recurrence recorded in Proposal 5's rationale only as evidence |
| 12 | `Check:` runs without a shell; `--no-cov` is a root-pocket flag; `Assignee` exactly `implementer` | both planner gotchas | Skip (dedup) | Memory `feedback_check_runs_without_a_shell`, `feedback_step_loop_files_globs_never_match`; pending 2026-10-11 Proposal 2 covers the `Files:`/`Check:` hygiene file |
| 13 | Mutation refusal line needs `(detail)` or the step is gated blocked | adherence-eval | Skip (dedup) | Memory `feedback_mutation_refusal_line_needs_detail`; grammar in `scripts/_mutation_grammar.py` |
| 14 | Background `Agent` launch returns a stub; the role's return arrives as `task_notification.summary` | adherence-eval Step 3 | Skip | Eval-harness specific, documented in `grade._role_return` and `eval/EVAL_PLAN.md`; unverified for long returns |
| 15 | Per-role allowance keys in a flat map; `uv run --directory eval pytest`; pyright widens comprehension literals; shlex C4 limits; kit/overlay shapes; ADR check part decomposition | both LEARNINGS | Skip | Package-local design detail with an ADR (dec-458/459) or code comment home; pyright item in memory |
| 16 | Out-of-`Files:` boy-scout edits committed separately and surfaced | both | Skip | Process works as written (verifier ruled no `[NON-SURGICAL]`) |
| 17 | Hook wrote a tracked file (`.ai-state/observations_summary.jsonl`) before the Base-commit gate | adr-move Surprising Findings | Defect | Listed below |
| 18 | Late-spec amendments, statistics ADR supersession, delivery batching | adherence-eval planner | Skip | One-off scheduling/decision records already in ADRs |

## Proposals

### Proposal 1: agent-evals — design the grader's subject and the arms' fixtures against the real session, not the task

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: sapling
- **Scope**: medium
- **Priority**: P1 (next-cycle)
- **Source(s)**: `adr-move-readiness/VERIFICATION_REPORT.md` #warn-1 (reproduced: a conforming draft plus `.ai-state/calibration_log.md` or `.pytest_cache/README.md` failed placement and category) and Merge-to-LEARNINGS candidate (a); `adr-move-readiness/LEARNINGS.md` "Lesson" and Surprising Findings (hackathon block in a non-hackathon fixture; header-only `DECISIONS_INDEX.md` leaking the drafts path; arm copy carrying the full protocol through skill references); `adherence-eval/LEARNINGS.md` Steps 8 and 8r (`proof_prompt()` takes no nonce; lean proven by the declared `NO-MARKER` reply, not by the nonce's absence).
- **Description**: Add a short "process-adherence evals" section to `eval-design-patterns.md` with three declarative gotchas. (1) A grader that defines its subject as "any new file of a type" is checked against what the always-loaded process tells every session to write and what tools write unasked, before the first paid run; a risk rated only against the task's own requests misses both. (2) A floor/lean arm is contaminated by any other channel that carries the governed text (skill references, an index header, a canonical block the fixture project would not carry), so fixtures mirror a real project of that kind and the arm copy is audited for such channels. (3) An arm proof routes its marker only through the channel under test (never the prompt both arms see), and proves the ablated arm by a positive observation, not by absence.
- **Rationale**: Both pipelines hit the same class of failure in different eval moves: a measurement that would have read 0% or 100% for reasons unrelated to the behavior under test. The portable principle (validate the instrument against the real session before paying for runs) is not in `agent-evals`, whose gotchas cover grader fairness and transcript review generally. Three sightings across two pipelines; the adr-move one was caught only by the verifier's reproduction.
- **Estimated scope**: SKILL.md gotcha line (one) + one section in `references/eval-design-patterns.md`
- **Overlap check**: `skills/agent-evals/SKILL.md` lines 30, 46 ("0% pass rate usually means broken eval"; "skip transcript review at your peril") are adjacent, not equal; `rules/swe/gate-liveness.md` covers canaries, not subject definition. Partial.
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `skills/agent-evals/references/eval-design-patterns.md` (+ pointer in `skills/agent-evals/SKILL.md`)

### Proposal 2: applied-statistics — three gate-design gotchas from the statistician consult

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: mature
- **Scope**: narrow
- **Priority**: P1 (next-cycle)
- **Source(s)**: `adherence-eval/CONSULT_statistician.md` CH-03 (best of three runs clears a truly 10 pp worse arm 16-20% vs 5.5-7.2% for one run), CH-04 (judge flips with probability `e` give observed d = true d x (1 - 2e); a 15 pp regression clears at about the nominal rate at `e` = 0.15), CH-05 (one errored session in 50 makes a role underpowered on 40-92% of runs at 1-5% error), CH-06 (excluding errored-side pairs removes exactly the pairs the rule needs when the treatment causes the error); all dispositioned switch-now.
- **Description**: Three gotchas for `skills/applied-statistics/SKILL.md`, with the derivations in `references/eval-inference.md`: (a) rerun-until-clear is optional stopping across runs, so a gate's record cites every run at that configuration and binds the verdict to the first; (b) non-differential judge error attenuates a paired difference, which is anti-conservative for non-inferiority; read the margin on the truth scale or say "as the judge scores it" and measure judge sensitivity/specificity; (c) plan target-plus-slack and exclude errored pairs only with a worst-case recount, because errors caused by the treatment are not missing at random.
- **Rationale**: The consult produced exact figures that survived dispositioning, and the existing gotchas cover benchmark-level best-of-N and unbounded peeking but not these three. The knowledge now lives only in an ephemeral consult and a draft ADR, and every future gated A/B eval repeats the same design traps.
- **Estimated scope**: 3 gotcha bullets in SKILL.md + one section in `references/eval-inference.md`
- **Overlap check**: SKILL.md "best of N benchmarks is a selection", "stopping when the result becomes significant" (adjacent); `references/power-and-sample-size.md` line 31 non-inferiority (no misclassification coverage). Partial.
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `skills/applied-statistics/SKILL.md`, `skills/applied-statistics/references/eval-inference.md`

### Proposal 3: implementation-planner — do not tag `mutation: on` on a layout the sensor always refuses

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: sapling
- **Scope**: narrow
- **Priority**: P1 (next-cycle)
- **Source(s)**: `adr-move-readiness/VERIFICATION_REPORT.md` Test Coverage ("the five tags bought no mutation reading at all ... tag only flat-layout steps"); `adr-move-readiness/LEARNINGS.md` Steps 10, 13, 18 (`not-flat-layout` recorded verbatim); `adherence-eval/LEARNINGS.md` Steps 3, 5, 7, 8, 13, 14, 15 (planner predicted the refusal at plan time: "mutation: on will likely return the declared not-flat-layout refusal"); ledger `td-522`.
- **Description**: One paragraph in `decomposition-guide.md § mutation: on` and the world-read row of `agents/implementation-planner.md`: before tagging a step, check whether its `Files:` sit in a layout the sensor refuses (`src/` layout with tests in a sibling directory, e.g. `eval/`). If so, either drop the tag and record why, or keep it only for the explicit dead-read canary substitute, naming that as the step's guard. The tag otherwise costs a driver-read refusal line per step and yields no reading.
- **Rationale**: Two pipelines, about fifteen steps, zero survivor readings; the planner knew in advance in one of them. The existing guide says when to tag but not when the tag is futile. `td-522` addresses the tool (teach the sensor the layout); this addresses the plan until that lands.
- **Estimated scope**: one paragraph in an existing reference + one table-row sentence in the agent definition
- **Overlap check**: pending 2026-09-27 Proposal 5 (record the verbatim refusal, never fabricate) is complementary: it covers the disposition after the refusal, this covers avoiding the futile tag; memory `feedback_mutation_refusal_line_needs_detail` covers the line grammar.
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `skills/software-planning/references/decomposition-guide.md`, `agents/implementation-planner.md`

### Proposal 4: implementation-planner — put the module a step will overflow or retype into its `Files:`

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: sapling
- **Scope**: narrow
- **Priority**: P2 (someday)
- **Source(s)**: `adherence-eval/LEARNINGS.md` Technical Debt (`model.py` 906 lines, `cli.py` 944 lines over the 800-line ceiling because the plan put every closed type in one file), Step 3 (`BindsFor` takes `TaskSpec` but `model.py` outside `Files:`), Step 13 (split moved two data types, new modules written "beside the declared files"), Step 15 (`checks_common.py` split into `output_forms.py`), Step 17 (`results.py` edited outside `Files:`, committed alone); `adr-move-readiness/LEARNINGS.md` Step 18 (shared helper put in `declaration.py` because `model.py` was outside Files), Step 7 (`test_moves_arms.py` outside Files).
- **Description**: A planner checklist line: for each step, list the files it will grow and read their current size; a file within about 100 lines of the ceiling, or a shared closed-type module that later steps consume, gets its split target (or the sibling module) in the step's `Files:`, or a prior step splits it. A needed type change in a module outside `Files:` is a plan amendment before the step starts, not a boy-scout edit.
- **Rationale**: Seven out-of-`Files:` edits or ceiling overruns across two pipelines, each surfaced correctly but each forcing an orchestrator amendment or a ledger row. The planner can see file sizes and type consumers at planning time. Priority is P2 because the existing surfacing path works; this reduces its load.
- **Estimated scope**: one checklist item in the planner's decomposition guidance
- **Overlap check**: `agents/implementation-planner.md` mentions boy-scout edits only in passing; pending 2026-10-11 Proposal 2 (`plan-files-and-checks.md`) covers path syntax, not sizing. Partial.
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `skills/software-planning/references/decomposition-guide.md` (or the pending `skills/step-loop/references/plan-files-and-checks.md`)

### Proposal 5: step-loop / implementation-planner — guard ownership, node partition check and binding order

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: sapling
- **Scope**: narrow
- **Priority**: P2 (someday)
- **Source(s)**: `adr-move-readiness/LEARNINGS.md` implementation-planner decisions (driver bindings precede every production step; "guards are owned by the earliest step that can regress them" because a failing node owned by a not-yet-done step reads as pending and hides a regression; Check commands use the owner's outer-loop nodes); `adherence-eval/LEARNINGS.md` Patterns That Worked ("machine-checking the node partition against `pytest --collect-only` with the gate's own longest-prefix rule caught the report-before-catalog ordering"), Edge Cases (guard node owned by Step 9 makes its check slow); `adherence-eval/VERIFICATION_REPORT.md` new-2 (a fix with no test through the production caller).
- **Description**: Extend the pending plan-authoring reference with: a guard that is green at base belongs to the earliest step that can break it; verify the node partition against `--collect-only` with the gate's longest-prefix rule before spawning; unbound driver hooks are bound (lazy imports) before any production step; a function the live run fixes gets a test through its production caller.
- **Rationale**: Both planners independently developed the same four-part discipline and it caught real ordering errors before any implementer ran. It is shipped nowhere. Merging with the pending `Files:`/`Check:` hygiene reference keeps one home for plan authoring.
- **Estimated scope**: 4 bullets in a reference page (shared with pending Proposal 2 of 2026-10-11)
- **Overlap check**: pending 2026-10-11 Proposal 2 (adjacent, extends it); pending 2026-09-23_23-05-46 production-caller proposal (the last bullet); memory `feedback_unproven_step_keeps_nodes_pending` (related mechanism).
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `skills/step-loop/references/plan-files-and-checks.md`

### Proposal 6: rework-manifest — a row that bundles a FAIL with a WARN must name both in its step

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: seedling
- **Scope**: narrow
- **Priority**: P2 (someday)
- **Source(s)**: `adherence-eval/VERIFICATION_REPORT.md` Merge-to-LEARNINGS candidate ("a rework row that bundles a FAIL with a WARN loses the WARN when the step is planned from the FAIL alone (warn-3)") and Round 1 table (warn-3 untouched by Steps 16-18, re-opened as td-429).
- **Description**: One sentence in `rework-manifest.md`: each finding in a bundled row is listed by id in the planned step's `Done when`, so a lower-severity finding cannot drop out when the plan is derived from the row's FAIL.
- **Rationale**: One sighting, with a clean mechanism and a concrete cost (warn-3 slipped one full round). Held at seedling; reject if the user prefers to wait for a second instance.
- **Estimated scope**: one sentence in an existing reference
- **Overlap check**: `skills/software-planning/references/rework-manifest.md` and `skills/resume-rework/SKILL.md` define rows and dispatch; neither mentions per-finding closure. Partial.
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `skills/software-planning/references/rework-manifest.md`

## Recommended Delegations

| Proposal | Delegation Path | Notes |
|---|---|---|
| 1 | context-engineer | Skill reference update; load `skill-crafting` |
| 2 | context-engineer | Skill update; load `skill-crafting`; derivations from the consult |
| 3 | context-engineer | Reference + agent-definition edit; load `skill-crafting`, `agent-crafting` |
| 4 | context-engineer | Reference edit; consider merging into pending plan-hygiene reference |
| 5 | context-engineer | Merge with pending 2026-10-11 Proposal 2 |
| 6 | context-engineer | Single sentence; seedling |

## Defects and Deferred Fixes (for ledger routing; not artifact proposals)

Ledger rows already present for the adherence-eval round-2 findings (`td-428`, `td-429`, `td-431` resolved at 02d181ce) and for adr-move (`td-518`, `td-521` to `td-524`, `td-526`) are not repeated. Items below had no matching row in `.ai-state/TECH_DEBT_LEDGER.md` or `TECH_DEBT_RESOLVED.md` at the time of grep; the orchestrator should confirm before filing.

| # | Location | Evidence | Note |
|---|---|---|---|
| D1 | `eval/src/praxion_evals/adherence/checks_common.py:387-465` (`_COMMAND_PREFIXES`, `_HISTORY_WRITERS`, `git_safety`) | adherence-eval VR new-1: `git cherry-pick/revert/am/pull` not in the writer set; `env GIT_DIR=. git commit` and `bash -c "git commit ..."` read as other commands; detail says "ran" for a refused attempt | No `td` row found for new-1/new-3 |
| D2 | `checks_common.py:672-687, 744-750` | adherence-eval VR new-3: catalog still registers the two-signal `_commit_canary`; `commit_attempt_canary` has one test caller | Gate-liveness: catalog canary does not cover the live-reachable path |
| D3 | `smoke/smoke-rerun.json`, `smoke/smoke-run.json` | adherence-eval VR new-4: lean verifier errored as `isolation_breach` in 3 of 3 sessions (a `Read` of the real `~/.claude/CLAUDE.md`), full 0 of 4; under the recount policy every verifier pair reads as a lean failure | Design question (score as signal or fix sandbox) for systems-architect before Phase 2 relies on a verifier reading |
| D4 | `MEASUREMENTS.md` § Step 18; `docs/architecture.md:22` | adherence-eval VR new-5 (recorded USD 9.97 vs ledger 11.48), warn-16 (verification date unstamped), warn-11 (stale SQ-1 prose and `pipeline_tier` in two ADR drafts), new-7 (15 rework tests untraced) | Orchestrator-owned, may already be closed at merge |
| D5 | `.ai-state/observations_summary.jsonl` | adr-move LEARNINGS: modified in the worktree during the spec phase by hooks, while the Base-commit gate expects no tracked change; reproduced in this session's `git status` (` M .ai-state/observations_summary.jsonl`) | Hook writes a tracked file; decide gitignore, untracked-by-design, or gate exemption |
| D6 | `eval/src/praxion_evals/adherence/moves/kit_git.py` (`_project_instructions`) and `kit_adr.py` fixture build | adr-move Surprising Findings: git kit managed fixture carries the hackathon block; onboarded-fresh `DECISIONS_INDEX.md` names `decisions/drafts/` | Fidelity gap that would contaminate floor runs; check whether `td-526` covers it |
| D7 | move checkout copies `.ai-state/eval_ledger/adherence` (committed floor run `ac88c00a`) | adr-move Step 8: two cli-level acceptance nodes stay red because `results == []` cannot hold with a committed run in the copy | Verify closed by later steps; if not, the checkout should exclude the ledger |
| D8 | `eval/README.md` ("Scope today", about line 72), `eval/EVAL_PLAN.md` ("Batch-1 scope and the deferred batch", about line 188); `kit_adr.py:9` docstring; `kit_adr.py:289` 133-char string | adherence-eval Step 15 and adr-move delta C4/O3: stale prose saying kits are not built; branch-segment docstring; unsplit string | Doc owner / boy-scout; confirm against current files |

## Disposition Log

<!-- Populated by /skill-genesis-review. Empty on report creation. -->

| Timestamp | Proposal | Disposition | Notes |
|---|---|---|---|
| _(empty — pending review)_ | | | |

## Recommended Next Steps

- Run `/skill-genesis-review` to disposition the 6 pending proposals (Proposals 4 and 5 overlap pending siblings from 2026-10-11; consider reviewing them together).
- Route D1 to D8 to tech-debt ledger rows after confirming none is already covered.
- Remaining batches (2 to 5 of 5) may repeat evidence for Proposals 3 to 5; check this report's headings before re-proposing.
