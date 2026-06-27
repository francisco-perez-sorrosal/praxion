# Plan: p06 canary — TASK_BRIEF absent

This is a minimal sentinel gate-liveness fixture for the P06 check.

The sentinel P06 check flags any `.ai-work/<slug>/` directory that contains
`SYSTEMS_PLAN.md` (indicating a Standard/Full pipeline ran) but no `TASK_BRIEF.md`
(indicating the brief was never produced).

This directory intentionally has `SYSTEMS_PLAN.md` and NO `TASK_BRIEF.md`.
The sentinel must emit a WARN for P06 on this input.

Golden bad-case per `rules/swe/gate-liveness.md` (PROMPT-kind gate).
