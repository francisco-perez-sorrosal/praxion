# ralph-lite

The procedure for the step-loop driver's goal mode: one well-gated, single-behaviour goal that a pytest command checks, run through a bounded loop of fresh headless workers.

## When to Use

When one behaviour is to be reached and a pytest command checks it, for example making a failing test file green, and a person accepts that the run is opt-in and paid. The skill scaffolds the goal plan and prints the terminal-form command for the person; it does not start the run.

## Activation

- Slash: `/praxion:ralph-lite <slug> --goal <sentence> --check <command> --expects <expectations> --paths <path>...`.
- Auto: the model may start it when a request names one pytest-checkable goal; it still only scaffolds.

## Skill Contents

- `SKILL.md` — the standing rules (checkable goal, protected paths, opt-in and paid, never from a hook, CI or pipeline step, scratch worktree, permission modes), the scaffold procedure with its terminal and in-session forms, and the safety profile of an unattended run.

## Related Skills

- `step-loop` — the relay procedure the in-session form drives the goal plan through.
- `software-planning` — the plan and `WIP.md` the scaffold writes and the driver reads.
