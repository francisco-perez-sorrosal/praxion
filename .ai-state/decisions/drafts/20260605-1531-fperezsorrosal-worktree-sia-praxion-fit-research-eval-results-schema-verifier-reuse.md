---
id: dec-draft-ccb70b10
title: EVAL_RESULTS.md schema as sibling to TRAINING_RESULTS.md with verifier tolerance-band reuse
status: proposed
category: architectural
date: 2026-06-05
summary: EVAL_RESULTS.md + eval_ledger/EVAL_LOG.md live in agent-evals as a sibling schema; the verifier reuses eval-driven-verification tolerance bands by feeding the eval metric instead of val_bpb.
tags: [eval, schema, run-ledger, verifier, tolerance-band, agent-evals, sia-fit]
made_by: agent
agent_type: systems-architect
branch: worktree-sia-praxion-fit-research
pipeline_tier: standard
affected_files:
  - skills/agent-evals/references/run-ledger-schema.md
  - rules/ml/eval-driven-verification.md
  - rules/swe/agent-intermediate-documents.md
  - commands/scores.md
related: [dec-draft-9c30645e, dec-draft-52949236]
---

## Context

P2 needs a committed tier-2 schema for kept eval/agentic runs. Praxion already owns
`TRAINING_RESULTS.md` (in `llm-training-eval`), consumed by the verifier's metric-threshold
evaluation against training runs. The question (CONTEXT_REVIEW Decision B) is whether the new
eval schema merges into a super-schema with `TRAINING_RESULTS.md` or stands as a sibling. R3
additionally corrects the schema's home: `agent-evals/references/`, NOT
`llm-training-eval/references/`.

## Decision

Create **`EVAL_RESULTS.md`** (project root, sibling to `TRAINING_RESULTS.md`) as a **separate
sibling schema** owned by the `agent-evals` skill
(`skills/agent-evals/references/run-ledger-schema.md`), plus an append-only
`.ai-state/eval_ledger/EVAL_LOG.md` aggregate. Eval-run-specific fields: `run_id`, `store_uri`,
`task`, `generation`, `primary_metric`, `held_out_delta`, `model_id`, `prompt_hash`,
`dataset_sha`, `token_usage`, `cost_usd`, `git_sha`, `verdict`.

**Verifier reuse:** the single shared mechanism is `rules/ml/eval-driven-verification.md`. When a
plan's acceptance criteria carry metric-threshold syntax and `EVAL_RESULTS.md` is present, the
verifier evaluates the eval metric (task accuracy / held-out delta) against the threshold using
the **same tolerance-band logic** that today evaluates `val_bpb` — no new verifier code,
the eval metric simply substitutes for `val_bpb`.

## Considered Options

### A — One super-schema merging training + eval results
- Pros: a single results file type.
- Cons: training-specific fields (`epoch`, `val_bpb`, `gpu_hours`, `checkpoint_path`) and
  eval-specific fields (`generation`, `primary_metric`, `held_out_delta`, `prompt_hash`) bleed
  into one another; every managed project must understand both halves; both consumers
  (verifier vs `/scores`/dashboard) see noise.

### B — Sibling schema in agent-evals, sharing only the verifier mechanism (CHOSEN)
- Pros: each consumer sees only its fields; the schema lives in the skill that owns eval harnesses
  generically; the only shared surface is the tolerance-band rule, reused by reference.
- Cons: two schemas to keep conceptually aligned.

## Consequences

- **Positive:** clean separation; the verifier mechanism is unchanged and proven; `EVAL_LOG.md`
  instantiates the established `<thing>_reports/ + <THING>_LOG.md` pattern a fourth time.
- **Negative:** conceptual drift risk between the two schemas — mitigated by both citing the
  shared verifier rule and the `run-ledger-schema.md` noting its conceptual ancestry from
  `training-results-schema.md`.
- **Binding:** the `prompt_hash` and `dataset_sha` fields are the binding points for P4
  (prompt versioning) and P3 (dataset provenance) respectively.
