---
id: dec-draft-626e3311
title: Paired refactoring-delivery runs keep a results directory of their own by default
status: proposed
category: behavioral
date: 2026-11-18
summary: "Without --output, a run of the refactoring-delivery axis writes, lists, closes and reindexes in .ai-state/eval_ledger/adherence/refactoring-delivery, named by a results_subdir field on the axis's AxisRun record; the ordinary comparison keeps .ai-state/eval_ledger/adherence. --close and --continue find a run in any axis's directory. The adoption gate's reader and its parity test are unchanged."
tags: [eval, adherence, refactoring-delivery, results, flip-gate]
made_by: agent
agent_type: systems-architect
branch: worktree-liveness-eval-rows
pipeline_tier: standard
affected_files:
  - eval/src/praxion_evals/adherence/axis_runs.py
  - eval/src/praxion_evals/adherence/session_loop.py
  - eval/src/praxion_evals/adherence/cli.py
affected_reqs: [REQ-15, REQ-16]
---

## Context

The paired axis wrote its results file into the committed adherence results directory and listed itself in that directory's index, where the adoption gate reads every file. The gate's reader (`scripts/kernel_run_evidence.py`) cannot parse a paired file, so the parity test `scripts/test_kernel_run_evidence_parity.py` failed seven times on 2026-11-16 (td-674). The three paired files were moved by hand to `.ai-state/eval_ledger/adherence/refactoring-delivery/` with their own index. Nothing writes there by default, and nothing finds a run there by id.

## Decision

`AxisRun` gains `results_subdir`: `""` for `inherited-context` and `"refactoring-delivery"` for the paired axis. Without `--output`, a run's results file, its index and the stopped runs it checks against live in `OUTPUT_DIR / results_subdir`. `--reindex --axis <axis>` rebuilds that axis's directory. `--close RUN` and `--continue RUN` look for `<RUN>.json` in every axis's directory, the named axis's first, without being told the axis. A run found nowhere is refused with today's text. `--output` still decides any run's location.

## Considered Options

### Option 1: an axis-named default directory (chosen)

- **Pro:** the gate stays ignorant of eval axes. No gate's scope narrows. It follows dec-477's move results store, a subdirectory the flip gate never reads.
- **Con:** it changes a shipped default, and operators must name `--axis` to reindex a paired directory.

### Option 2: teach the gate's reader and its parity test to pass over another axis's files by name

- **Pro:** no default moves.
- **Con:** it couples the flip gate to the eval's axis vocabulary and narrows what the gate reads. A gate that skips files by name is a gate whose computed scope can silently shrink.

## Consequences

**Positive:**

- The committed directory the gate reads holds only files it parses.
- The three committed paired runs read where they are.

**Negative:**

- A committed paired run that stopped and was never closed now refuses a fresh paired run until it is closed. This is correct, and `--close` now finds it.
- One more field on the axis record.
