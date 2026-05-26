# experiment-tracking

ML experiment lineage tracking for Praxion ML/AI projects. Covers the experiment log
artifact — per-run hyperparameters, metrics (val_bpb, loss curves), artifact URIs, and
run-to-run comparison. Distinct from application observability (RED/OTel/Prometheus/Grafana):
experiment tracking records historical run lineage and enables keep-or-discard decisions;
observability monitors current system behavior. Supports MLflow, W&B (Weights & Biases),
and Aim; `program.md` declares which tracker the project uses.

## When to Use

- Setting up experiment tracking for a training project (connecting the training loop to MLflow or W&B)
- Mapping run IDs to `TRAINING_RESULTS.md` for cross-reference
- Configuring `program.md` tracker declaration (`mlflow` or `wandb`)
- Understanding the experiment log artifact and reproducibility minima
- Choosing between MLflow (self-hosted) and W&B (cloud-native)

## Activation

Auto-triggers on: `mlflow`, `wandb`, `mlflow.start_run`, `wandb.init`, `mlruns`,
`experiment tracking`, `run lineage`, `hyperparameter logging`, `metric curves`,
`program.md tracker declaration`, `experiment log`, `W&B`, `Weights & Biases`.

## Skill Contents

**SKILL.md sections:**
- Experiment Log — the ML Artifact Type — what an experiment log record contains
- Tool Ecosystem — MLflow, W&B, Aim version table; v1 coverage scope
- MLflow vs W&B Quick Comparison — hosting, local-first, auth, run ID formats
- program.md Tracker Declaration — the single source of truth for tracker choice
- Reproducibility Minima — five required log fields; when a run is reproducible
- Integration with TRAINING_RESULTS.md — run_tag cross-reference protocol
- Related Skills

**References (loaded on demand):**
- `references/mlflow-integration.md` — MLflow `3.10.1` quickstart; tracking URI convention;
  core training loop pattern; run_id mapping; self-hosted server; reproducibility fields
- `references/wandb-integration.md` — W&B `0.25.1` quickstart; auth; entity/project convention;
  training loop pattern; run.id mapping; offline/air-gapped use; reproducibility fields

## Related Skills

- `ml-training` — ML archetype vocabulary, six artifact types, operational modes, compute-budget requirements
- `llm-training-eval` — TRAINING_RESULTS.md schema (the outcome that experiment tracking records)
- `neo-cloud-abstraction` — backend dispatch and job lifecycle — the run that generates the experiment log
- `observability` — app observability (RED/USE, OTel, Prometheus, Grafana); distinct domain
