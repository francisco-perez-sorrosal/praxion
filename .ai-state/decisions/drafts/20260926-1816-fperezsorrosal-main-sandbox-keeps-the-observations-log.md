---
id: dec-draft-f3bc0103
title: The live eval sandbox keeps the observations log and silences only chronograph event posting
status: proposed
category: implementation
date: 2026-09-26
summary: "Live eval sessions stop setting PRAXION_DISABLE_OBSERVABILITY and set a new, narrower PRAXION_DISABLE_EVENT_POSTING instead, so the observations log is written into the throwaway fixture while send_event.py still posts nothing; the log's four files are excluded from recorded paths. Without the log, any hook that qualifies a session from it (the Stop-time calibration reminder) could not fire in the sandbox, so its before/after pair measured nothing."
tags: [eval, context-layer, sandbox, observability, hooks, process-economy, td-258]
made_by: agent
agent_type: orchestrator
branch: main
pipeline_tier: lightweight
affected_files:
  - eval/src/praxion_evals/live/session.py
  - eval/src/praxion_evals/live/scenarios.py
  - hooks/_hook_utils.py
  - hooks/send_event.py
  - README_DEV.md
affected_reqs: []
supersedes_in_part: [dec-391]
dissent: "A new kill switch is one more flag to document; pointing CHRONOGRAPH_PORT at a closed port would have silenced posting with no hook change."
---

## Context

dec-391 builds each live eval session's environment from an allowlist plus the side-effect-only hook kill switches, one of which is `PRAXION_DISABLE_OBSERVABILITY`. That one flag gates five hooks: `send_event.py` (chronograph POSTs to localhost), `capture_observations.py`, `capture_session.py` and `measure_context_surface.py` (the local `.ai-state/observations.jsonl` log and the session summary), and `notify_bg_session_state.py` (inert in a sandbox HOME with no rework markers). The Stop-time calibration reminder (td-253) qualifies a session only from that log, so in the sandbox it could never fire: its before/after pair read 4/5 in both arms at 962f0f01 and bf908f8d, an instrument-blind result recorded as td-258.

## Decision

- `hooks/_hook_utils.py` gains `PRAXION_DISABLE_EVENT_POSTING`, read only by `send_event.py`, which now returns early when either it or `PRAXION_DISABLE_OBSERVABILITY` is set.
- `session.py`'s `FIXED_SWITCHES` replaces `PRAXION_DISABLE_OBSERVABILITY` with `PRAXION_DISABLE_EVENT_POSTING`: the log is written into the throwaway fixture; nothing is posted.
- `scenarios.py` treats `.ai-state/observations.jsonl`, its `.1` rotation, `observations.lock` and `observations_summary.jsonl` as hook-created byproducts, so the log never counts as the agent's authored change.

## Considered Options

| Option | For | Against |
|---|---|---|
| **Narrow switch for posting (chosen)** | Each side effect has its own named control; the sandbox states exactly what it turns off | One more documented flag |
| Point `CHRONOGRAPH_PORT` at a closed port | No hook change | Relies on a connection failing rather than a declared intent; a listener on that port would receive sandbox events |
| Keep the log off; drive the reminder from another source | No sandbox change | Changes the hook under test to suit the instrument |

## Consequences

- Hooks that read the observations log become measurable by the live runner; the td-253 pair can be re-run with the reminder able to fire.
- Sandbox sessions spend a little more time and I/O writing the log; it is deleted with the fixture.
- A project that sets `PRAXION_DISABLE_EVENT_POSTING` keeps its local log and loses only chronograph telemetry.

## Prior Decision

Narrows dec-391's list of side-effect switches: `PRAXION_DISABLE_OBSERVABILITY` leaves the list and `PRAXION_DISABLE_EVENT_POSTING` joins it. Every other clause of dec-391 stands unchanged: the per-session sandbox HOME and config dir, the environment allowlist, `--plugin-dir`/`--add-dir`, `--strict-mcp-config`, the runner's interpreter first on PATH, env-credential auth, and the real-home telemetry check.
