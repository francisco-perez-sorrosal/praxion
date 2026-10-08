# step-loop

The relay procedure for the step-loop driver: the orchestrator passes the driver's spawn requests to the Agent tool and each return back to the driver, and decides nothing in between.

## When to Use

After the pre-mortem gate of a Standard or Full pipeline, when the plan is ready and its implementer steps are to run through `scripts/step_loop.py`. The driver picks each step, gates the return on ground truth, commits it and records it; this skill is the orchestrator's side of that exchange.

## Activation

- Slash: `/praxion:step-loop <task-slug>`.
- Auto: the coordination protocol's "Plan ready" bullet in `rules/swe/swe-agent-coordination-protocol.md` names it; the model may also start it when the plan is ready.

## Skill Contents

- `SKILL.md` — the relay rules (pass the spawn request unchanged, `record` only after the completion notification, never edit or read the rendered prompt, never commit), the `next` / `record` procedure and its exit-code table, the marker note and the `--not-started` form.

## Related Skills

- `software-planning` — the plan, `WIP.md` and the spawn budget the driver draws on.
