---
id: dec-draft-ba1cc0a9
title: Embed SOLID for the AI era as the "Balanced Coupling" principle + software-design-principles skill
status: proposed
category: architectural
date: 2026-06-16
summary: Add a dedicated "Balanced Coupling" philosophy principle and a canonical software-design-principles skill that reframes SOLID as knowledge-flow heuristics for the AI era, composed by software-planning and refactoring and enforced via fitness functions.
tags: [philosophy, principles, solid, coupling, cohesion, design, ai-era, skill, agent-as-consumer]
made_by: user
pipeline_tier: standard
branch: worktree-solid-ai-era-embedding
affected_files:
  - claude/config/CLAUDE.md.tmpl
  - skills/software-design-principles/
  - skills/software-planning/SKILL.md
  - skills/refactoring/SKILL.md
  - skills/architectural-fitness-functions/SKILL.md
  - agents/systems-architect.md
  - agents/verifier.md
---

## Context

Praxion is an operating system for software development in the AI era, yet its
philosophy embodied SOLID only *implicitly and by scattered fragments*: `Structural
Beauty` and `Incremental Evolution` preached clean boundaries and cohesion; the
`refactoring` skill carried "Four Pillars" (modularity, low coupling, high
cohesion, pragmatic structure) but framed them *reactively*; `systems-architect`
and `verifier` reasoned about coupling without a named discipline. Nothing named
the unifying idea, captured Liskov substitution / interface segregation, or carried
the AI-era reinterpretation.

Research (Uncle Bob, "Solid Relevance" 2020; DigitalOcean canonical; Vladikk,
"SOLID Principles in the AI Era" 2026; plus 2026 agentic-SE literature) converges
on a durable thesis: the five SOLID principles are all manifestations of **one**
concern — managing knowledge flow between components ("balanced coupling":
integration strength × distance, modulated by volatility). *"AI changes the author;
it does not change the physics of software complexity."* The AI-era twist is
urgency, not novelty: generated code accrues technical debt faster than ever, so the
discipline matters *more*. A Praxion-specific angle the sources only gesture at: the
agent is itself a consumer, and code-level coupling becomes context-level coupling.

## Decision

1. **Add a dedicated philosophy principle, "Balanced Coupling"**, to
   `claude/config/CLAUDE.md.tmpl` (the tracked source of the rendered, gitignored
   `~/.claude/CLAUDE.md`). It states the knowledge-flow core, frames SOLID as
   heuristics-not-commandments (governed by Pragmatism + Incremental Evolution),
   ties modularity to Context Engineering for agent consumers, and names the AI-era
   urgency. The name is citable as `CLAUDE.md§Balanced Coupling`.
2. **Create a canonical `software-design-principles` skill** (deep tier, progressive
   disclosure): `SKILL.md` + `references/solid-heuristics.md` +
   `references/agent-as-consumer.md`. It is orthogonal to both pipeline skills.
3. **Compose, don't duplicate**: `software-planning` references it for *up-front*
   boundary design; `refactoring` references it as the *reactive* application of the
   same canon.
4. **Enforcement is opt-in**: `architectural-fitness-functions` documents that
   SOLID-derived invariants cite `CLAUDE.md§Balanced Coupling`.
5. **Pipeline awareness**: one-line references in `systems-architect` Phase 3 and
   `verifier`'s architecture-bucket criteria, both with the "only where coupling
   actually hurts" guard.

## Considered Options

### A. Dedicated principle + canonical skill + compose into both pipeline skills (chosen)
- **Pros:** names the durable idea once at the philosophy layer; deep content lives behind progressive disclosure (token-budget-respecting); single source of truth with two composing consumers; enforcement reuses existing machinery (zero new mechanism).
- **Cons:** adds always-loaded tokens for the new principle; a new skill surface to maintain.

### B. Augment `Structural Beauty` only; no new principle
- **Pros:** zero new top-level concept; smallest always-loaded delta.
- **Cons:** buries the AI-era design discipline inside an aesthetics-framed principle; less discoverable; weaker enforcement citation anchor. Rejected — user chose a dedicated principle.

### C. Extend the `refactoring` skill to hold the full SOLID canon
- **Pros:** reuses the richest existing home.
- **Cons:** keeps the framing reactive (cleanup), not up-front design; conflates two distinct triggers. Rejected — user judged the canon orthogonal to both refactoring and planning.

## Consequences

**Positive:** SOLID is now named, unified, and AI-era-aware at the root of the
philosophy; both up-front and reactive design paths draw from one canon; invariants
are enforceable with a stable citation; the agent-as-consumer lens is captured as a
first-class Praxion contribution.

**Negative / watch-items:** always-loaded budget grows by one principle (~1 paragraph
— stay under the 25k ceiling); the rendered `~/.claude/CLAUDE.md` must be
regenerated (it is gitignored) for the principle to take effect in live sessions;
the new skill's description competes in the always-loaded skill listing — keep it
high-signal. The "heuristics not commandments" guard must hold so the embedding does
not degrade into dogma (this would violate Pragmatism and Incremental Evolution).
