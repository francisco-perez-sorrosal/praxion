---
title: Agent Readiness
diataxis: explanation
summary: How Praxion scores a codebase's readiness for autonomous AI-agent development, why it matters, and how the capability is wired into /project-metrics and the dashboard.
---

# Agent Readiness

Agent Readiness measures how well a codebase supports autonomous software development by
AI coding agents — and, by extension, how effectively Praxion's own agent fleet can operate
in a managed project. It is computed as part of `/project-metrics` and surfaced as a section
on each project's dashboard, so readiness shows at a glance beside complexity, churn, and
hot-spots.

## Why it matters

The model is adapted from [Factory.ai's Agent Readiness](https://docs.factory.ai/web/agent-readiness/overview),
whose founding observation is environmental, not model-based: *"the agent is not broken; the
environment is,"* and *"a more agent-ready codebase improves the performance of all software
development agents… regardless of which tools you use."*

That tool-agnosticism is exactly why it is valuable to Praxion. A higher readiness score is a
direct proxy for "how manageable is this project by our agents" — tighter feedback loops,
clearer instructions, fewer dead-ends for every agent in the pipeline. Improvements compound:
better environments make agents more productive, and more productive agents can invest in the
environment.

## The rubric

Praxion adopts Factory's published model verbatim so the headline number stays externally
comparable, then adds one Praxion-native pillar:

- **8 Factory pillars** — Style & Validation · Build System · Testing · Documentation ·
  Dev Environment · Debugging & Observability · Security & Governance · Code Quality.
- **5 maturity levels** — 1 Functional → 2 Documented → **3 Standardized (the target)** →
  4 Optimized → 5 Autonomous. Level 3 is the minimum for autonomous operation.
- **80%-per-level gate** — a level unlocks when ≥80% of its (applicable) criteria pass, across
  all lower levels too. Criteria are binary pass/fail; in monorepos each is reported as
  `numerator/denominator` (apps passing / apps evaluated).
- **Pillar 9 — Praxion Manageability** (native) — CLAUDE.md blocks, git hooks, `.ai-state/`
  skeleton, settings toggles, and AGENTS.md (as an *INFO* signal, never a failure). Reported as
  a **separate sub-score** so it never distorts the Factory-comparable 8-pillar level.

Criteria are project-type/language aware: a criterion that does not apply to a project leaves
the denominator rather than counting as a failure, so a plugin-shaped repo (like Praxion
itself) scores fairly next to an application. The concrete criterion set lives in
`scripts/project_metrics/collectors/readiness/criteria.py`; the human-readable rubric is in the
`agent-readiness` skill's `references/rubric.md`.

## How it works

Readiness rides the existing `/project-metrics` pipeline as a collector, embedding a
`readiness` block in the metrics report (`METRICS_REPORT_*.json`) — no new state directory, no
new command. Scoring has two tiers split along the metrics pipeline's determinism boundary:

- **Mechanical tier** — file-existence and config-parse checks, run inside the deterministic,
  offline collector. Always on, free, reproducible.
- **LLM-judged tier** — four subjective criteria (naming conventions, test quality, README
  quality, docs agent-friendliness) judged by an LLM. It runs **outside** the collector (in the
  CLI enrichment step) so the collector stays byte-deterministic, is **on by default**, and is
  **grounded on the prior report** to keep run-to-run variance low. When no API credential is
  available (e.g. offline CI) it **degrades gracefully** to a mechanical-only score rather than
  failing. Each criterion's evidence comes from a per-criterion gatherer
  (`collectors/readiness/artifacts.py`): documentation criteria read the README, `test_quality`
  gets a bounded multi-section bundle (framework config across monorepo apps, coverage config +
  this run's measured coverage, a test-file inventory, deterministic samples of real test code,
  and testing-policy docs), and unregistered criteria fall back to a top-level repo listing.

The dashboard reads the `readiness` block and renders a level badge, an 8-pillar radar, the
Pillar-9 sub-score, and the top failing criteria.

### Running it

| Command | Effect |
|---|---|
| `/project-metrics` (or `python3 -m scripts.project_metrics`) | Full run: mechanical + LLM-judged readiness (LLM tier scored when an API credential is present, skipped gracefully otherwise) |
| `… --mechanical-only` | Skip the LLM tier entirely — fast, free, fully offline/deterministic |
| `… --require-readiness-ai` | Hard-fail (non-zero, no partial write) if the LLM tier cannot run — for CI that enforces full-fidelity scoring |

Authentication reuses the eval harness's precedence (`ANTHROPIC_API_KEY`, then
`CLAUDE_CODE_OAUTH_TOKEN`); the judge model defaults to `claude-haiku-4-5`.

### Remediation

A readiness report's failing criteria are a ready-made backlog. Rather than a bespoke
auto-fixer, feed them into the existing Praxion pipeline (promethean → researcher →
implementation-planner → implementer) — the same remediation loop, built on machinery the
project already has. The `agent-readiness` skill documents this handoff and how to interpret
each level.

## Design decisions

The load-bearing choices are recorded as ADRs (tagged `agent-readiness` in
`.ai-state/decisions/DECISIONS_INDEX.md`):

- **Judge transport** — the LLM judge is a stdlib-`urllib` direct Anthropic Messages API call,
  not the `anthropic` SDK and not a shell-out to the eval harness. This keeps the metrics
  package dependency-free (so it ships to every managed project via `claude plugin install`
  with no installer change) and re-affirms the nested-invocation refusal decision (a shell-out
  to `claude` deadlocks under `CLAUDECODE=1`).
- **Determinism boundary** — the non-deterministic LLM call runs outside the collector's
  byte-identical `collect()` pass, preserving the metrics pipeline's reproducibility contract.
- **Embed vs. sibling** — the readiness data is embedded in the metrics report rather than a
  separate `readiness_reports/` directory, minimizing dashboard and storage surface.

## Why build native rather than adopt Factory's product

Factory's Agent Readiness is delivered through its Droid CLI / dashboard / API and is bundled
with adopting Droid as your agent platform (BYOK is free; the readiness dashboard is included
from the **$20/mo Pro** tier; the Improvement Program is Enterprise-only). Praxion runs Claude
Code, and the goal is to ship readiness to *every* managed project by default. Because the
methodology is published and ~90% mechanical — and Praxion already owns the LLM-as-judge
machinery — a native implementation costs $0 marginal per project, carries no external
subscription or second agent platform, and reuses the metrics + dashboard + skill surfaces the
project already has. Factory's free BYOK tier remains useful as an optional external
cross-validation benchmark for flagship repositories.
