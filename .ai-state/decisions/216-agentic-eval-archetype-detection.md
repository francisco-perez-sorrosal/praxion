---
id: dec-216
title: Broaden paradigm-detection for the agentic-eval archetype; cite-as-canonical from onboarding
status: accepted
category: architectural
date: 2026-06-05
summary: Extend the single-source paradigm-detection.md with custom-evaluate.py + LLM-SDK-dep eval signals (core-deps-only + two-tier strength, refined by R5 validation against 4 repos); onboarding cites it as canonical rather than forking. Provisional until R1+R2 are implemented.
tags: [archetype, detection, paradigm, onboarding, agentic-eval, provisional, sia-fit]
made_by: agent
agent_type: systems-architect
branch: worktree-sia-praxion-fit-research
pipeline_tier: standard
affected_files:
  - skills/roadmap-synthesis/references/paradigm-detection.md
  - skills/onboard-project/SKILL.md
related: [dec-219, dec-221]
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

Broadened eval signal set (added to the detection table), **refined by R5 validation (2026-06-05)**:
- **Strong LLM-SDK deps (fire alone):** `claude-agent-sdk`, `openhands`/`openhands-ai`, `anthropic`,
  `openai`, MCP SDKs (`@modelcontextprotocol/*`, `mcp`).
- **Weak/general LLM deps (require a corroborant):** `litellm`, `google-generativeai` fire only with
  ≥1 structural corroborant — agentic keywords, an `agents/` dir, or the custom-eval-harness layout.
  *(R5-R2: prevents single-weak-signal misfire on general ML libraries.)*
- **Custom-eval-harness signal:** a `evaluate.py` plus a `tasks/` / `benchmarks/` / `data/private`
  layout — closing the homegrown-harness blind spot that named-framework detection misses.
- **Core-deps-only scope (R5-R1):** dependency signals match `[project.dependencies]` only, **never**
  `[project.optional-dependencies]`/extras. *(Without this, `lm-evaluation-harness` false-positives on
  its optional `litellm`.)*

Onboarding's Phase 8f describes its *own* signal subset inline (the agentic/eval heuristics it
acts on) with a cross-reference to `paradigm-detection.md` for the full taxonomy — no duplication,
single source of truth preserved.

**Provisional marker — validation status (CONTEXT_REVIEW R5):** the signal set was validated
2026-06-05 against four repos (`.ai-work/sia-praxion-fit/RESEARCH_FINDINGS_detection-validation.md`):
SWE-agent (true positive ✓), Inspect AI (true positive ✓), `lm-evaluation-harness` (boundary —
non-agentic eval; clean non-fire **only** under R1), and `httpx` (negative control — clean ✗-fire).
The two refinements above (R5-R1 core-deps-only, R5-R2 two-tier strength) were **folded in as a
result of that validation** and eliminate the false-positive and single-weak-signal misfire vectors.
The `<!-- provisional: validate against N repos -->` marker on the `paradigm-detection.md` edit
**may be removed once R1+R2 are implemented as written**; until the code reflects them, it stays
provisional. Three lower-priority refinements (model-benchmarking archetype, provider-module dep
scan, benchmark-dir root-depth constraint) are deferred — see the validation report.

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
  parallel). Feeds `project_profile.yaml` (`dec-219`).
