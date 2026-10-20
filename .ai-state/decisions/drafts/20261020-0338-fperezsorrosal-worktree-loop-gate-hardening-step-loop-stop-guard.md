---
id: dec-draft-4646100d
title: A Stop hook holds the orchestrator's stop once when a step-loop agent of this session has ended unrecorded, judged by the driver's own end evidence
status: proposed
category: architectural
date: 2026-10-20
summary: "Adds hooks/guard_step_loop_stop.py, a synchronous Stop hook, and scripts/_step_loop_outstanding.py, a driver-side probe it imports lazily. The hook holds a stop (decision block) only when a request the driver issued is absent from the iteration ledger and the transcript of the agent this session started on it ends by the same predicate record accepts; it names the first such request (oldest issued, then slug) with the exact, filled record command. It passes on stop_hook_active, on any unreadable input (a transcript with any unparseable line included), outside a step loop without reading a transcript or starting a process, and writes nothing."
tags: [step-loop, hooks, stop-hook, orchestration, fail-open, td-464]
made_by: agent
agent_type: systems-architect
branch: worktree-loop-gate-hardening
pipeline_tier: standard
affected_files:
  - hooks/guard_step_loop_stop.py
  - scripts/_step_loop_outstanding.py
  - hooks/hooks.json
  - skills/step-loop/SKILL.md
affected_reqs: [REQ-01, REQ-02, REQ-03, REQ-04, REQ-05, REQ-06]
supersedes: null
superseded_by: null
re_affirms: null
re_affirmed_by: null
retired_by: null
supersedes_in_part: null
superseded_in_part_by: null
dissent: null
---

## Context

A step-loop agent ended with a terminal marker but left its own background jobs running; the harness labelled its completion notification "may be interim", the orchestrator ended its turn waiting for a second notification, and the session sat idle for hours (td-464). `record` already refuses an agent whose transcript does not show the end (`agent-running`), so taking a return back early is safe; nothing prompted the orchestrator to do it. Hooks ship to every managed project, most of which never run a step loop.

Activation: fired — honest uncertainty (the brief rates detection 6/10) on a one-way-ish shipped surface; lenses: Security (none: read-only), Performance (cost outside a loop), Testability (parity with `record`), Simplicity.

## Decision

1. A new synchronous `Stop` hook, `hooks/guard_step_loop_stop.py`, registered once in `hooks/hooks.json` (`async: false`, timeout 10 s). It is a thin shell: parse stdin; return at once when `stop_hook_active` is true; find `.ai-work/` at the checkout root, the first ancestor holding a `.git` entry, which is the root `record` derives (going past it would read an outer checkout's loop and print a command `record` rejects); read each task's `WIP.md` and `ITERATION_LEDGER.jsonl` as text; when no request id on a task's `Attempts:` lines is missing from that task's ledger text, return with no transcript read, no import and no process started.
2. Only past that test it imports a new driver-side module, `scripts/_step_loop_outstanding.py`, which composes the driver's existing readers (`Attempts:` parsing, the ledger reader, the shared transcript reader, `names_request`, `end_evidence`, `end_source`, the observation-log stop row, the declared turn cap) and the driver's record-command composer. There is one definition of "ended" and one of the command: the driver's.
3. It judges only transcripts under this session's own `subagents/` directory, and refuses a session id that is not one plain path segment. Before reading, it keeps only files named by an agent id and modified no earlier than the oldest outstanding request's prompt file. A task directory whose name is not a slug yields no request. A transcript ties to a request only when `names_request` names it and its prompt also carries the request's own `Task slug:` line, because request ids restart in every task. A transcript with any unparseable line counts as unreadable and passes. When several transcripts of the session tie to one request and any of them is running, the request is not held. It holds only when `end_source` names an end, so the set it holds is a strict subset of what `record` accepts: it never holds an agent `record` would refuse, and it passes some that `record` would accept (a transcript `record` salvages, an ended agent with a running sibling).
4. It holds with exit 0 and `{"decision":"block","reason":...}`: one message of at most 600 bytes naming the request, the agent, how it ended and the fully filled record command, for the first held request ordered by issue time (the prompt file's mtime) then slug. It keeps no state.
5. Any failure (unreadable input, exception, a missing plugin `scripts/` tree) exits 0 with no output: today's behaviour. The step-loop skill's `## Rules` bullet on `record` states the same rule for the orchestrator (a marker is final under an "interim" note; `record` is always safe).

## Considered Options

### A thin hook plus a driver-side probe (chosen)

Pros: one end predicate and one command composer; the hook's own code is input handling and rendering; the import cost is paid only inside a loop. Cons: the hook depends on the plugin's `scripts/` tree being importable (same plugin, same version).

### Move the end judgement into `hooks/_agent_transcript.py`

Pros: no cross-tree import. Cons: moves a driver responsibility (what counts as ended, the turn cap, the stop row) into a hooks reader for one caller, and the driver would then import it back; the command composer would still live in the driver.

### Call `step_loop.py status` from the hook

Pros: no import. Cons: `status` runs the reconciler and git on every candidate stop; it does not know transcripts' end state per agent; seconds of latency on a hook every Stop.

### `additionalContext` instead of a block

Pros: softer transcript label. Cons: the spec and the acceptance contract define a hold; both forms share the same loop protections, so the label is the only difference.

## Consequences

- Positive: an ended, unrecorded agent cannot leave the orchestrator idle past one stop; the guard never holds an agent `record` would refuse as running.
- Negative: one more synchronous hook on every Stop in every managed project (bounded to two small file reads per task directory outside a loop); a cross-tree import inside the plugin.
- The hook has no Codex bridge entry, following `remind_calibration` and the orientation hook; the Cursor export carries no hooks.

## Disconfirmation

- **Falsifier:** a fixture where the guard holds and `record` on the same transcript refuses `agent-running`; or a project with no `.ai-work/` loop where the guard opens a transcript or starts a process; or a stop held twice in a row.
- **Steelmanned runner-up:** moving the end predicate into the shared transcript reader removes the hook's dependency on `scripts/` entirely and makes the hook importable in isolation, which is what a hook usually wants; the driver would import the predicate from the reader it already uses. It loses because the predicate's inputs (declared turn cap from agent definitions, the observation-log stop row) and the record-command composer are driver knowledge, so the move would split one responsibility across two trees instead of keeping it in one.
- **Reversal trigger:** if the lazy import fails in a managed project more than once (a liveness finding or a user report), or if a second hook needs the same predicate, move the predicate into the shared reader.
