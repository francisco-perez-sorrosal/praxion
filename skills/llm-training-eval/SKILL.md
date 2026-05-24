---
name: llm-training-eval
description: >
  LLM pre-training evaluation methodology: primary metric val_bpb (bits-per-byte,
  vocab-independent), validation perplexity (secondary, vocab-dependent), tolerance
  bands for PASS/FAIL/WARN classification, baseline-comparison syntax for
  SYSTEMS_PLAN.md acceptance criteria, EleutherAI lm-evaluation-harness.
  Owns the canonical TRAINING_RESULTS.md schema (verifier reads, /run-experiment
  writes). Triggers: designing training-run acceptance criteria, setting metric
  thresholds, verifier evaluating training results; val_bpb, bits-per-byte,
  perplexity, lm-eval-harness, training evaluation, metric thresholds, tolerance
  bands. Compose with ml-training and neo-cloud-abstraction.
allowed-tools: [Read, Write, Edit, Glob, Grep, Bash]
compatibility: Claude Code
staleness_sensitive_sections:
  - "Eval Harness"
  - "Metric Reference"
---

# LLM Training Evaluation

Evaluation methodology for LLM pre-training projects within Praxion. The primary goal is
answering: **did this training run meet its acceptance criteria?** The secondary goal is
capturing enough metric detail for future baseline comparisons.

**Satellite files** (loaded on-demand):

- [references/training-results-schema.md](references/training-results-schema.md) -- canonical TRAINING_RESULTS.md YAML schema; reader/writer contract; dual lifecycle; verifier consumption notes

## Primary Metric: val_bpb

<!-- last-verified: 2026-05-03 -->

`val_bpb` (validation bits-per-byte) is the **primary metric** for pre-training evaluation.
It is **vocabulary-independent**, making it comparable across tokenizers and model families.

**Formula:**

```
val_bpb = cross_entropy_nats / (log(2) × total_bytes)
```

- `cross_entropy_nats` is the mean per-token cross-entropy in natural units (nats)
- `total_bytes` counts the UTF-8 byte length of the validation text (not token count)
- `log(2) ≈ 0.6931` converts nats → bits
- **Lower is better.** A run with `val_bpb = 1.70` outperforms one at `val_bpb = 1.75`

### Scope: when val_bpb is the primary metric

`val_bpb` is the primary metric for **pre-training of language models**. For other ML training
shapes the primary metric differs:

| Training shape | Typical primary metric |
|---|---|
| LLM pre-training (this skill's v1 scope) | `val_bpb` (vocab-independent) |
| LLM fine-tuning / SFT | Task-specific perplexity or held-out task scores (lm-eval-harness, custom evals) |
| RL fine-tuning (DPO, PPO, GRPO) | Reward-model score, win-rate vs. baseline |
| Inference / eval-only harness runs | Direct task scores from the harness — no `val_bpb` |
| Embedding-model fine-tuning | Retrieval recall@k, MTEB scores |
| Multimodal training | Task-dependent (CLIPScore, FID, downstream accuracy) |

For non-pre-training shapes, declare the relevant metric in `SYSTEMS_PLAN.md` acceptance
criteria using the same threshold syntax (`<metric_name> < <value>` or with `± <tolerance>`).
The verifier's Phase 3a evaluates any named metric; it is not val_bpb-specific.

## Secondary Metric: val_perplexity

`val_perplexity` is vocabulary-dependent and should be used only when:
- All compared runs use the same tokenizer
- Communicating with audiences who expect perplexity over bits-per-byte

**Formula:** `val_perplexity = 2^(val_bpb × bytes_per_token)`

Flag this dependency in any report that uses perplexity for cross-run comparison.

## Metric Reference

<!-- last-verified: 2026-05-03 -->

| Metric | Type | Direction | Vocab-dependent | Primary use |
|---|---|---|---|---|
| `val_bpb` | float | lower=better | No | Acceptance criteria, cross-model comparison |
| `val_perplexity` | float | lower=better | Yes | Human reporting when tokenizer is fixed |
| `train_loss_final` | float | lower=better | Yes (token-space) | Training stability signal; not an AC metric |
| `eval_harness` | dict | task-dependent | Yes | Downstream task performance (lm-eval-harness output) |

## Baseline Comparison Syntax

Declare metric thresholds in `SYSTEMS_PLAN.md` acceptance criteria using this syntax:

```
val_bpb < 1.75                  # strict threshold — must beat 1.75
val_bpb < 1.75 ± 0.02           # threshold with tolerance band (WARN zone: 1.75–1.77)
val_perplexity < 12.4            # secondary metric threshold
val_bpb < baseline_run_tag       # compare against a named prior run's val_bpb
```

The `verifier` parses this syntax in Phase 3a when `TRAINING_RESULTS.md` exists. See
`rules/ml/eval-driven-verification.md` for the full threshold and PASS/FAIL/WARN protocol.

## PASS/FAIL/WARN Classification

Given a threshold `metric < value ± tolerance`:

| Result | Condition | Meaning |
|---|---|---|
| **PASS** | `recorded < value` | Criterion met; within or outside tolerance band |
| **WARN** | `value ≤ recorded ≤ value + tolerance` | Within tolerance band; directionally missed |
| **FAIL** | `recorded > value + tolerance` | Criterion missed outside tolerance band |

When no tolerance is declared, the tolerance band is `0` (strict threshold): PASS or FAIL only.

When `TRAINING_RESULTS.md` is absent and the plan has metric-threshold criteria, the verifier
emits WARN (not FAIL) — the run may not have executed yet.

## TRAINING_RESULTS.md Schema

This skill owns the schema. `/run-experiment` writes it; verifier reads it.
Full canonical schema, dual lifecycle, and verifier consumption notes:
→ [references/training-results-schema.md](references/training-results-schema.md)

**Abbreviated schema** (SKILL.md summary; reference file is authoritative):

```yaml
schema_version: "1.0"
run_id: <string>           # unique run identifier (UUID or slug)
run_tag: <string>          # human-readable tag (e.g., "run-001-lr3e4")
git_commit: <sha>
started_at: <ISO 8601>
completed_at: <ISO 8601>
status: completed | failed | crashed | timeout | cancelled | budget_exhausted
resources_used:
  gpu_hours: <float>
  wall_clock_seconds: <int>
  actual_cost_usd: <float>   # 0.0 for local backend
metrics:
  val_bpb: <float>
  val_perplexity: <float>
  train_loss_final: <float>
  eval_harness: {}           # lm-eval-harness output dict (optional)
verdict:
  acceptance_criteria_met: <bool>
  tolerance_band_applied: <bool>
  notes: <string>
```

**Dual lifecycle:** ephemeral primary at `.ai-work/<task-slug>/TRAINING_RESULTS.md` (verifier
reads this during the pipeline); archived to `.ai-state/training_runs/<run-tag>.md` only when
the run is "kept" (opt-in via `/run-experiment` prompt). Discarded runs have no archive.

## Eval Harness

<!-- last-verified: 2026-05-03 -->

**EleutherAI `lm-evaluation-harness`** is the standard external eval harness for LLM
pre-training validation in Praxion. It runs standardized downstream task benchmarks
(HellaSwag, MMLU, ARC, WinoGrande, etc.) and outputs structured JSON.

Praxion teaches the harness; project teams pin their own version. The `eval_harness` field
in `TRAINING_RESULTS.md` holds the harness output dict keyed by task name.

The harness is optional in v1 — `val_bpb` is the required primary metric. Harness results
supplement but do not replace threshold evaluation.

## Related Skills

| Skill | When to load it |
|---|---|
| `ml-training` | ML archetype vocabulary, operational modes, compute-budget requirements |
| `neo-cloud-abstraction` | Backend dispatch, lifecycle operations, training_job_descriptor schema |
| `experiment-tracking` | MLflow / W&B run logging; mapping run IDs to TRAINING_RESULTS.md |
