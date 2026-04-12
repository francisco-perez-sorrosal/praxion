---
id: dec-013
title: "Layered duplication prevention via existing agents, not a new dedicated agent"
status: accepted
category: architectural
date: "2026-04-04"
summary: "Duplication prevention uses three layers (rule + hook + verifier extension) instead of introducing a new agent, preserving agent boundary discipline"
tags: [code-quality, duplication, agents, hooks]
made_by: agent
agent_type: systems-architect
pipeline_tier: standard
affected_files:
  - rules/swe/coding-style.md
  - hooks/detect_duplication.py
  - hooks/hooks.json
  - agents/implementer.md
  - agents/verifier.md
  - agents/sentinel.md
  - install_claude.sh
---

## Context

The Praxion ecosystem had zero duplication detection. No hook, agent, skill, or rule checked for code duplication. The Direct tier (ad-hoc changes) had no quality gates beyond ruff formatting/linting. The user required cross-module detection with a self-healing loop where the verifier detects duplication and routes fixes back through the implementation cycle.

The key design question: should duplication detection be owned by a new dedicated agent or distributed across existing agents?

## Decision

Use a layered combination of existing components:

1. **Always-loaded DRY section** in `coding-style.md` for behavioral guidance (every session, every tier)
2. **PostToolUse `command` hook** (`detect_duplication.py`) for real-time intra-file detection
3. **Verifier Phase 4 Convention Compliance** extension for cross-module LLM-judged analysis
4. **Implementer self-review checklist** extension for pre-flight duplication awareness
5. **Sentinel Code Health dimension** (CH01) for periodic systemic audits

No new agent is introduced.

## Considered Options

### Option A: New dedicated agent

A new "duplication-guard" agent running after implementation and before verification.

**Pros:** Single owner. Clear, isolated responsibility. Could evolve independently.

**Cons:** Adds coordination complexity (new agent in pipeline, plugin.json update, protocol revision, downstream consumers). Needs a trigger protocol with no natural trigger point — the verifier already runs post-implementation. Disproportionate overhead for a single concern.

### Option B: Extend verifier only

**Pros:** Single point of detection. Already reads changed files.

**Cons:** No real-time feedback during implementation. No Direct tier coverage. No periodic backstop.

### Option C: Extend sentinel only

**Pros:** Periodic, systematic. Catches accumulated duplication.

**Cons:** Post-hoc only. Duplication already committed by the time sentinel runs.

### Option D: Layered combination (chosen)

**Pros:** Each layer addresses a different scope at a different cost point. Respects agent boundary discipline. No new coordination complexity. Direct tier gets advisory coverage.

**Cons:** No single "owner" of duplication detection. Direct tier remains advisory-only for cross-module analysis.

## Consequences

**Positive:**
- Zero new agents to maintain, coordinate, or register
- Each existing agent gains one small, focused extension within its existing responsibility
- Real-time feedback in all tiers via hook
- Cross-module LLM-judged analysis in pipeline tiers via verifier
- Self-healing loop: verifier FAIL → planner → implementer → re-verify (existing machinery)
- Periodic backstop via sentinel CH01

**Negative:**
- Direct tier has no automated cross-module analysis (advisory only)
- Duplication detection responsibility is distributed, not centralized
- Verifier Phase 4 scope expands slightly
