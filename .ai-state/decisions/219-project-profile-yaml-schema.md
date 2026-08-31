---
id: dec-219
title: .ai-state/project_profile.yaml as the machine-consumable archetype + run-store record
status: accepted
category: configuration
date: 2026-06-05
summary: Record archetype/paradigm, run_store_root, run_store_backend, and eval_framework in .ai-state/project_profile.yaml as a Phase 8f output (not a prerequisite); CLAUDE.md gets only a one-line pointer.
tags: [config, project-profile, archetype, run-store, onboarding, sia-fit]
made_by: agent
agent_type: systems-architect
branch: worktree-sia-praxion-fit-research
pipeline_tier: standard
affected_files:
  - .ai-state/project_profile.yaml
  - rules/swe/agent-intermediate-documents.md
  - skills/onboard-project/SKILL.md
related: [dec-221, dec-220, dec-216]
superseded_in_part_by:
  - dec-263
---

## Context

P1's archetype detection produces a classification (`agentic-eval` / `ml-training` /
`deterministic` / `hybrid`) and the storage model (`dec-221`) needs a committed home
for the portable `run_store_root` default. CONTEXT_REVIEW Decision C adjudicated where this record
lives: a CLAUDE.md block field (always-loaded in every managed project) vs a machine-consumable
YAML file.

## Decision

Record project archetype + run-store config in **`.ai-state/project_profile.yaml`**, produced as
a **Phase 8f output** (never a prerequisite for other phases). Fields:

```yaml
schema_version: "1.0"
paradigm: agentic | deterministic | hybrid
archetype: agentic-eval | ml-training | service | library
run_store_root: "~/.<project-name>"     # PORTABLE default; machine-specific abs paths NEVER here
run_store_backend: local-home | local-custom | s3 | tracker
eval_framework: custom | inspect-ai | deepeval | promptfoo | none
```

CLAUDE.md gets only a one-line `## Project Type` pointer referencing this file — no always-loaded
archetype field. Machine-specific absolute paths live in gitignored `.claude/settings.local.json`
or env, never in `project_profile.yaml`.

## Considered Options

### A — Archetype as a CLAUDE.md canonical-block field
- Pros: visible in always-loaded context.
- Cons: every managed project carries it even when irrelevant; grows the always-loaded budget;
  not machine-consumable for tools (sentinel, architect) that want a stable read.

### B — .ai-state/project_profile.yaml, machine-consumable (CHOSEN)
- Pros: zero always-loaded cost; stable artifact other tools read without re-running detection;
  precedent `readiness_config.json`; natural home for `run_store_root`.
- Cons: one more `.ai-state/` artifact (negligible).

## Consequences

- **Positive:** clean separation of machine-readable config from always-loaded prose; a single
  read surface for archetype + storage config.
- **Negative / constraint:** `project_profile.yaml` must be added to the permanent inventory in
  `rules/swe/agent-intermediate-documents.md` (one row). **Verify sentinel BC03 does not
  hard-code/enumerate `.ai-state/` artifact names before shipping** (CONTEXT_REVIEW R6) — else
  false-positive.
- **Dogfood:** Praxion adopts its own `project_profile.yaml` (`paradigm: hybrid`,
  `eval_framework: custom`) per Decision E.

## Prior Decision Note (partial supersession)

The Phase 8f *producer clause* of this decision (project_profile.yaml written by /onboard-project
Phase 8f) is retired by dec-263 — the producer was never built and the file has zero
live consumers (every consumer falls back to live detection). The schema and location decision in
this ADR stands unchanged and re-activates if the agentic-eval archetype feature ships a producer.
