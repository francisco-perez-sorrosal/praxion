---
id: dec-117
title: ML training onramp uses four new skills + extensions to deployment/cicd, not one mega-skill
status: accepted
category: architectural
date: 2026-05-03
summary: Four new skills (ml-training, llm-training-eval, neo-cloud-abstraction, experiment-tracking) plus two reference-file extensions (gpu-compute-budgeting under deployment, ml-experiment-ci under cicd). Pre-training is a coherent skill-granular domain; eval and neo-cloud abstraction are independently reusable; experiment tracking has its own conceptual frame distinct from app observability (per user adjudication 2026-05-02 — Q3 override).
tags: [ml-training, skill-architecture, archetype-extension, neo-cloud, llm-training-eval]
made_by: agent
agent_type: systems-architect
pipeline_tier: standard
affected_files:
  - skills/ml-training/SKILL.md
  - skills/llm-training-eval/SKILL.md
  - skills/neo-cloud-abstraction/SKILL.md
  - skills/experiment-tracking/SKILL.md
  - skills/deployment/references/gpu-compute-budgeting.md
  - skills/cicd/references/ml-experiment-ci.md
affected_reqs: []
re_affirmed_by:
  - dec-120
---

# ADR — Skill scope and extension strategy for ML training onramp

## Context

`RESEARCH_FINDINGS.md` "Consolidated v1 deliverable shape" identifies six potential new skills/skill-extensions: `ml-training`, `llm-training-eval`, `experiment-tracking`, `gpu-compute-budgeting`, `neo-cloud-abstraction`, `ml-data-management` (deferred to v2). The architect must decide which are standalone skills and which are reference-file extensions to existing skills.

Three considerations bound the choice:

- **Coherence at skill-granularity**: a skill should be a coherent domain teachable as one unit with progressive disclosure. Pre-training (training loops, optimizers, checkpointing, distributed) is one such domain.
- **Reusability**: a skill should be reusable beyond its primary consumer. `neo-cloud-abstraction` is reusable beyond ML (any GPU-bound workload — inference, batch jobs).
- **Co-location with nearest existing skill**: smaller concerns that extend an existing domain (experiment tracking is a flavor of observability; GPU compute budgeting is a flavor of deployment economics; ML CI is a flavor of cicd) live as reference files under that skill, not as standalone skills.

## Decision

| Artifact | Status | Rationale |
|---|---|---|
| `skills/ml-training/SKILL.md` | New skill (medium) | Pre-training is a coherent domain (training loops, framework patterns, configs, data pipelines, checkpointing, distributed) — too broad to fit as a reference under another skill |
| `skills/llm-training-eval/SKILL.md` | New skill (medium) | Eval methodology (val_bpb, perplexity, lm-eval-harness, baseline comparison, tolerance bands, `TRAINING_RESULTS.md` schema) is a coherent domain. Owns the schema verifier reads (per dec-116). |
| `skills/neo-cloud-abstraction/SKILL.md` | New skill (medium) | The mode-invariant `training_job_descriptor`, lifecycle operations, and three-tier backend strategy is the abstraction Praxion teaches. Reusable beyond ML training (any GPU-bound workload). |
| `skills/experiment-tracking/SKILL.md` | New skill (medium) | Per user adjudication 2026-05-02: ML experiment tracking is conceptually distinct from app observability — RED/USE methodology vs experiment lineage tracking; different time horizons, data shapes, decision models, and toolchains (MLflow / W&B / Aim vs Prometheus / OTel / Grafana). Maps to the 6-artifact taxonomy's `experiment log` type (RESEARCH_FINDINGS Theme 1). Standalone skill is honest; folding into `observability` would constantly fork. |
| `skills/deployment/references/gpu-compute-budgeting.md` | Reference (small) under `deployment` | GPU economics are deployment economics for ML; lives next to `ai-native-platforms.md` |
| `skills/cicd/references/ml-experiment-ci.md` | Reference (small) under `cicd` | ML experiment CI patterns (eval-gated PRs, checkpoint upload artifacts, baseline diffing) are a flavor of CI |
| `ml-data-management` | Deferred to v2 | Dataset versioning (DVC, LakeFS) is its own domain but not blocking for v1 |

This complements ADR `dec-118` (tiered backend strategy) by locking in *where* the abstraction lives — a standalone skill, not a `deployment` reference. The two ADRs are independent dimensions of the design (backend strategy vs. skill placement); this ADR does not supersede the other.

## Considered Options

### Option 1 — One mega-skill `ml-training-stack`

**Pros:** One trigger; everything together; one set of references.

**Cons:** Too broad to fit one progressive-disclosure pattern. Training-loop conventions are very different from neo-cloud abstraction internals. The skill would either become unwieldy or the references would functionally be sub-skills with no top-level navigation.

### Option 2 — Four new skills + extensions to deployment/cicd (chosen; revised 2026-05-02 per user adjudication)

**Pros:**
- Each new skill is a coherent domain at the right granularity
- Smaller concerns co-locate with their nearest existing surface — keeps skill catalog from sprawling
- `neo-cloud-abstraction` is reusable beyond ML (inference, batch jobs)
- `llm-training-eval` is the natural owner of the `TRAINING_RESULTS.md` schema
- `ml-training` is the umbrella the implementer reaches for when writing training code

**Cons:**
- Skill catalog grows by 3
- Some users may want `gpu-compute-budgeting` and `experiment-tracking` as standalone skills later — flagged for skill-genesis review

### Option 3 — All extensions, no new skills

**Pros:** Catalog stays small.

**Cons:** ML training is a domain large enough to warrant its own progressive-disclosure home. Cramming it under existing skills (where? `python-development`?) deforms both. Verifier needs an `llm-training-eval` skill body to read for the `TRAINING_RESULTS.md` schema, and embedding it deep in another skill's reference is an awkward fit.

## Consequences

**Positive:**
- Three new skills with clear scopes and clean boundaries
- Skill catalog grows with intent, not by accident
- Existing skills (`deployment`, `observability`, `cicd`) co-locate ML-flavored extensions with their core concerns
- `llm-training-eval` skill is the durable home for `TRAINING_RESULTS.md` schema

**Negative:**
- Four new SKILL.md files to write and maintain
- `gpu-compute-budgeting` may want to graduate to a standalone skill if it accumulates enough content; skill-genesis can promote it later (`experiment-tracking` already promoted to standalone per user adjudication 2026-05-02)

**Neutral:**
- Skill names follow Praxion conventions (kebab-case, descriptive, action-oriented where applicable)
- The `external-api-docs` skill obligation applies to all three new skills when they reference SDKs (PyTorch, MLflow, SkyPilot, RunPod MCP, lm-eval-harness)
