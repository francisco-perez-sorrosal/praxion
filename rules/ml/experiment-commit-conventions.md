---
paths: ["program.md", "train.py", "prepare.py", "runs/**", "experiments/**", "TRAINING_RESULTS.md"]
core: false
---

## Experiment-Branch Commit Conventions

Extends [`git-conventions.md`](../swe/vcs/git-conventions.md) with the commit semantics for
ML experiment branches. Loaded when working on training files (`program.md`, `train.py`,
`prepare.py`, `runs/`, `experiments/`, `TRAINING_RESULTS.md`).

Branches matching `experiment/<run-tag>` / `exp/<run-tag>`, or those the project's
`program.md` declares as experiment branches, use extended commit semantics. The
"one logical change" rule still applies, but a "kept" training run is the logical unit:

- Each kept run gets its own commit; message format: `exp(<run-tag>): <primary-metric>=<value> gpu_h=<hours>`
  (e.g., `exp(run-001-lr3e4): val_bpb=1.72 gpu_h=2.0`)
- `TRAINING_RESULTS.md` and any `program.md` update are committed together with the kept run
- `git reset --hard` to a prior checkpoint commit is the canonical discard mechanism — NOT a
  violation of the one-commit principle; this is the documented workflow for experiment branches
- Checkpoint files (`.pt`, `.bin`, `.safetensors`) are gitignored by default; commit only
  `TRAINING_RESULTS.md` and `program.md` updates, not binary weights

These semantics are scoped to experiment branches; feature branches and `main` are unaffected.
Karpathy's `autoresearch` uses this pattern with a project-specific branch namespace — see
`skills/ml-training/SKILL.md` for the case study and operational modes.
