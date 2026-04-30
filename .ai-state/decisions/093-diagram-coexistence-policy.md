---
id: dec-093
title: Two-toolchain coexistence policy — LikeC4 for C4-architectural; Mermaid for everything else
status: re-affirmation
category: configuration
date: 2026-04-30
summary: 'Replace the Mermaid-only mandate in `rules/writing/diagram-conventions.md` with a coexistence policy: LikeC4+D2 for C4-architectural diagrams, Mermaid for sequence/state/ER/flowchart/topology, no retroactive migration of existing Mermaid blocks.'
tags: [diagrams, conventions, rules, mermaid, likec4, coexistence]
made_by: agent
agent_type: systems-architect
pipeline_tier: standard
affected_files:
  - rules/writing/diagram-conventions.md
  - skills/doc-management/references/diagram-conventions.md
  - commands/onboard-project.md
re_affirms: dec-028
---

## Context

`rules/writing/diagram-conventions.md` currently declares: *"All diagrams in project documentation use **Mermaid** syntax. No other diagram format … is acceptable for committed documentation."* This rule was authored before the modeling-first / multi-view requirement emerged, and it is path-scoped (per dec-028 to documentation-authoring surfaces).

Adopting LikeC4 + D2 for C4-architectural diagrams (per `dec-095`) requires a substantive change to the rule body. Without this change, the sentinel will flag every committed `.c4` and `.d2` file as a convention violation, and reviewers will reasonably challenge the new format.

A binary "switch all to LikeC4" or "ban Mermaid" decision is unwarranted: 21 of the 27 Mermaid diagrams in the repo (per the internal research fragment) are sequence diagrams, state machines, ER diagrams, generic flowcharts, or pipeline-topology maps for which Mermaid is the right tool. Migrating those would burn effort against zero benefit.

The right shape is a coexistence policy keyed off diagram purpose.

## Decision

Replace the opening Mermaid-only paragraph in `rules/writing/diagram-conventions.md` with a two-toolchain policy:

- **LikeC4 → D2 → SVG** for C4-style architectural diagrams (System Context L0, Container/Component L1).
- **Mermaid** for everything else: sequence diagrams, state diagrams, ER diagrams, generic flowcharts, process diagrams, pipeline topologies, and any architectural diagram authored before this convention took effect (frozen in place — no retroactive migration).
- **Other formats (ASCII art, PlantUML, hand-drawn-image embeds) remain unacceptable.**

The remainder of the rule (Clarity First, Decomposition Strategy, Diagram Type Selection, Styling Consistency, When NOT to Diagram) is toolchain-agnostic and stays unchanged. The Diagram Type Selection table gains one row for "Multi-view C4 architecture → LikeC4".

The supporting skill (`skills/doc-management/references/diagram-conventions.md`) gains a "LikeC4 + D2" integration section parallel to the existing claude-mermaid integration section.

This ADR re-affirms `dec-028` (which narrowed `paths:` for token-budget reasons) — that scoping decision still holds; only the rule *body* changes here, not its `paths:` frontmatter. The token-budget calculus from `dec-028` remains valid.

## Considered Options

### Option 1 — Migrate all C4-shaped Mermaid diagrams to LikeC4

**Pros:** Single canonical toolchain for architectural diagrams. No "which tool do I pick?" decision for contributors.

**Cons:** 6 diagrams to migrate (templates + live files) plus an additional 5 borderline cases (deployment templates) plus the 21 frozen Mermaid blocks would also need re-evaluation. Wide blast radius. Many of the 21 are sequence/state/ER/flowchart diagrams for which LikeC4 is not the right tool. Would force LikeC4 onto non-C4 use cases or require a tertiary toolchain choice.

### Option 2 — Coexistence keyed by diagram purpose (chosen)

**Pros:** Minimal blast radius (6 migrations + 1 rule body update). Each toolchain used where it shines: LikeC4 for SSOT multi-view C4; Mermaid for GitHub-native rendering of sequence/state/ER/flowchart. Existing 21 Mermaid blocks frozen in place — no risk of breaking working documentation.

**Cons:** Two toolchains in the project — contributors must know which to use. Risk of a future contributor authoring a new C4-architectural diagram in Mermaid by mistake. Mitigated by (a) the rule update making the policy explicit, (b) the skill section providing decision guidance, (c) the sentinel surfacing C4-shaped Mermaid in newly-authored architecture documents as a finding for review.

### Option 3 — Allow either toolchain freely; no policy

**Pros:** Maximum flexibility for contributors.

**Cons:** Predictable drift: contributors author in whichever they know; sibling diagrams diverge in tooling and aesthetic; reviewers cannot enforce any consistency. Defeats the modeling-first motivator (whose value comes from a single authoring discipline). No.

## Consequences

**Positive:**

- Sentinel can pass on `.c4`/`.d2` artifacts without rule violations.
- Existing 21 Mermaid blocks remain valid — no rework.
- New C4-architectural diagrams default to LikeC4 via the updated templates and onboarding command.
- The two-toolchain decision tree is simple enough to encode in a single sentence ("multi-view C4 → LikeC4; otherwise Mermaid").

**Negative:**

- Contributors must understand the boundary. Mitigated by the rule update + skill section + onboarding probe.
- A future contributor may add a C4 architectural diagram in Mermaid by mistake; the rule update makes that catchable in review, but does not auto-prevent it.

**Operational:**

- Edit `rules/writing/diagram-conventions.md` body (no frontmatter change — `dec-028` scoping retained).
- Add LikeC4 integration section to `skills/doc-management/references/diagram-conventions.md`.
- Update `commands/onboard-project.md` Phase 8 prompt to instruct LikeC4 for C4 architectural diagrams.
- Update both `ARCHITECTURE_TEMPLATE.md` and `ARCHITECTURE_GUIDE_TEMPLATE.md` to use the new format in §2 and §3 placeholders.

## Prior Decision

`dec-028` narrowed the `paths:` frontmatter on this rule for token-budget reasons; it did not address the rule's body. The substantive Mermaid-only mandate predates `dec-028`. This ADR changes the body without changing the `paths:` scope, so `dec-028`'s budget calculus is unaffected. The re-affirmation flag formalizes that this ADR builds on top of `dec-028` rather than replacing it: future supersessions of *either* must consider both.
