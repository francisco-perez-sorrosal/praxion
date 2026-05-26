# MLflow Integration

Integration recipe for connecting a training loop to MLflow experiment tracking.
Back to [SKILL.md](../SKILL.md).

Curated chub reference: `mlflow/package` (maintainer, Python, `3.10.1`). Fetch for
current endpoint signatures: `chub get mlflow/package --lang python`.

<!-- last-verified: 2026-05-03 -->

## Contents

- [Version Note](#version-note)
- [Install](#install)
- [Tracking URI Convention](#tracking-uri-convention)
- [Core Training Loop Pattern](#core-training-loop-pattern)
- [Mapping run_id to TRAINING_RESULTS.md](#mapping-run_id-to-training_resultsmd)
- [Self-Hosted Tracking Server (Team Use)](#self-hosted-tracking-server-team-use)
- [Reproducibility Fields to Log](#reproducibility-fields-to-log)

## Version Note

MLflow `3.10.1` is the chub-verified current version. MLflow 3 introduced first-class
Logged Models and `model_id`. Older codebases may use run-artifact URIs
(`runs:/<run_id>/model`) rather than model IDs — both are valid in 3.x.

## Install

```bash
pip install "mlflow==3.10.1"
# or with uv:
uv add mlflow==3.10.1
```

## Tracking URI Convention

For **local tracking** (modes A and B), MLflow writes to `./mlruns` by default. To
redirect to `.ai-state/mlflow/` (shared across pipeline runs):

```python
import mlflow

mlflow.set_tracking_uri(".ai-state/mlflow")
```

For a **shared remote server** (team use or mode C):

```bash
export MLFLOW_TRACKING_URI="http://your-mlflow-server:5000"
```

Praxion recommends `.ai-state/mlflow/` for local projects so the tracking store is
co-located with other `.ai-state/` artifacts. Add `mlruns/` to `.gitignore` (the
checkpoint gitignore block in Phase 8c covers this).

## Core Training Loop Pattern

Wrap your training loop with `mlflow.start_run()`. Log hyperparameters at the start,
metrics per step, and checkpoint paths at the end:

```python
import mlflow

mlflow.set_tracking_uri(".ai-state/mlflow")
mlflow.set_experiment("my-model-pretraining")

with mlflow.start_run(run_name="run-001-lr3e4") as run:
    # Log hyperparameters once at run start
    mlflow.log_params({
        "learning_rate": 3e-4,
        "batch_size": 32,
        "num_layers": 12,
        "git_commit": git_commit_sha,
        "dataset_version": dataset_hash,
    })

    for step, batch in enumerate(train_loader):
        loss = train_step(batch)
        val_bpb = compute_val_bpb()  # on validation set

        # Log metrics per training step
        mlflow.log_metrics({
            "train_loss": loss,
            "val_bpb": val_bpb,
        }, step=step)

    # Log checkpoint as artifact at run end
    mlflow.log_artifact("checkpoints/best.pt", artifact_path="checkpoints")

    # Capture the run identifier for TRAINING_RESULTS.md
    run_id = run.info.run_id          # UUID — use as run_tag
    run_name = run.info.run_name      # "run-001-lr3e4"
```

## Mapping run_id to TRAINING_RESULTS.md

Set `run_tag` in `TRAINING_RESULTS.md` to the MLflow `run.info.run_id` (UUID) or the
`run_name` you pass to `start_run()`. The `run_name` is more human-readable; the `run_id`
is the stable cross-reference:

```yaml
# In TRAINING_RESULTS.md
run_id: "a1b2c3d4e5f6..."          # optional; the MLflow run UUID
run_tag: "run-001-lr3e4"           # matches run_name in mlflow.start_run()
```

To look up a run later:

```python
import mlflow

client = mlflow.tracking.MlflowClient()
run = client.get_run(run_id)
print(run.data.metrics)
```

## Self-Hosted Tracking Server (Team Use)

Start the server with:

```bash
mlflow server \
  --backend-store-uri sqlite:///mlflow.db \
  --default-artifact-root ./mlflow-artifacts \
  --host 0.0.0.0 \
  --port 5000
```

Point training code at it via `MLFLOW_TRACKING_URI=http://<server-ip>:5000`.

## Reproducibility Fields to Log

Per the reproducibility minima in the parent skill, log these at every run:

```python
mlflow.log_params({
    "git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"]).decode().strip(),
    "dataset_version": dataset_hash,          # sha256 of the dataset manifest
    "environment": open("requirements.txt").read(),  # or: pip freeze output
})
```
