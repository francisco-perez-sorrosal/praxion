---
schema_version: 1
report_id: skill-genesis-2026-11-05_21-28-47
generated_at: 2026-11-05T21:28:47Z
task_slug: pg-harvest
agent_version: skill-genesis@0a0d4772
invocation_args: { since: null, scope: "project-gating pipeline (v0.58.0)", sources: ".claude/worktrees/project-gating/.ai-work/project-gating", batch: null, dry_run: false }
review_status: pending
disposition_count: { pending: 6, approved: 0, rejected: 0, refined: 0, deferred: 0 }
---

# Skill Genesis Report — 2026-11-05 21:28:47

## Summary

Post-pipeline harvest of the merged `project-gating` pipeline (Full tier, released v0.58.0). 3 sources read; 32 learning items extracted; 12 feed the 6 proposals, 3 feed the 6 defects listed below (several VERIFICATION findings share a row), and 17 are skipped or deduplicated (already built, already documented, already a ledger row, or a one-off narrative). Review status: pending.

Interpretation and assumptions: (1) the pipeline's product (gated hook delivery, `scope_of`, the slot legs, the budget scope) is shipped, so only learnings about *how future pipelines should run* are proposal candidates; (2) td-577 to td-586 are the rows already filed from this pipeline and every item they carry is a Skip; (3) a defect still open in the tree with no row goes in `## Defects Without a Ledger Row`, not in the proposals, and no ledger row is written here; (4) no memory entry is proposed; each proposal names an artifact the orchestrator, planner, test-engineer or implementer reads.

## Learning Sources Consumed

| Source | Path | Items Extracted | Status |
|---|---|---|---|
| LEARNINGS.md (worktree, read-only) | `.claude/worktrees/project-gating/.ai-work/project-gating/LEARNINGS.md` | 22 | Read |
| VERIFICATION_REPORT.md (worktree, read-only) | `.claude/worktrees/project-gating/.ai-work/project-gating/VERIFICATION_REPORT.md` | 8 | Read |
| Archived spec (context) | `.ai-state/specs/SPEC_project-gating_2026-11-06.md` | 2 | Read ("Key Decisions", "Deferred at Close", "Gotchas Worth Keeping"; uncommitted, read from disk) |
| Tech-debt ledger | `.ai-state/TECH_DEBT_LEDGER.md` | n/a | Read (td-577 to td-586, plus greps for each candidate defect) |
| Latest IDEA_LEDGER | `.ai-state/idea_ledgers/IDEA_LEDGER.md` | 0 | Not consulted (nothing here is a feature idea) |
| SENTINEL_REPORT, ADRs, calibration log, CONSULT fragments | n/a | 0 | Not consulted; the spec's Key Decisions section carries dec-489 and dec-490 |
| Prior pending reports | `.ai-state/skill_genesis_reports/` (latest 2026-10-31_20-11-33, complete) | n/a | Grepped for overlap; none pending |

## Triage Results

| # | Item | Source | Decision | Rationale |
|---|---|---|---|---|
| 1 | A delivery-channel change reaches every reader of that event (30 kernel scenarios found only by the derived scope) | LEARNINGS orchestrator step 16; spec gotcha | Skill | Proposal 1. No text in `skills/` or `agents/` says it. |
| 2 | A new hook helper module must join both move-eval copy lists (52 failures, 38 errors; recurred at `_rule_delivery.py`, `_project_scope.py`, `_rule_blacklist.py`; td-575 earlier) | LEARNINGS implementer (twice); VERIFICATION note 10 | Skill | Proposal 1. Grep of `skills/hook-crafting` finds no copy-list text. |
| 3 | Base-frozen oracles blind to the channel under test: hookless launch driver, frontmatter lines counted, budget reading missing `CLAUDE_PLUGIN_ROOT` (SQ-07, SQ-08, SQ-10) | LEARNINGS gotchas, step 17 spec question; VERIFICATION SQ record | Skill | Proposal 2. Three of six spec questions had this root. |
| 4 | Host-platform loading docs read as "A4 harness isolation" (F-AI1) | VERIFICATION F-AI1 | Fold | Proposal 2, last bullet. |
| 5 | A mitigation that cites an existing mechanism is an unverified claim (td-585, td-586 found at release and archive) | Spec gotcha; td-585/586 | Skill | Proposal 3. |
| 6 | Token reading carries the session's installed plugin; record the plugin root | Spec gotcha; SQ-10 | Skill | Proposal 4. |
| 7 | Run `check_footprint_criteria.py --stage verify` right after writing baseline rows (43 findings at step 20) | LEARNINGS orchestrator; spec gotcha | Skill | Proposal 4. |
| 8 | `measure_token_budget.py --ratchet` writes a sample into `token_budget_baseline.json`; use `--json` | LEARNINGS implementer step 12 | Skill | Proposal 4. The flag is documented only in `--help` and the inventory row. |
| 9 | Resolver lines are 3-7k characters; `cut -c1-400` made pytest report `no tests ran` (exit 5) | LEARNINGS orchestrator step 16 | Skill | Proposal 5. |
| 10 | `resolve_test_scope.py \| sh -e` on a clean committed tree selects nothing; a checkpoint's scope is `--changed-from <base>` | LEARNINGS orchestrator step 19 | Skill | Proposal 5; `test-selection.md:165` names the flag but not the failure. |
| 11 | Step 7's 13 survivors ruled equivalent with no ids recorded; two were not (F-C5) | VERIFICATION F-C5, note 1 | Skill | Proposal 6; the fix itself is td-584. |
| 12 | Stale `.pyc` after a hand mutation within one second (3.13 serves the mutant) | LEARNINGS implementer step 7 | Skill | Proposal 6, one sentence. |
| 13 | Planner `Check:` wrote bare `python3 -m pytest ... -n 4`; ambient python lacks xdist | LEARNINGS orchestrator step 19 | Skip | td-573 (ledgered). |
| 14 | Timing scenario flakes under the full pocket | LEARNINGS orchestrator step 16 | Skip | td-577. |
| 15 | `agent:<name>` placeholder is whole-token only in the footprint grammar | LEARNINGS / VERIFICATION | Skip | td-578. |
| 16 | The move eval cannot express project gating; adherence unmeasured | LEARNINGS step 22; VERIFICATION F-N8 | Skip | td-579; the D1 ADR draft now records it. |
| 17 | `omitClaudeMd: true#x` reads as lean; parity test misses it | VERIFICATION F-C1 | Skip | td-580. |
| 18 | Spawn scope follows the current cwd, not the start directory | VERIFICATION F-C2, B1 | Skip | td-581. |
| 19 | `locate` surviving mutant | VERIFICATION F-T2 | Skip | td-582. |
| 20 | Stale numbers: "six core rules", agent-crafting 21,287, DESIGN row 140, architecture "last verified" | VERIFICATION F-C6/C7/D1/D2 | Skip | td-583. |
| 21 | `install.sh --check` passes with swept links present; `auto_complete_install.py` finds nothing on the versioned cache | spec Deferred at Close | Skip | td-585, td-586. |
| 22 | Orchestrator spec edit late in a pipeline needs `extract_spec.py --check` and a Spec Question (F-AI2, F-AI3, B2) | VERIFICATION FAILs, merge candidates | Skip | Already the "Orchestrator-made amendments" clause in `coordination-details.md`; the failure was non-compliance, resolved by SQ-11/SQ-12. Revisit if it recurs in another pipeline. |
| 23 | Traceability entries go stale when a step splits a file | LEARNINGS orchestrator step 21; spec gotcha | Skip | One occurrence, caught by the verifier's own resolve pass (0 unresolved); no script exists to propose around. Revisit on a second occurrence. |
| 24 | zsh does not word-split `$var` (twice) | LEARNINGS implementer, planner | Skip | Memory `feedback_zsh_param_expansion_no_word_split`; user-environment, not a Praxion artifact. |
| 25 | Full suite exceeds a tool call; detach | LEARNINGS planner, implementer step 12 | Skip | Memory `feedback_detach_long_test_runs`. |
| 26 | Importing fixtures from a sibling test module trips ruff F811; no `conftest.py` under `hooks/` | LEARNINGS implementer | Skip | One-off local; the file is named in its commit. |
| 27 | Mutation sensor cannot run subprocess-style hook tests; needs flat imports and a parent-walking fixture root | LEARNINGS steps 5, 6, 7, 17 | Skip | td-574 (ledgered); the plan already moved the tag to the pure planner. |
| 28 | Hook-channel design choices: event from payload, no effects in a spawn, one effects slot, slots = parts + 1 spare, floor path on any manifest damage, dual import in `location.py`, `namedtuple` scope types under the hot-path import ban | LEARNINGS decisions, dec-489, dec-490 | Skip | Product, now in the tree and the ADRs. |
| 29 | Dead `swe/memory-protocol` entry in `HOOK_DELIVER_ORDER` | LEARNINGS step 16 | Defect | D1. |
| 30 | Canonical block still says host-native subagents do not load `CLAUDE.md` | LEARNINGS technical debt | Defect | D2. |
| 31 | `_budget_scope.py` import-time `StopIteration` and global `sys.path` insert (F-C4); `--dry-run` hides the launch switches (F-C3); no outer-loop pin for an `Explore`/`Plan` spawn (F-SQ1); steps hand-gated outside the loop read `mismatch` | VERIFICATION F-C4, F-C3, F-SQ1, note 5 | Defect | D3 to D6. |
| 32 | Landing order for a channel move: delivery code inert, flip, then the budget instrument | LEARNINGS planner, spec Key Decisions | Skip | One occurrence; a plan-specific ordering argument. Revisit if a second channel move follows. |

## Defects Without a Ledger Row

Still open in the tree at `0a0d4772` and carried by none of td-577 to td-586. For a ledger writer; no row was written here.

| # | Location | Defect | Evidence |
|---|---|---|---|
| D1 | `scripts/regenerate_rules_manifest.py:50` | `HOOK_DELIVER_ORDER` lists `swe/memory-protocol`; `rules/swe/memory-protocol.md` does not exist. The planner and implementer both flagged it as a ledger candidate; the unit fixtures still seed such a rule, so removal needs a test edit. | `ls rules/swe/memory-protocol.md` fails; LEARNINGS step 16, Edge Cases |
| D2 | `claude/canonical-blocks/praxion-process.md:5` | "Host-native subagents do not load CLAUDE.md; the orchestrator is the only delivery path." The pipeline's REQ-02 and the 2026-11-03 context-engineer note contradict it, and managed spawns now receive the process text through `SubagentStart`. Shipped into managed projects. | LEARNINGS Technical Debt; the line is present in the tree |
| D3 | `scripts/_budget_scope.py:19-23` (F-C4) | `next(...)` with no default raises a bare `StopIteration` when no ancestor holds `hooks/_project_scope.py`, and `sys.path.insert(0, hooks/)` runs for every importer of `measure_token_budget`. A same-named module would be shadowed silently. | VERIFICATION F-C4; lines read in the tree |
| D4 | `eval/src/praxion_evals/adherence/cli.py` (F-C3) | `--dry-run` does not print each launch's `PRAXION_DISABLE_PROCESS_INJECT` / `PRAXION_DISABLE_OBSERVABILITY` switches, so a paid run's free pre-flight cannot confirm the condition REQ-12's grading relies on. td-567 covers a different dry-run gap (which arm is measured). | VERIFICATION F-C3; no switch reference in `cli.py` |
| D5 | `tests/acceptance/` (F-SQ1) | No project-gating scenario drives an `Explore` / `Plan` / `general-purpose` spawn; after SQ-09, `test_spawn_kernel_injection.py` fails only on kernel strings, so "a read-only built-in spawn receives no rule part" is pinned only by `hooks/test_inject_rules_subagent.py`. Outer-loop files are the test-engineer's. | VERIFICATION F-SQ1; grep of the gating acceptance files |
| D6 | `scripts/reconcile_pipeline_state.py` | Steps gated by hand after the step loop's iteration budget ran out (16 to 18 here) leave no iteration-ledger record, so the reconciler reads `mismatch` and any `/resume-pipeline` treats them as unverified; the hand gates live only in prose. td-462 is a different reconciler case (test status taken from the latest result). | VERIFICATION note 5 |

## Proposals

### Proposal 1: Hook-crafting reference "Changing what a hook emits or imports"

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: sapling
- **Scope**: medium
- **Priority**: P1 (next-cycle)
- **Source(s)**: LEARNINGS `[orchestrator] A delivery-channel change reaches every reader of that event` (step 16, 30 nodes, SQ-09); LEARNINGS `[implementer] A new hook helper module must join the move-eval copy lists` (step 10, 52 failures + 38 errors; step 9 attempt 2; again for `_rule_blacklist.py`); VERIFICATION note 10 (names td-575 as the earlier break of the same kind); spec "Gotchas Worth Keeping" items 3 and 4.
- **Description**: A short reference page under `skills/hook-crafting/` with two standing rules for a step that touches a hook. (1) A hook module the injector imports must be added in the same step to both copy lists, `tests/acceptance/drivers/move_eval.py::MOVE_CHECKOUT_FILES` and the tuple in `eval/tests/test_moves_observe.py`; name the symptom (`ModuleNotFoundError` across the move-eval nodes) and the grep that finds the lists. (2) A step that changes what a hook event emits names, in its `Check:`, every acceptance file that drives that event (`grep -l "SubagentStart\|kernel_spawn" tests/acceptance`), not only the files written for the change. Two or three lines each, with the numbers above as the reason.
- **Rationale**: Both defects reached the orchestrator as late reds (a 90-node red after step 10; 30 kernel nodes found only by the derived scope after the flip), and the copy-list one has now recurred at least three times in this pipeline plus td-575. The knowledge lives only in a worktree `LEARNINGS.md` that is deleted at close; no artifact a planner or implementer reads carries it. Hook authors load `hook-crafting` when they touch `hooks/`.
- **Estimated scope**: one new reference (about 30 lines) plus one link from `SKILL.md`; optionally one sentence in the `Check:` paragraph of `agents/implementation-planner.md` pointing at it.
- **Overlap check**: `skills/hook-crafting/references/testing-guide.md` (no copy-list or event-reader text); `skills/software-planning/references/document-templates.md` `Check:` schema (grammar only). Partial: none.
- **Recommended delegation**: context-engineer (skill-crafting)
- **Suggested artifact path**: `skills/hook-crafting/references/changing-a-hook.md`

### Proposal 2: Acceptance design proves the driver can see the moved channel

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: sapling
- **Scope**: medium
- **Priority**: P1 (next-cycle)
- **Source(s)**: VERIFICATION Spec Question Record SQ-07 (frozen base readings counted frontmatter lines), SQ-08 (the launch driver ran no hook, so the base was frozen hookless), SQ-10 (the budget reading was blind to the hook channel, `CLAUDE_PLUGIN_ROOT` unset); LEARNINGS step 16 gotchas ("the adherence driver's checkout runs no hook", "the frozen readings count frontmatter lines"); LEARNINGS step 17 Spec Question; VERIFICATION F-AI1.
- **Description**: Extend `coordination-details.md § Acceptance-Design Stage` (and its operational copy in `agents/test-engineer.md`) with a rule for scenarios that compare a base reading with a head reading of a delivery channel: before freezing the base, the test-engineer shows that the driver observes the channel the change moves, by one canary reading that is non-empty on the moved channel at the base (for example a spy on the driver, or one hook-delivered statement present in the frozen text). A base reading that cannot contain the moved text makes the head comparison vacuous. Add one sentence to the A4 class: host-platform pages that describe how the host loads instruction files may inform the harness's model of loading, never an oracle. Keep the paired-site notes.
- **Rationale**: Three of the six spec questions in this pipeline had this one root, each costing a re-freeze and a driver edit after production code existed (the commit-order check then had to account for each). The Spec-Question route handles the symptom; a pre-freeze canary closes the cause at the stage that owns it. Priority P1 because every future channel move (rules, hooks, templates) uses frozen base readings.
- **Estimated scope**: edits to two paired sites (`coordination-details.md`, `agents/test-engineer.md`); `agents/verifier.md` carries class names only, so a one-line note there at most.
- **Overlap check**: `coordination-details.md § Allowed and Forbidden Inputs` and `§ Spec-Question Routing` (partial: route the symptom, not the canary); feedback memory `feedback_rehearse_real_checkout_before_paid_run` (user-side, not an artifact). Pending reports: none.
- **Recommended delegation**: context-engineer (review scope), then implementer (content)
- **Suggested artifact path**: `skills/software-planning/references/coordination-details.md`, `agents/test-engineer.md`

### Proposal 3: Verify the mechanism a mitigation cites on the real layout

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: sapling
- **Scope**: narrow
- **Priority**: P1 (next-cycle)
- **Source(s)**: spec "Gotchas Worth Keeping" item 1 (the double-delivery row leaned on the auto-completion hook, which does nothing once the links exist and whose tests build an unversioned cache; td-586); td-585 (`install.sh --check` passes with swept links present, found at the release).
- **Description**: Add to the risk check in `skills/software-planning/references/design-synthesis.md` (signal 2) and the Risk Assessment guidance in `agents/systems-architect.md`: a mitigation that names an existing mechanism ("re-arms after an update", "the check catches it") cites it with a command that exercises that mechanism on the real install layout, or is recorded as unverified and costed as such. An unverified citation does not count as a concrete mitigation for a High-likelihood by High-impact risk.
- **Rationale**: Two defects of the same shape surfaced after merge, at the release and at the archive, each in an installer path whose unit tests used a simplified layout. Signal 2 currently accepts "a concrete mitigation"; nothing separates a verified one from a cited one. Narrow, but it gates the one point where a design can be wrong without any test noticing.
- **Estimated scope**: two short edits (one paragraph in `design-synthesis.md`, one row-guidance sentence in `agents/systems-architect.md`).
- **Overlap check**: `design-synthesis.md:117` (risk-budget satisfaction, partial); `agents/systems-architect.md` Risk Assessment table (template only). Surface Assumptions in the behavioral contract covers the stance, not this check.
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `skills/software-planning/references/design-synthesis.md`, `agents/systems-architect.md`

### Proposal 4: Footprint measurement steps: check early, record the plugin root, read the budget without ratcheting

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: sapling
- **Scope**: narrow
- **Priority**: P1 (next-cycle)
- **Source(s)**: LEARNINGS `[orchestrator] Run the footprint check right after writing the baseline rows` (step 3's rows read nothing until step 20 failed 43 findings); spec gotcha "A token reading carries the session's installed plugin" (SQ-10); LEARNINGS `[implementer] Step 12: measure_token_budget.py --ratchet writes a sample` into `.ai-state/token_budget_baseline.json`.
- **Description**: In `skills/software-planning/references/document-templates.md` (the footprint measurement step, lines 92-98), add three sentences: after the baseline step, run `check_footprint_criteria.py <slug> --stage verify` on the baseline rows alone, since it names every grammar defect (`missing-final` aside) while they are cheap to fix; record `CLAUDE_PLUGIN_ROOT` (and the plugin version it resolves to) beside any reading that counts hook-delivered rules, since the instrument reads them from there and a head reading under an older install mixes versions; take a reading with `measure_token_budget.py --json` and leave `--ratchet` to the commit gate, which appends to a committed baseline file.
- **Rationale**: Each gotcha cost a late repair (43 findings, a re-frozen oracle, a restore by `git checkout`), and all three belong to one step type the planner and orchestrator author from this template. Cheap to add, narrow, and the template is read at planning time.
- **Estimated scope**: one paragraph in `document-templates.md`; no new file.
- **Overlap check**: `skills/spec-driven-development/references/footprint-criteria.md` and `scripts/check_footprint_criteria.py --help` describe the grammar and stages, not these three practices.
- **Recommended delegation**: context-engineer (review scope), then implementer (content)
- **Suggested artifact path**: `skills/software-planning/references/document-templates.md`

### Proposal 5: Test-selection gotchas: capture the resolver raw; a committed tree selects nothing

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: seedling
- **Scope**: narrow
- **Priority**: P2 (someday)
- **Source(s)**: LEARNINGS `[orchestrator] Resolver lines are long; never cut them` (step 16); LEARNINGS `[orchestrator] Step 19's command lines as written do not run here` (`resolve_test_scope.py | sh -e` on a clean, committed tree selects nothing).
- **Description**: Two sentences in `skills/testing-strategy/references/test-selection.md`: the resolver emits one command per pocket of 3-7k characters, so capture its stdout raw (truncation leaves pytest reporting `no tests ran`, exit 5, which reads as an error only if the exit code is read); and on a clean committed tree the no-argument form returns `nothing-to-run`, so a checkpoint or final-step scope uses `--changed-from <base>`.
- **Rationale**: Both are real stalls in one pipeline, but each occurred once and the second is partly in the file already (line 165 names `--changed-from` for checkpoints without the failure it prevents). Seedling: worth a line, not a section.
- **Estimated scope**: two sentences in an existing reference.
- **Overlap check**: `test-selection.md:92` (input modes) and `:165` (checkpoint table). td-573 covers the separate xdist/`python3` finding.
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `skills/testing-strategy/references/test-selection.md`

### Proposal 6: Mutation dispositions record survivor ids; clear stale bytecode after a hand mutation

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: seedling
- **Scope**: narrow
- **Priority**: P2 (someday)
- **Source(s)**: VERIFICATION F-C5 and note 1 (13 survivors ruled equivalent, no ids recorded, two not equivalent; td-584); LEARNINGS `[implementer] Stale bytecode after a hand mutation (step 7)`.
- **Description**: In `skills/testing-strategy/references/python-testing.md` at the "Dispose of each remaining survivor" paragraph (line 238), add: record each survivor's id beside its argument, and test the boundary class (`<=` against `<` on a size or count limit) before ruling it equivalent, since it changes an observable count. Add one sentence to the manual-mutation advice, if the page carries any, or here: delete the module's `__pycache__` entry after a hand mutation, since a same-size, same-second edit keeps the old `.pyc`.
- **Rationale**: The existing text demands a written argument but not the ids, which is why the verifier could not audit step 7's ruling. Recurrence is one pipeline, so seedling.
- **Estimated scope**: two sentences in `python-testing.md`.
- **Overlap check**: `python-testing.md:233-238` (survivor classes and the written-argument demand); td-584 holds the concrete missing boundary test.
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `skills/testing-strategy/references/python-testing.md`

## Recommended Delegations

| Proposal | Delegation Path | Notes |
|---|---|---|
| 1 | context-engineer | New reference under `hook-crafting`; load `skill-crafting` |
| 2 | context-engineer (review scope) then implementer (content) | Paired sites: `coordination-details.md` is authoritative, `agents/test-engineer.md` the operational copy |
| 3 | context-engineer | Two short edits; load `skill-crafting` |
| 4 | context-engineer (review scope) then implementer (content) | One paragraph in an existing template reference |
| 5 | context-engineer | Two sentences |
| 6 | context-engineer | Two sentences |

## Disposition Log

<!-- Populated by /skill-genesis-review. Empty on report creation. -->

| Timestamp | Proposal | Disposition | Notes |
|---|---|---|---|
| _(empty — pending review)_ | | | |

## Recommended Next Steps

- Run `/skill-genesis-review` to disposition the 6 pending proposals.
- Hand the 6 defects (D1 to D6) to a ledger writer (verifier, orchestrator, sentinel or architect-validator); none is written here.
- After approval, invoke `context-engineer` for the skill edits; the delegations table names the path per proposal.
