---
name: ralph-lite
description: "Drive one well-gated, single-behaviour goal that a pytest command checks through a bounded loop of fresh headless workers (Ralph-lite), given the goal arguments."
argument-hint: "<slug> --goal <sentence> --check <command> --expects <expectations> --paths <path>... [--protect <path>...] [--iterations <n>]"
allowed-tools: ["Bash(step_loop.py goal:*)", "Bash(python3 scripts/step_loop.py goal:*)"]
---

# Ralph-lite

Hand one well-gated goal to the step-loop driver's goal mode: a fresh worker per iteration, the gate deciding each iteration, the driver committing the progress.

## Rules

- A goal must be checkable by a pytest command: refuse a goal no pytest command can check, and a goal whose paths lie under the protected paths.
- A check that is not a pytest command reads as no run every iteration and stalls the loop at two.
- A goal whose paths lie under the protected paths is refused, which excludes context-artifact work on Praxion itself.
- A run is opt-in and paid: it costs real API credits.
- Never start a run from a hook, CI or a pipeline step.
- A person launches the terminal form; never launch it yourself.
- Work in a scratch worktree, never the main checkout: the scaffold's deny rules bind every session of the checkout it runs in.
- The scaffold writes its deny rules to `.claude/settings.local.json` of that checkout and removes them there when the work is done.
- Never use `bypassPermissions` outside a container, and never `acceptEdits` alone: it denies the test command.

## Procedure

1. Scaffold the goal plan from the scratch worktree with `step_loop.py goal $ARGUMENTS`; in the Praxion checkout run `python3 scripts/step_loop.py goal $ARGUMENTS` instead. Quote the `--goal` and `--check` values. The scaffold writes the plan, a `WIP.md`, a `TASK_BRIEF.md` and the deny rules for the protected paths.
2. Terminal form: print `step_loop.py run <slug>` for the person to run in a terminal from the scratch worktree.
3. In-session form: drive the goal plan through `/praxion:step-loop <slug>`; the relay rules live in the [step-loop](../step-loop/SKILL.md) skill.
4. At a stop, show the stop and its `HANDOFF.md`: that file is where a person picks the work up.

## Safety profile

- The worker runs under `--permission-mode dontAsk` with the goal's check and the `resolve_test_scope.py` resolver allow-listed.
- Deny rules on the protected paths hold in every permission mode.
- Each iteration is bounded by a turn bound and a dollar fuse.
- The `Iterations:` budget bounds the loop; two non-progressing iterations in a row stop it as a stall.
