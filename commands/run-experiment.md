---
description: >
  Dispatch an ML training experiment using the project's configured backend (local
  subprocess, SkyPilot, or RunPod direct). Reads the training_job_descriptor from
  the active WIP.md step, validates the compute budget is declared before dispatch,
  invokes the matching backend lifecycle operations, streams metrics to the configured
  experiment tracker (from program.md's tracker: declaration, or MLflow by default),
  writes TRAINING_RESULTS.md at .ai-work/<task-slug>/ on completion, and offers
  opt-in archival to .ai-state/training_runs/<run-tag>.md when the run is kept.
  Supports operational modes A (co-located owned GPU), B (co-located rented GPU box),
  and C (separated cloud via SkyPilot or RunPod direct). The same
  training_job_descriptor dispatches without modification in all three modes —
  only the backend configuration varies. Use when starting a training run,
  re-dispatching a failed run, or initiating an autonomous experiment loop (autoresearch is one such loop pattern).
argument-hint: [--descriptor <path>] [--task-slug <slug>]
allowed-tools: [Read, Write, Edit, Bash, Glob, AskUserQuestion]
disable-model-invocation: true
---

Dispatch a training experiment, validate the compute budget, stream metrics, and write
`TRAINING_RESULTS.md`. Integrates the [neo-cloud-abstraction](../skills/neo-cloud-abstraction/SKILL.md)
backend operations, [llm-training-eval](../skills/llm-training-eval/SKILL.md) results schema,
[experiment-tracking](../skills/experiment-tracking/SKILL.md) metric streaming, and
[gpu-budget-conventions](../rules/ml/gpu-budget-conventions.md) enforcement in one workflow.

## Arguments

- `$ARGUMENTS` is optional. Two optional flags:
  - `--descriptor <path>` — path to a `training_job_descriptor` YAML file; overrides the descriptor read from WIP.md
  - `--task-slug <slug>` — the active pipeline task slug; used to locate `.ai-work/<task-slug>/`; inferred from the nearest `.ai-work/` directory when absent

## Prerequisites

Load these skills before acting:

1. `skills/neo-cloud-abstraction/SKILL.md` — descriptor schema, 8 lifecycle operations, backend config convention
2. `skills/llm-training-eval/references/training-results-schema.md` — the writer-side contract for TRAINING_RESULTS.md
3. `skills/ml-training/SKILL.md` — ML artifact vocabulary, operational modes, program.md artifact type
4. `skills/experiment-tracking/SKILL.md` — tracker integration patterns, run_tag mapping

## Process

### 1. Read Experiment Configuration

**Locate the training_job_descriptor:**

- If `--descriptor <path>` was provided: read the descriptor from that path.
- Otherwise: read the active step in `.ai-work/<task-slug>/WIP.md` and extract the `training_job_descriptor` YAML block embedded in the step's body.

Parse the descriptor according to the schema in `skills/neo-cloud-abstraction/SKILL.md §training_job_descriptor`. Verify the descriptor contains **no `mode:` field** and **no `backend:` field** — if either is present, halt and instruct the user to remove it:

```text
The training_job_descriptor must not contain a mode: or backend: field.
These are backend configuration concerns, not descriptor fields.
Remove the field and re-run /run-experiment.
See skills/neo-cloud-abstraction/SKILL.md for the invariant schema.
```

**Read the git commit at HEAD:**

```bash
git rev-parse HEAD
```

Record the full 40-character SHA as `git_commit`.

### 2. Validate Compute Budget

**Before dispatching**, verify the compute budget is declared. Apply
[rules/ml/gpu-budget-conventions.md](../rules/ml/gpu-budget-conventions.md) and
[skills/deployment/references/gpu-compute-budgeting.md](../skills/deployment/references/gpu-compute-budgeting.md).

**Check `gpu_hours_budget` in the descriptor:**

```yaml
gpu_hours_budget: <float>   # must be present and > 0 for remote backends
```

If `gpu_hours_budget` is absent from the descriptor, **STOP** and emit:

```text
Budget not declared. Add gpu_hours_budget: <float> to the training_job_descriptor
before dispatching. Remote backends require a non-zero budget cap.
See rules/ml/gpu-budget-conventions.md for the required field format.
```

If the backend is `local` and `gpu_hours_budget` is `0.0`, this is acceptable — owned
hardware has no monetary cap. Proceed.

**Check the WIP.md step for `gpu_hours_budget`:** The active step must also carry a
`gpu_hours_budget:` field at the step level (per `rules/ml/gpu-budget-conventions.md`).
If absent from WIP.md, emit a WARN (not a STOP):

```text
[WARN] Active WIP.md step does not declare gpu_hours_budget. The verifier will emit
a FAIL finding when reviewing this step. Add gpu_hours_budget: <float> to the step.
```

### 3. Detect Backend and Load Reference

Read the project's backend configuration:

```text
.ai-state/neo_cloud_backend.yaml
```

Parse the `backend:` key. Expected values: `local`, `skypilot`, `runpod-direct`.
If the file is absent, default to `local` and note:

```text
neo_cloud_backend.yaml not found — defaulting to backend: local (Mode A/B).
To use SkyPilot or RunPod direct, create .ai-state/neo_cloud_backend.yaml.
See skills/neo-cloud-abstraction/SKILL.md §Tiered Backend Strategy.
```

Load the matching backend reference for the operation details:

| `backend:` value | Reference file to load |
|---|---|
| `local` | `skills/neo-cloud-abstraction/references/local-backend.md` |
| `skypilot` | `skills/neo-cloud-abstraction/references/skypilot-backend.md` |
| `runpod-direct` | `skills/neo-cloud-abstraction/references/runpod-direct-adapter.md` |

The backend reference describes how to invoke each lifecycle operation for that backend.
Record `started_at` as the current UTC timestamp.

### 4. Dispatch

Invoke the `create()` lifecycle operation for the detected backend, passing the
descriptor. The backend assigns `job_id` and returns it.

Then invoke `start()` with the returned `job_id` (some backends no-op `start()`;
others require an explicit start call — see the backend reference).

Surface the dispatch confirmation:

```text
Dispatched <run_tag> to <backend> backend. job_id=<job_id>.
Monitoring execution...
```

### 5. Stream Metrics

**Detect the configured tracker.** Read `program.md` at the project root and extract
the `tracker:` key. Accepted values: `mlflow`, `wandb`, `aim`. If `program.md` is absent
or has no `tracker:` key, default to `mlflow` and note this to the user.

Load the matching tracker integration reference for streaming patterns:

| `tracker:` value | Reference file to load |
|---|---|
| `mlflow` | `skills/experiment-tracking/references/mlflow-integration.md` |
| `wandb` | `skills/experiment-tracking/references/wandb-integration.md` |

**Poll `log_stream()` during execution.** Use the backend's `log_stream()` operation
(see the backend reference) to stream stdout/stderr. Surface key metric lines as they
appear (look for lines containing `val_bpb`, `val_loss`, `train_loss`, `step`).

Monitor for terminal status using `status()`. Expected terminal values:
`completed | failed | crashed | timeout | cancelled | budget_exhausted`.

The `run_tag` written to the tracker's run must match the descriptor's `run_tag` field
exactly, so that `TRAINING_RESULTS.md` and the tracker's record are cross-referenceable.
See `skills/experiment-tracking/SKILL.md §Integration with TRAINING_RESULTS.md`.

**On `budget_exhausted`:** this is NOT a failure. It is the expected termination path
when the budget cap is reached. Preserve checkpoints; proceed to completion handling.

### 6. Write TRAINING_RESULTS.md

When `status()` returns a terminal value, call `artifact_fetch()` for the paths listed
in the descriptor's `artifact_paths` field.

Record `completed_at` as the current UTC timestamp.

Write `TRAINING_RESULTS.md` at `.ai-work/<task-slug>/TRAINING_RESULTS.md`. Use the
**writer-side contract** in
`skills/llm-training-eval/references/training-results-schema.md`. The file is
YAML front-matter followed by Markdown sections.

Populate the front-matter from the run's observed values:

- `schema_version`: `"1.0"` (quoted string — never bare float)
- `run_id`: a UUID or content-addressed slug (generate if the backend did not assign one)
- `run_tag`: from the descriptor's `run_tag` field
- `git_commit`: the 40-char SHA recorded in Step 1
- `backend`: the detected backend value (`local | skypilot | runpod-direct`)
- `descriptor`: path to the descriptor YAML if `--descriptor` was provided; omit otherwise
- `started_at` / `completed_at`: UTC ISO 8601 timestamps
- `status`: the terminal status from `status()`
- `crash_reason`: populate only if `status ∈ {crashed, failed}`
- `resources_used.gpu_hours`: from backend cost API or tracker; `0.0` for local
- `resources_used.wall_clock_seconds`: elapsed seconds between `started_at` and `completed_at`
- `resources_used.actual_cost_usd`: from `pricing_query()` × elapsed GPU-hours; `0.0` for local
- `metrics.*`: extract from the tracker's run record or from the backend's log output
- `checkpoints`: list any checkpoint paths returned by `artifact_fetch()`
- `verdict`: populate `acceptance_criteria_met` and `tolerance_band_applied` based on
  the SYSTEMS_PLAN.md metric-threshold acceptance criteria; leave to the verifier if
  thresholds are not yet declared

Generate the Markdown body sections (Summary, Metrics, Comparison, Notes) following
the template in the schema reference.

### 7. Archive on Kept Run (opt-in)

After writing the ephemeral `TRAINING_RESULTS.md`, ask:

```text
Run <run_tag> completed with status: <status>.
Archive this result? It will be copied to .ai-state/training_runs/<run-tag>.md
and committed with the experiment-mode git convention
(exp(<run-tag>): val_bpb=<metric> gpu_h=<hours>).
[Yes / No]
```

**Archive rules** (per the dual lifecycle in the schema reference):

- `status: completed` AND user confirms → write archival copy; update `program.md §Current Run`
- `status: failed | crashed | cancelled | budget_exhausted` → do NOT offer archival
- `status: completed` AND user declines → ephemeral copy only; deleted at pipeline cleanup

**When archiving:**

1. Copy `.ai-work/<task-slug>/TRAINING_RESULTS.md` to `.ai-state/training_runs/<run-tag>.md`
2. Offer to stage and commit the archival files:
   - `TRAINING_RESULTS.md` archival copy at `.ai-state/training_runs/<run-tag>.md`
   - `program.md` with the updated `§Current Run` and `§History` blocks
   - Commit message format per `rules/swe/vcs/git-conventions.md §Experiment-mode branches`:
     `exp(<run-tag>): val_bpb=<metric> gpu_h=<hours>`
3. Do NOT commit automatically — stage the files and present the `git diff --staged`
   to the user for review before committing

## Exit Conditions

| Status at exit | Outcome | Action |
|---|---|---|
| `completed` | Run succeeded | TRAINING_RESULTS.md written; archival offered |
| `budget_exhausted` | Budget cap reached | TRAINING_RESULTS.md written; checkpoints preserved; no archival offered |
| `cancelled` | User cancelled mid-run | TRAINING_RESULTS.md written with partial metrics if available; no archival offered |
| `failed \| crashed` | Run errored | TRAINING_RESULTS.md written with `crash_reason`; no archival offered |
| Budget not declared | Pre-flight blocked | STOP before dispatch; user must add `gpu_hours_budget` |
| Descriptor has `mode:` or `backend:` field | Schema violation | STOP before dispatch; user must remove the field |

## Cross-References

| Artifact | Role in this command |
|---|---|
| `skills/neo-cloud-abstraction/SKILL.md` | Descriptor schema; 8 lifecycle operations; backend selection |
| `skills/neo-cloud-abstraction/references/local-backend.md` | Dispatch + streaming for Mode A/B |
| `skills/neo-cloud-abstraction/references/skypilot-backend.md` | Dispatch + streaming for Mode C (SkyPilot) |
| `skills/neo-cloud-abstraction/references/runpod-direct-adapter.md` | Dispatch + streaming for Mode C (RunPod) |
| `skills/llm-training-eval/references/training-results-schema.md` | Writer-side contract for TRAINING_RESULTS.md |
| `skills/experiment-tracking/references/mlflow-integration.md` | MLflow metric streaming patterns |
| `skills/experiment-tracking/references/wandb-integration.md` | W&B metric streaming patterns |
| `skills/deployment/references/gpu-compute-budgeting.md` | Budget regime details; cost estimation by backend |
| `rules/ml/gpu-budget-conventions.md` | Budget validation discipline; FAIL-if-absent rule |
| `rules/ml/experiment-tracking-conventions.md` | run_tag ↔ tracker ID mapping; program.md tracker: key |
| `rules/swe/vcs/git-conventions.md §Experiment-mode branches` | Kept-run commit format; git reset --hard semantics |
| `/check-experiment` | Status-check companion for in-flight and completed runs |
