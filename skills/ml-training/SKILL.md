---
name: ml-training
description: >
  ML/AI pre-training project management and execution within Praxion. Covers the
  ML/AI training archetype vocabulary (six artifact types: frozen eval harness,
  pinned dataset, experiment log, checkpoints, compute budget, hyperparameter
  block), three operational modes (A: co-located owned GPU; B: co-located rented
  GPU; C: separated cloud), program.md as the project-local experiment-loop
  meta-prompt, compute-budget requirements for training-dispatch steps, and
  cross-references to llm-training-eval, neo-cloud-abstraction, and
  experiment-tracking skills. Use when onboarding projects that train neural
  networks, when a project has train.py / prepare.py, when the user mentions GPUs
  / compute budget / checkpoints / loss curves / perplexity / autoresearch /
  Karpathy, or when a pipeline manages torch / jax / tensorflow dependencies.
  Activate alongside agentic-sdks and agent-evals for dual-archetype
  compositions where an autonomous agent drives an ML training loop.
allowed-tools: [Read, Write, Edit, Glob, Grep, Bash]
compatibility: Claude Code
staleness_sensitive_sections:
  - "API Version Drift"
  - "Compute Backend Quick Reference"
---

# ML/AI Training

Praxion's third project archetype: ML/AI pre-training. Extends the traditional-SWE and
agentic-AI archetypes with vocabulary, compute-budget discipline, and experiment-loop
tooling. v1 scope is pre-training (single-node + simple multi-GPU); post-training and
multimodal are v2 deferrals.

**Satellite files** (loaded on-demand):

- [references/operational-modes.md](references/operational-modes.md) -- full Mode A / B / C walkthroughs; when to transition between modes; project config convention

## Six ML Artifact Types

`systems-architect` distinguishes these six artifact types as distinct rows in the
Components table when running on an ML training project (AC2).

| Artifact type | What it is | Praxion home |
|---|---|---|
| Frozen eval harness | Locked version of the eval suite (e.g., `lm-evaluation-harness`) used for all runs | `llm-training-eval` skill |
| Pinned dataset | Exact dataset version + preprocessing hash; changes constitute a new experiment | `.ai-state/` or DVC pointer |
| Experiment log | Per-run metadata, hyperparameters, metrics over time, artifact URIs | `experiment-tracking` skill |
| Checkpoints | Serialized model weights at training steps (`.pt`, `.bin`, `.safetensors`) | gitignored; local or object store |
| Compute budget | `gpu_hours_budget` + `wall_clock_seconds_max` per run; enforced by backend | `neo-cloud-abstraction` skill |
| Hyperparameter block | The YAML/dict defining learning-rate, batch-size, architecture choices for a run | `program.md` or WIP.md step YAML |

## `program.md` — the experiment-loop meta-prompt

`program.md` at repo root is a Praxion-recognized artifact category — a sibling of `CLAUDE.md`
focused on guiding an autonomous experiment loop rather than a session.

- **Discovered by file presence** at repo root (no configuration required)
- **Consumed by** `implementation-planner` and `verifier` alongside `CLAUDE.md`
- **Scope**: project-local, not cross-project (unlike rules and skills)
- **Tracker declaration**: `program.md` MUST declare `tracker: mlflow` or `tracker: wandb`
  so `/run-experiment` knows where to stream metrics; absence defaults to MLflow
- **Not a**: rule, skill, ADR, behavioral spec, or project documentation

Template scaffold is written by `/onboard-project` Phase 8c if `program.md` does not exist.

## Operational Modes (summary)

Three modes share one `training_job_descriptor` schema (AC6). Mode is a **project-level
configuration**, not a descriptor field. See
[references/operational-modes.md](references/operational-modes.md) for the full walkthrough.

| Mode | Name | Backend | Description |
|---|---|---|---|
| A | Co-located owned GPU | `local` | Mac M-series, RTX, on-prem — Praxion and project co-located |
| B | Co-located rented GPU | `local` | SSH'd into rented H100 box, Praxion installed there |
| C | Separated cloud | `skypilot` or `runpod-direct` | Laptop drives remote cloud GPU |

**Key invariant:** Modes A and B are **identical from Praxion's perspective** — both use the
local backend (`neo_cloud_backend: local`). Mode B is "free" once Mode A works because the
local backend cannot tell the difference between owned and rented hardware. This is the most
important insight users miss without being told explicitly.

## Compute-Budget Requirement

Every WIP.md step that dispatches a training run MUST carry:

```yaml
gpu_hours_budget: <float>    # hard cap for this step
```

And an acceptance criterion that is one of:
- **Metric threshold**: `step completes when val_bpb < 1.75`
- **Budget gate**: `step completes when gpu_hours_budget consumed OR val_bpb < 1.75, whichever first`

A step without a declared budget MUST be flagged FAIL by the verifier (per `rules/ml/gpu-budget-conventions.md`).

## API Version Drift
<!-- last-verified: 2026-05-03 -->

| Library | autoresearch pin | Current upstream | Priority | Action |
|---|---|---|---|---|
| `torch` (PyTorch) | `2.9.1` | `2.10.0` (chub maintainer doc) | High (taught) | Note here; do not auto-upgrade autoresearch's pin |
| `skypilot` | not pinned by Praxion | `0.12.1` (PyPI) | Critical (default-remote backend) | Teach `~=0.12`; flag for refresh at 0.13+ |
| `@runpod/mcp-server` | not pinned by Praxion | `1.1.0` (npm) | High (reference direct adapter) | Teach `~1.1`; vendor-maintained — verify before using |

autoresearch pins `torch==2.9.1`. The chub maintainer doc covers `2.10.0`. This is minor
drift (backward-compatible minor release). Do not auto-upgrade autoresearch's pin. Users
building new projects should start at `2.10.0`.

## Compute Backend Quick Reference
<!-- last-verified: 2026-05-03 -->

| Backend config | Operational mode(s) | Teaches |
|---|---|---|
| `neo_cloud_backend: local` | A, B | `subprocess.Popen` semantics; `wall_clock_seconds_max` via `signal.alarm` |
| `neo_cloud_backend: skypilot` | C | SkyPilot `~=0.12` YAML task spec; 20+ provider coverage |
| `neo_cloud_backend: runpod-direct` | C (opt-in) | `@runpod/mcp-server ~1.1`; `RUNPOD_API_KEY` env var |

Configure via `.ai-state/neo_cloud_backend.yaml` at project root. See `neo-cloud-abstraction`
skill for the full lifecycle operations table.

## Related Skills

| Skill | When to load it |
|---|---|
| `llm-training-eval` | Designing or reading evaluation criteria (val_bpb thresholds, PASS/FAIL/WARN classification) |
| `neo-cloud-abstraction` | Configuring backends, dispatching runs, reading lifecycle operations |
| `experiment-tracking` | Setting up MLflow or W&B run logging; mapping run IDs to TRAINING_RESULTS.md |
| `deployment` → `references/gpu-compute-budgeting.md` | Budget declaration patterns, cost estimation by backend |
| `cicd` → `references/ml-experiment-ci.md` | Eval-gated PRs, checkpoint artifact upload, baseline diffing |
| `agentic-sdks` | Dual-archetype composition with autoresearch (ML training × agentic-AI) |
| `agent-evals` | Evaluating agent behavior within the autonomous experiment loop |
