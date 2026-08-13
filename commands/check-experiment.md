---
description: "Poll or report an ML training run: in-flight status/metrics, or completed results with PASS/FAIL/WARN checks. Use after /run-experiment or before verifying."
argument-hint: "[<run_tag>] [--task-slug <slug>]"
allowed-tools: [Read, Bash, Glob]
---

Poll or report on an ML training experiment. Reads
[TRAINING_RESULTS.md](../skills/llm-training-eval/references/training-results-schema.md)
for completed runs; invokes
[neo-cloud-abstraction](../skills/neo-cloud-abstraction/SKILL.md) lifecycle ops for
in-flight runs.

## Arguments

- `$ARGUMENTS` is optional.
  - First positional arg (if present): `<run_tag>` — identifies the run to check
  - `--task-slug <slug>` — the active pipeline task slug; inferred from the nearest
    `.ai-work/` directory when absent

## Step 1 — Identify the Run

**Determine which run to check** (in priority order):

1. If `<run_tag>` was provided as a positional argument, use it. Skip to Step 2.
2. Otherwise, look for `.ai-work/<task-slug>/TRAINING_RESULTS.md`. If found, read
   its `run_tag` field from the YAML front-matter. Use that run_tag. Skip to Step 2.
3. Otherwise, list recent archived runs:

   ```bash
   ls -t .ai-state/training_runs/*.md 2>/dev/null | head -10
   ```

   Surface the list and ask the user which run to check. Use the selected file's
   basename (without `.md`) as the run_tag.

4. If no runs exist anywhere, surface:

   ```text
   No experiment runs found. Run /run-experiment to dispatch a training job.
   ```

   Stop.

## Step 2 — Read the Backend Configuration

Read `.ai-state/neo_cloud_backend.yaml` for the `backend:` key. If absent, default
to `local`. Load `skills/neo-cloud-abstraction/SKILL.md` for the lifecycle operations
(`status()`, `log_stream()`, `list()`, `pricing_query()`).

Attempt to resolve the backend `job_id` for lifecycle polling. The `job_id` is the
backend-assigned identifier from `create()` — it is not persisted in TRAINING_RESULTS.md.
If available in memory (current session), use it. Otherwise, lifecycle polling is
unavailable; skip to Step 4 and report from the file.

## Step 3 — Poll In-Flight Runs

**Only if `job_id` is available.** Call `status()` for the configured backend (see
`skills/neo-cloud-abstraction/SKILL.md §Lifecycle Operations`).

**If status is `pending` or `running`:**

Call `log_stream()` to fetch recent output. Extract metric lines containing `val_bpb`,
`val_loss`, `train_loss`, or `step`. Build a snapshot table:

```text
Step 3 — In-Flight Status
─────────────────────────────────────────────────
Run:      <run_tag>
Status:   running
Backend:  <backend>

Latest metrics (last 3 checkpoints):
  step   val_bpb   train_loss
  ----   -------   ----------
  500    1.82      2.61
  1000   1.79      2.48
  1500   1.76      2.37

Budget:   2.1 / 8.0 GPU-hours (26% used) ← WARN if > 80%
```

Emit a `[WARN]` line if GPU-hours consumed exceeds 80% of `gpu_hours_budget`:

```text
[WARN] Budget 80% consumed (6.5 / 8.0 GPU-hours). Consider /check-experiment again
       near completion or set a lower wall_clock_seconds_max.
```

Surface an actionable next-step:

```text
Next: Re-run /check-experiment to poll again, or wait for the run to complete and
      invoke /run-experiment (if retrying) or verifier.
```

**If status is terminal** (`completed | failed | crashed | timeout | cancelled | budget_exhausted`), proceed to Step 4.

## Step 4 — Report Completed Runs

Read the TRAINING_RESULTS.md file:

- Primary: `.ai-work/<task-slug>/TRAINING_RESULTS.md`
- Fallback: `.ai-state/training_runs/<run_tag>.md`

Parse the YAML front-matter per the reader contract in
`skills/llm-training-eval/references/training-results-schema.md`.

Surface a concise status report:

```text
Step 4 — Run Results
─────────────────────────────────────────────────
Run:       <run_tag>
Status:    <status>
Backend:   <backend>
Git:       <git_commit[:8]>

Resources used:
  GPU-hours:   <gpu_hours>
  Wall clock:  <wall_clock_seconds>s
  Cost (USD):  $<actual_cost_usd>

Metrics:
  val_bpb:          <value>
  val_perplexity:   <value>  (if present)
  train_loss_final: <value>  (if present)
```

If `status` is `failed` or `crashed` and `crash_reason` is populated, surface it:

```text
Crash reason: <crash_reason>
```

## Step 5 — Optional Acceptance Check

**This step is optional — skip if no metric-threshold ACs exist.**

Scan the active `SYSTEMS_PLAN.md` (or `WIP.md`) for acceptance criteria containing
metric threshold syntax (e.g., `val_bpb < 1.75`, `val_bpb < 1.75 ± 0.02`).

If metric-threshold ACs are found, apply the
[eval-driven-verification](../rules/ml/eval-driven-verification.md) PASS/FAIL/WARN
classification. **Do not redefine the classification logic here — cite the rule.**

Surface the AC check results:

```text
Acceptance check (rules/ml/eval-driven-verification.md):
  [PASS]  AC-1: val_bpb=1.72 vs threshold < 1.75
  [WARN]  AC-2: val_bpb=1.76 vs threshold < 1.75 ± 0.02 (within tolerance)
  [FAIL]  AC-3: val_perplexity=14.1 vs threshold < 12.4
```

Then surface an actionable next-step based on the result:

| Outcome | Next-step suggestion |
|---|---|
| All PASS | Invoke verifier — TRAINING_RESULTS.md is ready for Phase 3a |
| Any WARN | Invoke verifier — WARN findings will appear; consider re-running with adjusted hyperparams |
| Any FAIL | Re-run `/run-experiment` with adjusted hyperparams before invoking verifier |
| No metric ACs | (Skip this step) — non-metric ACs are evaluated by verifier standard Phase 3 |

## Cross-References

| Artifact | Role in this command |
|---|---|
| `skills/neo-cloud-abstraction/SKILL.md` | `status()`, `log_stream()`, `pricing_query()` lifecycle ops; Status enum |
| `skills/llm-training-eval/references/training-results-schema.md` | Reader contract for TRAINING_RESULTS.md fields |
| `rules/ml/eval-driven-verification.md` | PASS/FAIL/WARN classification for metric-threshold ACs |
| `/run-experiment` | Write-side companion — dispatches runs and writes TRAINING_RESULTS.md |
