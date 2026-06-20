---
id: dec-243
title: Agentic-app-reliability frontier practices land as skills, not a 17th agent
status: accepted
category: architectural
date: 2026-06-20
summary: Blend the five agentic-app-reliability frontier candidates into Praxion as two new skills plus deepened references in two existing skills and zero new rules, consumed by existing agents — no new shadow sub-architect agent.
tags: [agents, skills, agentic-reliability, evals, observability, guardrails, budget, pipeline]
made_by: agent
agent_type: systems-architect
pipeline_tier: full
branch: main
affected_files:
  - skills/agent-runtime-guardrails/
  - skills/agent-failure-taxonomy/
  - skills/agent-evals/references/eval-rigor.md
  - skills/agent-evals/references/online-evals.md
  - skills/agent-evals/references/simulation-testing.md
  - skills/observability/references/distributed-tracing.md
dissent: A coherent reliability discipline spanning all five candidates could justify a standing advocate agent with challenge-loop teeth, exactly as agentic-transactions-architect guards real-money safety; under a build-production-multi-agent-apps workload, a skills-only carrier leaves no owner to object to an un-guard-railed architecture.
---

## Context

A frontier scan (`RESEARCH_FINDINGS_AGENTIC.md`, Lens A) surfaced five agentic-app-reliability practices Praxion does not yet embody: (1) runtime guardrails / deterministic-harness discipline, (2) production-grounded eval loop, (3) agent-native trajectory observability + a failure-mode taxonomy, (4) simulation/scenario testing with a user-simulator, (5) cost/latency/turn budgets as enforced gates. They share one domain — the runtime reliability of the agentic app a managed project builds.

The load-bearing question: does that commonality warrant a NEW domain-expert shadow sub-architect agent (mirroring the proven `interface-designer` and `agentic-transactions-architect` precedent — shadow researcher+architect, write a `*_DESIGN.md`, own an orchestrator-mediated `## Architecture Challenges` loop), or are the candidates better absorbed as new/deepened skills consumed by existing agents?

Two hard constraints frame the answer: (a) Praxion already has 16 agents and the always-loaded surface measures **24,081 tokens (~96% of the 25,000-token guardrail; ~919 tokens of headroom)** — under budget, but tight, so a 17th agent's standing four-row always-loaded cost is disproportionate against the remaining headroom; (b) the behavioral-contract mandate of Simplicity First and Balanced Coupling.

## Decision

Land the five candidates as **skills, not a new agent, and zero new rules**: two new skills — `agent-runtime-guardrails` (candidate 1) and `agent-failure-taxonomy` (candidate 3b, seeded from the Microsoft failure-mode taxonomy as a classification rubric) — plus deepened reference files inside two existing skills: `agent-evals/references/eval-rigor.md` (candidate 2a — judge-calibration + dataset-split, the dev-time gateable win), `agent-evals/references/online-evals.md` (candidate 2b advisory online grounding + candidate 5 budget gates), `agent-evals/references/simulation-testing.md` (candidate 4), and a refreshed agent-span section in `observability/references/distributed-tracing.md` (candidate 3a).

Two refinements distinguish this from a path-scoped-rule carrier: (1) the failure-mode taxonomy is a **skill, not a rule** — "agentic-app source" has no clean `paths:` glob (globs match paths, not content), so description-match activation is the correct trigger; (2) agentic cost/latency/turn **budget gates reuse the existing gpu-budget discipline** (`rules/ml/gpu-budget-conventions.md`: declare → enforce → exhaustion is a normal termination) placed in the `agent-evals` eval-gate surface, **not a new rule** (which would hit the same no-glob problem). Candidate 2 also splits explicitly into a dev-time, in-pipeline-gateable part (2a) and an advisory-only production-grounding part (2b), since Praxion can enforce the former but only teach the latter.

Existing agents consume them: systems-architect (guardrail design checklist, span model), implementer (instrumentation, harness build), test-engineer (eval rigor + gates, simulation, budget gates), verifier (failure-mode classification, guardrail presence check).

No 17th agent is created. The decision is revisitable via a `skill-genesis` promotion hook if reliability later proves to be a genuinely cross-cutting adversarial decision.

## Considered Options

### Option 1 — New shadow sub-architect agent `agentic-reliability-architect`
- **Pros:** single named owner/advocate; coherent north-star like the transactions agent; challenge-loop teeth to object to un-guard-railed architectures; fresh proven precedent.
- **Cons:** the domain fails the three-part earns-its-place test — no conflicting decision seam with the architect (the practices are advisory knowledge the architect *wants*, not an adversarial X-vs-Y), weak hand-forward decision authority (mostly checklists), no irreversible blast radius (gaps are caught downstream by verifier + agent-evals + the taxonomy rubric). Adds four+ always-loaded rows that could consume most of the ~919-token headroom (24,081 / 25,000); not reversible cheaply.

### Option 2 — Skills-only (chosen)
- **Pros:** near-zero always-loaded delta (~80–120 tokens = two skill-index lines; deepened references load on demand; ZERO new rules → no rule-description cost, no glob-maintenance fragility); every candidate maps onto an existing consumer; lowest operational overhead (no spawn-routing, no plugin.json churn); reversible and incremental; lowest integration strength carrier for advisory knowledge (Balanced Coupling). The taxonomy-as-skill and budget-gates-via-gpu-budget-discipline refinements eliminate the only would-be new rules.
- **Cons:** no single named reliability advocate; no challenge-loop teeth to block an un-guard-railed architecture (mitigated: verifier + Pre-mortem gate + the new taxonomy rubric provide downstream coverage).

### Option 3 — Hybrid (thin agent + skills)
- **Pros:** some ownership without full agent weight.
- **Cons:** dominated — pays the agent's standing always-loaded cost without the full justification; worst of both on the budget axis.

## Consequences

**Positive:** budget-safe (decisive given only ~919-token headroom under the 25k guardrail; delta ~80–120 tokens); pipeline graph unchanged; zero new rules; implementable in six independent phases (3a observability-span-refresh ALONE first as the clean factual-drift fix, then 2a eval-rigor gateable win, then 3b taxonomy skill, then guardrails skill, then 2b online-evals + budgets, then simulation last); reversible; clear ownership boundaries vs. `agentic-sdks`, `llm-prompt-engineering`, `context-security-review`, and (new skill vs. new skill) classification-vs-prevention between `agent-failure-taxonomy` and `agent-runtime-guardrails`.

**Negative:** no standing advocate for agentic-app reliability; if the user's dominant workload shifts to building production multi-agent apps, the absence of an owner may surface as under-specified reliability shape — handled by the promotion hook, not by pre-emptive agent creation.

## Disconfirmation

- **Falsifier:** evidence that this decision is wrong — `skill-genesis` (or repeated verifier findings) showing the architect *systematically* under-specifies agentic-app reliability shape on production builds, with a recurring adversarial X-vs-Y seam the skills cannot resolve because no agent holds decision authority to object. If that pattern appears, skills-only was the wrong carrier.
- **Steelmanned runner-up:** Option 1. The five candidates do cluster under one coherent discipline (Anthropic's harness/eval/observability guidance reads as one body of practice), and a standing advocate with challenge-loop teeth is exactly how Praxion guards real-money safety today via agentic-transactions-architect. If "ship a reliable agentic app" became as high-stakes-and-adversarial as "execute a real-money trade," a 17th agent would be earned — the runner-up is strongest precisely for production multi-agent-app builders.
- **Reversal trigger:** after the guardrails skill ships (Phase 4 in the revised phasing), a `skill-genesis` harvest showing a recurring, cross-cutting, adversarial agentic-app-reliability decision the architect mishandles. That signal — not a priori coherence of the domain — is the trigger to promote skill→agent (the cheap direction; agent→skill demotion is not).
