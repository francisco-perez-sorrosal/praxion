# TRAINING_RESULTS.md — Canonical Schema

Schema reference for `TRAINING_RESULTS.md`. Owned by the `llm-training-eval` skill.
Back to [SKILL.md](../SKILL.md).

<!-- last-verified: 2026-05-03 -->

## Contents

- [Schema Overview](#schema-overview)
- [Canonical YAML Front-Matter](#canonical-yaml-front-matter)
- [Field Constraints](#field-constraints)
- [Markdown Body](#markdown-body)
- [Dual Lifecycle](#dual-lifecycle)
- [Verifier Consumption (Phase 3a)](#verifier-consumption-phase-3a)
- [Schema Versioning](#schema-versioning)
- [Minimal Valid Example](#minimal-valid-example)

---

## Schema Overview

`TRAINING_RESULTS.md` is a **YAML front-matter + Markdown body** file. The front-matter
is the machine-readable contract (consumed by verifier and `/check-experiment`). The
Markdown body is the human-readable narrative (written by `/run-experiment` or the
autonomous experiment loop).

**Writer:** `/run-experiment` command (or the project's autonomous experiment loop)
**Readers:** `verifier` (Phase 3a metric threshold evaluation), `/check-experiment`

---

## Canonical YAML Front-Matter

```yaml
---
schema_version: "1.0"            # Required. Increment major on breaking changes.

# Run identity
run_id: <string>                 # Required. Unique run identifier. Use UUID or
                                 # a content-addressed slug (e.g., "run-a3f2b1").
run_tag: <string>                # Required. Human-readable label for this run
                                 # (e.g., "run-001-lr3e4-bs32"). Must match the
                                 # experiment tracker's run ID (MLflow / W&B) so
                                 # results are cross-referenceable.
git_commit: <sha>                # Required. Full SHA of HEAD at dispatch time.
descriptor: <path>               # Optional. Path to the training_job_descriptor
                                 # YAML file used for this run.
backend: local | skypilot | runpod-direct | <other>
                                 # Required. The neo-cloud backend that executed
                                 # the run. Derived from neo_cloud_backend.yaml.

# Timestamps
started_at: <ISO 8601>           # Required. UTC timestamp when dispatch began.
completed_at: <ISO 8601>         # Required. UTC timestamp when run terminated
                                 # (completed, failed, cancelled, or timed out).

# Status
status: completed | failed | crashed | timeout | cancelled | budget_exhausted
                                 # Required. Terminal state of the run.
crash_reason: <string>           # Optional. Populated only when status = crashed
                                 # or failed. Short human-readable error summary.

# Resources
resources_used:
  gpu_hours: <float>             # Required. GPU-hours consumed (0.0 for CPU-only).
  wall_clock_seconds: <int>      # Required. Elapsed wall-clock time in seconds.
  actual_cost_usd: <float>       # Required. Monetary cost. Set to 0.0 for local
                                 # backend (no billing). SkyPilot and RunPod
                                 # backends populate from provider cost APIs.

# Metrics
metrics:
  val_bpb: <float>               # Required for pre-training. Validation
                                 # bits-per-byte (lower=better; vocab-independent).
                                 # Formula: cross_entropy_nats / (log(2) × total_bytes)
  val_perplexity: <float>        # Optional. Vocab-dependent secondary metric.
                                 # Use only when tokenizer is fixed across runs.
  train_loss_final: <float>      # Optional. Final training loss at run end.
                                 # Useful for diagnosing training stability.
  eval_harness: {}               # Optional. lm-evaluation-harness output dict,
                                 # keyed by task name (e.g., {"hellaswag": 0.412}).
                                 # Populated when the harness was run post-training.

# Checkpoints
checkpoints:
  - step: <int>                  # Training step at which checkpoint was saved.
    path: <string>               # URI or local path to the checkpoint file.
    val_bpb: <float>             # val_bpb at this checkpoint step (optional but
                                 # recommended for curve analysis).

# Verdict
verdict:
  acceptance_criteria_met: <bool>     # Required. True only if ALL metric-threshold
                                      # AC items in SYSTEMS_PLAN.md were PASS.
  tolerance_band_applied: <bool>      # Required. True if any AC used a ± band.
  notes: <string>                     # Optional. Free-form evaluation summary.
---
```

---

## Field Constraints

| Field | Required | Type | Notes |
|---|---|---|---|
| `schema_version` | Yes | string | `"1.0"` for v1 schema; quoted to avoid YAML float coercion |
| `run_id` | Yes | string | Unique per run; UUID or content-addressed slug |
| `run_tag` | Yes | string | Must match tracker run ID for cross-referenceability |
| `git_commit` | Yes | string | Full 40-char SHA; short SHAs are not accepted |
| `descriptor` | No | string | Relative or absolute path |
| `backend` | Yes | enum | `local \| skypilot \| runpod-direct \| <other>` |
| `started_at` | Yes | ISO 8601 | UTC; include timezone offset or `Z` suffix |
| `completed_at` | Yes | ISO 8601 | UTC; same format as `started_at` |
| `status` | Yes | enum | See valid values above |
| `crash_reason` | No | string | Omit when `status ∈ {completed, cancelled, budget_exhausted}` |
| `resources_used.gpu_hours` | Yes | float | `0.0` for CPU-only or local backend with no GPU |
| `resources_used.wall_clock_seconds` | Yes | int | Rounded to nearest second |
| `resources_used.actual_cost_usd` | Yes | float | `0.0` for local backend |
| `metrics.val_bpb` | Yes* | float | *Required for pre-training; omit only for non-language models |
| `metrics.val_perplexity` | No | float | Secondary; document the tokenizer if included |
| `metrics.train_loss_final` | No | float | Final step loss |
| `metrics.eval_harness` | No | dict | EleutherAI harness JSON output |
| `checkpoints` | No | list | Omit if no intermediate checkpoints were saved |
| `verdict.acceptance_criteria_met` | Yes | bool | Synthesized from verifier Phase 3a evaluation |
| `verdict.tolerance_band_applied` | Yes | bool | True if any AC declared `± <value>` |
| `verdict.notes` | No | string | One paragraph; omit if empty |

---

## Markdown Body

Below the YAML front-matter, the Markdown body provides human-readable narrative.
`/run-experiment` generates this body automatically; it may be edited by the user.

```markdown
# Training Results — <run-tag>

## Summary

[One paragraph: model, dataset, hyperparameter highlights, overall outcome.]

## Metrics

[Table or prose describing the primary metric results. If val_bpb improved over
baseline, state by how much. If the eval harness ran, summarize key task results.]

## Comparison

[Comparison vs. baseline or prior run. State the baseline source (run_tag or
threshold from SYSTEMS_PLAN.md). Highlight delta on val_bpb.]

## Notes

[Free-form analysis: what worked, what to try next, anomalies observed during
training (loss spikes, NaN gradients, OOM events).]
```

---

## Dual Lifecycle

**Ephemeral primary (always written):**
- Location: `.ai-work/<task-slug>/TRAINING_RESULTS.md`
- Written by: `/run-experiment` at run completion
- Read by: `verifier` Phase 3a during the current pipeline
- Deleted: with `.ai-work/<task-slug>/` at pipeline cleanup

**Archival copy (opt-in):**
- Location: `.ai-state/training_runs/<run-tag>.md`
- Written by: `/run-experiment` upon user confirmation ("Keep this run?")
- Triggered by: the autoresearch experiment loop's "kept" semantics — a run
  whose `val_bpb` improved over the prior kept run, or one the user explicitly
  marks to preserve
- Retained: indefinitely; committed to git; cross-pipeline reproducibility audit
- Naming: `<run-tag>.md` where `run-tag` matches the front-matter `run_tag` field

**Signaling the archival decision:**
- `status: completed` + user confirmation → archival copy written
- `status: failed | crashed | cancelled | budget_exhausted` → no archival copy
- `status: completed` + user declines → ephemeral copy only; deleted at cleanup
- The `archival_path` field is NOT present in the schema by design — the presence
  of the file at `.ai-state/training_runs/<run-tag>.md` IS the signal

---

## Verifier Consumption (Phase 3a)

The `verifier` agent reads `TRAINING_RESULTS.md` in Phase 3a under two conditions:
1. `SYSTEMS_PLAN.md` acceptance criteria contain metric threshold syntax
   (e.g., `val_bpb < 1.75`, `val_perplexity < 12.4`)
2. `.ai-work/<task-slug>/TRAINING_RESULTS.md` exists

**Verifier evaluation steps:**
1. Load this schema reference to understand field layout
2. Read `metrics.*` block from the YAML front-matter
3. For each metric-threshold AC item:
   - Parse syntax: `<metric> <op> <value>` or `<metric> <op> <value> ± <tolerance>`
   - Compare `metrics.<metric>` against the threshold
   - Classify: PASS / FAIL / WARN (see tolerance rules in `SKILL.md`)
4. Set `verdict.acceptance_criteria_met` to `true` iff all AC items are PASS
5. Emit findings in `VERIFICATION_REPORT.md`:
   ```
   [PASS] AC-3: val_bpb=1.72 vs threshold=1.75 (no tolerance band)
   [WARN] AC-4: val_bpb=1.76 vs threshold=1.75 ± 0.02 (within tolerance)
   [FAIL] AC-5: val_perplexity=14.1 vs threshold=12.4 (outside tolerance)
   ```

**When `TRAINING_RESULTS.md` is absent:**
```
[WARN] TRAINING_RESULTS.md not found — metric threshold criteria not evaluated.
Run /run-experiment and re-invoke verifier, or confirm training was not expected
for this step.
```

---

## Schema Versioning

`schema_version` is a quoted string (`"1.0"`) to prevent YAML from parsing it as a float.

| Version | Change |
|---|---|
| `"1.0"` | Initial schema (this document) |

**Versioning rules:**
- Additive fields (new optional fields): increment minor (`"1.0"` → `"1.1"`)
- Breaking changes (rename, type change, remove required field): increment major (`"1.0"` → `"2.0"`)
- Verifier checks `schema_version` and emits WARN if the version is newer than expected

---

## Minimal Valid Example

```yaml
---
schema_version: "1.0"
run_id: "a3f2b1c4-0001"
run_tag: "run-001-lr3e4-bs32"
git_commit: "d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3"
backend: local
started_at: "2026-05-03T08:00:00Z"
completed_at: "2026-05-03T09:45:00Z"
status: completed
resources_used:
  gpu_hours: 1.75
  wall_clock_seconds: 6300
  actual_cost_usd: 0.0
metrics:
  val_bpb: 1.73
  val_perplexity: 11.8
  train_loss_final: 2.41
verdict:
  acceptance_criteria_met: true
  tolerance_band_applied: false
  notes: "val_bpb 1.73 beats threshold 1.75 by 0.02. No tolerance band needed."
---

# Training Results — run-001-lr3e4-bs32

## Summary

Baseline run on autoresearch corpus with lr=3e-4, batch_size=32. val_bpb improved
from 1.81 (random init) to 1.73 after 1.75 GPU-hours on local backend (Mode A).

## Metrics

| Metric | Value | Threshold | Result |
|---|---|---|---|
| val_bpb | 1.73 | < 1.75 | PASS |
| val_perplexity | 11.8 | — | (informational) |

## Notes

Loss curve was stable throughout; no spikes detected. Next: try lr=1e-3.
```
