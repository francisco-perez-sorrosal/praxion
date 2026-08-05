# ML Experiment CI Patterns

CI patterns for ML training projects: eval-gated PRs, checkpoint artifacts, baseline diffing,
cost gating. Back to [../SKILL.md](../SKILL.md).

<!-- last-verified: 2026-08-05 -->

ML experiment CI differs from application CI in one fundamental way: the "pass" condition is a
**metric threshold**, not a binary test result. A PR that trains worse models should not merge,
even if all unit tests pass.

---

## Eval-Gated Pull Requests

Merge is blocked until an eval-aware CI run produces a `TRAINING_RESULTS.md` with
`verdict.acceptance_criteria_met: true`.

```yaml
# .github/workflows/eval-gate.yml
name: ML Eval Gate
on:
  pull_request:
    branches: [main]
    paths:
      - "**.py"
      - "configs/**"

jobs:
  eval-gate:
    runs-on: ubuntu-latest
    timeout-minutes: 60
    permissions:
      contents: read
      pull-requests: write    # for posting metric summary as PR comment
    steps:
      - uses: actions/checkout@<full-sha>
        with:
          persist-credentials: false

      - name: Run eval harness
        run: python eval/run_eval.py --config configs/eval.yaml

      - name: Check TRAINING_RESULTS verdict
        run: |
          python scripts/check_verdict.py .ai-work/eval-gate/TRAINING_RESULTS.md
          # exits non-zero if acceptance_criteria_met: false

      - name: Post metric summary to PR
        if: always()
        run: python scripts/post_metrics_comment.py
```

**Metric threshold source:** `SYSTEMS_PLAN.md` acceptance criteria use the threshold syntax
from `skills/llm-training-eval/SKILL.md` (e.g., `val_bpb < 1.75 ± 0.02`). The CI script
reads thresholds from the plan; do NOT hardcode them in workflow YAML.

**Absent `TRAINING_RESULTS.md`:** treat as WARN, not FAIL. The PR may be a non-training
change (data pipeline, architecture, infra). Use path filters (`paths:` trigger) to skip
the eval gate when only non-training files changed.

---

## Checkpoint Artifact Upload

Upload the best checkpoint as a CI artifact for post-run inspection and registry promotion.

```yaml
      - name: Upload best checkpoint
        uses: actions/upload-artifact@<full-sha>
        with:
          name: checkpoint-${{ github.sha }}
          path: ${{ steps.eval.outputs.best_checkpoint_path }}
          retention-days: 30
          if-no-files-found: warn
```

**Checkpoint path source:** read from `TRAINING_RESULTS.md` front-matter:
`checkpoints[].path` for the checkpoint with the best `val_bpb`. Pass it as a step
output from the eval step.

**Storage backends (v2):** GitHub does not document a universal per-artifact size cap. What
it documents is **artifact storage quota per plan** — Free **500 MB**, Pro **1 GB**, Team
**2 GB**, Enterprise Cloud **50 GB**. So the ceiling is plan-dependent, and on Free or Pro a
single checkpoint often exceeds the entire quota. (An earlier version of this file said
">2 GB", which conflated the Team-tier *account storage quota* with a per-artifact limit and
under-warned the two most common plans.)

Treat an external registry as the default for anything but the smallest checkpoints: upload
to W&B model registry (`wandb artifact put`) or MLflow model registry instead of GitHub
artifacts. Reference path in `TRAINING_RESULTS.md` `checkpoints[].path` stays the same
regardless of backend.

---

## Baseline Diffing

Compare the current PR's `val_bpb` against a registered baseline. Emit the delta in a PR
comment and mark WARN if regression exceeds tolerance.

**Baseline sources (in priority order):**

1. `.ai-state/baselines/val_bpb.yaml` — project-maintained baseline file committed to repo
2. Latest "kept" run in `.ai-state/training_runs/` — most recent archived TRAINING_RESULTS.md
3. `SYSTEMS_PLAN.md` metric threshold — the acceptance criterion itself is the floor

```yaml
      - name: Diff against baseline
        run: |
          python scripts/baseline_diff.py \
            --results .ai-work/eval-gate/TRAINING_RESULTS.md \
            --baseline .ai-state/baselines/val_bpb.yaml \
            --tolerance 0.02
          # writes delta to $GITHUB_STEP_SUMMARY (visible in Actions UI)
```

**Delta format in PR comment:**

```text
val_bpb: 1.73 → 1.71 (Δ -0.02) ✅ improvement
val_bpb: 1.73 → 1.76 (Δ +0.03) ⚠️ regression — within 0.02 tolerance
val_bpb: 1.73 → 1.81 (Δ +0.08) ❌ regression — exceeds tolerance
```

---

## Triggered Experiment Dispatch

Long training runs belong to `workflow_dispatch`, not push-triggered CI. Experiments are
expensive and intentional — not gated on every commit.

```yaml
name: Experiment Dispatch
on:
  workflow_dispatch:
    inputs:
      experiment_config:
        description: "Path to experiment config YAML"
        required: true
        default: "configs/experiments/baseline.yaml"
      gpu_hours_budget:
        description: "GPU-hours budget for this run"
        required: true
        default: "2.0"
      dataset_version:
        description: "Dataset version tag (git ref or artifact tag)"
        required: false
        default: "latest"
```

**Budget gate:** before dispatching, validate that `gpu_hours_budget` ≤ project ceiling.
See `skills/deployment/references/gpu-compute-budgeting.md` for the three-regime cost model
and the pre-dispatch validation contract.

---

## Integration with TRAINING_RESULTS.md

The CI job is the writer; the verifier is the reader.

| Actor | File location | Action |
|---|---|---|
| CI eval script | `.ai-work/<task-slug>/TRAINING_RESULTS.md` | writes after run completes |
| GitHub Actions artifact step | `actions/upload-artifact` | archives the file as a CI artifact |
| Verifier (Phase 3a) | `.ai-work/<task-slug>/TRAINING_RESULTS.md` | reads front-matter; evaluates metric thresholds |
| PR comment script | — | reads `metrics.*` and `verdict.*`; formats summary |

**Schema reference:** `skills/llm-training-eval/references/training-results-schema.md` —
authoritative field layout, status enum, verdict block.

---

## Cost Gating in CI

For Mode C (remote dispatch via SkyPilot or RunPod), refuse to start the workflow if the
declared `gpu_hours_budget` would exceed the project policy cap.

```yaml
      - name: Pre-dispatch cost gate
        run: |
          python scripts/cost_gate.py \
            --budget ${{ github.event.inputs.gpu_hours_budget }} \
            --config .ai-state/gpu_budget.yaml
          # exits non-zero if budget exceeds project ceiling
```

**Local backend (Modes A/B):** cost gate passes trivially — `pricing_query()` returns `0.0`.
No confirmation step needed. See `skills/deployment/references/gpu-compute-budgeting.md`
for the Mode B clarification on why `0.0` is correct even for rented boxes.

---

## Cross-References

- **Metric threshold syntax:** [llm-training-eval/SKILL.md](../../llm-training-eval/SKILL.md) — PASS/FAIL/WARN classification with tolerance bands
- **TRAINING_RESULTS.md schema:** [llm-training-eval/references/training-results-schema.md](../../llm-training-eval/references/training-results-schema.md) — full field layout
- **Budget enforcement:** [deployment/references/gpu-compute-budgeting.md](../../deployment/references/gpu-compute-budgeting.md) — three-regime model, pre-dispatch validation
- **Backend dispatch:** [neo-cloud-abstraction/SKILL.md](../../neo-cloud-abstraction/SKILL.md) — `training_job_descriptor`, `workflow_dispatch` → backend mapping
- **Operational modes:** [ml-training/references/operational-modes.md](../../ml-training/references/operational-modes.md) — Mode A / B / C full walkthroughs
