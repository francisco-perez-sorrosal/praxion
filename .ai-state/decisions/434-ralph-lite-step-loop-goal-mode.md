---
id: dec-434
draft_id: dec-draft-1c61d1e2
title: Ralph-lite is the step-loop driver's goal mode — a one-step goal plan driven by a fresh process per iteration, entered through a skill, bounded by an iteration budget and a two-iteration stall cap
status: accepted
category: architectural
date: 2026-10-08
summary: The Ralph-lite loop for one well-gated single-behaviour task is the step-loop driver running a one-step goal plan — a `goal` verb scaffolds the plan (Files, protected paths as Read-only, the Check, an Iterations budget, a progress record in WIP.md), a `run` verb loops next, spawn, record with a new `claude -p` spawner module (dec-432's v2) so every iteration is a fresh process, the gate excludes the goal's own targets as pending and requires monotone counts, a progressing green iteration is committed by pathspec, two consecutive non-progressing iterations stop for a human, the Iterations field is the loop's budget; the entry is a user- and model-invocable skill, never a command; the single-session `/goal` form is a one-line no-artifact fallback. Replaces the `/goal` prose recipe of dec-431; keeps the execution-mode placement of dec-262.
tags: [ralph-lite, step-loop, goal-mode, spawner, claude-p, fresh-context, lightweight, execution-mode, skill]
made_by: agent
agent_type: orchestrator
branch: main
pipeline_tier: spike
affected_files:
  - scripts/step_loop.py
  - scripts/_step_loop_state.py
  - scripts/_step_loop_action.py
  - scripts/_step_loop_record.py
  - scripts/_step_loop_files.py
  - scripts/_step_loop_render.py
  - scripts/_plan_steps.py
  - scripts/_loop_fields.py
  - scripts/_step_verdict.py
  - scripts/iteration_ledger.py
  - hooks/_agent_transcript.py
  - skills/software-planning/references/tier-templates.md
  - rules/swe/swe-agent-coordination-protocol.md
  - .ai-state/specs/SPEC_step-loop-driver_2026-10-05.md
affected_reqs: [REQ-34, REQ-35]
supersedes: dec-431
supersedes_in_part: [dec-427]
re_affirms: [dec-429, dec-432, dec-262]
dissent: []
---

## Context

`dec-431` placed Ralph-lite as an execution mode named in the Lightweight tier row and specified it as a prose recipe over the native `/goal` loop. The user confirmed the placement on 2026-10-07 on the condition that the recipe carry Ralph's two durable ideas, then asked for a reconsideration with research. A spike (`ralph-lite-spike`, two lens-independent researchers and live probes on Claude Code 2.1.290) found that the `/goal` form cannot meet the condition: `claude -p "/goal …"` runs the whole loop in one session with auto-compaction, its evaluator judges printed output and runs nothing, and its turn clause is judged by a model rather than enforced. A standalone shell loop around `claude -p` would meet Ralph's essence but add a second crank beside the step-loop driver. The driver, meanwhile, already is a fresh-context, state-on-disk crank with a spawner seam built for a headless process worker (`dec-432`, v2 designed and not built), a ground-truth gate, pathspec commits, a ledger and a handoff at every stop. What it lacks is a plan shape for a goal and the spawner.

Live facts the decision rests on (2026-10-07, 2.1.290, raw docs plus probes): a nested `claude -p` run starts from inside a session; its `--output-format json` result carries `session_id`, `num_turns`, `is_error`, `subtype`, `terminal_reason`, `total_cost_usd`, `permission_denials` and the final `result` text; the session transcript lands at `~/.claude/projects/<cwd-slug>/<session_id>.jsonl` with the prompt as its first user text and a `requestId` on every assistant record; an unpinned `-p` run's starting permission mode depends on the environment; `acceptEdits` alone denies the test command; deny rules hold in every mode while the harness's protected paths cover neither tests nor `CLAUDE.md` nor rules; a fresh process pays the always-loaded prefix each time (29k to 54k tokens measured). Custom slash commands "have been merged into skills" and the vendor's guidance is to prefer a skill for new work.

## Decision

Ralph-lite is **the step-loop driver running a one-step goal plan through a fresh process per iteration**, entered through a skill.

1. **The goal plan.** A `goal` verb (`step_loop.py goal <slug> --goal … --check … --expects … --paths … --protect … --iterations <n>`) scaffolds `.ai-work/<slug>/`: an `IMPLEMENTATION_PLAN.md` with one implementer step whose `Files:` are the paths in scope, whose `Read-only:` names the protected paths (outer-loop tests first), whose `Check:` is the goal's command and expectation, and which carries a new `Iterations:` field; a `WIP.md` with the step and a `## Progress record` the worker appends one line to per iteration; a `TASK_BRIEF.md` with the goal as the one Key Signal. Nothing an iteration needs lives anywhere but these files, the rendered prompt, the snapshot patches of failed iterations and git.
2. **The iteration.** `next` renders the goal prompt (the goal, the check and its current reading, the progress record, the paths, the protected paths, the finish ordering, the request id). The worker is one fresh context: in the terminal form a `claude -p` process started by a new spawner module behind the existing `Spawner` seam — `--model` by routing, `--max-turns` and `--max-budget-usd` as per-iteration fuses, `--permission-mode dontAsk --permission-prompts none`, an allow list naming the check and the resolver, `--output-format json` — whose end is the process result, whose turns and cost are the result's fields, whose marker is parsed from the result text, and whose transcript the shared reader finds through a second lookup arm for top-level sessions; in the in-session form a fresh subagent through the orchestrator's relay, as built. `record` gates on ground truth: the derived scope over the files the iteration changed must be green excluding the goal's own targets, which the step owns as `Read-only` and which read `pending` while red; the goal check's counts may not regress between committed iterations; a green, progressing iteration with a non-empty diff and a progress line is committed by pathspec with the request trailer; a red, regressing or empty iteration commits nothing and leaves its snapshot patch; a change under a protected path is a disturbed tree and stops the loop; the goal's check decides completion.
3. **The bound.** The `Iterations:` field is the goal plan's derived budget (exit 3 when spent). The attempt cap of two is read in goal mode as two consecutive iterations that committed no unit (exit 2, cause `stalled`); a progressing iteration resets it; for an ordinary step every failed attempt is a non-progressing iteration, so the rule reduces to today's two attempts exactly. A `[BLOCKED]`, `[CONFLICT]` or impossible return stops at once. Every stop composes `HANDOFF.md`. The cap's reading becomes a per-step datum read by the state module, the action layer, the CLI, `record` and the reconciler's verdict policy at once.
4. **The runner.** `step_loop.py run <slug>` loops `next`, spawn, `record` until complete or a stop, printing one line per iteration with its cost. It is the only loop Praxion ships: Standard and Full plans run the same verbs through the orchestrator's relay; a goal plan runs them through the runner.
5. **The entry is a skill.** `skills/ralph-lite/SKILL.md`, invocable by the user as `/praxion:ralph-lite …` and by the orchestrator when a request reads as one well-gated single-behaviour task; its body scaffolds the goal plan and then runs the loop in the terminal form or drives it in-session. No command is added.
6. **Safety.** The scaffold writes `permissions.deny` for the protected paths (`tests/acceptance/**`, `tests/e2e/**`, `CLAUDE.md`, `rules/**`, `agents/**`, `skills/**`, `.claude/**`) into the scratch worktree's local settings; `bypassPermissions` is never used outside a container; a Ralph-lite run is user-launched from a scratch worktree, opt-in and paid, never from a hook, CI or a pipeline step.
7. **Placement.** Unchanged: an execution mode named in the Lightweight row; the tier stays the size (Lightweight, or Direct for a trivial goal); the calibration row's `Source` cell records the mode. The recipe in `tier-templates.md` describes the skill and its two forms; `/goal` stays one line as the no-artifact fallback for a repository without Praxion, named as the form that keeps one context and judges printed output.
8. **Scope of the first increment.** Goals whose check is a pytest invocation (the gate reads pytest summaries); an exit-code oracle for lint and migration goals is a later increment. The worker is routed to the implementer's tier (sonnet); `--bare` is an opt-in lever only, since it drops `CLAUDE.md`, rules and hooks.

## Considered Options

### Option A — A prose recipe over `/goal` in one session (dec-431 as written)
- **Pros:** zero code; an independent small-model judge; a turn clause and an impossible exit; headless-capable.
- **Cons:** one accumulating context (no fresh context per iteration); the carrier between turns is the transcript; the judge reads printed output and runs nothing; the turn clause is model-judged; the human commits once at the end; nothing lands in the pipeline's artifacts; the harness protects neither tests nor standing instructions. Fails the two durable ideas by construction.

### Option B — A standalone shell loop around `claude -p` reading a goal file
- **Pros:** the canonical Ralph loop; fresh process per iteration; state in goal and progress files; cheap to write.
- **Cons:** a second crank beside the driver — selection, attempt counting, cap, gate, commit, ledger and handoff re-implemented (about 1,250 lines if faithful) or omitted; its own files instead of the shared artifacts; protected paths by prompt unless the loop enforces them.

### Option C — The step-loop driver in a goal mode with a `claude -p` spawner (chosen)
- **Pros:** meets every criterion of both essences; one crank, two spawners, two plan shapes; realises `dec-432`'s v2 as designed and gives the driver a hard per-iteration turn bound and a direct cost reading; the artifacts every reader already parses; the gate, the pathspec commit and the ledger phases untouched.
- **Cons:** a spawner module, a goal scaffold, a runner verb, a reader arm and a per-step cap field to build; a fresh process pays the always-loaded prefix per iteration; pytest-only oracle at first; the worker picks its unit within the goal, not the step.

### Option D — The official `ralph-loop` plugin as-is
- **Pros:** zero code; vendor-maintained.
- **Cons:** same session, prompt re-injection through a Stop hook, completion by a self-emitted string, no gate, no artifacts, amplifies its own prompt. Rejected by the earlier spike and again here.

## Consequences

**Positive.** A Lightweight task can be handed to a bounded, unattended loop that keeps every Praxion guarantee: ground truth decides, the worker never commits, protected paths are denied at the harness and caught at the gate, every iteration leaves a ledger record with turns and cost, every stop leaves a handoff. The driver gains the headless spawner its own reversal trigger may demand for Standard and Full. One loop implementation serves every tier.

**Negative.** About eight implementation steps and their tests; a fixed per-iteration cost from the always-loaded prefix, mitigated by routing and caching; the thirteen `/goal`-shaped acceptance scenarios retire with the recipe step they tested and are rewritten from a fresh spec; the attempt cap's goal-mode reading adds one concept (progress) to the state module; the first increment serves pytest-checkable goals only.

## Disconfirmation

- **Falsifier:** over the first three Ralph-lite runs on real tasks, the loop reaches its goal in no fewer iterations than a hand-run Lightweight task takes turns, or the per-iteration fixed cost dominates the task cost by more than three to one, or a protected path is changed and committed despite the deny rules and the disturbed-tree stop.
- **Steelmanned runner-up:** Option B. A forty-line shell loop around `claude -p` gives a fresh context, state on disk and a cap today, with no change to the driver and no new plan field; the pipeline's artifacts are an elaboration a Lightweight task may not need, and the cost of a second crank is paid only if the two loops diverge.
- **Reversal trigger:** if the goal mode's state changes break an ordinary plan's attempt semantics (a two-attempt step reads differently than before), or if the driver's live dogfood shows the headless spawner cannot find or read a process transcript reliably, build Option B as a thin wrapper that writes the same ledger records and handoff, and keep the goal scaffold.

## Prior Decision

**`dec-431` is superseded.** It decided two things: the placement (an execution mode named in the Lightweight row, not a sixth tier) and the recipe (a prose recipe over `/goal`). The placement survives unchanged in clause 7 above; the recipe is replaced by the driver's goal mode, because the `/goal` form cannot provide a fresh context per iteration or state on disk between iterations, the two ideas the user's confirmation of 2026-10-07 made binding. The five criteria of that confirmation are met by construction here: a fresh context per iteration (a `claude -p` process or a subagent), state on disk (the plan, the WIP progress record, the ledger, the prompt files, the snapshot patches, git), one mechanically verified unit per iteration committed by pathspec, a cap and an impossible exit with a handoff, and `/goal` only as the labelled fallback. The entry moves from a prose recipe to a skill at the user's request; no command is added.

**`dec-427` is superseded in part.** Narrowed: the clause that the two-attempt cap counts fresh attempts per step. In goal mode an attempt is an iteration that committed no unit, so the cap bounds stalls while a goal may run as many progressing iterations as its `Iterations:` field allows; the cap's reading becomes per-step data rather than a bare module constant. Surviving unchanged: the `Check:` grammar and its parser, the check-first verdict, the `Attempts:` write-ahead line, the number two, the human-routed stop when the cap is spent, and the reconciler's refusal to run a declared command itself.

**`dec-429` is re-affirmed.** Iterations remain the budget unit; a goal plan's derived budget is its `Iterations:` field. The per-iteration `--max-budget-usd` flag is a fuse against a runaway iteration, not a loop budget, which reconciles `dec-432`'s mention of the flag with `dec-429`'s "nothing is capped in dollars"; the ledger record's cost now comes from the spawner's own `total_cost_usd` where it has one. Evidence that would justify a future supersession: a goal loop that converges only when bounded by cost rather than by iterations.

**`dec-432` is re-affirmed.** The v2 spawner lands as designed behind the same seam, with a process-exit end-evidence source and a second transcript lookup arm; the orchestrator's relay stays the v1 spawner for Standard and Full. Evidence that would justify a future supersession: the live dogfood showing the headless worker's transcript unreadable by the shared reader.

**`dec-262` is re-affirmed.** The tier still measures size and Ralph-lite is still an execution mode; the artifacts a goal plan creates are the loop's state, not process weight. Evidence that would justify a future supersession: a calibration log in which goal-mode runs cannot be told from Lightweight tasks run by hand.

## Status note (orchestrator, 2026-10-08) — built; five narrowings; first live run

Built by the `ralph-lite` pipeline as decided (Claude Code 2.1.293): the `goal` and `run` verbs, the headless
`claude -p` spawner behind the existing seam, the session-transcript lookup arm, goal mode in the state, gate and
verdict readers, the skill `skills/ralph-lite/SKILL.md`, the recipe and the Lightweight-row clause, the launch-policy
clause. Five narrowings of the text above, recorded at design and held through verification: N1 the ledger's turns
are the transcript's distinct-request count, the one definition, not the result object's `num_turns` (clause 2);
N2 the goal's targets that read pending are the tests the goal's own check fails, never an error and never a
`Read-only` entry as such (clause 2); N3 `run` saves each worker's result object as `WORKER_<request>.json` beside
the task files and `record` reads the worker's end from it (clause 2); N4 `run` never passes `--bare` in this
increment (clause 8's opt-in lever is a later increment's); N5 `run` is the shipped `drive` loop with the headless
spawner, and the skill scaffolds and prints the terminal-form command for the person rather than starting it
(clauses 4 and 5). The planner split the spawner into `scripts/_goal_worker.py` (the headless worker) and `scripts/_goal_run.py` (the `run` verb) instead of the one module named above. Two additions the live run taught: the goal's test module must exist before `goal` runs (pytest
prints no summary for a missing path, and the scaffold refuses a check the gate could never read), and the goal's
expectation must encode the whole intent, because the check decides completion. First live run (td-265, a scratch
worktree, five iterations allowed): the check met in three iterations (the expectation pass>=8 was reached with three of the four named functions pinned; `compute` stayed unpinned, so the reading is "three iterations to the check", not to the whole goal), three pathspec commits with the request trailer,
no protected path changed, one permission denial absorbed by the worktree's own deny rules; cost $1.35 in total with
a fixed cost of $0.14 per iteration (ratio 0.46 to 1 against the 3 to 1 trigger); the hand-run comparator (td-301)
took 35 requests. The falsifier is judged over three runs; this is the first. The frontmatter's `affected_reqs` names the step-loop-driver spec's REQ-34 and REQ-35, the requirements the decision answered when it was written; in the ralph-lite spec that built it, the decision is REQ-23 to REQ-27 (the skill, its two forms, the recipe, the fallback, safe unattended).

## Status note (orchestrator, 2026-10-08, rework round) — eight narrowings from the first verification

The first verification pass (PASS WITH FINDINGS) found that an unattended worker could forge a green gate or loosen
the loop's bounds through the task directory, that a goal check's `fail=0` constrains nothing, that an interrupt
orphaned a paid worker, and — surfaced by the architect at the rework — that the headless worker inherited the
person's own `permissions.allow` rules from the settings files (on the machine that built it: `git add`, `git push`,
`gh repo` among them). The rework round (Band D, sixteen steps in the same pipeline, Claude Code 2.1.293) narrowed
the text above in eight further points, held through the second verification pass (PASS WITH FINDINGS at 99e57ebb: 0 FAIL, 9 WARN open and ledgered, after a third round closed the one failed criterion): N6 the worker's
`--allowedTools` is a write allow-list — the read tools, one `Edit(/<path>)` per entry of the goal step's `Files:`,
the task's progress file, and the check and resolver shell prefixes; no bare `Edit` or `Write` (clause 2); N7 the
worker holds only the pre-approvals `run` grants it: `run` reads the user, project and local settings' allow rules,
mirrors each scoped shell rule as a `--disallowedTools` deny of the same text, refuses before any worker on a
tool-wide shell rule or any edit rule it cannot mirror, and passes `--strict-mcp-config` (clause 2); N8 `record`
never reuses a gate block already written for a goal step — the gate runs on every record of a goal iteration,
whoever wrote the earlier block (clause 2); N9 `run` re-checks its preconditions before every worker, not once: the
deny rules present, the inherited allows neutralisable, the tree outside the goal's paths and the task directory
unchanged, the goal step's block at its starting digest; a failure withdraws the request and ends the run before a
further worker is paid for (clause 6); N10 an edit outside `Files:` is never committed and never restored — the
restore keeps its declared scope — and it stops the terminal form before the next worker; a run that ends complete
with one standing discloses it on a closing line (clause 2); N11 the scaffold warns (`check-completes-early`) when a
goal's expectation can be met with the check's own failing targets still failing; a goal check's `fail=0` is always
met, `pending=0` makes the goal's own tests part of completion, and requiring it is a later spec amendment
(clause 2); N12 the unattended-safety claim covers the worker's tool surface: code the check runs is fenced by the
scratch worktree, the per-iteration and per-loop fuses, N8 and N9, and a person reading the kept commits before the
scratch branch is merged — a sandbox for the worker's shell and the gate's check run is a later increment
(clause 6); N13 a hook refusal of work the gate passed is a non-progressing attempt whose evidence names the
refusing hook's own words and says the gate passed (clause 3). Live evidence of N6 and N7 on 2.1.293: a worker
under the new argv was denied a write outside its list while its named edits landed, a mirrored `git push *` rule
denied a dry-run push, and the harness accepted `--strict-mcp-config` with eleven mirrored denies ($0.46 in three
probes). One reading stays unprobed: whether a new file named in `Files:` can be created through the Write tool under an `Edit(/<path>)` allow (the probes edited existing files); the next live goal that creates a file reads it. The first live run's reading stands as recorded above; no second loop was run in the rework.
