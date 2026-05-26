# ml-training

Praxion's ML/AI pre-training archetype skill. Provides the vocabulary, compute-budget
discipline, and experiment-loop tooling that the `systems-architect`, `implementation-planner`,
and `verifier` agents need when working on neural-network training projects. Covers three
operational modes (owned GPU, rented GPU, separated cloud), the `program.md` meta-prompt
artifact, and the six ML artifact types that distinguish training projects from traditional SWE.

## When to Use

- Onboarding a neural-network training project to Praxion
- Working in a repo where `train.py`, `prepare.py`, or `program.md` is present
- Discussion involves GPUs, loss curves, perplexity, autoresearch, Karpathy, or torch/jax/tensorflow
- An autonomous agent is driving a training loop
- Deciding between owned GPU, rented GPU box, or cloud dispatch

## Activation

Auto-triggers on mention of training vocabulary: `program.md`, `train.py`, `gpu_hours_budget`,
`val_bpb`, `perplexity`, `checkpoints`, `SkyPilot`, `RunPod`, `MLflow`, `W&B`, or
`neo_cloud_backend`. Can also be loaded alongside sibling skills when starting full ML
pipeline work.

## Skill Contents

**SKILL.md sections:**
- Six ML Artifact Types — artifact taxonomy for the architect's Components table
- `program.md` — the experiment-loop meta-prompt; its discovery and tracker declaration
- Operational Modes (summary) — Mode A/B/C overview table and key invariant
- Compute-Budget Requirement — `gpu_hours_budget` YAML field; verifier FAIL condition
- API Version Drift — library version table (`torch`, `skypilot`, `@runpod/mcp-server`)
- Compute Backend Quick Reference — backend config values and what each teaches
- Related Skills

**References (loaded on demand):**
- `references/operational-modes.md` — full Mode A/B/C walkthroughs; SSH setup for Mode B;
  transition guidelines; project config convention

## Related Skills

- `llm-training-eval` — acceptance criteria, val_bpb metric, TRAINING_RESULTS.md schema
- `neo-cloud-abstraction` — backend dispatch, training_job_descriptor schema
- `experiment-tracking` — MLflow/W&B run logging; connecting training loop to a tracker
