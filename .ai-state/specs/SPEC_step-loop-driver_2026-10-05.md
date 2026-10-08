# Spec: step-loop-driver (a deterministic step-loop driver for the span between the pre-mortem gate and the pre-verification checkpoint)

**Task slug**: `step-loop-driver`
**Feature**: A deterministic, file-driven step-loop driver (`scripts/step_loop.py` with the verbs `next`, `record` and `status`) takes over the crank the orchestrator used to turn by hand between the pre-mortem gate and the pre-verification checkpoint: it selects the next plan step from the reconciler's ground truth, renders a fixed prompt and an Agent-tool spawn request for one fresh implementer, writes the attempt ahead of the spawn, gates the returned attempt on its own transcript's end evidence plus the derived test scope and the step's `Check:`, commits a verified step by explicit path with a request trailer, appends one iteration-ledger record per return, enforces the two-attempt cap and the plan-derived iteration budget in code, and stops for a human with a composed handoff. The orchestrator relays three values per request through a spawner seam. This pipeline shipped the driver's core, bindings and `record`; the in-loop light reviews, the turn-budget reminder hook, the `/step-loop` command, the Ralph-lite recipe, the spawn-counter iterations, the architecture documents, the plan-local review-trigger prose and the loop pointers moved to a follow-up pipeline by the split decision at close.
**Tier**: Full (from intake; the previous pipeline, step-schema, was Full-shaped and had to be re-tiered at its verifier seam). Budget 32 spawns, charged 32 (27 spawns, 5 heavy resumes); the final verifier ran as spawn 33 with the user's authorization.
**Pipeline branch**: `worktree-step-loop-driver`
**Start date**: 2026-10-04
**End date**: 2026-10-05
**Archived**: 2026-10-05 (post-merge; merged to main as `449141f4`)
**Status**: completed -- verifier first pass PASS WITH FINDINGS (0 FAIL, 12 WARN; a registered objection that the split of steps 21–28 and 30 to the follow-up pipeline was self-gated by the orchestrator; the user ratified the split on 2026-10-07, which lifts the condition); two in-worktree rework steps (33, 34) closed the four code findings (the handoff's fork point and the driver's base ref, the results reader's non-step heading, SIGTERM in the command runner, the reconciler's function size); re-verified at `bc256126` as PASS WITH FINDINGS, 0 FAIL, 9 WARN open, all rework rows closed; calibration verdict under-calibrated (36 spawns against 32, 9 steps split out, 2 rework steps added)
**ADRs**: `dec-432` (category: architectural -- a deterministic step-loop driver owns the crank between the pre-mortem gate and the pre-verification checkpoint; the orchestrator relays spawn requests through a spawner seam), `dec-433` (category: architectural -- a synchronous PreToolUse hook reminds a capped subagent at 60 and 80 percent of its maxTurns; the component is deferred to the follow-up pipeline; on 2026-10-07 the user kept the record accepted as the design to build and ruled it not in force until the hook ships within its latency bounds), `dec-428` (category: behavioral -- attempt evidence in the WIP line and the ledger), `dec-429` (category: behavioral -- driver-emitted spawns budgeted as iterations against a plan-derived budget), `dec-430` (category: behavioral -- the light-review trigger is plan-local), `dec-431` (category: behavioral -- Ralph-lite is an execution mode in the Lightweight row; confirmed by the user on 2026-10-07 on condition that the recipe carries the loop's two durable ideas, a fresh context per iteration and state on disk) -- superseded on 2026-10-08 by `dec-434`, which makes Ralph-lite the step-loop driver's goal mode (a fresh headless process per iteration, entered through a skill) after the `ralph-lite-spike` research. All six were promoted and marked accepted by the finalize at merge; on 2026-10-07 the user confirmed `dec-431` with its condition and ruled `dec-433` accepted but not in force until the follow-up pipeline measures the hook.
**Evidence base**: the six ADRs above; the fast-forward merge `449141f4`; the pipeline's completion row in `.ai-state/calibration_log.md` dated 2026-10-05; the committed suites named in the matrix below (unit suites under `scripts/test_loop_*.py`, `scripts/test_plan_steps*.py`, `hooks/test_agent_transcript.py`; outer-loop scenarios under `tests/acceptance/test_step_loop_*.py` and `tests/e2e/test_step_loop_drives_a_plan.py`); the AC-13 replay record in the pipeline's `LEARNINGS.md` (harvested under `.ai-work/_harvest/step-loop-driver/`).

## Feature Summary

Before this change the orchestrator was the loop: it picked each step, wrote the spawn prompt, judged the implementer's return from a self-reported marker, committed, appended the ledger record and enforced the attempt cap by hand. The spike that preceded the step-schema pipeline measured the cost: a live orchestrator context around 420k tokens at the verifier spawn, capped implementer work absorbed by the orchestrator itself, and a single committer that also had to recover every truncation by archaeology. The step-schema pipeline made steps machine-checkable (`Check:` lines, `Attempts:` lines, the iteration ledger); this pipeline builds the driver on top of them.

The driver is pure code over the pipeline documents. `next` reads the plan, `WIP.md`, the iteration ledger, the light-review files and the task brief, asks the reconciler for ground truth against the pipeline's base, and prints one JSON envelope naming the one next action: a spawn request (the Agent tool's four parameters passed unchanged, a `PROMPT_<request>.md` file written first, the `Attempts:` line written ahead with the request id), `complete`, or a stop for a human or the budget. Selection honours `[depends-on]` and `[parallel-group]`, is deterministic, and reissues a pending request instead of duplicating it. `record` takes back an ended agent by its own transcript (found by agent id under the harness config directory, required to open with the request's `Spawn request:` line and to show an end: a final text, the turn cap or an `agent_stop` row), derives the turns, the marker (the transcript's wins over the relay) and the stop reason, runs the derived test scope over the declared files that differ from HEAD and the step's `Check:` as one gate block ending on the deciding `Result:` line, commits a verified attempt by literal pathspec while refusing or snapshotting any disturbance of the tree, appends exactly one ledger record per request, and replans or stops when the cap is spent. `status` reports without writing. Every phase is keyed by the request, so a call cut off part-way completes when run again. Precedence of outcomes is complete, then needs-human, then budget-exhausted, then spawn; a marked series is done only with a verified implement record and a satisfied light review.

The shared reader of a subagent's own transcript (`hooks/_agent_transcript.py`) serves the driver's end evidence today and the turn-budget reminder hook in the follow-up pipeline. The reconciler's JSON became one shape (closing a step-schema debt), its `Files:` reader moved into a plan-step module, and the derived test scope became collision-free (one pytest invocation per group that shares a `tests` package). The handoff composer takes the driver's next action and writes a forced handoff at every stop.

Shape of the delivery: twenty implementer steps in band A were hand-delegated with the orchestrator running each step's `Check:` and committing by pathspec, seven light reviews caught three revise rounds (an unreadable ledger record that left a step in-flight forever, fail-open pytest parsing, the commit adapter's handling of staged renames and interrupted runs, and four record-pipeline holes fixed in the last commit), and the pipeline closed after band A when the spawn envelope ran out: the live dogfood (band B) moved to the follow-up pipeline and the dogfood criterion was met in the replay form the specification allows, with two consecutive steps of the harvested step-schema pipeline driven end to end in a scratch clone through a substitute spawner.

## Requirements

Verbatim from `SYSTEMS_PLAN.md § Behavioral Specification` as extracted by `extract_spec.py` (digest `eecc7767aab6`; REQ ids are pipeline-local and appear nowhere in code, tests or docstrings). The extract's Observable Surface defines the terms the requirements use.

The requirements describe the loop at its surface: the driver's command and its three verbs, the pipeline documents it reads and writes, the Agent tool request the orchestrator executes, the reminder an agent sees, and the texts a reader follows. The attempt cap is the value stated once in the completion-handshake procedure (two fresh attempts today); "the cap" below means that value.

### Observable Surface

- `python3 scripts/step_loop.py` — the step-loop driver's command, named at intake; its verbs, output envelope and exit codes follow the interface design's public contract
- `next` — the verb that returns the loop's next action: a spawn request, completion, or a stop
- `record` — the verb the orchestrator calls after an agent's completion notification
- `status` — the read-only verb that reports the loop's state
- `--request`, `--agent-id`, `--marker` — the only three values the orchestrator relays to `record`: the spawn request's id, the agent id the Agent tool result carries, and the terminal marker the orchestrator saw (complete, blocked, conflict, partial or none)
- `--json` — the machine-readable output flag of `status` and of the existing reconciler and ledger commands
- `spawn`, `complete`, `needs-human`, `budget-exhausted`, `error` — the outcome values of the driver's output envelope
- `Task slug:` — the attribution line a spawn prompt begins with, read by the existing spawn counter
- `IMPLEMENTATION_PLAN.md`, `WIP.md`, `TEST_RESULTS.md`, `TASK_BRIEF.md`, `HANDOFF.md`, `LEARNINGS.md`, `MEASUREMENTS.md`, `ITERATION_LEDGER.jsonl` — existing pipeline documents in the task's working directory
- `Files:`, `Check:`, `Read-only:`, `Attempts:`, `Result:`, `Mutation:` — existing step, progress and results fields
- `[depends-on]`, `[parallel-group]`, `review: force`, `review: off`, `tier: H`, `tier: L`, `mutation: on` — existing step annotations
- `[COMPLETE]`, `[BLOCKED]`, `[CONFLICT]`, `[PARTIAL]` — existing terminal markers
- `verified-complete`, `attempts-exhausted` — existing reconciler verdict words
- `python3 scripts/reconcile_pipeline_state.py` — the existing reconciler command
- `python3 scripts/iteration_ledger.py` — the existing iteration-ledger command
- `python3 scripts/iteration_ledger.py read step-loop-driver --json` — the ledger reading behind FC-10 and FC-11
- `python3 scripts/resolve_test_scope.py` — the existing derived-test-scope command
- `uv run pytest -q -p no:cacheprovider` — the CI-shaped full run from the repository root
- `PreToolUse`, `additionalContext`, `maxTurns` — the harness's hook event, its hook output field, and the agent-definition turn cap
- `hooks/hooks.json` — the plugin's existing hook registration
- `/goal`, `acceptEdits` — the harness's goal command and permission mode
- `python3 scripts/check_state_ledgers.py`, `python3 scripts/sync_canonical_blocks.py --check` — existing health-guard commands
- `python3 scripts/check_agent_prompt_size.py --json`, `python3 scripts/measure_token_budget.py --json`, `python3 scripts/measure_selection_size.py --compare-ref <base>`, `python3 scripts/context_baseline.py --project-root /Users/fperez/dev/praxion --json`, `/usr/bin/time -p <command...>` — existing measurement instruments named by the footprint criteria

### REQ-01: Next-step selection honours the plan's order

**When** `next` is called, no spawn request is pending, and the plan holds at least one step that is not `verified-complete`
**the system** selects the first step in plan order that is not `verified-complete` and whose `[depends-on]` steps are all `verified-complete`, where membership of a `[parallel-group]` never makes a step wait for a sibling in its own group, and keeps at most one request outstanding at a time
**so that** the loop runs the plan's steps in the order and under the dependencies the planner declared, and never starts a step whose prerequisites are unverified

### REQ-02: Selection is deterministic and a pending request is reissued, not duplicated

**When** `next` is called again with the plan, WIP.md, the tree and the ledger unchanged, or again before the pending request has been recorded
**the system** returns the same answer every time; while a request is pending it returns that same request marked as reissued, leaves every file byte-identical and counts no new attempt
**so that** an agent that returns asynchronously, or an orchestrator that asks twice, can never cause two spawns for one attempt

### REQ-03: A plan with no eligible step stops for a human

**When** `next` is called and some step is not `verified-complete` but no step is eligible, because a dependency names a step the plan does not contain or the dependencies form a cycle
**the system** stops with exit 2 and names each step that cannot start and the dependency that holds it
**so that** a planning defect surfaces at once instead of looping or silently skipping work

### REQ-04: No step escapes the gate

**When** the next eligible step is assigned to an agent other than the implementer
**the system** neither skips it nor reads it as complete unless the same ground-truth gate an implementer step passes (REQ-15) verifies it, or the step declares no `Files:` and no `Check:` and its WIP.md entry claims it complete
**so that** a step's assignee is never a way around the gate, while a step that gives the gate nothing to judge does not stop every plan for good

### REQ-05: The spawn request is ready to execute as it stands

**When** `next` selects a step for a fresh attempt
**the system** prints one JSON envelope with outcome `spawn` whose request carries the request's id, the step, the attempt number and the cap, and the Agent tool's parameters to be passed unchanged: the implementer agent type; the model the step's routing annotation selects (Opus for `tier: H`, Sonnet otherwise, never the bare Haiku alias); a short description; and a prompt whose first line is the `Task slug:` line
**so that** the orchestrator executes the request without composing anything, and the spawn counter attributes the spawn to this pipeline

### REQ-06: The rendered prompt carries exactly its fixed parts

**When** the driver renders the prompt for an attempt at a step
**the system** produces it from a fixed template carrying exactly: the `Task slug:` line; the step block verbatim from IMPLEMENTATION_PLAN.md, with its `Read-only:` and `Check:` lines inside it and not repeated elsewhere; the user's operating constraints recorded at intake, verbatim; the standing corrections that are not already part of the implementer's own instructions; from the second attempt on, what stopped each earlier attempt; and the stop instruction (stop in a committable state; never commit). It carries nothing else: no model name, no plan field from outside the step block, and no text the orchestrator wrote for this spawn
**so that** every attempt is briefed from the plan and the brief alone, and the orchestrator has nothing to write by hand

### REQ-07: The prompt is reproducible and bounded

**When** the same step and attempt are rendered twice from unchanged inputs, or a step block is large
**the system** produces byte-identical prompts, keeps every prompt within a stated size ceiling, and reports a step block that would push the prompt past that ceiling instead of silently truncating it
**so that** a golden test can pin the prompt and an oversized step is caught before it reaches an agent

### REQ-08: The attempt is counted before the request is printed

**When** `next` prints a fresh request for attempt n+1 of a step
**the system** has already written count=n+1 on that step's `Attempts:` line in WIP.md
**so that** a crash or a lost return between the request and the spawn can never leave an attempt uncounted

### REQ-09: A running attempt is not an exhausted one

**When** a step's capped attempt has been requested and not yet recorded
**the system** reports that step as in flight, not `attempts-exhausted`, both in `status` and in the reconciler's verdict, and reads it as `attempts-exhausted` only once that attempt has been recorded without verified completion; a WIP.md written without the driver reads exactly as it does today
**so that** the cap verdict applies only after the capped attempt has ended, and no reader routes a still-running step to a human

### REQ-10: The attempt cap stops the step

**When** a step's attempt that reaches the cap has been recorded without verified completion, including an attempt that returned `[COMPLETE]` while its declared check fails
**the system** emits no further request for that step, reads it as `attempts-exhausted`, and stops with exit 2 and a replan request naming what stopped each attempt
**so that** capped work reaches a human with the evidence needed to replan, instead of being retried again or absorbed by the orchestrator

### REQ-11: A plan revision reopens an exhausted step

**When** a step has stopped as `attempts-exhausted` and a human then revises that step's text in IMPLEMENTATION_PLAN.md
**the system** offers a fresh attempt series for the step on the next `next`; without a revision, every `next` returns the same stop
**so that** granting more attempts is a visible, reviewable plan edit and never a hidden switch

### REQ-12: A spawn that never started costs no attempt

**When** the orchestrator reports through `record` that a request never started an agent, because the Agent tool call failed before launch
**the system** withdraws that request's write-ahead attempt and appends no ledger record; when evidence shows an agent did start for that request, it refuses the report as a caller error and changes nothing
**so that** the cap counts only agents that actually ran

### REQ-13: The orchestrator relays three values after the completion notification

**When** the implementer, which its agent definition always runs in the background so that no spawn request carries a flag choosing foreground or background, ends and the orchestrator receives its completion notification
**the system** accepts from the orchestrator, for that return, only `--request`, `--agent-id` and `--marker` on `record`, and derives the attempt's turn count, stop reason, test result and commit itself, from the tree, TEST_RESULTS.md and the agent's own transcript; the spawn request that started the agent carried only the parameters the Agent tool accepts (the agent type, the model, the prompt and a description) and nothing that chooses how the spawn runs
**so that** the orchestrator never reads a transcript into its own context and never relays a fact it cannot observe

### REQ-14: Nothing is gated while the agent may still be editing

**When** `record` is called for an agent whose end the driver cannot yet see
**the system** refuses with exit 4, gates nothing, commits nothing and leaves the request pending
**so that** no commit ever captures a tree an agent is still editing

### REQ-15: The gate reads ground truth only

**When** the driver gates a recorded attempt
**the system** runs the step's declared `Check:` command itself and compares its result with the declared expectations, including the due acceptance pending count; runs the step's derived test scope; and, for a step tagged `mutation: on`, requires a usable `Mutation:` reading. A step with no declared check is gated on its declared files having changed and its derived tests passing. The relayed marker and the WIP.md checkbox are recorded but never decide the gate
**so that** a step is verified by evidence, never by an agent's claim

### REQ-16: A failed gate commits nothing

**When** an attempt fails the gate, whatever marker it returned
**the system** creates no commit, records the attempt as failed together with what stopped it, and leaves every file outside the step's declared files untouched
**so that** unverified work never enters history, and the next attempt or the human sees why the attempt failed

### REQ-17: The derived test scope reports no false red

**When** the driver runs a step's derived test scope and the selected tests span test packages that one test process cannot collect together
**the system** reports green whenever the CI-shaped run (`uv run pytest -q -p no:cacheprovider`) passes on the same tree, and red whenever a selected test fails
**so that** a red gate always means a real failure, never a collection artefact

### REQ-18: The gate and the reconciler agree

**When** `record` has gated an attempt
**the system** leaves the tree, TEST_RESULTS.md and the ledger in a state where the reconciler's verdict for that step agrees with the gate, the verdict's evidence shows the result came from the driver's own run rather than from the agent's report, and the reconciler itself still runs no declared command
**so that** the ledger, the reconciler and every later recovery reader see the same truth the gate acted on

### REQ-19: Each return's cost and stop reason are derived and recorded

**When** `record` records a return
**the system** records the attempt's turn count (the distinct API requests in the agent's own transcript) against the agent's declared `maxTurns`, and a stop reason that tells apart a completed return, the turn cap reached, `[BLOCKED]`, `[CONFLICT]`, `[PARTIAL]` and no marker; when the transcript cannot be read it records the count as unknown and says so instead of guessing
**so that** what stopped each attempt is a recorded fact, and per-attempt cost is observed in every pipeline

### REQ-20: The driver is the one committer, by explicit path

**When** an attempt verifies
**the system** creates exactly one commit that stages, by explicit path, only the step's declared files and the step's own unit-test files, never an outer-loop acceptance test and never through a stage-everything form; unrelated staged, unstaged and untracked files survive byte-identical and outside the commit; an edit outside the declared files is left uncommitted and reported; the commit message names the driver and the step and carries no AI-authorship line
**so that** each verified step is one reviewable commit and nothing else in the tree is swept into it

### REQ-21: One ledger record per return

**When** `record` processes a return for the first time, whether it verified, failed or reached the cap
**the system** appends exactly one record to ITERATION_LEDGER.jsonl, with no commit when nothing was committed, and the ledger's own reader (`python3 scripts/iteration_ledger.py`) reports no findings; repeating a `record` that was already applied appends nothing, commits nothing and reports itself as a replay
**so that** the ledger holds one honest line per agent return, and a retried call cannot double-count

### REQ-22: A stale request is refused

**When** `record` names a request that is neither pending nor already recorded
**the system** exits 4, changes nothing, and names the pending request or says that none is pending
**so that** a confused relay is caught before it touches any state

### REQ-23: Every outcome is one envelope and one of five exit codes

**When** `next` or `record` runs, for any outcome including errors
**the system** prints exactly one JSON envelope on stdout and exits 0 when a request is pending (`spawn`) or every step is complete (`complete`), 2 when a human must decide (`needs-human`), 3 when the iteration budget is used up (`budget-exhausted`), 4 on a caller error and 1 on a driver failure (`error`); no other exit code is ever returned, a usage error exits 4, and every envelope except a usage or missing-document error reports the iterations used and the budget
**so that** the orchestrator acts on the exit code alone and always parses exactly one document

### REQ-24: Completion hands over to the pre-verification checkpoint

**When** every plan step reads `verified-complete`
**the system** returns outcome `complete` with exit 0 and emits no further request
**so that** the pre-verification checkpoint follows and the verifier runs as before

### REQ-25: Stops that need a human

**When** an attempt returns `[BLOCKED]` or `[CONFLICT]`, a step reads `attempts-exhausted`, the reconciler routes a step to a human, WIP.md carries an `Attempts:` line that names no step, or a light review asks for revision a second time
**the system** stops with exit 2, naming the step when there is one and the cause, after committing any attempt that verified
**so that** every condition the loop cannot resolve by itself reaches a human with its evidence, and verified work is never lost to a stop

### REQ-26: The iteration budget is derived from the plan and its stop is reachable

**When** the loop runs
**the system** derives the iteration budget from the plan alone (the steps the loop drives times the cap, plus one for each of those steps the light-review trigger marks), never from a hand-set value, and stops with exit 3 when the iterations used reach the budget while a step is still not `verified-complete`; completion takes precedence over a human stop, and a human stop over the budget stop; the budget stop is reachable, so that at least one plan and history make it fire
**so that** a loop that keeps consuming iterations is surfaced for a re-tier and never closes by skipping the verifier

### REQ-27: Every pause leaves a handoff

**When** the loop stops with exit 2 or 3, including after a failed attempt left edits in the tree
**the system** leaves HANDOFF.md in its standard eight-section shape, whose next-action section names the stopped step, the cause, each attempt with what stopped it, and the command that resumes the loop; the step any handoff names as next is the step `next` would select
**so that** a fresh session resumes from files alone, and the handoff and the driver never disagree on what comes next

### REQ-28: Light reviews run inside the loop

**When** a step verifies that the existing light-review trigger marks as risky or that carries `review: force`, and the step does not carry `review: off`
**the system** emits a light-review request for that step before any later step's request; an accept advances the loop, a revise yields a revision request for the same step, a second revise stops for a human (REQ-25), and a review still marked unfinished is never read as an accept
**so that** the bounded light review keeps its place at the step boundary when the driver turns the crank

### REQ-29: The loop's state is readable without changing it

**When** `status` is called
**the system** reports each step's verdict, attempts used and commit, the pending request if any, the iterations used and the budget, and the stop if one holds, as a table or, with `--json`, as one object; it writes no file and exits with the class of the outcome it reports
**so that** a human or the orchestrator can inspect the loop at any time without side effects

### REQ-30: The loop runs with a substitute for the Agent tool

**When** spawn requests are answered by a substitute that is not the Agent tool, such as a test double that edits the tree and returns an agent id and a marker
**the system** behaves identically in selection, prompt, gating, commit, ledger and stops
**so that** other ways of starting an agent, such as a headless session or a workflow script, can be added later without changing the loop's behaviour

### REQ-31: The reconciler's JSON output has one shape

**When** `python3 scripts/reconcile_pipeline_state.py` runs with `--json` on any WIP.md
**the system** prints the verdict array on stdout in every case, reports any `Attempts:` line that names no step on stderr in both output modes, and still exits 2 when such a line exists
**so that** every consumer that parses an array keeps working, whatever WIP.md holds

### REQ-32: A turn-budget reminder reaches the agent before its cap

**When** an agent running as a subagent with a declared `maxTurns` makes a tool call after its distinct API requests have crossed 60 percent, or 80 percent, of that cap
**the system** delivers, as `additionalContext` from a `PreToolUse` hook, one reminder per agent and threshold, stating the turns used of the cap and what to do (at 80 percent: finish the current edit, record results, stop in a committable state); it never fires for the main session or for an agent without a declared cap
**so that** an implementer learns it is near its cap while it can still stop in a committable state

### REQ-33: The reminder never gets in the way

**When** the reminder cannot read its input, the agent's transcript or the agent's declared cap, or fails in any other way
**the system** emits nothing, exits 0 and lets the tool call proceed; the hook is registered in `hooks/hooks.json`, so it runs in every session that loads the plugin
**so that** a defect in the reminder costs at most a missed reminder, never a blocked tool call

### REQ-34: The Ralph-lite recipe is reachable from tier selection

**When** a reader choosing a process for a well-gated, single-behaviour task (make a test file green, a mechanical migration, a lint sweep) walks the tier selection
**the system** names the Ralph-lite recipe, and where it lives, in the process-calibration text that reader follows at task intake (the always-loaded coordination protocol's tier selection, whatever framing the recipe is given there), and every text that enumerates the tiers or their selection order agrees with the framing chosen for the recipe
**so that** the recipe is found at the moment of choice and the tier vocabulary stays consistent

### REQ-35: The recipe is safe to run unattended

**When** a reader opens the Ralph-lite recipe
**the system** states: a scratch worktree; `/goal` run under auto mode or with the check command allow-listed, never under `acceptEdits` alone; the derived test command as the stated check, with its raw result printed every turn, because the goal's evaluator judges only the conversation; a turn clause bounding the run; the "impossible" verdict as the exit that needs a human; and what the recipe is not for (Standard and Full step loops, and work that relies on background agents)
**so that** a goal loop neither stalls at its first permission prompt nor is judged on claims instead of a printed check

### REQ-36: The budget procedure says how loop spawns count

**When** the orchestrator reads the spawn-budget procedure for a pipeline whose implementer steps the driver runs
**the system** states, in one authoritative place, how driver-emitted spawns are budgeted (as iterations, bounded by the plan-derived iteration budget), that quality bounds the loop (cap, then surface; never grind), and that cost is observed and recorded per pipeline, never capped in dollars; every other text that mentions the budget points to that place
**so that** the spawn budget and the attempt cap cannot contradict each other inside the loop

### REQ-37: Pipelines without the driver are unaffected

**When** the reconciler, the ledger reader or the handoff composer reads plans, WIP.md files and ledgers written without the driver
**the system** produces exactly the results it produces today, with no existing fixture rewritten
**so that** the driver is additive, and in-flight and archived pipelines keep their meaning

### REQ-38: Inside the loop the orchestrator only relays

**When** the orchestrator passes the pre-mortem gate of a pipeline whose plan has implementer steps
**the system** gives it a procedure that runs the loop by repeating `next`, executing each request through the Agent tool unchanged and calling `record` after each completion notification, and that forbids it, inside the loop, to compose an implementer prompt, read the rendered prompt, commit, or edit an `Attempts:` line
**so that** between the two checkpoints the orchestrator's role is relay only, and its context stays small by construction

## Traceability Matrix

Rendered from `traceability.yml` at archival: unit tests and acceptance nodes (outer-loop, designed from the extract alone before any production commit) per requirement, with the implementation symbols' files. `Status` is the final verifier's reading.

| REQ | Unit tests | Acceptance nodes | Implementation | Status |
|---|---|---|---|---|
| REQ-01 | 2 test(s) -- `scripts/test_loop_cli_next.py` (test_a_new_request_is_counted_in_the_progress_file_and_its_prompt_written_first, test_the_fixtures_of_an_earlier_pipeline_read_as_a_stop_for_a_human) | 4 test(s) -- `tests/acceptance/test_step_loop_selects_the_next_step.py` (test_a_fresh_plan_starts_with_its_first_step, test_a_step_whose_dependency_is_verified_is_the_next_one, test_a_step_waiting_on_an_unverified_dependency_is_passed_over_for_a_later_one, test_a_parallel_group_never_makes_a_step_wait_for_its_sibling) | 1 file(s) -- `scripts/step_loop.py` | PASS |
| REQ-02 | 2 test(s) -- `scripts/test_loop_cli_next.py` (test_asking_twice_reissues_the_request_and_changes_no_byte, test_a_stop_repeats_byte_for_byte_and_rewrites_the_handoff_only_when_it_changes) | 2 test(s) -- `tests/acceptance/test_step_loop_selects_the_next_step.py` (test_asking_twice_reissues_the_pending_request_and_changes_no_file, test_selection_over_unchanged_inputs_is_the_same_in_a_second_identical_checkout) | 2 file(s) -- `scripts/_step_loop_cli.py`, `scripts/step_loop.py` | PASS |
| REQ-03 | 1 test(s) -- `scripts/test_loop_cli_next.py` (test_a_stop_carries_a_stop_object_naming_the_resume_command_and_the_handoff) | 2 test(s) -- `tests/acceptance/test_step_loop_selects_the_next_step.py` (test_a_dependency_on_a_step_the_plan_lacks_stops_for_a_human_naming_both, test_a_dependency_cycle_stops_for_a_human_naming_each_step_in_it) | 2 file(s) -- `scripts/_step_loop_cli.py`, `scripts/step_loop.py` | PASS |
| REQ-04 | 1 test(s) -- `scripts/test_loop_cli_next.py` (test_status_exits_with_the_class_of_the_stop_it_reports_and_writes_nothing) | 1 test(s) -- `tests/acceptance/test_step_loop_selects_the_next_step.py` (test_a_step_assigned_to_another_agent_is_neither_skipped_nor_read_as_done) | 1 file(s) -- `scripts/step_loop.py` | PASS |
| REQ-05 | 2 test(s) -- `scripts/test_loop_cli_next.py` (test_a_spawn_carries_a_request_and_a_then_and_nothing_of_the_other_outcomes, test_a_script_started_by_explicit_path_reports_the_checkout_form) | 5 test(s) -- `tests/acceptance/test_step_loop_spawn_request.py` (test_the_request_names_its_step_attempt_and_cap_under_a_deterministic_id, test_the_agent_call_is_the_implementer_with_a_short_description, test_the_model_follows_the_step_routing_annotation, test_the_agent_prompt_is_three_lines_opening_with_the_task_slug, test_the_envelope_tells_the_orchestrator_which_record_call_follows) | 2 file(s) -- `scripts/_step_loop_cli.py`, `scripts/step_loop.py` | PASS |
| REQ-06 | 1 test(s) -- `scripts/test_loop_cli_next.py` (test_a_new_request_is_counted_in_the_progress_file_and_its_prompt_written_first) | 6 test(s) -- `tests/acceptance/test_step_loop_spawn_request.py` (test_the_rendered_prompt_holds_its_fixed_parts_in_order, test_the_rendered_prompt_tells_the_agent_to_stop_committable_and_never_commit, test_the_rendered_prompt_binds_the_results_and_progress_files_for_the_step, test_nothing_from_outside_the_step_block_leaks_into_the_prompt, test_the_prompt_carries_no_model_name, test_a_first_attempt_prompt_has_no_earlier_attempts_and_a_second_names_the_first) | 1 file(s) -- `scripts/step_loop.py` | PASS |
| REQ-07 | 1 test(s) -- `scripts/test_loop_cli_next.py` (test_a_reissue_restores_a_prompt_file_that_has_gone) | 3 test(s) -- `tests/acceptance/test_step_loop_spawn_request.py` (test_rendering_the_same_step_and_attempt_again_gives_byte_identical_prompts, test_an_ordinary_prompt_stays_within_the_size_ceiling, test_an_oversized_step_block_is_reported_and_carried_whole_never_truncated) | 1 file(s) -- `scripts/step_loop.py` | PASS |
| REQ-08 | 2 test(s) -- `scripts/test_loop_cli_next.py` (test_a_new_request_is_counted_in_the_progress_file_and_its_prompt_written_first, test_a_fresh_series_after_a_plan_revision_restarts_its_count_at_one) | 2 test(s) -- `tests/acceptance/test_step_loop_attempt_cap.py` (test_the_attempt_is_counted_in_wip_before_its_request_is_printed, test_a_second_attempt_is_counted_as_two_before_its_request_is_printed) | 1 file(s) -- `scripts/step_loop.py` | PASS |
| REQ-09 | 4 test(s) -- `scripts/test_loop_cli_record_caps.py` (test_the_replan_text_is_one_line_naming_each_attempt_its_stop_evidence_and_commit, test_an_exhausted_series_is_written_as_a_replan_on_the_attempts_line, test_the_same_series_settles_to_the_same_line_and_writes_nothing_the_second_time, test_a_series_that_is_not_exhausted_leaves_the_line_alone) | 2 test(s) -- `tests/acceptance/test_step_loop_attempt_cap.py` (test_a_capped_attempt_still_running_reads_as_in_flight_not_exhausted, test_a_step_exhausted_in_a_wip_written_without_the_loop_stops_the_loop) | 2 file(s) -- `scripts/_step_loop_record.py`, `scripts/_step_loop_settle.py` | PASS |
| REQ-10 | 1 test(s) -- `scripts/test_loop_cli_record_caps.py` (test_a_replay_of_the_capped_attempt_settles_the_replan_and_the_stop_carries_it) | 4 test(s) -- `tests/acceptance/test_step_loop_attempt_cap.py` (test_a_complete_marker_whose_check_fails_on_the_capped_attempt_stops_for_a_human, test_the_replan_request_comes_with_what_stopped_each_attempt, test_an_exhausted_step_reads_as_attempts_exhausted_to_the_reconciler, test_no_request_beyond_the_cap_is_ever_emitted_however_often_next_is_asked) | 1 file(s) -- `scripts/_step_loop_settle.py` | PASS |
| REQ-11 | (none) | 1 test(s) -- `tests/acceptance/test_step_loop_attempt_cap.py` (test_a_plan_revision_reopens_an_exhausted_step_with_a_fresh_attempt_series) | 1 file(s) -- `scripts/_step_loop_settle.py` | PASS |
| REQ-12 | 4 test(s) -- `scripts/test_loop_cli_record_caps.py` (test_a_withdrawn_request_restores_the_count_the_write_ahead_replaced, test_a_withdrawn_first_request_removes_the_line_and_the_prompt_it_wrote, test_a_withdrawn_second_request_is_issued_again_byte_for_byte, test_the_withdrawal_envelope_is_the_next_action_with_a_recorded_object_and_no_ledger) | 2 test(s) -- `tests/acceptance/test_step_loop_attempt_cap.py` (test_a_spawn_that_never_started_costs_no_attempt_and_no_ledger_record, test_reporting_not_started_for_an_agent_that_did_start_is_refused_and_changes_nothing) | 2 file(s) -- `scripts/_step_loop_record.py`, `scripts/_step_loop_settle.py` | PASS |
| REQ-13 | 5 test(s) -- `scripts/test_loop_cli_record_gate.py` (test_a_record_the_transcript_does_not_support_is_refused_with_its_code); `tests/acceptance/test_step_loop_driver_binding.py` (test_the_sandbox_config_directory_and_a_zero_end_wait_reach_the_commands_environment, test_a_transcript_lives_under_the_config_directory_at_the_subagents_layout, test_a_transcript_opens_with_the_user_line_that_carries_the_requests_prompt, test_the_double_for_the_agent_tool_returns_the_id_of_the_transcript_it_leaves) | 2 test(s) -- `tests/acceptance/test_step_loop_records_each_return.py` (test_record_derives_the_turns_from_the_agents_own_transcript_against_its_cap); `tests/acceptance/test_step_loop_spawn_request.py` (test_the_agent_call_carries_only_the_agent_tools_parameters_and_no_background_flag) | 2 file(s) -- `scripts/_step_loop_record.py`, `scripts/step_loop.py` | PASS |
| REQ-14 | 6 test(s) -- `scripts/test_loop_cli_record_gate.py` (test_a_record_the_transcript_does_not_support_is_refused_with_its_code, test_the_wait_polls_until_the_transcript_shows_the_end, test_the_bounded_wait_comes_from_the_environment, test_an_unreadable_transcript_still_names_its_request_and_its_end_unless_cut_off); `tests/acceptance/test_step_loop_driver_binding.py` (test_a_running_transcript_ends_on_a_tool_call_below_the_cap, test_an_ended_transcript_holds_the_requested_requests_and_closes_on_text_only) | 1 test(s) -- `tests/acceptance/test_step_loop_records_each_return.py` (test_a_record_before_the_agent_has_ended_is_refused_and_changes_nothing) | 1 file(s) -- `scripts/_step_loop_record.py` | PASS |
| REQ-15 | 3 test(s) -- `scripts/test_loop_cli_record_gate.py` (test_a_derived_scope_of_several_runs_merges_into_one, test_one_run_that_showed_no_summary_makes_the_merged_scope_no_run, test_a_red_run_fails_the_attempt_whatever_the_check_judged) | 6 test(s) -- `tests/acceptance/test_step_loop_gate.py` (test_an_attempt_whose_check_passes_verifies_even_when_the_agent_recorded_no_result, test_an_attempt_with_no_marker_whose_check_passes_verifies_and_is_committed, test_a_passing_check_does_not_verify_a_step_whose_derived_tests_fail, test_a_step_with_no_declared_check_verifies_on_its_changed_files_and_green_tests, test_a_step_with_no_declared_check_and_no_changed_files_does_not_verify, test_the_loop_runs_the_declared_check_and_the_reconciler_never_does) | 1 file(s) -- `scripts/_step_loop_record_gate.py` | PASS |
| REQ-16 | 2 test(s) -- `scripts/test_loop_cli_record_gate.py` (test_a_refused_commit_ends_the_block_on_a_no_result_line, test_a_red_run_fails_the_attempt_whatever_the_check_judged) | 3 test(s) -- `tests/acceptance/test_step_loop_gate.py` (test_a_complete_marker_whose_check_fails_is_a_failed_attempt_and_commits_nothing, test_a_failed_gate_leaves_every_file_outside_the_declared_files_as_it_was, test_a_verified_attempt_is_the_only_new_commit_after_a_failed_one) | 2 file(s) -- `scripts/_step_loop_record.py`, `scripts/_step_loop_record_gate.py` | PASS |
| REQ-17 | 8 test(s) -- `scripts/test_resolve_scope_invocations.py` (test_a_package_and_the_namespace_sharing_a_name_split_into_collectable_invocations, test_the_unsplit_command_would_not_collect, test_two_plain_modules_with_one_basename_split, test_every_selected_test_lands_in_exactly_one_invocation_in_selection_order, test_a_selection_without_a_clash_is_the_single_invocation_it_always_was, test_a_package_inside_the_namespace_directory_does_not_clash_with_its_siblings, test_a_widened_pocket_still_runs_its_whole_suite_as_one_invocation, test_import_claims_name_what_pytest_would_import) | 1 test(s) -- `tests/acceptance/test_step_loop_gate.py` (test_a_passing_check_does_not_verify_a_step_whose_derived_tests_fail) | 1 file(s) -- `scripts/resolve_test_scope.py` | PASS |
| REQ-18 | 2 test(s) -- `scripts/test_loop_cli_record_gate.py` (test_a_written_gate_block_is_read_back_whole_for_a_replay, test_no_gate_block_for_the_request_means_the_gate_runs) | 2 test(s) -- `tests/acceptance/test_step_loop_gate.py` (test_after_a_verified_attempt_the_reconciler_agrees_the_step_is_verified, test_after_a_failed_attempt_the_reconciler_does_not_read_the_step_as_verified) | 1 file(s) -- `scripts/_step_loop_record_gate.py` | PASS |
| REQ-19 | 5 test(s) -- `scripts/test_loop_cli_record_gate.py` (test_the_implementer_definition_declares_the_turn_cap_and_an_unknown_agent_none, test_a_readable_or_missing_transcript_passes_through_unchanged); `tests/acceptance/test_step_loop_driver_binding.py` (test_an_ended_transcript_holds_the_requested_requests_and_closes_on_text_only, test_each_request_but_the_last_is_a_text_then_a_tool_call_sharing_one_request_id, test_an_unreadable_transcript_has_a_non_json_line_before_its_ended_final_entry) | 4 test(s) -- `tests/acceptance/test_step_loop_records_each_return.py` (test_the_stop_reason_tells_each_kind_of_return_apart, test_an_agent_that_used_its_whole_turn_cap_without_a_marker_stopped_at_the_cap, test_an_unreadable_transcript_records_the_turns_as_unknown_and_says_so, test_a_relayed_marker_the_transcript_contradicts_is_flagged) | 1 file(s) -- `scripts/_step_loop_record.py` | PASS |
| REQ-20 | 4 test(s) -- `scripts/test_loop_cli_record_gate.py` (test_each_commit_outcome_says_what_holds_the_work_and_whether_to_stop, test_a_disturbed_tree_saves_the_earlier_state_beside_the_task, test_a_head_commit_naming_the_request_is_reused, test_a_left_index_lock_is_named_in_the_stop_text) | 5 test(s) -- `tests/acceptance/test_step_loop_commits_by_explicit_path.py` (test_a_verified_step_yields_exactly_one_commit_holding_only_its_files, test_unrelated_staged_unstaged_and_untracked_files_survive_outside_the_commit, test_an_outer_loop_test_is_never_committed_even_when_the_step_declares_it, test_an_edit_outside_the_declared_files_stays_uncommitted_and_is_reported, test_the_commit_message_names_the_loop_and_the_step_and_no_ai_author) | 2 file(s) -- `scripts/_step_loop_record.py`, `scripts/_step_loop_settle.py` | PASS |
| REQ-21 | 1 test(s) -- `scripts/test_loop_cli_record_gate.py` (test_the_step_line_is_ticked_once_and_no_other) | 2 test(s) -- `tests/acceptance/test_step_loop_records_each_return.py` (test_each_return_adds_exactly_one_ledger_record_and_the_ledger_reads_clean, test_a_replayed_record_adds_nothing_and_says_it_is_a_replay) | 2 file(s) -- `scripts/_step_loop_record.py`, `scripts/_step_loop_settle.py` | PASS |
| REQ-22 | 2 test(s) -- `scripts/test_loop_cli_next.py` (test_a_record_when_nothing_is_pending_is_refused_saying_none_is_pending, test_a_record_for_another_request_is_refused_naming_the_pending_one) | 2 test(s) -- `tests/acceptance/test_step_loop_records_each_return.py` (test_a_record_naming_a_request_that_is_not_pending_is_refused_naming_the_pending_one, test_a_record_when_nothing_is_pending_is_refused_saying_none_is_pending) | 1 file(s) -- `scripts/step_loop.py` | PASS |
| REQ-23 | (none) | 4 test(s) -- `tests/acceptance/test_step_loop_stops.py` (test_every_envelope_but_a_usage_error_reports_iterations_within_the_budget, test_a_usage_error_exits_four_with_one_usage_envelope, test_there_is_no_verb_beyond_next_record_and_status, test_a_task_without_a_plan_is_a_caller_error_naming_the_missing_document) | 1 file(s) -- `scripts/_step_loop_files.py` | PASS |
| REQ-24 | 3 test(s) -- `scripts/test_loop_state_review.py` (test_complete_outranks_a_human_stop, test_complete_outranks_the_budget_stop, test_a_plan_with_no_steps_is_complete) | 2 test(s) -- `tests/acceptance/test_step_loop_selects_the_next_step.py` (test_a_plan_whose_steps_are_all_verified_is_complete_with_no_request); `tests/e2e/test_step_loop_drives_a_plan.py` (test_a_dependent_two_step_plan_runs_to_completion_through_the_relay) | 1 file(s) -- `scripts/_step_loop_action.py` | PASS |
| REQ-25 | (none) | 3 test(s) -- `tests/acceptance/test_step_loop_stops.py` (test_a_blocked_or_conflicted_return_stops_for_a_human_naming_the_step, test_a_blocked_return_whose_work_verified_is_committed_before_the_stop, test_an_attempts_line_naming_no_step_stops_for_a_human) | 1 file(s) -- `scripts/_step_loop_settle.py` | PASS |
| REQ-26 | (none) | 4 test(s) -- `tests/acceptance/test_step_loop_stops.py` (test_the_iteration_budget_is_the_plans_steps_times_the_attempt_cap, test_a_human_stop_takes_precedence_over_a_used_up_budget, test_the_budget_stop_is_reachable_and_exits_three, test_completion_takes_precedence_over_a_human_stop) | 1 file(s) -- `scripts/_step_loop_record_gate.py` | PASS |
| REQ-27 | 6 test(s) -- `scripts/test_handoff_base_ref.py` (test_a_local_default_branch_ahead_of_its_remote_yields_the_local_fork_point, test_a_remote_default_branch_ahead_of_the_local_one_yields_the_remote_fork_point, test_the_command_line_hands_its_base_ref_to_the_writer, test_a_base_ref_given_on_the_command_line_names_the_header_fork_point); `scripts/test_loop_cli_next.py` (test_a_stop_composes_its_handoff_against_the_tasks_base_ref); `scripts/test_loop_io_files.py` (test_the_handoff_carries_the_base_ref_it_is_given) | 4 test(s) -- `tests/acceptance/test_step_loop_stops.py` (test_an_exhausted_step_leaves_a_handoff_whose_next_action_carries_the_stop, test_the_stop_names_the_command_that_resumes_the_loop, test_a_budget_stop_also_leaves_a_handoff_with_the_resume_command); `tests/e2e/test_step_loop_drives_a_plan.py` (test_an_exhausted_step_pauses_the_loop_keeping_verified_work_and_a_revision_resumes_it) | 1 file(s) -- `scripts/_step_loop_files.py` | PASS |
| REQ-28 | 7 test(s) -- `scripts/test_loop_state_review.py` (test_the_review_state_reads_the_trigger_the_returns_and_the_file, test_the_plan_local_trigger_marks_tier_h_and_forced_steps_unless_off, test_a_verified_step_is_done_only_once_its_review_is_satisfied, test_a_review_file_left_by_an_earlier_series_cannot_accept_a_new_one); `tests/acceptance/test_step_loop_driver_binding.py` (test_an_accepting_reviewer_leaves_an_accept_verdict_and_an_ended_transcript, test_a_revising_reviewer_leaves_its_findings_beneath_the_verdict, test_an_unfinished_review_leaves_a_verdict_still_marked_partial) | 6 test(s) -- `tests/acceptance/test_step_loop_light_review.py` (test_a_verified_step_marked_for_review_yields_a_review_before_the_next_step, test_a_verified_step_not_marked_for_review_moves_straight_to_the_next_step, test_an_accepted_review_advances_to_the_next_step, test_a_revise_verdict_yields_a_revision_request_for_the_same_step, test_a_second_revise_verdict_stops_for_a_human, test_an_unfinished_review_is_never_read_as_an_accept) | 2 file(s) -- `scripts/_step_loop_review.py`, `scripts/_step_loop_state.py` | DEFERRED -- in-loop light reviews (step 21) moved to the follow-up pipeline; scenarios red by design |
| REQ-29 | 2 test(s) -- `scripts/test_loop_cli_next.py` (test_status_writes_nothing_and_reports_the_pending_request, test_status_without_json_prints_a_table_and_ends_on_the_next_action) | 2 test(s) -- `tests/acceptance/test_step_loop_selects_the_next_step.py` (test_status_reports_the_pending_request_and_each_step_without_writing, test_status_without_json_prints_a_readable_table_naming_each_step) | 2 file(s) -- `scripts/_step_loop_cli.py`, `scripts/step_loop.py` | PASS |
| REQ-30 | 1 test(s) -- `scripts/test_loop_cli_next.py` (test_drive_hands_each_request_to_the_spawner_and_stops_once_one_never_started) | 1 test(s) -- `tests/e2e/test_step_loop_drives_a_plan.py` (test_the_ledger_holds_one_record_per_return_with_each_verified_commit) | 1 file(s) -- `scripts/step_loop.py` | PASS |
| REQ-31 | 4 test(s) -- `scripts/test_reconciler_json_shape.py` (test_json_stdout_is_the_verdict_array_when_a_line_names_no_step, test_every_unnamed_line_is_reported_on_stderr_in_either_output_mode, test_the_human_report_is_the_verdict_lines_alone_on_stdout, test_json_stdout_is_the_array_and_stderr_is_silent_when_every_line_names_its_step) | 3 test(s) -- `tests/acceptance/test_reconciler_json_has_one_shape.py` (test_json_output_is_the_verdict_array_even_with_an_unnamed_attempts_line, test_an_unnamed_attempts_line_is_reported_on_stderr_and_exits_two_in_json_mode, test_json_output_is_the_verdict_array_when_every_attempts_line_names_its_step) | 1 file(s) -- `scripts/reconcile_pipeline_state.py` | PASS |
| REQ-32 | 1 test(s) -- `tests/acceptance/test_turn_budget_driver_binding.py` (test_the_reminder_resolves_to_the_plugins_turn_budget_hook_script) | 8 test(s) -- `tests/acceptance/test_turn_budget_reminder.py` (test_an_agent_below_sixty_percent_of_its_cap_gets_no_reminder, test_crossing_sixty_percent_injects_one_reminder_stating_turns_used_of_the_cap, test_the_sixty_percent_reminder_fires_once_per_agent, test_crossing_eighty_percent_tells_the_agent_to_stop_in_a_committable_state, test_the_eighty_percent_reminder_fires_once_per_agent, test_each_agent_gets_its_own_reminder, test_the_main_session_never_gets_a_reminder, test_an_agent_with_no_declared_cap_never_gets_a_reminder) | (none in this pipeline) | DEFERRED -- the turn-budget reminder hook (step 22) moved to the follow-up pipeline |
| REQ-33 | 1 test(s) -- `tests/acceptance/test_turn_budget_driver_binding.py` (test_the_reminder_resolves_to_the_plugins_turn_budget_hook_script) | 4 test(s) -- `tests/acceptance/test_turn_budget_reminder.py` (test_an_unparseable_payload_fails_open_silently, test_a_missing_agent_transcript_fails_open_silently, test_an_agent_whose_definition_cannot_be_read_fails_open_silently, test_the_plugin_registers_the_reminder_for_every_tool_call) | (none in this pipeline) | DEFERRED -- the turn-budget reminder hook (step 22) moved to the follow-up pipeline |
| REQ-34 | (none) | 1 test(s) -- `tests/acceptance/test_ralph_lite_recipe.py` (test_the_tier_selection_text_names_the_recipe) | (none in this pipeline) | DEFERRED -- the Ralph-lite recipe (step 24) moved to the follow-up pipeline |
| REQ-35 | (none) | 2 test(s) -- `tests/acceptance/test_ralph_lite_recipe.py` (test_the_recipe_states_what_makes_an_unattended_goal_loop_safe, test_the_recipe_bounds_the_run_with_a_turn_clause) | (none in this pipeline) | DEFERRED -- the Ralph-lite recipe (step 24) moved to the follow-up pipeline |
| REQ-36 | (none) | (none) | (none in this pipeline) | DEFERRED -- the budget procedure prose and the spawn counter (steps 25, 28) moved to the follow-up pipeline |
| REQ-37 | 4 test(s) -- `scripts/test_compose_handoff.py (62 existing tests, unedited)` ((module)); `scripts/test_handoff_next_action.py` (test_without_a_next_action_section_two_is_the_derived_one, test_the_private_reader_name_is_the_moved_reader, test_the_handoff_error_the_composer_exports_is_the_one_the_readers_raise) | 5 test(s) -- `scripts/test_compose_handoff.py` ((module)); `tests/acceptance/test_iteration_ledger.py` ((module)); `tests/acceptance/test_legacy_pipelines_reconcile_as_before.py` ((module)); `tests/acceptance/test_step_attempt_accounting.py` ((module)); `tests/acceptance/test_step_completion_checks.py` ((module)) | 2 file(s) -- `scripts/_handoff_inputs.py`, `scripts/compose_handoff.py` | PASS |
| REQ-38 | (none) | (none) | (none in this pipeline) | DEFERRED -- the /step-loop command text (step 23) moved to the follow-up pipeline |

**Coverage**: 36 of 38 requirements carry unit or acceptance evidence; the rest are judged by the verifier from the records named in their Status cell.

## Key Decisions

Six ADRs landed (two architectural, four behavioral), one user decision at intake and the orchestrator's split decision at close shaped the result (context copied from `SYSTEMS_PLAN.md`, the ADR records and the pipeline's `LEARNINGS.md § Decisions Made`).

**[main-agent] User decisions at intake, 2026-10-03/04 -- driver, not gates**: the gap the spike found is the orchestrator as the party turning the crank, so the loop's two durable ideas (state on disk, one verified unit per fresh context) become a bounded driver and the gates accommodate it; the driver is code, not an agent; a Python driver with a pluggable spawner, the Agent tool first (`claude -p` and the Workflow tool designed only); the driver commits per step by pathspec; the budget is quality-first (two fresh attempts per step, the iteration budget derived from the plan, cost observed and not capped); the max-turns problem is in scope so no agent's feedback is cut at the end and repaired by archaeology.

**[systems-architect] D1 -- A deterministic step-loop driver owns the crank; the orchestrator relays through a spawner seam (`dec-432`, architectural)**: `scripts/step_loop.py` (`next`, `record`, `status`) over pure state, render and gate modules, an I/O adapter, a plan-step module and the shared transcript reader; selection, prompt composition, write-ahead attempts, ground-truth gating, pathspec commits, ledger appends and the attempt cap move from the orchestrator's prose procedure into the driver; the v1 spawner is the orchestrator's Agent tool, relaying three values per request after the completion notification. Rejected: an agent as the driver (another context to truncate), gates alone (the cost was the crank, not the gates).

**[systems-architect] D2 -- A synchronous PreToolUse hook reminds a capped subagent at 60 and 80 percent of its declared maxTurns (`dec-433`, architectural)**: `hooks/remind_turn_budget.py` counts distinct requests in the agent's own transcript through the shared reader and emits one `additionalContext` line per agent and threshold, silent for the main session, uncapped agents and every error. The hook's step and its live probe moved to the follow-up pipeline; the design and the latency bounds (0.2 s and 0.3 s) are carried there.

**[systems-architect] D3 -- Driver-emitted spawns are budgeted as iterations against a plan-derived budget (`dec-429`, behavioral)**: inside the loop an iteration is one driver request that started an agent; the budget is the attempt cap per driven step plus one per review-triggered step (amended by SQ-03 so planned reviews are not charged against an allowance that never included them); `spawn_count.py` reports those agents apart from charged spawns (follow-up); quality bounds the loop, cost is observed.

**[systems-architect] D4 -- Attempt evidence lives in the WIP line and the ledger (`dec-428`, behavioral)**: the `Attempts:` grammar gains an optional `request=<id>` token written ahead by the driver; an outstanding attempt reads `in-flight`, never `attempts-exhausted`; the ledger record gains `request`, `step_digest`, `turns` and `max_turns` plus the stop reasons `partial` and `conflict`; a plan revision opens a new series.

**[systems-architect] D5 -- The light-review trigger is plan-local (`dec-430`, behavioral)**: the planner turns the brief's uncertainty flags and one-way doors into `review: force` at planning time, so the driver reads only `review:` and `tier: H` and the trigger is deterministic, visible at the pre-mortem gate and derivable from the plan alone. The prose at the four trigger sites moved to the follow-up pipeline.

**[systems-architect] D6 -- Ralph-lite is an execution mode, not a tier (`dec-431`, behavioral)**: the `/goal`-based recipe for one well-gated single-behaviour task is reachable through one clause in the Lightweight tier row and lives in `tier-templates.md`; recommended over a sixth tier row and accepted at the architecture checkpoint by the orchestrator under the user's standing self-gate, the user keeping the override before merge. The recipe step moved to the follow-up pipeline.

**[orchestrator] Split decision at close, 2026-10-05**: implementer steps ran at about twice their estimate, so the plan's split rule fired at a clean seam. This pipeline closed after band A (the driver's core, bindings and `record`), the integration run and the final measurement; the live dogfood (band B) and the prose, hook and command steps moved to a follow-up pipeline started from this branch once merged, the spawn counter step first. The dogfood criterion AC-13 was met by the replay the specification allows (two consecutive steps of the harvested step-schema pipeline driven in a scratch clone through a substitute spawner), recorded as a replay and never as the live result. Ratified by the user on 2026-10-07, which makes the verifier's conditional verdict unconditional.

**Spec amendments**: SQ-03 (the iteration budget counts planned reviews), SQ-04 (a non-driven step with no `Files:` and no `Check:` is done when its WIP entry claims it; without it every normal plan would stop at its opening and closing orchestrator steps), SQ-05 (the reopen scenario runs on a two-step plan so it no longer contradicts the budget stop), and the close amendment that moved the two hook-latency footprint criteria to Footprints Not Measured with the deferred hook.

**Declared limits** (from `SYSTEMS_PLAN.md`, the step learnings and the light reviews): a driver started from a different session than the one that spawned the agent sees no `agent_stop` row (the other two end-evidence sources still hold); SIGTERM is not mapped in the runner (a driver cut off by the Bash tool's ceiling leaves the runner alive; SIGINT kills the process group); a mode-only change on an already-edited file shares its blob id, so a hook's `chmod` there escapes the tree snapshot; the handoff composer resolves its fork point against `origin/<default>` before the local default branch, so a local main ahead of origin yields a wrong base until the composer takes `--base-ref`; the reconciler attributes a non-`## Step N` heading's `Result:` line in `TEST_RESULTS.md` to the preceding step; the context-baseline instrument cannot read worktree sessions, so the implementer cap-out and orchestrator-context footprints are unchanged by construction and are judged over this and the next two pipelines; the harness places a subagent transcript at `<session>/subagents/agent-<id>.jsonl`, pinned by the bindings and surfaced loudly (never silently) by the `agent-running` refusal if a later harness moves it.

**Measured at close** (`MEASUREMENTS.md`, final rows at `9b650d6e`): 0 prompt files at fail severity; the planner prompt at 399 lines; 16726 always-loaded tokens (limit 16826); 9144 listing tokens (ceiling 9243); the narrow test selection median 46.0 files, identical with the resolver as it stood at the base; implementer cap-out rate 0.15 and orchestrator context at verifier spawn 429121 tokens median over the primary checkout's record, both unchanged by construction; 0 driver iterations against a budget of 0 and 0 absorbed steps in the driver's empty span. Read by hand for the calibration row: this orchestrator's context at the verifier spawn was about 375k tokens; no implementer in the ledger stopped at the turn cap, two cap-outs were recovered by the orchestrator.

**Follow-up.** The follow-up pipeline (steps 21–28 and 30 of this plan, re-declared against its own base): in-loop light reviews, the turn-budget reminder hook and its live probe, `/step-loop`, the Ralph-lite recipe, the spawn counter's iteration reporting, the architecture documents (`docs/architecture.md`, `scripts/CLAUDE.md`, `DESIGN.md § 3b.19` to Implemented), the plan-local review-trigger prose and the loop pointers; its band B is the live dogfood that closes the open risk on transcript layout and flush timing. Debt handed on: the composer's `--base-ref`, the reconciler's heading attribution, the SIGTERM mapping, the step-schema items td-338 and td-343.
