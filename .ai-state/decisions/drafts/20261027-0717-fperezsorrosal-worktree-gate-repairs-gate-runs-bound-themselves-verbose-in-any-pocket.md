---
id: dec-draft-2801fd08
title: Gate runs enforce their own bound, and read one line per test in any pocket
status: proposed
category: behavioral
date: 2026-10-27
summary: Each detached gate run's background watchdog stops the run's process group at its recorded deadline and writes the cut marker first, while the command keeps the launcher's foreground; gate pytest runs pass --verbosity=1 instead of -v so a pocket's -q cannot hide per-test outcomes.
tags: [step-loop, gate, pocket-runs, pytest]
made_by: agent
agent_type: systems-architect
branch: worktree-gate-repairs
pipeline_tier: standard
affected_files:
  - scripts/_step_loop_pocket_runs.py
affected_reqs: [REQ-09, REQ-10, REQ-11, REQ-12, REQ-13]
supersedes_in_part: dec-467
---

## Context

dec-467 clause 2: the bound is enforced when a later `record` attaches; nothing kills a run between calls, so a hung run of an abandoned request lives on (td-492). Clause 4: gate pytest runs carry `-v -rfE` so a cut-off run's failures can be read from its log; a pocket whose `addopts` carry `-q` (task-chronograph-mcp) nets verbosity 0, and its cut-off run names no failure (td-494, part W5).

## Decision

1. The command runs in the foreground of the launcher that leads the run's process group, so it keeps default signal dispositions (a non-interactive POSIX shell starts a background command with SIGINT ignored, which every test the gate ran would inherit). A background watchdog receives the run's deadline (recorded start plus the bound recorded in `<n>.start`, the bound capped at ten years) at start and ticks once a second. When the command outlives the deadline by a 5 s grace, the watchdog writes `<n>.cut` (and signals nothing when it cannot), ignores SIGTERM itself, sends SIGTERM to the launcher's own group in the POSIX spelling `kill -s TERM -- -<leader>` (dash refuses `kill -TERM --`), then SIGKILL to survivors after 2 s, and exits; it also ends with the run. The stop lands well inside the 30 s allowance. The attach-time kill stays as the backstop for a launcher the system killed. Stdlib only: no `timeout` tool, no hook.
2. Gate pytest invocations pass `--verbosity=1` (an absolute setting, applied after the ini `addopts`) instead of `-v`; `-rfE` stays. No pocket configuration is edited.

**Activation:** no -- each alternative fails a stated requirement (macOS lacks `timeout`; a kill without the marker reads as not started).

## Considered Options

### Launcher enforces its deadline (chosen)
- Pro: the process that owns the group holds the bound; no pid-reuse risk; the verdict still follows recorded files.
- Con: a launcher killed from outside leaves the run to the attach-time path, as today.

### `timeout` wrapper around the command
- Con: not shipped on macOS; kills without writing the cut marker, so the run would read as not started.

### Count `-q` in each pocket's configuration and add matching `-v`
- Con: reads four configuration formats and drifts; `--verbosity` makes it unnecessary.

## Consequences

- Positive: no gate run outlives its bound unattended; a quiet pocket's cut-off run names its failures.
- Negative: a pocket configured `-vv` reads at verbosity 1 under the gate (no reading needs more); `--verbosity` must exist on each pocket's pytest (checked at the step).

## Prior Decision

dec-467 clauses 2 and 4 are narrowed: the bound is now also enforced between calls by the run's launcher, and `-v` becomes `--verbosity=1`. Every other clause (bound sources, wait ceiling, run sum type, evidence slot, block lines) stands.
