---
name: experiment-tracking
description: >
  ML experiment lineage tracking — NOT app observability (use observability for
  RED/OTel/Prometheus/Grafana). Covers the experiment log artifact: per-run
  hyperparameters, metrics (val_bpb, loss curves), artifact URIs, run-to-run
  comparison. Tools: MLflow, W&B / Weights & Biases, Aim. Triggers: setting up
  experiment tracking, connecting a training loop to MLflow or W&B, mapping run
  IDs to TRAINING_RESULTS.md; run lineage, hyperparameter logging, metric curves,
  mlruns, wandb.init, mlflow.start_run, program.md tracker declaration, experiment
  log. Activate alongside ml-training and llm-training-eval.
allowed-tools: [Read, Write, Edit, Glob, Grep, Bash]
compatibility: Claude Code
staleness_sensitive_sections:
  - "Tool Ecosystem"
  - "MLflow vs W&B Quick Comparison"
---

# Experiment Tracking

**ML experiment tracking is not application observability.** This distinction earns its own
top-level skill because the two domains are conceptually incompatible:

| Dimension | ML experiment tracking | App observability |
|---|---|---|
| Time horizon | Historical run lineage | Current system behavior |
| Data shape | Per-run records of hyperparameters, metrics, artifact URIs | Time-series of service-level signals |
| Decision model | Run-to-run comparison: keep or discard? | SLO alerting: is the system healthy? |
| Toolchain | MLflow / W&B / Aim | Prometheus / OpenTelemetry / Grafana |

Folding experiment tracking into the `observability` skill would produce a constantly-forking
document. The two disciplines share almost no tooling, vocabulary, or decision context.

**Satellite files** (loaded on-demand):

- [references/mlflow-integration.md](references/mlflow-integration.md) -- MLflow quickstart patterns for training loops; self-hosted tracking URI; run_tag mapping to TRAINING_RESULTS.md
- [references/wandb-integration.md](references/wandb-integration.md) -- W&B (wandb 0.25.1) quickstart patterns; project/entity convention; run_tag mapping to TRAINING_RESULTS.md

## Experiment Log — the ML Artifact Type

The **experiment log** is one of the six artifact types in Praxion's ML taxonomy (see
`ml-training` skill). An experiment log record contains:

- **Run metadata**: `run_id`, `run_tag`, `git_commit`, start/end timestamps, status
- **Hyperparameters**: learning rate, batch size, architecture choices — everything that varied
- **Metrics over time**: training loss curve, `val_bpb` trajectory, evaluation task scores
- **Artifact URIs**: paths to checkpoints saved during this run

Each training run produces exactly one experiment log entry. The tracker (MLflow or W&B)
is the durable store; `TRAINING_RESULTS.md` is the pipeline-facing summary (owned by the
`llm-training-eval` skill).

## Tool Ecosystem

<!-- last-verified: 2026-05-03 -->

Three tools cover the v1 scope. Pick one per project; `program.md` declares which.

| Tool | Type | Version (chub verified) | Best for |
|---|---|---|---|
| **MLflow** | OSS, self-hostable | `3.10.1` (chub maintainer doc) | Projects wanting local or team-hosted tracking with no cloud account |
| **W&B** | Cloud-native (OSS backend available) | `0.25.1` (chub maintainer doc) | Projects wanting a hosted UI, team collaboration, artifact versioning |
| **Aim** | OSS, local-first | latest as project pins | Lightweight OSS alternative; no cloud required; smaller community |

v1 integration references cover MLflow and W&B. Aim follows the same pattern but is not
a v1 reference target; reach for it when the project needs a fully local OSS stack without
MLflow's UI overhead.

## MLflow vs W&B Quick Comparison

<!-- last-verified: 2026-05-03 -->

| Concern | MLflow | W&B |
|---|---|---|
| Hosting | Self-hosted or Databricks-managed | W&B cloud (free tier) or self-hosted |
| Local-first | Yes — `./mlruns` by default | No — needs internet or self-hosted server |
| Team collaboration | Via shared tracking server | Built-in (entity/project model) |
| Artifact versioning | Via MLflow artifact store | Via W&B Artifacts (first-class feature) |
| Hyperparameter sweeps | Via MLflow Projects | Via Sweeps (built-in, Bayesian + grid) |
| Auth requirement | Optional (open server by default) | API key required (`WANDB_API_KEY`) |
| Run ID format | UUID (`run.info.run_id`) | Short alphanumeric (`run.id`) |
| Tracking URI config | `MLFLOW_TRACKING_URI` env or `set_tracking_uri()` | `WANDB_ENTITY` + `WANDB_PROJECT` env or `wandb.init()` |

**Decision heuristic**: choose MLflow when the project requires self-hosted or air-gapped
operation; choose W&B when team dashboards, sweep orchestration, or artifact versioning
are first-class needs.

## program.md Tracker Declaration

`program.md` at repo root MUST declare the tracker in use:

```markdown
## Tracker

mlflow   # or: wandb
```

`/run-experiment` reads this field to know where to stream metrics. Absence defaults to
MLflow. The tracker declaration is the single source of truth — do not configure it in
any other file.

## Reproducibility Minima

For a training run to be reproducible, the experiment log MUST record:

1. **Config snapshot** — the full hyperparameter dict (not a summary)
2. **Dataset version** — a hash, DVC pointer, or dataset artifact URI
3. **Code commit** — `git_commit` SHA linking code to run
4. **Environment hash** — `pip freeze` output or `conda env export` committed alongside
5. **Checkpoint path** — path to the best or final checkpoint for this run

Missing any of these makes the run unreproducible. Log all five at run start (config,
dataset version, commit, environment) and run end (checkpoint path).

## Integration with TRAINING_RESULTS.md

The `run_tag` field in `TRAINING_RESULTS.md` MUST match the tracker's run identifier so
results are cross-referenceable:

- **MLflow**: `run_tag` = `run.info.run_id` (UUID) or the `run_name` you pass to
  `mlflow.start_run(run_name=...)`
- **W&B**: `run_tag` = `run.id` (short alphanumeric) or the `name` you pass to
  `wandb.init(name=...)`

This cross-reference allows the verifier and `/check-experiment` to look up full metric
histories in the tracker given only the `TRAINING_RESULTS.md` file.

## Related Skills

| Skill | When to load it |
|---|---|
| `ml-training` | ML archetype vocabulary, six artifact types, operational modes, compute-budget requirements |
| `llm-training-eval` | TRAINING_RESULTS.md schema (the outcome that experiment tracking records); metric thresholds; verifier consumption |
| `neo-cloud-abstraction` | Backend dispatch and job lifecycle — the run that generates the experiment log |
| `observability` | App observability (RED/USE, OTel, Prometheus, Grafana) — distinct domain; do not conflate |
| `rules/ml/experiment-tracking-conventions.md` | Path-scoped conventions for `runs/`, `experiments/`, `program.md` |
