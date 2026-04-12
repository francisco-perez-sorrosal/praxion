---
id: dec-027
title: Praxion-specific principles embedded via compact bullet block + README prose, anchored by diagram-conventions path-scoping
status: accepted
category: configuration
date: 2026-04-12
summary: Four durable principles embedded as a ~320-char compact block in repo CLAUDE.md + ~1,400-char rich prose in README.md; principle #3 (phase ordering) excluded as roadmap-execution rule; precondition is dec-028 path-scoping
tags: [principles, token-budget, documentation, claude-md, readme]
made_by: agent
agent_type: systems-architect
pipeline_tier: standard
affected_files:
  - CLAUDE.md
  - README.md
  - rules/writing/diagram-conventions.md
---

## Context

ROADMAP Phase 1.5 lists six guiding principles intended to be embedded in the Praxion repo to anchor agent and author behavior across projects. The context-engineer's shadow-research measured that the current always-loaded budget for a Praxion session sits at 52,130 chars (≈14,894 tokens at 3.5 chars/token, 99.3% of the 15,000-token ceiling). Faithful restatement of all six principles in `CLAUDE.md` — by any of the natural phrasings explored (dense one-liner, bullet list, subsection per principle) — pushes the always-loaded total over the 52,500-char ceiling by anywhere from 58 chars to 1,530 chars.

The six principles also vary in durability:

- Principle 1 (token budget first-class), Principle 4 (preserve what works) are partially or fully covered in global `~/.claude/CLAUDE.md` already ("Pragmatism" frames budget cost; "Incremental Evolution" covers preservation).
- Principles 2 (measure before optimizing), 5 (standards convergence), 6 (curiosity over dogma) are genuinely new at the framing level.
- Principle 3 (one phase at a time, with overlap between phases) is a ROADMAP-execution rule, not a durable project principle. It belongs in `ROADMAP.md`, not in always-loaded content.

The embedding strategy must keep always-loaded content under the ceiling while preserving faithful phrasing of the four durable principles and providing a stable anchor for future references.

## Decision

Embed the four durable Praxion-specific principles using a two-part pattern:

1. **`CLAUDE.md` (repo root) — compact bullet block, ~320 chars.** One header plus a single paragraph listing the four principle names in bold, separated by commas, followed by a pointer to `README.md#guiding-principles` for rationale and `ROADMAP.md#guiding-principles-for-execution` for full execution context. The block is designed to fit in ≤370 chars so that its contribution to the always-loaded budget stays under the 52,500-char ceiling after the `dec-028` path-scoping reclamation (~2,584 chars recovered). No per-principle exposition in `CLAUDE.md` — names + pointer only.

2. **`README.md` — rich prose, ~1,400 chars.** A new `## Guiding Principles` section between `## Core Concepts` and `## Quick Start`. Each principle gets a bolded one-line statement plus 1–2 sentences of rationale. README has no token budget; this is where faithful phrasing lives.

**Principle 3 is excluded from both surfaces.** "One phase at a time, with overlap between phases" is a roadmap-execution convention, not a durable project principle; embedding it would consume budget for a rule whose home is `ROADMAP.md`.

**Precondition**: `dec-028` (narrow `rules/writing/diagram-conventions.md` path-scope from `**/*.md` to documentation-authoring surfaces) MUST land before the `CLAUDE.md` block is added. Without it, adding 320 chars to always-loaded content crosses the ceiling.

## Considered Options

### Option A — Dense one-liner in `CLAUDE.md` (single long sentence naming all four principles with inline rationale)

**Pros:** Minimal surface; all principles present.
**Cons:** Measured at +580 chars → post-embed total 100.4% of ceiling (over by 100 chars). Unsafe even before future growth.

### Option B — Bullet list in `CLAUDE.md` (chosen, conditional on `dec-028`)

Each principle as a bullet with a one-line description. ~870 chars.
**Pros:** Faithful phrasing; readable at a glance; extensible.
**Cons:** +870 chars → post-embed total 101.2% of ceiling without path-scoping. Feasible only after `dec-028` reclaims ~2,584 chars (post-scope utilization ≈ 96.3%).

Chosen with path-scoping because it balances faithful phrasing with durable headroom. However, the final shipped variant is a compact ≤320-char block (closer to Option A in size but using bullet structure internally), with rich prose routed to README. The compact block cites principles by name and points to README for exposition — this preserves budget while honoring faithful phrasing at the documentation layer that has no budget.

### Option C — Subsection per principle in `CLAUDE.md` (full paragraph each)

**Pros:** Maximum faithfulness in always-loaded content.
**Cons:** +1,900 chars → post-embed 98.0% even after path-scoping. Consumes almost all reclaimed headroom; leaves the next convention add unsafe. Rejected.

### Option D — Cross-reference only in `CLAUDE.md` (no principle names, just a pointer)

**Pros:** Smallest possible footprint (~264 chars).
**Cons:** Agents consulting `CLAUDE.md` don't see principle names at all — discovery depends on following the link. Feels thin. Rejected in favor of the compact-named-bullet variant, which fits in roughly the same budget while keeping the principle names visible.

## Consequences

**Positive:**

- Four durable Praxion-specific principles are embedded at the right layer (compact in always-loaded, rich in user-facing docs).
- Principle 3 is correctly located in `ROADMAP.md` — not mixed with durable principles.
- `CLAUDE.md` block names all four principles, so discovery works even when the reader never clicks through to `README.md`.
- Post-embed non-doc session total ≈ 49,786 chars (94.8% utilization, ~2,700 chars headroom); doc-authoring session total ≈ 52,450 chars (99.9% utilization, ~50 chars headroom). Both under ceiling.
- `README.md#guiding-principles` becomes the stable anchor for all future principle references from agents, skills, and rules.

**Negative:**

- Doc-authoring sessions are ceiling-adjacent (≤50 chars headroom). The next always-loaded add on doc sessions requires either budget reclamation elsewhere or `paths:` scoping.
- Readers of `CLAUDE.md` alone get principle names without exposition — must follow the pointer for rationale. Mitigated by README-1's rich prose.
- The decision is coupled to `dec-028` — if `dec-028` is ever superseded to widen `diagram-conventions.md` path-scope again, this ADR's budget assumption breaks and the `CLAUDE.md` block may need to be trimmed.

**Operational:**

- `CLAUDE.md` block lives after the "Known Claude Code Limitations" section; README section lives between `## Core Concepts` and `## Quick Start`.
- Principle #3 remains in `ROADMAP.md` only; no embedding.
- A future phase may relocate principles into a skill (e.g., `skills/project-principles/SKILL.md`) once we have enough principle-dependent agent behavior to justify a skill; at that point this ADR can be superseded.
