# llm-training-eval

Evaluation methodology for LLM pre-training projects in Praxion. Defines the primary metric
(`val_bpb` — bits-per-byte, vocabulary-independent), tolerance bands for PASS/FAIL/WARN
classification, and the baseline-comparison syntax for `SYSTEMS_PLAN.md` acceptance criteria.
Owns the canonical `TRAINING_RESULTS.md` schema that `/run-experiment` writes and the verifier
reads in Phase 3a. Also covers the EleutherAI `lm-evaluation-harness` as the standard
downstream eval harness.

## When to Use

- Designing acceptance criteria for a training run (what `val_bpb` threshold to declare)
- Setting PASS/FAIL/WARN metric thresholds in `SYSTEMS_PLAN.md`
- The verifier is evaluating training results against acceptance criteria
- Working with `val_bpb`, bits-per-byte, perplexity, lm-eval-harness, tolerance bands
- Writing or reading a `TRAINING_RESULTS.md` file

## Activation

Auto-triggers on: `val_bpb`, `bits-per-byte`, `perplexity`, `lm-evaluation-harness`,
`lm-eval-harness`, `TRAINING_RESULTS.md`, `training evaluation`, `metric thresholds`,
`tolerance bands`, `PASS/FAIL/WARN` in a training context.

## Skill Contents

**SKILL.md sections:**
- Primary Metric: val_bpb — formula, vocab-independence, scope table across training shapes
- Secondary Metric: val_perplexity — when to use; vocab-dependency caveat
- Metric Reference — full metric table (val_bpb, val_perplexity, train_loss_final, eval_harness)
- Baseline Comparison Syntax — threshold syntax for `SYSTEMS_PLAN.md`
- PASS/FAIL/WARN Classification — tolerance-band evaluation table
- TRAINING_RESULTS.md Schema — abbreviated schema summary; pointer to reference file
- Eval Harness — EleutherAI `lm-evaluation-harness` overview
- Related Skills

**References (loaded on demand):**
- `references/training-results-schema.md` — canonical TRAINING_RESULTS.md YAML schema, full
  field constraints, dual lifecycle (ephemeral + archival), verifier consumption protocol,
  schema versioning, and minimal valid example

## Related Skills

- `ml-training` — ML archetype vocabulary, operational modes, compute-budget requirements
- `neo-cloud-abstraction` — backend dispatch, training_job_descriptor schema
- `experiment-tracking` — MLflow/W&B run logging; run_tag cross-reference to TRAINING_RESULTS.md
