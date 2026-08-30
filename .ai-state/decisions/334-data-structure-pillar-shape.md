---
id: dec-334
title: Data-structures pillar lands as principle + skill + embedded obligations + discipline row, not a dedicated agent
status: accepted
category: architectural
date: 2026-08-25
summary: Embed representation design (types, invariants, state shapes, schemas-as-contracts) as the Data Structures First principle operationalized by a new data-structure-design skill, per-agent pipeline obligations, a coding-style conventions anchor, and a gated data-structure-specialist discipline row — rejecting a dedicated always-on shadow agent
tags: [data-structures, representation-design, philosophy, pipeline, skills, discipline-consultant, systems-architect, verifier]
made_by: agent
agent_type: orchestrator
branch: worktree-data-structures-pillar
pipeline_tier: full
dissent: "Prompt obligations without a dedicated agent's separate context may under-enforce the pillar on exactly the large tasks where representation errors are costliest — a shadow sub-architect (interface-designer precedent) would guarantee focused attention."
affected_files:
  - claude/config/CLAUDE.md.tmpl
  - codex/config/AGENTS.md.tmpl
  - AGENTS.md
  - skills/data-structure-design/SKILL.md
  - skills/data-structure-design/references/design-review-checklist.md
  - skills/data-structure-design/references/python-patterns.md
  - skills/data-structure-design/references/typescript-patterns.md
  - skills/data-structure-design/references/schema-contract-patterns.md
  - skills/multi-perspective-analysis/references/discipline-registry.md
  - rules/swe/coding-style.md
  - agents/systems-architect.md
  - agents/implementation-planner.md
  - agents/implementer.md
  - agents/verifier.md
  - agents/interface-designer.md
  - agents/test-engineer.md
---

# Data-structures pillar lands as principle + skill + embedded obligations + discipline row, not a dedicated agent

## Context

Efficient software construction is Praxion's meta-goal, and program-level
representation design — the types, invariants, state shapes, and schemas at the
heart of every building block — had no owner anywhere in the ecosystem: the
`data-modeling` skill is persistence-only, `software-design-principles` is
coupling-only, and no agent, rule, or command named representation design as a
duty (the only prior art was the reactive `Extract Data Structure` refactoring
pattern and the test-engineer's property-based-testing hook). External research
verified five independent lineages (Brooks 1975, Wirth 1976, Pike, Torvalds
2006, Raymond 2003) converging on "data shape dominates control-flow
complexity," a 40-year Parnas↔type-driven convergence on protecting the
representation decision, and agentic-era evidence that schema shape is a
measured reliability lever for model consumers (format-error reduction
supported; end-task-success gains not yet proven). The user mandate: embed this
as a pillar of both philosophy and process, choosing the right component shape
(a dedicated expert agent was floated as one option).

## Decision

Embed the pillar in four layers, mirroring how Balanced Coupling is already
operationalized:

1. **Principle** — `### Data Structures First` in the philosophy template
   (`claude/config/CLAUDE.md.tmpl`), placed after Behavior-Driven Development
   (behavior defines *what*; representation is the first *how* decision), terse,
   delegating depth to the skill.
2. **Skill** — new `skills/data-structure-design/` carrying the Representation
   Design Pass (9 steps), core techniques, the schemas-as-agent-contracts
   canon, a verifier-facing `design-review-checklist.md` with golden bad-cases,
   and worked Python/TypeScript patterns.
3. **Embedded pipeline obligations** — systems-architect (Phase 3 duty +
   `### Data Structures` subsection in the SYSTEMS_PLAN Phase 10 schema +
   frontmatter skill injection), implementation-planner (representation-before-
   behavior step ordering + frontmatter injection), implementer (conditional
   skill load + self-review item), verifier (convention bullet anchored to the
   new `coding-style § Data Structures and Invariants` section + Specialist
   Design Review routing), interface-designer and test-engineer (cross-links,
   read-on-demand).
4. **Gated adversarial depth** — one `data-structure-specialist` row in the
   discipline registry (binds to the new skill; attaches to systems-architect
   and implementation-planner), for load-bearing representation decisions only.

No dedicated agent is created.

## Considered Options

### Option A — Dedicated shadow sub-architect agent (interface-designer precedent)

- Pros: separate context window guarantees focused representation attention on
  large tasks; a `DATA_DESIGN.md` artifact with a challenge loop; symmetrical
  with interface-designer / agentic-transactions-architect.
- Cons: representation concerns attach to *every* non-trivial task — unlike the
  interface or transactions domains, there is no cheap negative trigger, so the
  shadow would spawn on most Standard/Full pipelines, roughly doubling design-
  stage cost; adds an agent file, manifest entry, model-routing row, and
  coordination-protocol rows (permanent structural weight); overlaps the
  systems-architect's core duty rather than a genuinely separate domain.

### Option B — Principle + skill + embedded obligations + gated discipline row (chosen)

- Pros: always-on coverage at near-zero marginal cost (obligations ride
  existing agents' context); mastery loads on demand (progressive disclosure);
  adversarial depth available when a decision warrants it via the
  discipline-consultant, whose contract explicitly prices a new discipline at
  "one registry row plus at most one new skill file"; mirrors the proven
  Balanced Coupling operationalization; disposition ledger provides the
  calibration signal for later escalation.
- Cons: enforcement rides prompt compliance inside already-long agent
  definitions; no dedicated artifact or challenge loop; effectiveness depends
  on the verifier checklist actually firing (mitigated by the rule anchor and
  golden bad-cases).

### Option C — Philosophy-only addition (principle + prose mentions)

- Pros: minimal cost.
- Cons: the existing asymmetry proves this fails — `software-design-principles`
  is prose-mentioned in one agent and injected nowhere, and the cross-agent
  convention states "the agent's skill list is the enforcement surface"; a
  principle without process hooks is aspiration, not a pillar.

## Consequences

- Positive: representation design becomes a named, verifiable stage of every
  Standard/Full pipeline (`### Data Structures` → step ordering → self-review →
  checklist audit), with a rule anchor making verifier findings traceable and
  property-based tests gaining a declared oracle.
- Positive: zero new always-loaded bytes beyond the principle itself; the
  discipline row costs nothing until convened.
- Negative: always-loaded token budget grows by the principle (~200 tokens);
  re-measure via `scripts/measure_token_budget.py` on install.
- Negative: five agent definitions grow slightly; their line budgets absorb it.
- Neutral: the SYSTEMS_PLAN schema gains an omittable `###` subsection —
  additive, no downstream grep consumer breaks.

## Disconfirmation

- **Falsifier**: verification reports and consult dispositions over the next
  quarters showing representation defects (illegal-state bugs, shotgun
  parsing) surviving pipelines *despite* the embedded obligations — i.e. the
  checklist fires but the defects ship, or the architect's `### Data
  Structures` sections are routinely empty on tasks that clearly have a
  representation surface. That would prove prompt-embedded duties under-enforce
  and the dedicated-agent option was needed.
- **Steelmanned runner-up**: Option A. A separate context window is the only
  mechanism that *guarantees* representation attention is not crowded out on
  exactly the large, multi-concern tasks where the architect's attention is
  thinnest and representation errors are costliest; the pipeline already
  accepts this cost for interfaces and transactions, and data structures are
  arguably more universal than either.
- **Reversal trigger**: the disposition ledger showing `data-structure-specialist`
  convened on a majority of Standard/Full pipelines with a low dismiss rate —
  evidence the "gated" premise is wrong and demand is unconditional — at which
  point promote the discipline to a shadow sub-architect per the
  interface-designer template.
