---
id: dec-095
title: LikeC4 + D2 chosen as C4-architectural diagramming toolchain
status: proposed
category: architectural
date: 2026-04-30
summary: 'Adopt LikeC4 DSL + native D2 codegen + D2-rendered SVG for C4-architectural diagrams; reject Structurizr CLI (archived) and Structurizr vNext (D2 export bundling unconfirmed) and Mermaid C4 (no SSOT/multi-view).'
tags: [diagrams, c4, likec4, d2, toolchain, structurizr, mermaid]
made_by: agent
agent_type: systems-architect
pipeline_tier: standard
affected_files:
  - rules/writing/diagram-conventions.md
  - skills/software-planning/assets/ARCHITECTURE_TEMPLATE.md
  - skills/doc-management/assets/ARCHITECTURE_GUIDE_TEMPLATE.md
  - docs/architecture.md
  - .ai-state/ARCHITECTURE.md
  - skills/doc-management/references/diagram-conventions.md
  - commands/onboard-project.md
  - agents/systems-architect.md
  - agents/implementer.md
---

## Context

The user requested a modeling-first / multi-view C4 diagramming workflow with D2-aesthetic rendering, coexisting with Mermaid. Three researcher fragments produced a four-option landscape:

1. Structurizr DSL + D2 via the (now archived since 2026-02-04) `structurizr/cli` Java JAR plus the third-party `goto1134/structurizr-d2-exporter` v1.6.0.
2. Structurizr DSL + D2 via the consolidated `structurizr/structurizr` vNext WAR (`v2026.04.19`, Java 21). The vNext changelog only documents `png|svg` export formats; D2 bundling is unconfirmed and would require a runtime test.
3. LikeC4 DSL + native `likec4 gen d2` + D2 render. Active (`v1.56.0`, 2026-04-28), MIT, Node-only.
4. Mermaid C4 plugin syntax already shipped via the `claude-mermaid` plugin in the project. Per-diagram authoring; no single-model multi-view derivation.

Key surfacing facts: the `structurizr-d2-exporter` has a documented bug emitting `multiboard output cannot be written to stdout` (May 2025, paval.io). Mermaid C4 cannot deliver the user's #1 motivator (single-model multi-view). The `structurizr/cli` archive status removes the safe-default path that the user's scope text initially implied.

Praxion has zero Structurizr DSL on disk today, so DSL-portability cost is zero today.

## Decision

Adopt **LikeC4 DSL → `likec4 gen d2` → `d2 ... .svg`** as the canonical toolchain for C4-architectural diagrams in Praxion (and in projects scaffolded by Praxion's onboarding). Mermaid is retained for sequence diagrams, state diagrams, ER diagrams, generic flowcharts, pipeline topologies, and any pre-existing C4-shaped diagram outside the six migration candidates identified in research.

Pin D2 to v0.7.1 (the most recent release, August 2024); pin LikeC4 to a known-good `^1.56` major. Both pins are documented in onboarding install instructions and CI.

## Considered Options

### Option 1 — Structurizr DSL + D2 via the archived `structurizr/cli`

**Pros:** Mature, well-documented DSL; widely cited reference for C4 modeling; old CLI still functional and downloadable; the third-party D2 exporter is bundled into the JAR (no separate install).

**Cons:** CLI archived 2026-02-04 — read-only, no further bug fixes. The `multiboard output cannot be written to stdout` bug is unresolved upstream; usable only via `-output <dir>` mode. Java 17 dependency. Future D2 versions may drift past the bundled exporter. Adopts a tool whose maintainers have explicitly declared end-of-maintenance.

### Option 2 — Structurizr DSL + D2 via Structurizr vNext WAR

**Pros:** Active replacement for the archived CLI; preserves Structurizr DSL semantics; presumed long-term home of the Structurizr ecosystem.

**Cons:** Requires Java 21 (a step up from 17). The vNext changelog through `v2026.04.19` documents only `png|svg` exports — whether the `goto1134/structurizr-d2-exporter` is bundled into vNext is **unconfirmed**. Adopting an unverified capability fails the Surface Assumptions contract. WAR distribution is heavier than the old fat-JAR. The architect cannot perform the empirical verification (`java -jar structurizr.war export -workspace test.dsl -format d2 -output /tmp/`) needed to safely confirm the bundling.

### Option 3 — LikeC4 + D2 (chosen)

**Pros:** Active maintenance (v1.56.0 days before this decision). MIT license. Native `likec4 gen d2` codegen — does not invoke the buggy third-party exporter. No Java dependency; Node-only install. Smaller toolchain surface in CI. Renders via `d2` directly, preserving the D2 aesthetic the user requested. SSOT model with multi-view projection: matches the user's #1 motivator. Praxion has zero Structurizr DSL today, so the DSL-divergence cost is zero now.

**Cons:** Smaller community than Structurizr (~3,100 stars vs Structurizr's broader ecosystem). DSL is not Structurizr-compatible; if Praxion later wanted to share models with Structurizr cloud or Ilograph, a port would be needed. LikeC4's own renderer requires Playwright for PNG and historically lacked SVG; mitigated by routing through `likec4 gen d2` and using D2's native SVG renderer.

### Option 4 — Mermaid C4 plugin

**Pros:** Already in the project (claude-mermaid plugin v1.2.0 user-scope). Zero new dependencies. GitHub-native rendering with no committed SVG. Most contributors already know Mermaid syntax.

**Cons:** **Fails the user's #1 motivator** — no single-model multi-view derivation; each `C4Container` block is hand-authored independently. Drift between sibling diagrams is silent. Experimental status; no `systemLandscape` view. The C4 Mermaid syntax is less expressive than LikeC4 or Structurizr DSL. Adopting it would silently abandon the modeling-first goal.

## Consequences

**Positive:**

- Single-source-of-truth for architectural diagrams; multiple views projectable without copy-paste drift.
- D2 render aesthetic preserved end-to-end.
- No Java in the toolchain — onboarding is `npm install -g @likec4/likec4 && brew install d2`.
- Avoids the third-party Structurizr-D2 exporter's stdout bug structurally (no CLI invocation in the path).
- Active maintenance trajectory removes long-tail repair-cost overhang.

**Negative:**

- LikeC4's smaller community is a sustainability risk — pin versions and treat committed SVGs as the durable artifact.
- Two-toolchain coexistence (LikeC4 + Mermaid) requires rule + skill guidance so contributors know which to use; sentinel may need future tuning to recognize `.c4`/`.d2` as legitimate.
- D2 has not released since August 2024 (v0.7.1, ~20 months at decision date). Pin and watch for activity; rollback path is to fork-and-patch if needed.
- Future portability to the Structurizr ecosystem requires a DSL port — accepted because no current usage.

**Operational:**

- Render hook fires on staged `**/diagrams/*.c4` changes; gracefully skips when binaries are absent.
- CI gate regenerates and rejects PRs whose committed SVGs disagree with `.c4` source.
- Onboarding probe surfaces install requirement; non-installation does not block onboarding.
