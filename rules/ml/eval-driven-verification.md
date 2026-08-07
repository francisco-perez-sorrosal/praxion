---
paths:
- program.md
- runs/**
- experiments/**
- train.py
- prepare.py
- TRAINING_RESULTS.md
- EVAL_RESULTS.md
- .ai-work/**/SYSTEMS_PLAN.md
- .ai-work/**/WIP.md
- .ai-work/**/VERIFICATION_REPORT.md
- .ai-work/**/EVAL_RESULTS.md
core: false
---

## Eval-Driven Verification

ML training acceptance criteria use metric thresholds, not binary assertions. When
`TRAINING_RESULTS.md` exists and the plan contains metric threshold syntax, the verifier
reads recorded metrics and evaluates each criterion using a tolerance band.

### Threshold Syntax (in SYSTEMS_PLAN.md acceptance criteria)

- `val_bpb < 1.75` — strict less-than; no tolerance
- `val_bpb < 1.75 ± 0.02` — less-than with tolerance band

Direction is governed by the operator in the criterion: loss-style metrics use `<` (lower is
better), accuracy-style metrics use `>` (higher is better).

### PASS/FAIL/WARN Classification

- **PASS** — metric meets the criterion within tolerance
- **FAIL** — metric misses the criterion outside tolerance
- **WARN** — metric is within the tolerance band but criterion is directionally missed

### Metric Source Priority

| `TRAINING_RESULTS.md` | `EVAL_RESULTS.md` | Verifier behavior |
|---|---|---|
| absent | absent | emit **WARN**, not FAIL — the run may not have executed yet |
| present | absent or present | `TRAINING_RESULTS.md` governs; `EVAL_RESULTS.md` is ignored. Training runs own the verifier path; eval is the fallback |
| absent | present | read the eval metric instead of the training metric; identical threshold syntax and classification apply |

**Scope:** applies only when SYSTEMS_PLAN.md acceptance criteria contain metric threshold
syntax. Non-ML criteria use the standard binary PASS/FAIL protocol unchanged.

**Evaluation procedure** (step-by-step, both metric sources):
`skills/llm-training-eval/SKILL.md` § "Verifier Evaluation Procedure" — which delegates the
`TRAINING_RESULTS.md` path to `skills/llm-training-eval/references/training-results-schema.md`
§ "Verifier Consumption (Phase 3a)". That skill also carries the full tolerance-band methodology.

**Schema references:** `TRAINING_RESULTS.md` →
`skills/llm-training-eval/references/training-results-schema.md`. `EVAL_RESULTS.md` →
`skills/agent-evals/references/run-ledger-schema.md` § Field Constraints, which documents
`primary_metric` and `held_out_delta` types and semantics.
