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
- The goal's test module exists before `goal` runs, and an empty module is enough.
- Without the module pytest prints no summary for a missing path, and the scaffold refuses a check it cannot read.
- The check names the project's own test runner: `uv run pytest` where the project runs pytest through uv.
- Never name a bare interpreter in the check: it may lack pytest.
- The expectation encodes the whole goal.
- A goal check's `fail=0` is always met, because the goal's own failing tests read `pending`.
- Add `pending=0` so the goal's own failing tests become part of completion.
- A goal whose tests the loop writes must count every test it asks for in the pass count.
- Pass the goal's oracle to `--protect`: the target tests of a make-green goal, the module under test of a test-writing goal.
- A run is opt-in and paid: it costs real API credits.
- Never start a run from a hook, CI or a pipeline step.
- A person launches the terminal form; never launch it yourself.
- Work in a scratch worktree, never the main checkout: the scaffold's deny rules bind every session of the checkout it runs in.
- The scaffold writes its deny rules to `.claude/settings.local.json` of that checkout.
- Nothing removes the deny rules but the person.
- The deny rules stay in that checkout's `.claude/settings.local.json` until the person deletes them when the goal is done.
- In a scratch worktree the deny rules go with the worktree.
- Never use `bypassPermissions` outside a container, and never `acceptEdits` alone: it denies the test command.

## Procedure

1. Scaffold the goal plan from the scratch worktree with `step_loop.py goal $ARGUMENTS`; in the Praxion checkout run `python3 scripts/step_loop.py goal $ARGUMENTS` instead. Quote the `--goal` and `--check` values. The scaffold writes the plan, a `WIP.md`, a `TASK_BRIEF.md` and the deny rules for the protected paths.
2. Terminal form: print `step_loop.py run <slug>` for the person to run in a terminal from the scratch worktree.
3. In-session form: drive the goal plan through `/praxion:step-loop <slug>`; the relay rules live in the [step-loop](../step-loop/SKILL.md) skill.
4. At a stop, show the stop and its `HANDOFF.md`: that file is where a person picks the work up.

## Safety profile

- The worker runs under `--permission-mode dontAsk` with the goal's check and the `resolve_test_scope.py` resolver allow-listed.
- Deny rules on the protected paths hold in every permission mode.
- The worker may edit only the goal's paths and its progress record.
- The worker holds no pre-approval but the check and the resolver.
- `run` refuses before any worker when a settings file pre-approves a tool-wide `Bash` rule or an edit rule.
- `run` denies the worker every other inherited `Bash` pre-approval.
- Code the check runs is not fenced by permission rules.
- Read the kept commits before the scratch branch is merged.
- Each iteration is bounded by a turn bound and a dollar fuse.
- The `Iterations:` budget bounds the loop; two non-progressing iterations in a row stop it as a stall.
