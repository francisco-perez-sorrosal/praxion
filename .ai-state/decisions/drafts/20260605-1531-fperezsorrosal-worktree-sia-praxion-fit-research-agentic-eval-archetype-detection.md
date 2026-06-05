---
id: dec-draft-7aac9824
title: Broaden paradigm-detection for the agentic-eval archetype; cite-as-canonical from onboarding
status: proposed
category: architectural
date: 2026-06-05
summary: Extend the single-source paradigm-detection.md with custom-evaluate.py + LLM-SDK-dep eval signals; onboarding cites it as canonical rather than forking. Provisional until validated against more repos.
tags: [archetype, detection, paradigm, onboarding, agentic-eval, provisional, sia-fit]
made_by: agent
agent_type: systems-architect
branch: worktree-sia-praxion-fit-research
pipeline_tier: standard
affected_files:
  - skills/roadmap-synthesis/references/paradigm-detection.md
  - commands/onboard-project.md
related: [dec-draft-7df1a638, dec-draft-9c30645e]
---

## Context

Praxion's onboarding (Phase 8c) detects ML only via `train.py`/`prepare.py`, `torch|jax|tensorflow`
deps, or `program.md`. SIA matches none → reads as "generic Python" → no agentic/eval scaffold.
Paradigm detection *exists* but lives only in the roadmap-cartographer (on-demand audit) and is
framework-name-biased: its eval signal fires only for Inspect AI / DeepEval / Promptfoo
(`paradigm-detection.md:35`), missing custom `evaluate.py` harnesses like SIA's. CONTEXT_REVIEW
Decision D adjudicated how the detection logic is shared: promote the file to a new shared location
vs cite-as-canonical from onboarding.

## Decision

**Extend the existing single-source `paradigm-detection.md`** with a broadened agentic/eval signal
set, and have onboarding **cite it as canonical** (cross-reference) rather than fork or move it.

Broadened eval signal set (added to the detection table):
- LLM-SDK deps: `claude-agent-sdk`, `openhands`, `anthropic`, `openai`, MCP SDKs.
- **Custom-eval-harness signal:** a `evaluate.py` plus a `tasks/` / `benchmarks/` / `data/private`
  layout — closing the homegrown-harness blind spot that named-framework detection misses.

Onboarding's Phase 8f describes its *own* signal subset inline (the agentic/eval heuristics it
acts on) with a cross-reference to `paradigm-detection.md` for the full taxonomy — no duplication,
single source of truth preserved.

**Provisional marker required (CONTEXT_REVIEW R5):** the broadened signal set must be validated
against 2–3 more agentic/eval repos before locking, to avoid SIA-overfit. Ship behind a
`<!-- provisional: validate against N repos -->` marker. This pass designs the detection only;
it does not lock it.

## Considered Options

### A — New standalone detection module / promote to a shared location
- Pros: a "shared" home signals reuse beyond the cartographer.
- Cons: introduces a directory convention that doesn't exist in Praxion; a skills-root file isn't a
  recognized pattern; duplicates classification logic; violates progressive disclosure.

### B — Extend the existing reference; onboarding cites it as canonical (CHOSEN)
- Pros: one taxonomy, no duplication; clean two-consumer relationship (cartographer + onboarding);
  honors single-source and progressive disclosure.
- Cons: onboarding must describe its acted-on subset inline with a pointer.

## Consequences

- **Positive:** closes the homegrown-harness blind spot; onboarding classifies agentic-eval
  projects and offers the Phase 8f scaffold; the cartographer and onboarding share one source.
- **Negative:** the signal set is provisional until validated — an unvalidated heuristic risks
  false `agentic-eval` classification (mitigated by the provisional marker and the existing
  escalate-to-user-on-low-confidence path).
- **Delivery dependency:** P1's Phase 8f scaffold installs references to the P2/P3 artifacts, so
  the scaffold wiring lands AFTER those artifacts exist (the detection design can be authored in
  parallel). Feeds `project_profile.yaml` (`dec-draft-7df1a638`).
