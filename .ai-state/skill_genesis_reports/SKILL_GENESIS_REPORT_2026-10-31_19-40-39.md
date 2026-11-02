---
schema_version: 1
report_id: skill-genesis-2026-10-31_19-40-39
generated_at: 2026-10-31T19:40:39Z
task_slug: context-diet-resume
agent_version: skill-genesis@a3ba7469
invocation_args: { since: null, scope: null, sources: ".ai-work/_harvest-diet", batch: "3 of 5", dry_run: false }
review_status: complete
disposition_count: { pending: 0, approved: 1, rejected: 3, refined: 0, deferred: 1 }
---

# Skill Genesis Report — 2026-10-31 19:40:39

## Summary

1 queue source (`lean-spawn-pilot`, 148,940 bytes) analyzed, 22 learning items extracted, 5 proposals generated, 15 deduplicated or skipped as already carried by the current tree (shipped v0.52.0; dec-460 to dec-465 and later pipelines have absorbed most of the pilot). 2 defects listed for ledger routing. Review status: pending.

Interpretation and assumptions: (1) a learning counts as carried only if the current tree (rules, skills, agents, docs, scripts) holds it, not if a memory file does; (2) the pilot's own contracts (manifest, generator, ledger, hook) are design records, not reusable artifacts, and are skipped; (3) earlier reports that marked the worktree-guard learning "already captured in `docs/claude-code-limitations.md`" were checked and the doc does not hold it (verified by grep 2026-10-31).

## Learning Sources Consumed

| Source | Path | Items Extracted | Status |
|---|---|---|---|
| Queue source LEARNINGS.md | `.ai-work/_harvest-diet/lean-spawn-pilot/LEARNINGS.md` | 19 | Read whole |
| Queue source VERIFICATION_REPORT.md | `.ai-work/_harvest-diet/lean-spawn-pilot/VERIFICATION_REPORT.md` | 3 | Read whole |
| CONSULT fragments | `.ai-work/_harvest-diet/lean-spawn-pilot/CONSULT_*.md` | 0 | Not found |
| Sentinel report / idea ledger | `.ai-state/sentinel_reports/`, `.ai-state/idea_ledgers/` | 0 | Not consulted (queue mode; no overlap expected) |
| ADRs | `.ai-state/decisions/` | 0 | Not matched (the pilot's decisions are already ADR'd) |
| Calibration log Retrospective cells | `.ai-state/calibration_log.md` | 0 | Not consulted; the pilot's own cell is quoted in the verification report |
| Sibling reports | `SKILL_GENESIS_REPORT_2026-10-31_19-30-34.md`, `..._19-33-49.md` | n/a | Headings and overlapping bodies read |

## Triage Results

| # | Item | Source | Decision | Rationale |
|---|---|---|---|---|
| 1 | A refusal scenario that passes on any nonzero exit hid a harness fault (exit 2, venv lost) | LEARNINGS Step 14 T3; VR td-441 | Skill (update) | Proposal 1 |
| 2 | Worktree session refuses Bash by command text (`eval`, `git` in heredocs, `sh -e`, `$(...)`); written down by 7 agents in this pipeline | LEARNINGS Steps 6, 13, 15, 17, 18, 23, 27; planner | Skill (update) | Proposal 2; memory holds it, no artifact does |
| 3 | `**Read-only**:` read from one line only; bulleted form parses as zero owners | LEARNINGS Step 10 orchestrator note | Skill (update) | Proposal 3; defect D1 is the parser half |
| 4 | Paid-run premises proved by the paid run: delivery channel (two smoke pairs), credit balance (run 1), kit capacity vs the 20-pair floor (Step 30) | LEARNINGS Steps 20, 28, 30 | Skill (update) | Proposal 4 |
| 5 | Orchestrator brief to a test-engineer named the plan and traceability; failed acceptance independence | LEARNINGS rework dispositions; VR FAIL-2 | Skill (update) | Proposal 5; repeated in a second pipeline (memory) |
| 6 | Steps edited files outside `Files:` (BC05 consumers, observation-log registry, paid-eval guard scan, hook `files:` alternation, `kernel_model.py`) in Steps 11, 13, 14, 15, 19, 21, 22 | LEARNINGS objections | Skip (duplicate) | Pending 19-30-34 Proposal 4 and 19-33-49 Proposal 4 already carry it; this pipeline adds ten instances, see Proposal 4 evidence note of those reports |
| 7 | `generate_kernels.py` 577 lines because `Files` allowed no sibling; `kernel_model.py` 791/800 | LEARNINGS Steps 8, 11, 12, 15 | Skip (duplicate) | Same pending Proposal 4 (module size) |
| 8 | Guard-owned nodes and ownership partition by script | LEARNINGS Patterns That Worked | Skip (duplicate) | Pending 19-30-34 Proposal 5 |
| 9 | Step-scoped Checks never run the eval pocket; a pocket run belongs at each checkpoint | LEARNINGS Step 23 | Skip | Carried: `resolve_test_scope.py` unions pockets and the plan has an integration checkpoint |
| 10 | Spawn counter over-attributed headless instrument sessions (86 vs ~26) | LEARNINGS Step 15; VR | Skip | td-433 resolved; `scripts/CLAUDE.md` `spawn_count.py` row documents `left_out` |
| 11 | Runner did not stop on repeated identical infra errors and kept no stderr | LEARNINGS Step 28 run 1 | Skip | Carried: `--stop-count`, `--tail-chars` (`eval/README.md`; td-444, td-445 resolved) |
| 12 | Harness names transcript dirs by turning every non-alphanumeric into a dash | LEARNINGS Step 28 pair 2 | Skip | Fixed in `scripts/_workflow_run.py::transcripts_dir` and `transcript.py`; td-454 resolved. The memory `context-baseline-worktree-dir-resolution` still says "/" and "." only: stale |
| 13 | A trial closes as `held`, never by deletion | LEARNINGS Decisions (2026-10-15) | Skip | ADR'd; `docs/lean-spawn-how-to.md` § Hold a role |
| 14 | Re-tier to Full when the plan's spawn estimate (27) exceeds Standard's 16 | VR Calibration | Skip | Carried by the coordination protocol's envelope rule |
| 15 | Subscription token route for sessions, judge on the key; caps stated to the user | LEARNINGS Steps 29; VR WARN-2 | Skip | Carried: how-to "Before the first paid run" checklist states the credential and every cap before launch |
| 16 | Generated blocks and the gate that reads them change in one commit; regenerate before switching the gate | LEARNINGS Steps 12, 13 | Skip | One-off to this generator; the order is in the plan, not reusable |
| 17 | Pin extent, part cut, marker format, slot packing, ledger moves, I1-I10 contracts | LEARNINGS Steps 8-19, 27, 33 | Skip | Pilot design contracts, recorded in `docs/lean-spawn-kernels.md` and the checker |
| 18 | Judge failed both golden cases; C5 6-0 vs 0-2 draw; sign test | LEARNINGS Steps 28, 29 | Skip | Run-specific; dec-459 clause 6 already requires stating it |
| 19 | Stale DESIGN.md sentence and docs after the held follow-up | LEARNINGS Step 33 | Skip | Fixed in the current tree (no `design target since 2026-10-15`, `kernel_ledger_history` in `scripts/CLAUDE.md`) |
| 20 | Pre-existing label on a regression the flip caused | VR WARN-11 | Skip | Instance of Surface Assumptions; no new artifact |
| 21 | Nine synchronous hook starts per `praxion:*` spawn, latency declared not measured | LEARNINGS Step 19 | Skip (defect) | Defect D2 |
| 22 | Driver fix mixed into an implementer commit | VR WARN-10 | Skip | Carried by pathspec-commit practice and `[NON-SURGICAL]` tag |

## Proposals

### Proposal 1: gate-canaries — a refusal canary asserts the gate's own exit code and finding, not "any nonzero"

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: sapling
- **Scope**: narrow
- **Priority**: P1 (next-cycle)
- **Source(s)**: `lean-spawn-pilot/LEARNINGS.md` "Step 14 learnings (checker I1-I5)" Blocker (the sandbox shim lost the venv, so 11 of 18 gated scenarios exited 2 on a missing PyYAML), "Step 14 driver fix (T3)" Lesson ("a refusal-expecting scenario that passes on any nonzero exit hides a harness fault"); `VERIFICATION_REPORT.md` Test Coverage gaps (td-441, still open).
- **Description**: In `gate-canaries.md`, state that a canary asserts the exact refusal code the gate documents plus the named finding kind, and that "non-zero exit" alone is insufficient wherever the gate has a distinct input-error exit (usually 2). Add the bad-case: a harness fault (missing interpreter, lost venv) reads as a refusal, so the canary stays green while the gate never ran. Pair with a case where the gate runs on a good input in the same harness.
- **Rationale**: The current page names "non-zero exit, raised error, or a non-empty findings list" as sufficient proof of bite (line 9), which is the shape that hid a harness fault here for a whole step. This is the "existence is not operation" clause applied to canaries, and it cost an implementer blocker and a driver fix. One pipeline of evidence plus an open ledger row makes it a sapling.
- **Estimated scope**: one bullet and one bad-case in an existing reference
- **Overlap check**: `rules/swe/gate-liveness.md` ("Existence is not operation") covers the principle; `skills/testing-strategy/references/gate-canaries.md` line 9 states the weaker oracle; td-441 fixes one instance only. Partial.
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `skills/testing-strategy/references/gate-canaries.md`

### Proposal 2: claude-code-limitations — the worktree session's Bash command-text refusals, and the escape every agent should use

- **Disposition**: pending
- **Type**: skill (update) — placement ambiguous: the home is `docs/claude-code-limitations.md` plus one pointer line in the implementer and test-engineer definitions; the context-engineer decides
- **Maturity**: mature
- **Scope**: medium
- **Priority**: P1 (next-cycle)
- **Source(s)**: `lean-spawn-pilot/LEARNINGS.md` Gotchas (planner, "refuses commands containing the word `eval` and heredoc file writes"; implementer Step 23), Driver-binding learnings (test-engineer, heredoc-fed `python3 - <<EOF`), Step 13 attempt 2 (`sh -e <file>`, `$(...)`), Step 15 (`sh <file>`), Step 17 (`cd e[v]al`), Step 18 (heredoc whose text holds `git`), Step 27 (`resolve_test_scope.py | sh -e`); earlier reports 2026-09-04, 2026-09-23_23-16-24 and 2026-09-27 each skipped it as "already captured" in memory or limitations.
- **Description**: A limitations entry listing what the harness's worktree-isolated session refuses by command text (the word `eval` including as a path, `python3 -` or `-c` text naming `git`, heredocs holding git-like words, `sh -e`/`bash <file>` and `$(...)` expansions, `HOME=` overrides) and the one working escape: write a multi-line script with the `Write` tool to the scratchpad and run it by path, or run the emitted commands through a Python subprocess runner. Mark it with the Claude Code version observed and a re-verify date; the implementer and test-engineer definitions carry one pointer line.
- **Rationale**: Seven agents in one pipeline each re-discovered it, and three earlier harvests skipped it because memory holds it. Memory is a supplement; the agents that hit this are spawned without it, and `docs/claude-code-limitations.md` has no such entry (grep 2026-10-31). Recurrence across at least four pipelines makes it mature.
- **Estimated scope**: one limitations entry and two one-line pointers
- **Overlap check**: memory `worktree-guard-command-text-heuristics` (supplement only); `docs/claude-code-limitations.md` has no entry; `skills/merge-worktree/SKILL.md` mentions the retired guard only. Staleness risk: observed on Claude Code 2.1.296; re-run before writing the entry.
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `docs/claude-code-limitations.md` (+ `agents/implementer.md`, `agents/test-engineer.md`)

### Proposal 3: document-templates — the `**Read-only**:` field is one line of backticked spans

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: mature
- **Scope**: narrow
- **Priority**: P1 (next-cycle)
- **Source(s)**: `lean-spawn-pilot/LEARNINGS.md` "Step 10 learnings" last bullet (nine fields written as a count line plus indented bullets; the driver saw no owner for 78 nodes and gated a correct step, costing an attempt); `VERIFICATION_REPORT.md` td-432 (open); memory `plan-readonly-field-one-line`.
- **Description**: In the canonical `Read-only:` schema, add one sentence: write the field as a single line of comma-separated backticked `path::node` spans (a `contract:` entry likewise); indented sub-bullets are not read and yield zero owners. Add the matching bad-case to the planner's `**Read-only**:` bullet in `agents/implementation-planner.md`. Reproduced on the current tree: a bulleted field parses to `read_only=()` with no warning.
- **Rationale**: The planner follows the template, whose example is a bracketed free-text line; its literal form then differs from what `_plan_steps.py` reads. Until the parser accepts bullets (td-432), the contract must say which form is read. Two sightings (the pilot, plus the memory's identical note) and an open ledger row.
- **Estimated scope**: one sentence in the schema paragraph and one bad-case in the planner definition
- **Overlap check**: `document-templates.md` line 67 and `agents/implementation-planner.md` line 174 state the field's purpose and the one-step-per-node invariant, not the line form. Pending 19-33-49 triage row 9 mentions Read-only prefix ownership, not this. Partial.
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `skills/software-planning/references/document-templates.md` (+ `agents/implementation-planner.md`)

### Proposal 4: agent-evals — preflight a paid adherence run's premises with free probes, and size the kit against the floor at plan time

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: sapling
- **Scope**: narrow
- **Priority**: P1 (next-cycle)
- **Source(s)**: `lean-spawn-pilot/LEARNINGS.md` Spike Answers (Step 20 marker channel "load-bearing, unproven live"; "the first paid probe pair ... is what proves it"), Step 28 smoke pairs 1 and 2 (about USD 4.4 spent on a channel premise the free standalone probe then showed false), Step 28 run 1 (USD 15.34 into a dead key: credit balance exhausted), Step 30 (the three smoke-kit roles cannot reach 20 pairs: "a plan gap the pre-flip checkpoint did not catch"); memory `rehearse-real-checkout-before-paid-run` (an independent pipeline: a dry run built no arms).
- **Description**: A short "before the first paid session" list in the eval-design page: (1) prove the delivery channel with one free, unjudged session before any paid pair, and never make the paid pair the proof of a premise recorded as "verified in code, not run"; (2) probe the credential with one cheap call; (3) compare the kit's producible task count with the flip floor (20 complete pairs) at plan time, so a role that cannot reach it is held or given a larger kit before any run is scheduled; (4) rehearse the arm build on the real checkout, not a narrowed fixture.
- **Rationale**: Four separate paid-run failures across two pipelines share one cause: a precondition checked by the expensive step. Parts already shipped (`--stop-count`, the isolation preflight, the how-to checklist for move runs) bound the damage but do not move the proof earlier, and the how-to checklist covers move runs only.
- **Estimated scope**: one short section in an existing reference
- **Overlap check**: `skills/eval-praxion/SKILL.md` (isolation preflight session, credentials); `docs/lean-spawn-how-to.md` § "Before the first paid run" (move runs only); pending 19-30-34 Proposal 1 targets the same page (`eval-design-patterns.md`) with grader-subject gotchas, so land them together. td-449 tracks the kit gap itself. Partial.
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `skills/agent-evals/references/eval-design-patterns.md`

### Proposal 5: coordination-details — every test-engineer prompt that edits outer-loop files carries the allowed inputs only

- **Disposition**: pending
- **Type**: skill (update)
- **Maturity**: mature
- **Scope**: narrow
- **Priority**: P1 (next-cycle)
- **Source(s)**: `lean-spawn-pilot/LEARNINGS.md` rework dispositions (2026-10-16: row 1 "caused by the orchestrator's own brief pointing the test-engineer at the plan and traceability ... Lesson recorded: a brief to the test-engineer names only its allowed inputs; the orchestrator runs the pocket command and writes the traceability pointers itself"); `VERIFICATION_REPORT.md` FAIL-2 and its closing note; memory `acceptance-brief-allowed-inputs` (the same failure a second time, in lean-spawn-continuation, FAIL row 6).
- **Description**: In the test-engineer delegation checklist, extend the acceptance-design bullet to every prompt that lets the test-engineer touch an outer-loop file (a Spec-Question resume, a rework row, a late fix): name only the spec extract, existing acceptance tests and drivers, and public entry points. The orchestrator supplies the pocket `Run:` command and writes the `traceability.yml` node ids after the return. Bad-case: a brief that says "find the pocket command in the plan" or "add node ids to traceability".
- **Rationale**: The checklist constrains only `Mode: acceptance-design`; the failure came from resumes and rework briefs, outside that mode. It recurred in two pipelines and each time the final verifier failed the run on acceptance independence, costing a rework round and an extra spawn.
- **Estimated scope**: one checklist bullet in `coordination-details.md`, mirrored by the operational copy in `agents/test-engineer.md` (paired sites)
- **Overlap check**: `coordination-details.md` lines 37-40 and § "Allowed and Forbidden Inputs" (designer-mode inputs); pending 19-33-49 Proposal 1 (record the Spec Question at change time) is adjacent, not the same. Partial.
- **Recommended delegation**: context-engineer
- **Suggested artifact path**: `skills/software-planning/references/coordination-details.md` (+ `agents/test-engineer.md`)

## Defects and Deferred Fixes (for ledger routing; not artifact proposals)

Already filed, not repeated: td-432 (Read-only form), td-441 (refusal oracle), td-442/td-443 (hook `@path` scope and fences), td-448 (researcher early-stop form), td-449 (smoke kits cannot reach 20 pairs), td-452 (CLI tests encode the researcher kit), td-457 (e2e journeys read the live switched set), td-459 (files near the 800-line ceiling). Items the pilot recorded that are already resolved (td-433, 444 to 447, 450, 451, 453 to 455, transcript-dir mangling, stale docs) were confirmed fixed in the tree and are omitted.

| # | Location | Evidence | Note |
|---|---|---|---|
| D1 | `scripts/_plan_steps.py::_read_fields` / `parse_plan_steps` (extends td-432) | Reproduced 2026-10-31: a `**Read-only**:` line followed by indented bullet nodes returns `read_only=()` with no warning or error; the pilot's Step 10 attempt 1 was gated as a mismatch for this (`fail=231 pending=0`). td-432 asks for one canonical form; nothing flags a plan whose `ACCEPTANCE_TESTS.md` nodes have no owner | Suggest the parser (or `step_loop.py next`) refuse or warn when outer-loop nodes exist and no step owns any, per the gate-liveness "named consumer" clause; fold into td-432 or a new row |
| D2 | `hooks/hooks.json` (9 synchronous `SubagentStart` entries running `hooks/inject_kernel.py`; `claude/kernels/index.json` `slots` = 9); `docs/lean-spawn-kernels.md` | LEARNINGS Step 19 "Latency footprint (declared, not measured)": nine extra `python3` starts per `praxion:*` spawn plus one `git rev-parse` each; `grep -i latency` over `docs/lean-spawn-*.md` and both ledgers returns nothing, FC-05 measured tokens only | Spawn latency cost of the hook is unmeasured; either measure once (wall time of a `praxion:*` spawn, trial role vs none) and record it, or file as accepted with the figure |

## Recommended Delegations

| Proposal | Delegation Path | Notes |
|---|---|---|
| 1 | context-engineer | Load `skill-crafting`; one bullet plus bad-case in `gate-canaries.md` |
| 2 | context-engineer | Re-verify the refusal list on the current Claude Code first; placement (docs vs agent pointers) is the context-engineer's call |
| 3 | context-engineer | Schema sentence plus planner bad-case; coordinate with the td-432 fix so the sentence is dropped if the parser accepts bullets |
| 4 | context-engineer | Land with pending 19-30-34 Proposal 1 on the same page |
| 5 | context-engineer | Paired sites: `coordination-details.md` and `agents/test-engineer.md`, same commit |

## Disposition Log

<!-- Populated by /skill-genesis-review. Empty on report creation. -->

| Timestamp | Proposal | Disposition | Notes |
|---|---|---|---|
| 2026-11-01T23:00:00Z | Proposal 2: worktree session Bash command-text refusals | defer | Strong recurrence (4+ pipelines) but harness behaviour changes per version (4 additions in 2 months); re-verify on current Claude Code, then add to docs/claude-code-limitations.md |
| 2026-11-01T23:00:00Z | Proposal 3: Read-only: field is one line of backticked spans | reject | ledgered: td-432 open covers it (parser or template fix) |
| 2026-11-01T23:00:00Z | Proposal 4: preflight a paid adherence run with free probes | reject | built: Checklist for move runs exists with caps and credential statement |
| 2026-11-01T23:00:00Z | Proposal 5: test-engineer prompts carry allowed inputs only | reject | built: Allowed-inputs table and Spec-Question resume rule exist; residual gap is rework briefs |
| 2026-11-02T07:30:00Z | Proposal 1: gate-canaries — a refusal canary asserts the gate's own exit code and finding, not "any nonzero" | approve | pick 2 (bundled with 2026-09-23_22-43-59 P1): a refusal canary asserts the gate's documented exit code and named finding. Lightweight, built after routing-facts merges |

## Recommended Next Steps

- Run `/skill-genesis-review` to disposition the 5 pending proposals (review Proposal 4 with 19-30-34 Proposal 1; Proposal 5 beside 19-33-49 Proposal 1).
- Route D1 and D2 to tech-debt ledger rows (D1 may join td-432).
- The memory `context-baseline-worktree-dir-resolution` is stale on the dash mapping (now fixed in `scripts/_workflow_run.py`); update or retire it.
- Remaining batches (4 and 5 of 5) should check this report's headings before re-proposing.
