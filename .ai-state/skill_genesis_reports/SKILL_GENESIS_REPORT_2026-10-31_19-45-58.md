---
schema_version: 1
report_id: skill-genesis-2026-10-31_19-45-58
generated_at: 2026-10-31T19:45:58
task_slug: context-diet-resume
agent_version: skill-genesis@a3ba7469
invocation_args: { since: null, scope: null, sources: .ai-work/_harvest-diet, batch: "4 of 5", dry_run: false }
review_status: pending
disposition_count: { pending: 5, approved: 0, rejected: 0, refined: 0, deferred: 0 }
---

# Skill Genesis Report — 2026-10-31 19:45:58

## Summary

Interpretation: queue mode, batch 4 of 5, three parked pipelines (`loop-gate-followups`, `main-session-adherence`, `ralph-lite-spike`). Assumption surfaced: the earlier batches' reports (19-30-34, 19-33-49, 19-40-39) and the harness memory index are the dedup baseline, and a pending sibling proposal that already covers an item is cited, not re-proposed.

3 learning sources analyzed, 28 items extracted, 5 proposals generated, 15 deduplicated or skipped, 5 defects listed for ledger routing. The spike's recommendation is already shipped (`skills/ralph-lite/SKILL.md`, dec-434), and most of the two verified pipelines' lessons are already ADR'd, ledgered or sitting in a pending sibling proposal. The five survivors are process gaps with no carrying artifact. Review status: pending.

## Learning Sources Consumed

| Source | Path | Items Extracted | Status |
|---|---|---|---|
| loop-gate-followups LEARNINGS | `.ai-work/_harvest-diet/loop-gate-followups/LEARNINGS.md` | 11 | Read |
| loop-gate-followups VERIFICATION_REPORT | `.ai-work/_harvest-diet/loop-gate-followups/VERIFICATION_REPORT.md` | 6 | Read |
| main-session-adherence LEARNINGS | `.ai-work/_harvest-diet/main-session-adherence/LEARNINGS.md` | 4 | Read |
| main-session-adherence VERIFICATION_REPORT | `.ai-work/_harvest-diet/main-session-adherence/VERIFICATION_REPORT.md` | 5 | Read (sections 1-60 and 160-335; the per-requirement matrix and footprint tables skipped as non-learning) |
| ralph-lite-spike LEARNINGS | `.ai-work/_harvest-diet/ralph-lite-spike/LEARNINGS.md` | 2 | Read (no VERIFICATION_REPORT or CONSULT fragments) |
| Latest SENTINEL_REPORT_*.md | `.ai-state/sentinel_reports/` | 0 | Not read (queue mode, source-scoped) |
| Latest IDEA_LEDGER | `.ai-state/idea_ledgers/IDEA_LEDGER.md` | 0 | Not read (guards promethean ideas only) |
| ADRs | `.ai-state/decisions/` | 0 | Not scanned; the sources cite their own dec ids, and dedup used those |
| Calibration log Retrospective cells | `.ai-state/calibration_log.md` | 0 | Not read (queue mode) |
| Sibling reports and memory index | `.ai-state/skill_genesis_reports/` (3 batches), harness `MEMORY.md` | n/a | Read for dedup |

## Triage Results

| # | Item | Source | Decision | Rationale |
|---|---|---|---|---|
| 1 | A rule added to a function with an early dispatch leaves the dispatched branch ungated (goal-mode marked return committed; no test at either loop level) | loop-gate VR F1, Merge-to-LEARNINGS | Skill (Proposal 1) | Verifier-found FAIL; mode coverage has no carrier |
| 2 | An implementer or architect narrows a requirement ("out of scope here", DS-5) and nobody dispositions it | loop-gate VR B1, B2, LEARNINGS step 9 F2 | Skill (Proposal 1) | Two sightings, one cause: the note sits in LEARNINGS, not in the return |
| 3 | Planner probes the resolver per candidate `Files:` set; gate-build steps cannot be gated by the gate they change | loop-gate LEARNINGS planner entries, pattern that worked | Skill (Proposal 2) | Exposed a bootstrap trap; steps 2 to 6 ran outside the loop |
| 4 | Pocket Check flags differ (`--no-cov` unknown in the eval pocket, `-n 0` for e2e, eval-driving root tests inflate an eval step's gate) | main-session LEARNINGS gotchas | Skill (Proposal 2) | Cost a wasted baseline attempt; same reference as item 3 |
| 5 | An orchestrator spec ruling made without re-reading the governing REQ (step 11 F4) was reversed by the verifier | loop-gate LEARNINGS "Orchestrator correction"; memory `feedback_rule_escalations_against_req_text` | Skill (Proposal 3) | Process held only in memory |
| 6 | Footprint `Reading` cell carrying prose fails the parser; a malformed row cannot be cleared append-only | main-session VR "Process note", Merge candidate | Skill (Proposal 4) | One sighting; seedling |
| 7 | 36 new pyright errors in test files found only at the final health guard; implementers skipped pyright ("not installed") | loop-gate LEARNINGS steps 4-6, 19, 27 | Skill (Proposal 5) | No self-check line, unlike `check_id_citation_discipline.py` |
| 8 | Step `Files:` omitted a file the step had to edit (steps 9, 12, 20, 21; main-session steps 17, 31, 32 and four pathspec commits that left declared files out) | both LEARNINGS | Skip: duplicate | Pending 19-30-34 Proposal 4 and 19-33-49 Proposal 4; these are 8+ more sightings, cite when reviewing |
| 9 | A new module behind the driver must be named in `scripts/CLAUDE.md` and in the kernel hook's `files:` regex | loop-gate LEARNINGS orchestrator note, step 19 | Skip: duplicate | 19-33-49 Proposal 4 names the hook `files:` regex; add the catalog test as a sighting |
| 10 | The id-citation hook refused a `### Step 1` fixture literal | loop-gate LEARNINGS step 9 | Skip: covered | `agents/implementer.md:128` (td-491 resolved) |
| 11 | A named channel is not a deliverable one; an offline arm check blind to installer linking (SQ-18, D-2) | main-session VR AC-13, D-2 | Skip: duplicate | 19-40-39 Proposal 4 and 19-30-34 Proposal 1; td-518 resolved. Add as a sighting: "one instance traced through builder, installer, loader" |
| 12 | A grader regex copied from a rule's wording is wider than the REQ; parity test with the gate (CW-1, CW-13) | main-session VR | Skip: duplicate | 19-33-49 Proposal 2 |
| 13 | ADR draft sentences no longer match the code after revisions (W7) | loop-gate VR | Skip: duplicate | 19-33-49 Proposal 3 |
| 14 | `mutation: on` on `eval/src` always reads `not-flat-layout` | main-session LEARNINGS, VR | Skip: duplicate | 19-30-34 Proposal 3 (the planner predicted it and the tags stayed) |
| 15 | Spec Question answered late and recorded as `Resolved in:` | loop-gate VR (SQ-03) | Skip: duplicate | 19-33-49 Proposal 1 |
| 16 | Worktree guard refuses `sed -n` on a computed path and `sh <path>` | ralph-lite-spike Process | Skip: duplicate | 19-40-39 Proposal 2 |
| 17 | Ralph-lite is goal mode, entered through a skill | ralph-lite-spike Decisions | Skip: shipped | `skills/ralph-lite/SKILL.md`, dec-434 |
| 18 | `-p` facts: `--max-turns` is the hard bound, unpinned permission mode varies, `--bare` future default, `deny` holds in every mode | ralph-lite-spike Gotchas | Skip: covered | The skill's Safety profile carries the transferable parts; `--bare` is time-sensitive |
| 19 | A summarised fetch recorded wrong Stop-hook fields; raw pages win | ralph-lite-spike Gotchas | Skip: covered | `cross-agent-skill-conventions.md` asks for verbatim quotes and raw `curl` |
| 20 | `ATTEMPT_CAP` read by five readers | ralph-lite-spike, loop-gate decisions | Skip: resolved | dec-draft-4502a925 (`attempt_cap` in `status`) |
| 21 | Gate decisions (detached pocket runs, pocket-scoped bare names, marked stop, Stop-guard bounds, standing leaf, reaping sentence, allowlist class) | loop-gate LEARNINGS | Skip: recorded | Seven ADR drafts |
| 22 | Move-eval design choices (sibling subpackage, own results directory, derive kinds, wire forms W1 to W7) | main-session LEARNINGS | Skip: recorded | ADR drafts b9d1c991 and dec75e6b, plus the plan |
| 23 | Spec lint treats a backticked span as design vocabulary unless it equals a declared name exactly | main-session LEARNINGS | Skip: covered | `spec-format-guide.md` sends the reader to the `extract_spec.py` docstring |
| 24 | A criterion decided only on a CI artifact stays open until a push | main-session LEARNINGS, VR AC-20 (e) | Skip | One sighting and inferable; revisit if it recurs |
| 25 | A `test_`-named helper exported from a non-test module is collected by pytest | loop-gate LEARNINGS step 5 | Skip | Narrow; one sighting |
| 26 | `TEST_RESULTS.md` green sections over 1,024 bytes (16 in main-session, 3 in loop-gate) | both VR | Skip | The documented shape already forbids it; the writer of the 16 (agent or driver) is not stated, so no honest artifact can be named |
| 27 | Chronograph watcher flake fixed by polling, not sleeps | loop-gate LEARNINGS step 14 | Skip | Fixed at its root; general advice already in testing guidance |
| 28 | Defects found in the code (pending ownership, private imports, `_AMEND`, hook-reason regex, `read_run_files`) | both VR, re-checked against the tree | Defects section | Not artifact proposals |

## Proposals

### Proposal 1: implementer and verifier — name every mode of a governed function, and return a narrowed requirement instead of noting it

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: sapling
- **Scope**: narrow
- **Priority**: P1 (next-cycle)
- **Source(s)**: `loop-gate-followups/VERIFICATION_REPORT.md` F1 and "Merge to LEARNINGS" candidate ("a new gate placed after an early dispatch leaves the dispatched branch ungated"), B1 and B2; `loop-gate-followups/LEARNINGS.md` step 9 revise r1 F2 ("goal mode keeps committing marked returns; out of scope here") and the step 11 orchestrator corrections.
- **Description**: Two checklist lines. In the implementer's self-review: when a requirement governs a function, list its modes and early returns or dispatches and say how each is covered; a mode left out is a returned `Narrowed:` item (a Spec Question for the orchestrator), not a LEARNINGS note. In the verifier's code-review phase: grep every early return and dispatch in a function a new rule was added to, and read any "out of scope here" in LEARNINGS as an unsurfaced narrowing. The architect's design step gets the same one-line test for a data-structure choice that narrows a requirement (DS-5).
- **Rationale**: F1 (goal-mode marked returns still committed) reached the final verifier as a FAIL because the narrowing sat in LEARNINGS, was never dispositioned, and no test ran the goal path at either loop level. The behavioral contract already says Surface Assumptions; what is missing is the channel and the mode-matrix question. Two sightings with one mechanism, plus a verifier-authored candidate.
- **Estimated scope**: one checklist line each in `agents/implementer.md` and `agents/verifier.md`, one sentence in `agents/systems-architect.md`
- **Overlap check**: `rules/swe/agent-behavioral-contract.md` (Surface Assumptions, general); `agents/implementer.md` objection and Spec Question handling (no mode-matrix line). Partial.
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `agents/implementer.md`, `agents/verifier.md`, `agents/systems-architect.md`

### Proposal 2: step-loop plan authoring — probe the gate's cost per step, and write the Check for the pocket it runs in

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: sapling
- **Scope**: narrow
- **Priority**: P1 (next-cycle)
- **Source(s)**: `loop-gate-followups/LEARNINGS.md` implementation-planner entries (steps 2 to 6 run outside the loop because any edit to a driver module selected 60 eval test files plus 111 to 282 root tests against a 540 s bound; the whole root suite took 929.84 s; "Patterns That Worked": probing `resolve_test_scope.py --changed <paths> --json` on each candidate `Files:` set exposed the trap the architect missed) and orchestrator notes (the BA-01 scenarios ran 1,657 s); `main-session-adherence/LEARNINGS.md` planner gotchas (`--no-cov` unknown in the eval pocket, root-pocket commands carry it; `uv run pytest tests/e2e/... -n 0 --no-cov` from the root; the pocket gate for any `eval/src` step also runs the new eval-driving root tests, so a late step costs most).
- **Description**: Add a short "gate cost" section to the pending plan-authoring reference: before writing a step, run the resolver on its `Files:` and read the selected pockets and counts; a step whose selection cannot finish inside the gate's bound is declared a pocket bound (`gate-timeout-seconds`) or assigned outside the loop, with the reason recorded; a step that changes the gate cannot be gated by it. Add the per-pocket Check rules: no `--no-cov` in a pocket without pytest-cov, run e2e from the root with `-n 0 --no-cov`, and `uv run --project eval pytest` reads the root `addopts`.
- **Rationale**: Two pipelines paid for the same blind spot (one with 5 steps out of the loop, one with a wasted baseline and late-step gate cost), and the probe is cheap. The driver now bounds each pocket (td-527's fix is in flight), which makes the bound a thing a plan can declare, not only suffer.
- **Estimated scope**: one section in the pending reference
- **Overlap check**: pending 19-30-34 Proposal 5 proposes `skills/step-loop/references/plan-files-and-checks.md` for guard ownership and node partition; this extends it. `skills/step-loop/SKILL.md` mentions `not-driven` only as a stop cause. Partial.
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `skills/step-loop/references/plan-files-and-checks.md` (the pending page)

### Proposal 3: coordination-details — an orchestrator ruling on a spec call quotes the governing requirement

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: mature
- **Scope**: narrow
- **Priority**: P1 (next-cycle)
- **Source(s)**: `loop-gate-followups/LEARNINGS.md` step 11 decisions and "Orchestrator correction (2026-10-22, step 11 rev 2)" (the F4 ruling "a done marked step reads verified-complete" contradicted REQ-10 and was reversed, then the revision took the reviewer's edge option anyway and the verifier found it reachable through goal mode); harness memory `feedback_rule_escalations_against_req_text.md`.
- **Description**: In `coordination-details.md` § Spec-Question routing, add: when a reviewer or implementer asks for a spec call, the orchestrator's recorded decision quotes the governing REQ or AC line; if no requirement covers it, the call is a Spec Question for the architect, not a ruling; an edge is called unreachable only after every path into it (every mode of the function) has been traced. Pair it with the Conversation Checkpoints text so the ruling sits in the digest.
- **Rationale**: The lesson exists only in memory, and memory is not the channel. Two rulings in one step (F4 and the unreachable-edge argument) cost a rev-2 series and a verifier FAIL. The fix is a written rule at the point the orchestrator acts.
- **Estimated scope**: one paragraph in an existing section
- **Overlap check**: pending 19-33-49 Proposal 1 edits the same § Spec-Question routing (orchestrator-made amendments); review together. `rules/swe/swe-agent-coordination-protocol.md` § Conversation Checkpoints names the digest but not the quote. Partial.
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `skills/software-planning/references/coordination-details.md`

### Proposal 4: footprint-criteria — the measurer checks its own row, and `Reading` holds the instrument's label only

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: seedling
- **Scope**: narrow
- **Priority**: P2 (someday)
- **Source(s)**: `main-session-adherence/VERIFICATION_REPORT.md` first-pass FC-01 FAIL (FP02 x7, FP03 x2 on log form with the value holding), "Process note on the remedy", and the Merge candidate ("a measurement log whose Reading cells carry prose fails the footprint parser even when the value holds").
- **Description**: Change the Measurer row's check stage from `none` to `--stage verify` run right after appending, and state in "Reading a result" that the `Reading` cell is the instrument's own label (`measured` or `estimate`) and nothing else; notes go in a separate cell. If the project settles how a malformed row is superseded, say so in the same place.
- **Rationale**: The failure was a form defect on a correct value; the append-only rule then blocked its own repair. One sighting, so this is held at seedling, and the superseding rule needs the instrument owner (td-477 is in the same script) before it can be written.
- **Estimated scope**: two sentences in an existing reference
- **Overlap check**: `footprint-criteria.md` lines 22 and 52 (append-only, copy the label into `Reading`) are adjacent; td-477 is a matcher defect, not this. Partial.
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `skills/spec-driven-development/references/footprint-criteria.md`

### Proposal 5: implementer and test-engineer — type-check the files you changed, and know that pyright is not in the environment

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: sapling
- **Scope**: narrow
- **Priority**: P2 (someday)
- **Source(s)**: `loop-gate-followups/LEARNINGS.md` step 4 to 6 tooling ("`pyright` is not installed in the project environment; `uvx pyright <files>` works (root config)"), step 19 ("pyright is not installed in this environment; not run"), step 27 (163 errors at base, 179 at head, 36 new, all in test files, found at the final health guard and removed by the test-engineer without changing an assertion); `main-session-adherence/VERIFICATION_REPORT.md` (the verifier ran ruff and pyright over 63 files as a separate step).
- **Description**: Add one checklist line beside the id-citation line in the implementer's self-review (and the test-engineer's): run `uvx pyright <changed Python files>` against the root config when `pyright` is not installed, fix new errors without touching an assertion, and report "not run" only when it cannot run. Tests are in scope, since all 36 late errors were in test files.
- **Rationale**: Two implementers skipped it as "not installed" and the cost landed on a late test-engineer pass. The id-citation line (td-491) is the precedent: a cheap self-check that moves a known late failure to the step that causes it. Root CI runs pyright only on `eval/src`, so nothing else catches it.
- **Estimated scope**: one checklist line in each of two agent definitions
- **Overlap check**: `agents/implementer.md:128` (the id-citation check) is the model; no agent definition mentions pyright. td-484 closed the same class once. Partial.
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `agents/implementer.md`, `agents/test-engineer.md`

## Recommended Delegations

| Proposal | Delegation Path | Notes |
|---|---|---|
| 1 | context-engineer | Three agent definitions, one line each; load `agent-crafting` |
| 2 | context-engineer | Land with pending 19-30-34 Proposal 5 on the same page |
| 3 | context-engineer | Review with pending 19-33-49 Proposal 1 (same section) |
| 4 | context-engineer | Seedling; reject if the user prefers to wait for a second sighting |
| 5 | context-engineer | Paired sites: `agents/implementer.md` and `agents/test-engineer.md`, same commit |

## Defects and Deferred Fixes (for ledger routing; not artifact proposals)

Already filed, not repeated: td-488, td-489, td-490, td-491, td-492, td-493, td-494, td-487 (loop-gate findings, resolved or open as ledgered), td-495 (the five-name preview order), td-518, td-516, td-517, td-532 (`results.py` is 802 lines at HEAD against the 800 ceiling), td-527 (being fixed). Each row below was checked against the tree at `a3ba7469` and grepped against both ledgers (rows up to td-536); none matched.

| # | Location | Evidence | Note |
|---|---|---|---|
| D1 | `scripts/_step_loop_record_gate.py` `read_observed` (lines 353, 368, 374: `classify_run` and `_unanswered` run before `_in_pocket` qualifies the ids), `scripts/_step_loop_gate.py:215-227` (`is_pending`) | Probe at HEAD: `entry_owns("eval/tests/test_a.py::t", "tests/test_a.py::t")` and the file-level form both return `False`. A non-root pocket prints ids relative to itself, so a repo-relative `Read-only:` entry never owns them | loop-gate VR noted it as pre-existing, not a finding, and filed nothing. Impact today is bounded: pipelines so far list root outer-loop nodes. Either qualify the ids before judging, or document that `Read-only:` entries for a non-root pocket are pocket-relative |
| D2 | `eval/src/praxion_evals/adherence/moves/observe.py:40` (`from praxion_evals.live.materialize import _LINK_RULES`); `moves/tasks.py:25`, `moves/model.py:20`, `moves/lineage.py:42` (underscore helpers from `adherence.model`) | Present at HEAD by grep. main-session VR CW-7 (CLAUDE.md § Balanced Coupling: distant parts sharing private knowledge); the `live` import is the costly one | No ledger row. Make the names public or re-export; the `live` rename was deferred because `materialize.py` was outside the step's `Files:` |
| D3 | `eval/src/praxion_evals/adherence/moves/trigger.py:72` (`_AMEND`) | Reproduced at HEAD: `_AMEND.search("git commit -m 'document git commit --amend flow'")` is truthy. A heredoc message followed by `--amend` is the opposite miss (VR CW-5, probed by the step 20 reviewer) | Affects the history outcome only, which REQ-05 reports and never gates. Anchor `--amend` on a token |
| D4 | `moves/trigger.py:75` (the gate-reason pattern `hook error: \[[^\]]*\]`) | Read at HEAD: the bracketed hook command ends at the first `]`. VR CW-6: a hook command containing `]` truncates the recorded reason | Latent: no Praxion hook command contains `]` today |
| D5 | `scripts/kernel_run_evidence.py:174` (`read_run_files`) | No production caller at HEAD (grep over `scripts/*.py` finds only the definition); 7 references in `scripts/test_*.py`. loop-gate VR B3 `[DEAD-CODE-UNREMOVED]`, left open | Move the test sites to `read_results` and delete it |

## Disposition Log

<!-- Populated by /skill-genesis-review. Empty on report creation. -->

| Timestamp | Proposal | Disposition | Notes |
|---|---|---|---|
| _(empty — pending review)_ | | | |

## Recommended Next Steps

- Run `/skill-genesis-review` to disposition the 5 pending proposals. Proposals 2 and 3 land on pages that pending siblings from 19-30-34 and 19-33-49 also edit; review them together.
- Add these sightings to the pending sibling proposals, they are not new ones: Files omissions (Triage 8, 9) to 19-30-34 P4 and 19-33-49 P4; the named-channel trace (Triage 11) to 19-40-39 P4.
- Route D1 to D5 to tech-debt ledger rows (orchestrator or verifier, not this agent).
- Batch 5 of 5 may repeat evidence for Proposals 1 to 3; check these headings before re-proposing.
