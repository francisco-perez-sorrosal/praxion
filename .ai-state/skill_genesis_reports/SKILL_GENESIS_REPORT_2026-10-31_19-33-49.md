---
schema_version: 1
report_id: skill-genesis-2026-10-31_19-33-49
generated_at: 2026-10-31T19:33:49Z
task_slug: context-diet-resume
agent_version: skill-genesis@1ca8461a
invocation_args: { since: null, scope: null, sources: ".ai-work/_harvest-diet", batch: "2 of 5", dry_run: false }
review_status: complete
disposition_count: { pending: 0, approved: 1, rejected: 5, refined: 0, deferred: 1 }
---

# Skill Genesis Report — 2026-10-31 19:33:49

## Summary

Queue mode, batch 2 of 5. 2 sources analyzed (`apply-rule-moves`, `gate-repairs`), 22 triaged learning items (consolidated from about 80 raw LEARNINGS and verification lines), 7 proposals generated (6 skill updates, 1 rule update; no new artifacts), 9 items deduplicated or skipped, 6 defect or deferred-fix items listed separately for ledger routing. No discipline-gap signals. Review status: pending.

Interpretation and assumptions (surfaced):

1. Both sources are first harvests (`prior-report: no`). `memory: yes` was read as "a memory exists", not "the learning is captured"; each memory-held learning was still checked against shipped artifacts, per the orchestrator note.
2. Verification findings that the later rework or the merge already closed are not re-listed as defects. I checked D-1 (remote-ref regex), D-2 (key spacing) and D-4 (catalog wording) of the apply-rule-moves delta against HEAD: the first two are fixed in the code (`scripts/check_decision_records.py:98-100`, `scripts/_decision_records.py:57`), and the D-4 string no longer appears in `scripts/CLAUDE.md`. Only their portable lesson is proposed (Proposal 2).
3. Batch 1 (`SKILL_GENESIS_REPORT_2026-10-31_19-30-34.md`) proposed three plan-authoring items (3, 4, 5). Where this batch repeats their evidence, it is recorded as a recurrence in the Triage table, not re-proposed; Proposal 4 is a distinct angle on Proposal 4 there and says so.
4. Process learnings get an artifact proposal even where a memory holds them (Proposals 1, 3 and 5); memory is the supplement.

## Learning Sources Consumed

| Source | Path | Items Extracted | Status |
|---|---|---|---|
| Queue source: apply-rule-moves LEARNINGS | `.ai-work/_harvest-diet/apply-rule-moves/LEARNINGS.md` | 11 | Read |
| Queue source: apply-rule-moves VERIFICATION_REPORT | `.ai-work/_harvest-diet/apply-rule-moves/VERIFICATION_REPORT.md` | 8 | Read (Acceptance Criteria table, Footprint, Convention Compliance, Principles table 4 to 8 skimmed) |
| Queue source: gate-repairs LEARNINGS | `.ai-work/_harvest-diet/gate-repairs/LEARNINGS.md` | 12 | Read |
| Queue source: gate-repairs VERIFICATION_REPORT | `.ai-work/_harvest-diet/gate-repairs/VERIFICATION_REPORT.md` | 8 | Read (Acceptance Criteria table lines 33 to 63 and Convention Compliance lines 122 to 147 skimmed) |
| CONSULT fragments | `.ai-work/_harvest-diet/{apply-rule-moves,gate-repairs}/CONSULT_*.md` | 0 | Not found |
| Latest SENTINEL_REPORT / IDEA_LEDGER | `.ai-state/` | 0 | Not consulted (queue mode, scoped to listed sources); ledger rows checked by grep |
| ADRs | `.ai-state/decisions/` | 0 | Not matched (dec-480/481 and the gate drafts are the sources' own decisions, recorded) |
| Calibration log Retrospective cells | `.ai-state/calibration_log.md` | 0 | Not read (outside this batch's sources); the two `Calibration Verdict` cells in the sources were read |
| Sibling pending reports | `.ai-state/skill_genesis_reports/` | 0 | Grepped by proposal heading (mutation, Files:, outer-loop, parity, reader) |

## Triage Results

| # | Item | Source | Decision | Rationale |
|---|---|---|---|---|
| 1 | Outer-loop changes after the first production commit were recorded in the digest or a commit message but not as an answered Spec Question with `Resolved in:` (apply F-1, F-2; gate-repairs commit-order FAIL on `480edea7`, `Resolved in` missing on SQ-L1/SQ-L2) | apply VR LBA-3, Recommendations 1; gate VR Acceptance Coverage check 4 | Skill (update) | Proposal 1; same FAIL class in both pipelines |
| 2 | A gate that re-implements another component's reader and claims agreement with it: duplicate-key order (W-2), key spacing (D-2), anchored remote segment (D-1), remote-tracking default (W-1), exporter parity shapes missing two drift classes (W-6) | apply VR Carried Warnings, LBA-4, Delta | Rule (update) | Proposal 2; five sightings in one pipeline, all with a claim the code falsified |
| 3 | ADR drafts left describing a superseded shape after a revision or rework: gate draft names the wrong module (W-5), resident draft omits the Codex skip (W-5b), self-contradicting FC-01 sentence (D-3), launcher draft says it "ignores SIGTERM itself" (F10, td-508) | apply VR; gate VR Step 9 F10, Context Artifact Completeness | Skill (update) | Proposal 3; four sightings in two pipelines; the implementer authors no ADR, so a revision leaves it unowned |
| 4 | Consumer tests and config of a changed contract constant sat outside the step's `Files:`: kernel hook `files:` regex, pre-move fixture, observation-log registry tuple, writer-truth scenario, `test_loop_io_vcs.py`, oversized test files forcing sibling files | apply LEARNINGS steps 3, 6; gate LEARNINGS steps 6, 9 and planner File-sizes entry | Skill (update) | Proposal 4; extends batch 1 Proposal 4 (sizing) with consumer discovery |
| 5 | Pipeline-record defects after revisions or outside-loop steps: six dead traceability nodes, REQ-12 and REQ-13 `implementation: []`, Step 10 `Check:` result never written, seven `green-over-ceiling` sections, `check_test_results_shape` flagging the prescribed `## Rework` heading | gate VR Spec Conformance, Test Coverage; apply LEARNINGS Rework; apply VR (steps 19, 20 outside loop) | Skill (update) | Proposal 5; these files die at cleanup, so a ledger row would dangle |
| 6 | Mutation sensor cannot run on `hooks/` or on a script that imports `hooks/`; operating notes (PYTHONPATH refused in a worktree-isolated session, `mutants/` and generated `pyproject.toml` left by a killed run, shell-heavy tests outlast the tool limit, child-process cwd, import by file name) | gate LEARNINGS steps 6, 7, 9; apply LEARNINGS steps 7, 9, 10, 11 | Skill (update) | Proposal 6; extends pending 2026-09-23_23-05-46 P1 and 2026-10-10 P4 |
| 7 | A design leaned on `CLAUDE_PROJECT_DIR` naming the checkout, verified only for its companion variable; wrong when a session starts below the root (AC-04, td-502). A writer-truth test made to pass by setting the variables stopped exercising the no-evidence row (B2, td-504) | gate VR B1, B2, Re-verification | Skill (update) | Proposal 7; one pipeline, seedling to sapling |
| 8 | `mutation: on` tagged on a layout the sensor refuses | both LEARNINGS (steps 6, 7, 9, 10, 11) | Skip (dedup) | Recurrence evidence for batch 1 Proposal 3; folded into Proposal 6's rationale |
| 9 | Parametrized `Read-only:` prefix ownership at a `[` boundary; `Check:` figures assume sequential order; node partition parsed by script; `uv run python -m pytest` as the runner | apply LEARNINGS planner entries | Skip (dedup) | Batch 1 Proposal 5 (node partition) and 2026-10-11 Proposal 2 (`Files:`/`Check:`); memory `feedback_check_runs_without_a_shell` |
| 10 | Footprint registry row names a reference file, so editing it raises FP01 unless the spec declares it not measured | gate LEARNINGS planner entry | Skip | Handled in-pipeline as a Spec Question (SQ-P1) with a recorded ruling; single sighting, no standing gap shown |
| 11 | Step 6/7 `Mutation:` readings taken over a flat scratch copy with only the new test file | gate VR Test Coverage | Skip (dedup) | Proposal 6 covers the recipe; the "sensor measures the new test file, not the module" caveat is already in the verifier's reading |
| 12 | `interrupt_inside_a_run` test flaked under xdist in both pipelines | apply step 6; gate step 9 | Defect | D1 |
| 13 | Tier under-calibrated (Standard to Full mid-task, loop budget ran out at Step 9) | gate VR Calibration Verdict | Skip | Belongs to the calibration log; memory `feedback_ledger_triage_pipeline_corrections` ("re-tier past budget") |
| 14 | Step-loop `Check:` bound too short for a 1,500 s pocket; steps 19, 20 ran outside the loop | apply VR Calibration; td-527 | Defect (existing) | Already `td-527` |
| 15 | Gate design decisions: refusal-text budget, shell fast path, fail-open and its declared limits, per-segment commit regex, `git add -u` limit, Codex wrapper marker, pocket-drive edge, launcher shape | both LEARNINGS Decisions | Skip | Homes exist: dec-480/481, the three gate-repairs drafts, module docstrings; launcher in memory `feedback_posix_background_sigint_and_dash_kill` |
| 16 | Gate and grader differ on purpose (branch segment, category case, quoted ids) | apply LEARNINGS step 13 | Skip | Guarded by `eval/tests/test_decision_gate_parity.py`; a design choice, not debt (verifier ruled so) |
| 17 | Out-of-`Files:` boy-scout edits committed separately and surfaced | both | Skip | Process works as written; verifier ruled no `[NON-SURGICAL]`. The cause is Proposal 4 |
| 18 | `td-526` user decision (a subject over 50 characters never blocks; advisory check; reconcile "under 50" vs "at most 50") | td-526 notes | Defect routing | D6; no artifact proposal: the work is the ledgered gate and rule wording |
| 19 | Accepted-with-reason items: README exemption, `rule-crafting/SKILL.md` at 418 lines, `dec-draft` ids in architecture docs, FC-01 16-token headroom | apply VR Carried Warnings | Skip | Verifier accepted each with a reason |
| 20 | Spawn tally read `indeterminate` at planning time (the td-433 symptom) | gate LEARNINGS | Skip | Repaired by this pipeline |
| 21 | Hook processes inherit `CLAUDE_CODE_ENTRYPOINT`; unknown kind omits both keys | gate LEARNINGS | Skip | Recorded in the spawn-row ADR draft and the registry's own comment; the portable half is Proposal 7 |
| 22 | Late-spec/driver items: `HANDOFF.md` is a driver artifact; `tally(rows, root=None)` default kept | gate/apply LEARNINGS | Skip | Narrow, documented in code |

## Proposals

### Proposal 1: coordination-details — record the Spec Question when the outer-loop change is made, not at verification

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: mature
- **Scope**: narrow
- **Priority**: P1 (next-cycle)
- **Source(s)**: `apply-rule-moves/VERIFICATION_REPORT.md` FAIL F-1 and F-2 and LBA-3 (four amendments to acceptance-side files after design: `8d94e2d0`, `efe89a9e`, `069bdf31` and the FC-01 command form, each "justified and minimal on substance", each recorded in `CHECKPOINT_DIGEST.md` and none as an answered Spec Question; closed only in the delta, SQ-02 to SQ-05); `gate-repairs/VERIFICATION_REPORT.md` Acceptance Coverage check 4 (`480edea7` edited `tests/acceptance/test_workflows_are_skills.py` after the first production commit with no Spec Question; SQ-L1 and SQ-L2 lacked `Resolved in: 62ca1b65`; first-pass FAIL, closed in the re-verification); batch-1 pipelines did not repeat it.
- **Description**: Add to `coordination-details.md` § Spec-Question Routing a short "orchestrator-made amendments" paragraph: when the orchestrator, a driver-binding step or a boy-scout repair changes an outer-loop scenario, driver, allowlist entry or the spec digest after the first production commit, it appends the answered Spec Question to `ACCEPTANCE_TESTS.md` in the same sitting, with `Resolved in:` set once the sha exists, and re-runs `extract_spec.py --check` when requirement text moved. A digest line is not the record. Name the stronger form (a commit-time check that refuses an outer-loop path change without a matching question) as the hard-guarantee option, for the user to decide.
- **Rationale**: The same verifier FAIL class fired in both pipelines, each time on a change the verifier judged sound, so the cost was a rework row and a delta pass, not a defect. The independence rule and the verifier check already exist (coordination-details lines 205 to 211, `agents/verifier.md` check 4); what is missing is the instruction to the orchestrator that makes the record at the moment of the change. A prose line is advisory; if it recurs again, a hook is the right layer.
- **Estimated scope**: one paragraph in an existing reference
- **Overlap check**: `skills/software-planning/references/coordination-details.md` § Late path covers the implementer-raised question; `agents/test-engineer.md:279` says "the orchestrator records it" without saying when. Memory `feedback_goal_mode_protects_outer_loop_tests` and `feedback_acceptance_brief_allowed_inputs` are adjacent, not equal. Partial.
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `skills/software-planning/references/coordination-details.md`

### Proposal 2: gate-liveness — a gate that claims agreement with another reader is tested against that reader's grammar

- **Disposition**: pending
- **Type**: rule (update)
- **Maturity**: sapling
- **Scope**: narrow
- **Priority**: P1 (next-cycle)
- **Source(s)**: `apply-rule-moves/VERIFICATION_REPORT.md` Carried Warnings W-2 (first-wins duplicate `category:` against the index generator's last-wins), Delta D-2 (the gate's key pattern needed `category:` with no space, the index generator accepts `\s*:`), D-1 (`refs/remotes/.+/main` spans slashes so `origin/feature/main` counted as the default branch), W-1 (default branch read as local `main` only), W-6 and LBA-4 (exporter `resident_of` parity tests missed a `.md`-value requirement and a longer key name); Delta "Merge to LEARNINGS" candidates ("every 'agrees with reader X' claim needs a probe of X's own key grammar, not only of duplicate order"; "a widened ref pattern must anchor the remote segment"). Both gate bugs are fixed at HEAD; the lesson is not shipped.
- **Description**: Add one anti-pattern row, or extend the Scope fidelity clause, in `rules/swe/gate-liveness.md`: when a gate re-implements a parser or selector that another component owns (an index generator, a finalize regex, an exporter's detector) and a docstring, ADR or catalog row claims it agrees, the gate's canaries are derived from the other component's grammar (key spacing, quoting, duplicate order, anchoring), and a parity test over shapes enumerates the other side's accepted spellings. Remedy line: read the other side through its own function where the gate may import it, otherwise keep a parity test beside the copy.
- **Rationale**: Five distinct falsifications of an agreement claim, found by the verifier's probes, not by the gate's own tests; each had a canary for the shape the author thought of and none for the shape the other reader accepts. The existing Scope fidelity clause covers the gate's input set against its documented scope, not agreement with a second reader of the same text. The rule is path-scoped to gate files, so it loads where the gate is written.
- **Estimated scope**: one table row (or one clause) in a single rule file; check token impact with `scripts/measure_token_budget.py` (the rule is path-scoped, so off the always-loaded budget)
- **Overlap check**: `rules/swe/gate-liveness.md` Scope fidelity and the "convention lives at two+ textual sites" row (adjacent: that row is about prose sites, not parsers). Partial.
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `rules/swe/gate-liveness.md`

### Proposal 3: software-planning — an ADR draft whose decision a revision changes is refreshed before verification

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: sapling
- **Scope**: narrow
- **Priority**: P1 (next-cycle)
- **Source(s)**: `apply-rule-moves/VERIFICATION_REPORT.md` W-5 (gate draft summary, Decision and `affected_files` named a module the planner had split), W-5b (resident draft omitted the Codex bridge skip), Delta D-3 (self-contradicting FC-01 sentence left by the rework); `apply-rule-moves/LEARNINGS.md` Rework ("the ADR draft ... still says the key keeps the resident out of Codex: architect text, not touched here"); `gate-repairs/VERIFICATION_REPORT.md` Step 9 F10 and Context Artifact Completeness ("ADR draft `dec-draft-2801fd08` Missing ... not in any step's files"), td-508.
- **Description**: In the planner's decomposition guidance and the rework-manifest reference, state that a step revision, review revision or rework row that changes the built shape of a component an ADR draft describes also lists that draft's path as owed. Because the implementer authors no ADR, the plan schedules a short systems-architect refresh (or the orchestrator edits the draft) before the verifier runs; the check is that each draft's `affected_files` and Decision text name the modules that exist at HEAD.
- **Rationale**: Two pipelines, four findings, every one a WARN the verifier had to find by reading the draft against the code and every one needing a rework row routed to the architect. A draft is read at finalize and by later architects as the decision of record, so a stale one misleads long after the pipeline. The mismatch arises at a predictable moment (a revision), which a planning-time rule can catch.
- **Estimated scope**: one paragraph in `decomposition-guide.md` plus one sentence in `rework-manifest.md`
- **Overlap check**: `skills/software-planning/references/coordination-details.md:411` (fixing a draft before spawning a lens) is a different trigger. `rules/swe/adr-conventions.md` governs format, not drift. None on revision-driven drift.
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `skills/software-planning/references/decomposition-guide.md`, `skills/software-planning/references/rework-manifest.md`

### Proposal 4: implementation-planner — list the consumers of a changed contract constant in the step's `Files:`

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: sapling
- **Scope**: narrow
- **Priority**: P2 (someday)
- **Source(s)**: `apply-rule-moves/LEARNINGS.md` Step 3 (`.pre-commit-config.yaml` read-set regex had to name the new module `_resident_of`; the step's own new import forced it; also a Read-only node gated on a file step 5 ships, so `pending=44`, not 43), Step 6 (`eval/tests/fixtures/pre_move_adr_conventions.md` and a `before_the_adr_move` helper added outside `Files:` to keep arm fixtures building an unlanded move); `gate-repairs/LEARNINGS.md` Step 6 (`hooks/test_observation_log_registry.py` pinned the field tuple and `hooks/test_observation_log_writer_truth.py` checked every declared field, both outside `Files:`), planner entries "Hook row fields are declared twice" and "File sizes decide where new tests go" (2,088-line and 936-line test files force sibling files).
- **Description**: A planner checklist line for any step that adds a field, a module import, a registry entry or a config constant: grep for the tests and config that enumerate that constant (a registry-tuple test, a writer-truth scenario, a hook `files:` regex, a manifest fixture) and put them in `Files:` or name the sibling file for new tests when the existing one is near the ceiling. A consumer found only at implementation time is a plan amendment, not a boy-scout edit.
- **Rationale**: Six out-of-`Files:` edits in two pipelines, all correct and all needed to turn the step's gate green. The planners spotted two of them in advance (registry double declaration, file sizes), which shows the check is doable at planning time. This differs from batch 1 Proposal 4 (module size and type ownership): it is about consumers the change makes red, and the two should land in one checklist.
- **Estimated scope**: one checklist item in an existing reference; merge with batch 1 Proposal 4
- **Overlap check**: batch 1 Proposal 4 (`SKILL_GENESIS_REPORT_2026-10-31_19-30-34.md`, pending); `resolve_test_scope.py` derives the tests to run but does not widen `Files:`. Partial.
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `skills/software-planning/references/decomposition-guide.md`

### Proposal 5: software-planning — a close-out record checklist for revised steps and steps run outside the loop

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: sapling
- **Scope**: narrow
- **Priority**: P2 (someday)
- **Source(s)**: `gate-repairs/VERIFICATION_REPORT.md` Spec Conformance (six `tests`/`implementation` entries name symbols renamed or deleted by the Step 7 r1 and Step 9 revisions; REQ-12 and REQ-13 `implementation: []`; tests added by revisions unlisted), Test Coverage ("Step 10: the `Check:` result was never written to `TEST_RESULTS.md`", reconciler reads `mismatch`; seven `green-over-ceiling` sections of 1,110 to 1,327 B against a 1,024 B ceiling), Recommendations item 5 and the note that these `.ai-work/` defects are not ledgered because the files are deleted at cleanup; `apply-rule-moves/LEARNINGS.md` Rework (`check_test_results_shape.py` flags the prescribed `## Rework (verifier findings)` heading); `apply-rule-moves/VERIFICATION_REPORT.md` Calibration (steps 19 and 20 ran outside the loop, td-527).
- **Description**: A short close-out list in the step-loop skill (or `coordination-details.md` § step loop): after a revision, update the traceability nodes the revision renamed or deleted and list its new tests; after a step the orchestrator runs outside the loop, write its `Check:` outcome as a `Result:` line in `TEST_RESULTS.md` in the shape the reconciler reads (final count line last, under the size ceiling); and run `check_test_results_shape.py` and a traceability node resolution before spawning the verifier.
- **Rationale**: These defects live in files deleted at cleanup, so no ledger row can hold them; the only places that can prevent them are the instructions to the orchestrator. They cost the verifier turns on record repair instead of behavior. Held at P2 because each is a WARN and a node-resolution instrument does not appear to exist (see D5); a script would make the list mechanical.
- **Estimated scope**: one short section in an existing page
- **Overlap check**: memory `feedback_reconciler_last_line_test_status` (final count line), `feedback_step_loop_confirming_attempt_needs_mutation_line`, `feedback_unproven_step_keeps_nodes_pending` hold fragments; no shipped artifact lists the close-out. `skills/step-loop/` has no references directory today. Partial.
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `skills/step-loop/SKILL.md` (or `skills/software-planning/references/coordination-details.md`)

### Proposal 6: testing-strategy — mutation sensor recipe additions for `hooks/` and modules that import `hooks/`

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: sapling
- **Scope**: narrow
- **Priority**: P2 (someday)
- **Source(s)**: `gate-repairs/LEARNINGS.md` Step 6 (the sensor refuses `hooks/` with `run-failed`: the `_observation_log` package and about 90 sibling modules defeat the flat-layout recipe; readings taken over a flat scratch copy with `PYTHONPATH=hooks`), Step 7 (`spawn_count.py` finds `hooks/` through `SCRIPT_DIR.parent`, so `mutants/` under `scripts/` misses it and collection fails with `No module named '_hook_utils'`; a worktree-isolated session refuses `PYTHONPATH=` in command text, so set it from a small Python launcher), Step 9 (shell-level tests with 7 s launcher deadlines outlast the 600 s tool limit: run in the background with `--timeout 3000`; a killed run leaves `scripts/mutants/` and a generated `scripts/pyproject.toml`: delete both before re-running); `apply-rule-moves/LEARNINGS.md` Step 10 (a child-process test must not set `cwd` away from the sensor's directory), Step 11 (`_scripts_dir()` walks ancestors because a copy runs one directory deeper; test modules import the target by file name, never via `importlib` under another name).
- **Description**: Extend the pending mutation recipe with a "layouts and operations" section: `hooks/` is refused, so the reading is taken over a flat scratch copy and the line says so; a script that imports a sibling tree needs that tree on the path set by a launcher; long shell tests run detached with a raised `--timeout`; clean `mutants/` and the generated config after a killed run; child-process tests keep the sensor's cwd and the target is imported by its file name.
- **Rationale**: The pending recipe covers the flat `scripts/` layout and the `__file__` and subprocess blind spots; these additions come from five more steps in two pipelines, each of which re-derived the workaround. td-510 asks for a sensor recipe for `hooks/`; this is the interim text and the mechanical fix stays in the ledger. It also supports batch 1 Proposal 3: the futile-tag cost recurred on `hooks/` and on `scripts/` modules importing it.
- **Estimated scope**: a section of the pending mutation reference (merge, not a new file)
- **Overlap check**: pending `SKILL_GENESIS_REPORT_2026-09-23_23-05-46.md` P1 and `SKILL_GENESIS_REPORT_2026-10-10_00-49-38.md` P4 (extends); `td-510`, `td-522` (tooling). Partial.
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `skills/testing-strategy/references/python-testing.md` § Mutation Sensor (or the pending `mutation-testing.md`)

### Proposal 7: hook-crafting — derive project identity from where the hook writes, and test the no-evidence row

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: seedling
- **Scope**: narrow
- **Priority**: P2 (someday)
- **Source(s)**: `gate-repairs/VERIFICATION_REPORT.md` B1 (`CLAUDE_PROJECT_DIR` named the checkout, an assumption verified only for its companion `CLAUDE_CODE_ENTRYPOINT`; wrong for a session started in `<worktree>/dashboard_app`, escalated to FAIL AC-04, td-502; fixed by recording the checkout `locate` resolved, `location.state_dir.parent`), B2 and td-504 (a writer-truth scenario made to pass by setting both variables no longer exercised the env-less state, fixed by an `optional` field notion and a run with and without the variables), Load-bearing assumptions ("The contract is not right as written"); `gate-repairs/LEARNINGS.md` Step 6 (`checkout` symlink-resolved path).
- **Description**: Two gotchas for `skills/hook-crafting/references/testing-guide.md`: (1) a hook that records or gates by project identity takes it from the location it writes to (the state directory it resolved), not from an environment variable the harness may set to another directory, and each variable a design leans on is verified in a real session, started below the root and in a linked worktree; (2) when a field is conditional on harness evidence, the writer-truth test runs with and without that evidence, because making the test pass by supplying the variables hides the state the field's absence exists for.
- **Rationale**: One sighting, with a clean mechanism and a cost (a FAIL and a corrective step). The memory `feedback_plugin_cache_file_vs_git_root` holds the nearby lesson for hook scripts; this adds the recorded-identity and test-both-states halves. Held at seedling; reject if the user prefers a second instance first.
- **Estimated scope**: two bullets in an existing reference
- **Overlap check**: `skills/hook-crafting/references/testing-guide.md` line 24 sets `CLAUDE_PROJECT_DIR` for tests without saying it can disagree with the checkout; memory `feedback_context_baseline_worktree_dir_resolution`, `feedback_plugin_cache_file_vs_git_root`. Partial.
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `skills/hook-crafting/references/testing-guide.md`

## Recommended Delegations

| Proposal | Delegation Path | Notes |
|---|---|---|
| 1 | context-engineer | Reference paragraph; load `skill-crafting`; user to decide whether to also ledger a commit-time check |
| 2 | context-engineer | Rule update; load `rule-crafting`; path-scoped rule, token budget unaffected |
| 3 | context-engineer | Two reference edits; load `skill-crafting` |
| 4 | context-engineer | Merge with batch 1 Proposal 4 into one planner checklist |
| 5 | context-engineer | Choose home (step-loop SKILL.md or coordination-details) at review |
| 6 | context-engineer | Merge into the pending mutation recipe; do not add a second file |
| 7 | context-engineer | Seedling; two bullets |

## Defects and Deferred Fixes (for ledger routing; not artifact proposals)

Existing rows are not repeated: `td-501`, `td-505`, `td-506`, `td-510`, `td-511` (open) and `td-502` to `td-504`, `td-507`, `td-508`, `td-509` (resolved) for gate-repairs; `td-522`, `td-526`, `td-527`, `td-528` for the diet pipelines. Items below had no matching row at grep time; the orchestrator should confirm before filing. This report edits no ledger.

| # | Location | Evidence | Note |
|---|---|---|---|
| D1 | `scripts/test_loop_io_vcs.py::test_an_interrupt_inside_a_run_takes_the_runner_down_with_it` | apply LEARNINGS Step 6 ("failed once in the wide parallel run, passes alone, `-n 0`, 100 passed") and gate-repairs LEARNINGS Gotchas (Step 9 attempt 1, passed in six reruns; polls a driver subprocess for a pid file at 0.05 s) | Two sightings in two pipelines; gate-repairs asked for "a flake to harden in its own step". No ledger row matched the test name |
| D2 | `scripts/test_spawn_count.py` (2,099 lines), `scripts/test_loop_io_vcs.py` (1,072), `hooks/test_capture_observations.py` (936) | gate-repairs LEARNINGS planner entry (2,088 and 936 at the time) against the 800-line ceiling; line counts re-read at HEAD | Pre-existing size debt that forced sibling test files; split by behavior. No ledger row matched the file names |
| D3 | `hooks/hooks.json` (the `Write\|Edit` group around line 330) | apply VR Code-Review Angles: `MultiEdit` not matched by the decision-record write gate (INFO, same group as the dec-455 memory gate) | If the harness offers `MultiEdit`, a numbered record created through it is not refused at write time; the commit gate still holds. Decide with the dec-455 gate |
| D4 | `scripts/check_test_results_shape.py` and the rework instruction | apply LEARNINGS Rework: the tool flags the `## Rework (verifier findings)` heading as a non-step heading although the task prescribed that heading | The tool and the prescribed heading disagree; teach the tool the heading or change the prescription |
| D5 | no instrument (search of `scripts/` found none) | gate VR Spec Conformance: the verifier resolved every `traceability.yml` `tests` and `implementation` node against code with a scratch script and found six dead nodes and two empty lists | A `traceability.yml` node resolver (stdlib, read-only) would make Proposal 5's check mechanical. Confirm none exists before filing |
| D6 | `rules/swe/vcs/git-conventions.md` wording ("under 50") and the move grader ("at most 50") | `td-526` notes, user decision 2026-10-31: a subject over 50 characters must never block a commit; the check is advisory; 248 of the last 400 non-merge subjects (62%) exceed 50 | Routing note for `td-526`, not a new row: any advisory check must report and never refuse, and the rule's wording must match the grader. The authorship gate (`scripts/check_commit_msg_authorship.py`) must not gain a blocking length test |

## Disposition Log

<!-- Populated by /skill-genesis-review. Empty on report creation. -->

| Timestamp | Proposal | Disposition | Notes |
|---|---|---|---|
| 2026-11-01T23:00:00Z | Proposal 2: gate that claims agreement with another reader is tested against its grammar | defer | Five falsifications in one pipeline but gate-liveness is path-scoped to Praxion gate sites; wait for a managed-project gate case or a second pipeline |
| 2026-11-01T23:00:00Z | Proposal 3: ADR draft refreshed when a revision changes its decision | reject | built: The mechanical half (dead affected_files) exists as a non-blocking warning; Decision-text drift is not mechanically checkable |
| 2026-11-01T23:00:00Z | Proposal 4: list consumers of a changed contract constant in Files: | reject | below-bar: Prose planner checklist; each out-of-Files edit was surfaced and amended, cost is small |
| 2026-11-01T23:00:00Z | Proposal 5: close-out record checklist for revised steps | reject | below-bar: Prose; check_test_results_shape already covers the shape half |
| 2026-11-01T23:00:00Z | Proposal 6: mutation recipe additions for hooks/ and sibling-importing modules | reject | ledgered: Tool-side gaps are open rows |
| 2026-11-01T23:00:00Z | Proposal 7: hook identity from where the hook writes; test the no-evidence row | reject | ledgered: Both defects fixed and resolved |
| 2026-11-02T07:30:00Z | Proposal 1: coordination-details — record the Spec Question when the outer-loop change is made, not at verification | approve | pick 1: the Spec Question path for an outer-loop change the orchestrator makes itself, in coordination-details.md and agents/test-engineer.md. Lightweight, built after routing-facts merges |

## Recommended Next Steps

- Run `/skill-genesis-review` to disposition the 7 pending proposals. Proposals 4 and 6 extend pending siblings (batch 1 Proposal 4; the 2026-09-23 and 2026-10-10 mutation proposals); review them together.
- Route D1 to D6 to tech-debt ledger rows after confirming none is covered.
- Remaining batches (3 to 5 of 5) may repeat evidence for Proposals 1, 3 and 5; check this report's headings before re-proposing.
