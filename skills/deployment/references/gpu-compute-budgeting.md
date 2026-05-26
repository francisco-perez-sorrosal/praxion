# GPU Compute Budgeting
<!-- last-verified: 2026-05-03 -->

Discipline for declaring, estimating, and enforcing GPU compute budgets in Praxion ML projects.
Back to [SKILL.md](../SKILL.md).

GPU compute has **three distinct cost regimes** depending on operational mode. Budget discipline
differs across them; do not conflate Modes A/B with Mode C.

| Regime | Operational mode | Cost shape | Budget discipline |
|---|---|---|---|
| **Owned-local** | Mode A (Mac M-series, RTX, on-prem) | $0/hr explicit; VRAM-bound; wall-clock-bound | Enforce via `wall_clock_seconds_max`; no $/hr to track |
| **Rented-local** | Mode B (rented GPU box, Praxion runs there) | $/hr contract-side; `pricing_query()` returns `0.0` | Track wall-clock × $/hr manually; Praxion sees it as local |
| **Remote-via-dispatch** | Mode C (laptop → SkyPilot or RunPod direct) | $/hr per backend + spot reclamation risk | `/run-experiment` calls `pricing_query()` before dispatch; backends pre-empt on budget exhaustion |

> **Mode B clarification:** the rented box's $/hr cost is on your rental invoice, not visible
> to Praxion. `pricing_query()` returns `0.0` for the local backend (same as Mode A). Track
> rental cost separately in a WIP.md step comment or project note.

For the `pricing_query()` canonical pattern and why `0.0` is correct, see
[neo-cloud-abstraction/references/local-backend.md](../../neo-cloud-abstraction/references/local-backend.md).

## The `gpu_hours_budget` Field

The `gpu_hours_budget` field in `training_job_descriptor` is **defined in
`skills/neo-cloud-abstraction/SKILL.md`** — the abstraction owns the schema. This reference
teaches how to *use* the field correctly across the three regimes.

**Declaration pattern — two locations:**

```yaml
# .ai-state/gpu_budget.yaml  (project-level ceiling)
project_gpu_hours_budget: 20.0          # total budget for this project's training work

# WIP.md step (step-level budget for one run)
## Step N: Fine-tune on augmented dataset
gpu_hours_budget: 2.0
acceptance_criteria:
  - val_bpb < 1.72  OR  budget_consumed >= 2.0 GPU-hours (whichever first)
```

The step-level `gpu_hours_budget` feeds into the `training_job_descriptor` for `/run-experiment`.
The project-level ceiling is a soft guardrail — sentinel warns when the sum of step budgets
exceeds it.

## Budget Gate — Acceptance Criterion Pattern

Step acceptance criteria in ML projects MUST be one of:

- **Metric threshold**: `val_bpb < 1.75` — run until metric reached OR budget exhausted
- **Budget gate**: `step completes when budget consumed OR metric reached, whichever first`
- **Hard limit**: budget exhaustion alone is the criterion (exploratory runs, ablations)

The `budget_exhausted` status in `TRAINING_RESULTS.md` signals a budget gate was hit. The
verifier treats `budget_exhausted` as PASS if the AC was `budget gate` and FAIL if the AC
required a specific metric threshold.

## Pre-Dispatch Validation

Before `/run-experiment` dispatches a job, it MUST validate:

1. `gpu_hours_budget` is present in the descriptor — refuse dispatch if absent
2. `pricing_query(gpu_type, gpu_count)` × `gpu_hours_budget` ≤ remaining project budget
3. For Mode C only: surface the estimated cost to the user and require confirmation if
   estimated cost > `$10` (configurable threshold)

If validation fails, `/run-experiment` halts with a clear error — it does NOT dispatch a
potentially open-ended job.

## GPU-Hour Estimation Heuristics

When setting `gpu_hours_budget` for a WIP.md step, use these heuristics:

| Run type | Estimation method | Example |
|---|---|---|
| **Exploratory / ablation** | Small-budget runs (~5 min wall-clock; ~0.1 GPU-hours) so many hypotheses can be tested in parallel — autoresearch's 300-token-budget pattern is one concrete recipe | `gpu_hours_budget: 0.1` |
| **Short fine-tune** | `(tokens_per_batch × steps × model_flops) / (GPU_TFLOPS × 3600)` | 1B tokens on A100 ≈ 2 GPU-hours |
| **Full pre-train** | Scale from a small-model calibration run | Calibrate on 1% of data; multiply by 100 |
| **Serving / inference** | Not a training budget — use `ai-native-platforms.md` for serving cost | — |

For Mode C, use `sky show-gpus` (SkyPilot) or the RunPod `pricing` MCP tool to get
`$/GPU-hour` before estimating cost. For Modes A and B, GPU-hours budget is a wall-clock
proxy only (`gpu_hours_budget = wall_clock_seconds_max / 3600`).

## Enforcement Behavior on Overrun

| Regime | Overrun action | Status written to TRAINING_RESULTS.md |
|---|---|---|
| Mode A/B (local) | `signal.alarm` fires → SIGTERM → SIGKILL | `budget_exhausted` |
| Mode C / SkyPilot | SkyPilot job timeout + `sky cancel` | `budget_exhausted` |
| Mode C / RunPod direct | `pod_stop` via MCP tool | `budget_exhausted` |

The `budget_exhausted` status is **not a failure** — it means the budget gate was the
termination condition. Checkpoints written before exhaustion are preserved and fetchable
via `artifact_fetch()`.

## Cross-References

- **Schema definition:** [neo-cloud-abstraction/SKILL.md](../../neo-cloud-abstraction/SKILL.md) — `training_job_descriptor` with `gpu_hours_budget` field
- **Local backend enforcement:** [neo-cloud-abstraction/references/local-backend.md](../../neo-cloud-abstraction/references/local-backend.md) — `wall_clock_seconds_max` + `pricing_query() → 0.0`
- **Operational modes:** [ml-training/references/operational-modes.md](../../ml-training/references/operational-modes.md) — Mode A / B / C full walkthroughs
- **Cloud pricing:** [ai-native-platforms.md](ai-native-platforms.md) — GPU marketplace comparison table (A100 ~$1.29–$2.78/hr depending on platform)
