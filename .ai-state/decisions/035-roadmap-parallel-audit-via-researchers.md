---
id: dec-035
title: Parallel audit fan-out via N=3–6 researchers, not a new project-auditor agent
status: accepted
category: architectural
date: 2026-04-12
summary: 'Cartographer spawns N=3-6 parallel researchers (each with a distinct audit lens) via the Task tool; each writes a fragment under `.ai-work/<slug>/AUDIT_<lens>.md`; cartographer synthesizes. No new auditor agent'
tags: [architecture, roadmap, researcher, parallel-execution, audit, boundary-discipline]
made_by: agent
agent_type: systems-architect
pipeline_tier: standard
affected_files:
  - agents/roadmap-cartographer.md
  - skills/roadmap-synthesis/references/audit-methodology.md
---

## Context

Praxion's exemplar `ROADMAP.md` methodology footer states it was produced via *"6 parallel deep-dive audits covering: skills (33 skills, 7,312 total SKILL.md lines), agents (12 agents, ~55,000 tokens of prompts), rules/commands/hooks... external research (10 topic areas, 60+ sources)."* This parallel-fan-out pattern is the direct reason the exemplar achieves its depth — a single-agent sweep cannot produce equivalent breadth within a single context window without saturating attention.

SPIRIT dimension 6 (Curiosity / multi-angle framing) reinforces this: *"we approach problems from different angles ... we may devise solutions that we didn't see initially."* Parallel researchers with distinct lenses produce structurally diverse findings a single synthesizer can compose; sequential single-agent analysis tends to converge on the first angle it considers.

Three options for the audit phase:

- **Consume sentinel only** — use `SENTINEL_REPORT_*.md` as the audit input.
- **New project-auditor agent** — introduce a dedicated agent that generalizes sentinel for non-Praxion projects.
- **Parallel researchers** — cartographer fan-outs to N existing researchers with distinct lenses.

## Decision

Cartographer spawns **N=3–6 parallel researchers** via the `Task` tool, each with a distinct audit lens. Default lens set:

1. **Structure** — ecosystem layout, boundaries, coupling, cohesion
2. **Quality** — tests, linting, CI, error handling, coverage
3. **Evolution** — 2026 state-of-art, standards convergence, external research
4. **Automation** — hooks, CI, automation opportunities, user-gate points
5. **Coordinator awareness** — AGENTS.md / CLAUDE.md presence, delegation coverage
6. **Curiosity** — alternative framings, rejected approaches, unconventional angles

The cartographer selects the lens count (3–6) and composition based on the paradigm detected in Phase 1 (deterministic projects may drop the coordinator-awareness lens; agentic projects emphasize it). Each researcher writes a fragment to `.ai-work/<slug>/AUDIT_<lens>.md`. The cartographer reads all fragments and synthesizes in Phase 4.

The `Task` tool's parallel invocation is the canonical Praxion pattern for intra-stage parallelism (see coordination-protocol rule). No new agent is introduced; the researcher is reused verbatim.

## Considered Options

### Option 1 — Consume sentinel only

Reuse existing `SENTINEL_REPORT_*.md` as audit input; cartographer synthesizes from it.
**Pros:** zero new infrastructure; sentinel already audits the Praxion ecosystem.
**Cons:** sentinel is **Praxion-tuned** — its dimensions (DL01-DL05 ADR checks, spec health, hook freshness) are specific to this project's conventions. A roadmap-creation feature must work on any project. Sentinel also misses external-research synthesis (SPIRIT dim 5 Pragmatism). Rejected for paradigm-agnosticism.

### Option 2 — New project-auditor agent

Introduce a dedicated agent that generalizes sentinel for non-Praxion projects.
**Pros:** formal audit capability; agent-level parallelism (auditor + cartographer coordinate).
**Cons:** scope creep — this single ADR would have to define a generalized audit framework as a side effect; overlaps substantially with the researcher's existing capability; violates boundary discipline (researcher already does codebase exploration + external docs; orchestrating N researchers achieves the same outcome without a new agent). Rejected.

### Option 3 — Parallel researchers (chosen)

Cartographer fan-outs to existing researchers.
**Pros:** reuses a proven agent; matches the exemplar's actual methodology; boundary-disciplined (orchestration in cartographer, research in researchers); paradigm-agnostic (researcher's external-research capability handles any paradigm); lens set configurable per project; each researcher's fragment file provides audit trail.
**Cons:** cartographer must manage N concurrent Task invocations; fragment reconciliation is the cartographer's responsibility; slightly higher orchestration complexity than Option 1.

### Option 4 — User/coordinator produces audit manually

Cartographer consumes audit input the user provides.
**Pros:** lowest automation complexity.
**Cons:** violates SPIRIT dim 1 (automate as much as possible); pushes significant work onto the user that the automation should own. Rejected.

## Consequences

**Positive:**

- Matches the exemplar's proven methodology ("6 parallel deep-dive audits").
- Reuses researcher; no new agent to maintain.
- Boundary-disciplined: cartographer orchestrates, researcher researches.
- Lens set is configurable per project paradigm.
- Each audit fragment is a persisted artifact for debugging and audit trail.
- Paradigm-agnostic by construction (researcher handles any codebase + external research).

**Negative:**

- Cartographer manages N concurrent `Task` invocations; must handle fragment reconciliation semantics (per `coordination-details.md#parallel-execution-fragments`).
- Lens-selection heuristic requires tuning per paradigm; default lens set is a starting point, not a fixed contract.
- Concurrent researchers consume tokens in parallel; large projects may hit per-agent token limits before synthesis. Mitigated by lens scoping (each researcher has a narrow lens, not a full-project sweep).
- Researcher must produce a grounded, token-aware fragment — the cartographer relies on this; implementer verifies fragment schema in AC-4 (evidence grounding).

**Operational:**

- Cartographer's Phase 3 prompt outlines the lens set selection + fan-out procedure.
- `skills/roadmap-synthesis/references/audit-methodology.md` documents the lens catalog with definition, detection heuristics, fragment schema, and paradigm applicability.
- Fragment files follow the pattern `.ai-work/<slug>/AUDIT_<lens>.md`.
- The cartographer's Phase 4 synthesizes fragments using the six-dimension lens (dec-033) and the template asset (dec-032).
- Verifier AC-7 confirms the cartographer spawned N researchers in parallel (checked via `PROGRESS.md` timestamps or Task-tool invocation count).
