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

**Schema reference:** `skills/llm-training-eval/references/training-results-schema.md`

### Threshold Syntax (in SYSTEMS_PLAN.md acceptance criteria)

- `val_bpb < 1.75` — strict less-than; no tolerance
- `val_bpb < 1.75 ± 0.02` — less-than with tolerance band

### PASS/FAIL/WARN Classification

- **PASS** — metric meets the criterion within tolerance
- **FAIL** — metric misses the criterion outside tolerance
- **WARN** — metric is within the tolerance band but criterion is directionally missed

### Verifier Behavior

When TRAINING_RESULTS.md is absent and the plan has metric-threshold criteria, emit
**WARN** (not FAIL) — the run may not have executed yet.

When TRAINING_RESULTS.md is present:

1. Extract recorded metrics from the `metrics:` block
2. Parse each threshold criterion
3. Apply tolerance band if declared in the plan or in `verdict.tolerance_band_applied`
4. Emit findings: `[PASS|FAIL|WARN] AC-N: val_bpb=<recorded> vs threshold=<declared>`

**Scope:** applies only when SYSTEMS_PLAN.md acceptance criteria contain metric threshold
syntax. Non-ML criteria use the standard binary PASS/FAIL protocol unchanged.

See `skills/llm-training-eval/SKILL.md` for the full tolerance-band methodology.

### EVAL_RESULTS.md Fallback

When `TRAINING_RESULTS.md` is **absent** and `EVAL_RESULTS.md` is **present**, the verifier
reads the eval metric instead of the training metric and applies the same tolerance-band logic.

**Priority rules:**

- **Both absent** — emit **WARN** (existing behavior, unchanged): the run may not have
  executed yet.
- **Both present** — `TRAINING_RESULTS.md` takes precedence; `EVAL_RESULTS.md` is ignored.
  Training runs own the verifier path; eval is the fallback.
- **`TRAINING_RESULTS.md` absent, `EVAL_RESULTS.md` present** — use the eval path below.

**Eval path (TRAINING_RESULTS.md absent, EVAL_RESULTS.md present):**

1. Read `primary_metric` and `held_out_delta` from the `EVAL_RESULTS.md` YAML frontmatter.
2. Parse each metric-threshold criterion from `SYSTEMS_PLAN.md` acceptance criteria.
3. Apply the same threshold syntax and tolerance-band classification as the `val_bpb` path.
   Note that direction may flip: accuracy-style metrics use `>` (higher is better), while
   loss metrics use `<` (lower is better). The operator in the criterion governs direction.
4. Apply tolerance band if declared (`± <tolerance>`) in the plan.
5. Emit findings in the same format:
   `[PASS|FAIL|WARN] AC-N: primary_metric=<recorded> vs threshold=<declared>`

**Classification (identical to `val_bpb` path):**

- **PASS** — metric meets the criterion within tolerance
- **FAIL** — metric misses the criterion outside tolerance
- **WARN** — metric is within the tolerance band but criterion is directionally missed

**Schema reference:** `skills/agent-evals/references/run-ledger-schema.md` §Field Constraints
documents `primary_metric` and `held_out_delta` types and semantics.
