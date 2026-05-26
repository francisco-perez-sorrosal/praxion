# W&B (Weights & Biases) Integration

Integration recipe for connecting a training loop to Weights & Biases experiment tracking.
Back to [SKILL.md](../SKILL.md).

Curated chub reference: `wandb/package` (maintainer, Python, `0.25.1`). Fetch for
current endpoint signatures: `chub get wandb/package --lang python`.

<!-- last-verified: 2026-05-03 -->

## Contents

- [Version Note](#version-note)
- [Install](#install)
- [Authentication](#authentication)
- [Project and Entity Convention](#project-and-entity-convention)
- [Core Training Loop Pattern](#core-training-loop-pattern)
- [Mapping run.id to TRAINING_RESULTS.md](#mapping-runid-to-training_resultsmd)
- [Offline / Air-Gapped Use](#offline--air-gapped-use)
- [Reproducibility Fields to Log](#reproducibility-fields-to-log)

## Version Note

W&B `0.25.1` is the chub-verified version used here. The SYSTEMS_PLAN specifies this as
the v1 reference version. If the project pins a different `wandb` version, match that
instead.

## Install

```bash
pip install "wandb==0.25.1"
# or with uv:
uv add wandb==0.25.1
```

## Authentication

W&B requires an API key. Set it via environment variable — never hardcode it:

```bash
export WANDB_API_KEY="your-api-key"
```

For a self-hosted W&B instance:

```bash
export WANDB_API_KEY="your-api-key"
export WANDB_BASE_URL="https://wandb.your-org.com"
```

## Project and Entity Convention

W&B organizes runs by **entity** (user or team) and **project** (experiment group):

- **Entity**: your W&B username or team name (e.g., `my-team`)
- **Project**: corresponds to the model or experiment group (e.g., `my-model-pretraining`)

For ML projects with a `program.md` meta-prompt, the convention is:

- Entity: the team or user name from `WANDB_ENTITY` env
- Project: the repo name or model name (set once in `program.md`'s `Tracker` section or in `wandb.init(project=...)`)

## Core Training Loop Pattern

Call `wandb.init()` at run start, `run.log()` per step, and `run.finish()` at the end.
Use the context manager form to ensure `finish()` is always called:

```python
import os
import wandb

run = wandb.init(
    project="my-model-pretraining",
    entity=os.environ.get("WANDB_ENTITY"),
    name="run-001-lr3e4",           # human-readable tag; maps to run_tag in TRAINING_RESULTS.md
    config={
        "learning_rate": 3e-4,
        "batch_size": 32,
        "num_layers": 12,
        "git_commit": git_commit_sha,
        "dataset_version": dataset_hash,
    },
)

for step, batch in enumerate(train_loader):
    loss = train_step(batch)
    val_bpb = compute_val_bpb()     # on validation set

    run.log({
        "train_loss": loss,
        "val_bpb": val_bpb,
        "step": step,
    })

# Log checkpoint as artifact
artifact = wandb.Artifact(name="best-checkpoint", type="model")
artifact.add_file("checkpoints/best.pt")
run.log_artifact(artifact)

# Capture the run identifier for TRAINING_RESULTS.md
run_id = run.id       # short alphanumeric (e.g., "2k3m5n8p")
run_name = run.name   # "run-001-lr3e4"

run.finish()
```

## Mapping run.id to TRAINING_RESULTS.md

Set `run_tag` in `TRAINING_RESULTS.md` to the `name` you pass to `wandb.init()`. The
`run.id` (short alphanumeric) is the stable cross-reference for W&B API lookups:

```yaml
# In TRAINING_RESULTS.md
run_id: "2k3m5n8p"          # W&B run.id — stable alphanumeric cross-reference
run_tag: "run-001-lr3e4"    # matches name= in wandb.init()
```

To look up a run later via the W&B API:

```python
import wandb

api = wandb.Api()
run = api.run(f"{entity}/{project}/{run_id}")
print(run.summary)        # final metric values
print(run.history())      # full metric time series
```

## Offline / Air-Gapped Use

For environments without internet access, run W&B offline:

```bash
export WANDB_MODE=offline
```

Runs are stored locally under `./wandb/`. Sync to the server later with:

```bash
wandb sync ./wandb/run-<run-id>
```

## Reproducibility Fields to Log

Per the reproducibility minima in the parent skill, include these in the `config` dict
passed to `wandb.init()`:

```python
config={
    "git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"]).decode().strip(),
    "dataset_version": dataset_hash,       # sha256 of the dataset manifest
    "wandb_version": wandb.__version__,
    # ... hyperparameters
}
```

W&B automatically captures the host environment (Python version, OS, GPU info) in
the run's system metrics — no manual logging needed.
