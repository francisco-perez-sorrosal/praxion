---
id: dec-432
draft_id: dec-draft-53a46554
title: A deterministic step-loop driver owns the crank between the pre-mortem gate and the pre-verification checkpoint; the orchestrator relays spawn requests through a spawner seam
status: accepted
category: architectural
date: 2026-10-05
summary: New scripts/step_loop.py (next/record/status) over pure _step_loop_{state,render,gate} modules, an I/O adapter, _plan_steps.py and hooks/_agent_transcript.py; selection, prompt composition, write-ahead attempts, ground-truth gating, pathspec commits, ledger appends and the attempt cap move from the orchestrator's prose procedure into the driver; v1 spawner is the orchestrator's Agent tool across two CLI calls, v2 headless and v3 Workflow are designed implementations of the same seam.
tags: [step-loop, driver, orchestrator, spawner, gate, pathspec-commit, ralph-loop, pipeline]
made_by: agent
agent_type: systems-architect
branch: worktree-step-loop-driver
pipeline_tier: full
affected_files:
  - scripts/step_loop.py
  - scripts/_step_loop_state.py
  - scripts/_step_loop_render.py
  - scripts/_step_loop_gate.py
  - scripts/_step_loop_io.py
  - scripts/_plan_steps.py
  - hooks/_agent_transcript.py
  - scripts/reconcile_pipeline_state.py
  - scripts/compose_handoff.py
  - scripts/resolve_test_scope.py
  - commands/step-loop.md
  - skills/software-planning/references/agent-pipeline-details.md
affected_reqs: [REQ-01, REQ-02, REQ-03, REQ-04, REQ-05, REQ-06, REQ-07, REQ-08, REQ-10, REQ-12, REQ-13, REQ-14, REQ-15, REQ-16, REQ-17, REQ-18, REQ-19, REQ-20, REQ-21, REQ-22, REQ-23, REQ-24, REQ-25, REQ-27, REQ-28, REQ-29, REQ-30, REQ-38]
supersedes_in_part: [dec-426, dec-427]
dissent: []
---

## Context

Between the pre-mortem gate and the pre-verification checkpoint, the orchestrator turns the crank by hand. It picks the next step, writes the `Attempts:` line ahead, composes an implementer prompt, spawns, runs the completion handshake, commits by pathspec and appends the iteration ledger. Measured consequences:

- implementer cap-outs of 0.143;
- a median orchestrator context of 411,395 tokens when the verifier spawns;
- 5–6 steps per pipeline absorbed by the orchestrator;
- a verifier first-pass PASS of 2 of 15.

The step-schema pipeline turned the check, the attempt count and the ledger into data with one parser each (dec-426, dec-427), so that a driver could sit on them. The user's constraints: the problem is the driver, not the gates; choose the most reliable and extensible option; quality is the guide; do not cut feedback and force archaeology.

## Decision

1. **Components.**
   - `scripts/step_loop.py` (CLI; verbs `next`, `record` and `status`, exactly three).
   - Pure modules: `_step_loop_state.py` (series states, selection, iteration budget, stop precedence), `_step_loop_render.py` (request ids, `agent_call`, rendered prompts, stop text, commit message) and `_step_loop_gate.py` (pytest-output classification with `pending` by `Read-only:` ownership, result-line ordering, end evidence, stop reasons).
   - `_step_loop_io.py`, the adapters for git, the command runner, transcripts and writers.
   - `scripts/_plan_steps.py`, the plan-step record, taking over the `Files:` reader from the reconciler.
   - `hooks/_agent_transcript.py`, the one subagent-transcript reader.
   - Contract: the module docstring and `--help`. Prose elsewhere points to it, and the loop procedure is `commands/step-loop.md`.
2. **Responsibility moved.** Inside the loop, the driver selects the step (plan order, `[depends-on]`, `[parallel-group]` never waiting on a sibling), writes the attempt ahead, renders the prompt from a fixed template into `PROMPT_<request>.md`, and gates on ground truth. The gate runs the derived scope, then the step's `Check:`, and reads the verdict through `reconcile(..., assume_recorded={request})`. The driver commits by explicit pathspec (never outer-loop files), appends one ledger record per agent return, and enforces the cap. The orchestrator executes `request.agent_call` unchanged and calls `record` with the request id, the agent id and the marker, after the completion notification.
3. **No private state.** Pending, attempts, the series, review state and iterations are re-derived on every call from `WIP.md`, the ledger, `TEST_RESULTS.md`, `LIGHT_REVIEW_step-<id>.md`, the reconciler and git. `next` is idempotent, and `record` is idempotent per phase, keyed by request id. A `record` cut off by a tool timeout completes when it is run again.
4. **Steps outside the loop.** A step not assigned to the implementer stops the loop (exit 2, `not-driven`) until it is done. The orchestrator runs it outside the loop, ticks its `WIP.md` line and resumes; every other exit 2 goes to the user. Such a step is done when:
   - the reconciler reads `verified-complete` with a `COMPLETE` claim; or
   - the step declares no `Files:` and no `Check:`, and its `WIP.md` line claims `COMPLETE`, since there is no ground truth to contradict the claim.

   The planner keeps such steps outside the driven span where it can, and gives a non-implementer step that turns tests red a `Check: … pending=<n>`.
7. **Invocation.** The `/step-loop <slug>` procedure is model-invocable. `then` and `stop.resume` echo the caller's invocation: `step_loop.py` through `PATH`, `python3 scripts/step_loop.py` otherwise.
5. **Stops** persist while their evidence holds, and every exit 2 or 3 composes HANDOFF.md through `compose_handoff.write_handoff(..., next_action=<stop text>)`, rewriting only when § 2 changes.
6. **Spawner seam.** `SpawnRequest` → `SpawnReturn = AgentRan | NotStarted`. v1: the orchestrator's Agent tool across `next` and `record`. v2 (designed): `claude -p --agent implementer --max-turns --max-budget-usd --output-format json`. v3 (designed): one `Workflow` run per parallel group. A test-only scripted spawner and the acceptance double prove the seam.

## Considered Options

### Option 1 — Python driver, Agent tool as the v1 spawner (chosen)
- **Pros:** incremental; observability unchanged (WAL attribution through `Task slug:`, light reviews, `spawn_count.py`); testable against harvested pipelines; the orchestrator reads about 150 tokens per spawn.
- **Cons:** the orchestrator still executes the spawn and relays three values.

### Option 2 — Headless `claude -p` per step
- **Pros:** true fresh process; native `--max-turns` and `--max-budget-usd`; `num_turns` and cost come back in JSON.
- **Cons:** new observability and attribution wiring; worktree write scope unresearched; the spawn budget needs re-basing anyway. Designed as v2.

### Option 3 — `Workflow` script owns the loop
- **Pros:** deterministic and resumable; cached prompt prefixes.
- **Cons:** no mid-run user input, which conflicts with human stops; a workflow script has no shell to run gates; per-agent options unverified. Designed as v3, for parallel groups only.

### Option 4 — Prose procedure only
- **Cons:** it is the measured failure.

## Consequences

**Positive:** the orchestrator's context grows by pointers only. There is one committer, and each verified step is one reviewable commit. Capped work reaches a human with what stopped each attempt. Verdicts and the gate agree by construction.

**Negative:** about 2,000 new lines across seven modules, and the reconciler gains a ledger read. The managed-project invocation is resolved: the driver echoes the caller's invocation, so the `then` and resume commands are right both in the self-host checkout and where `step_loop.py` is installed on `PATH`. A model-invocable `/step-loop` costs about 31 listing tokens.

## Disconfirmation

- **Falsifier:** on this pipeline and the next two, implementer cap-outs do not fall below 20 percent, or absorbed steps stay above 0, or orchestrator context at verifier spawn stays above 150,000 tokens. Any of these means the crank was not the cause.
- **Steelmanned runner-up:** headless sessions (Option 2). They give a real per-attempt turn cap, dollar caps, and turn counts without transcript archaeology, and they remove the orchestrator from the loop entirely. The orchestrator would no longer hold even the pointers. Its costs are attribution and isolation work the research did not cover.
- **Reversal trigger:** if the relay proves unfaithful (requests altered, `record` called before the end), or the orchestrator's context still grows past 150,000 tokens with the driver live, build v2 behind the same seam and make it the default.

## Prior Decision

dec-427 clause 7 (the orchestrator writes the `Attempts:` line write-ahead) and dec-426 clause 4 (one ledger record per implementer return, appended after the handshake commit) are narrowed. Inside the loop the step-loop driver is the writer of both; outside the loop the orchestrator still is. Everything else in both records stands.
