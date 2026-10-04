---
id: dec-draft-6aad9591
title: A Praxion-owned D2 emitter over `likec4 export json` replaces native `likec4 gen d2` in every C4 render path
status: proposed
category: architectural
date: 2026-10-04
summary: "New component scripts/regenerate_diagrams.py reads each LikeC4 workspace via `likec4 export json --skip-layout`, emits category-styled D2 (classes, plain multi-line labels, in-render title and legend, synthesized edge labels), renders with pinned d2 0.7.1, scrubs the version stamp, fails only on the four regeneration-failure kinds, and under --check reports review findings DRC-01..DRC-12; the hook, both CI drift gates and onboarding all call it; likec4 pinned to 1.59.4, d2 stays 0.7.1."
tags: [diagrams, c4, likec4, d2, rendering, toolchain, review-checks, determinism]
made_by: agent
agent_type: systems-architect
branch: worktree-likec4-diagram-craft
pipeline_tier: full
affected_files:
  - scripts/regenerate_diagrams.py
  - scripts/test_regenerate_diagrams.py
  - scripts/diagram-regen-hook.sh
  - scripts/normalize_d2_svg.sh
  - .pre-commit-config.yaml
  - .github/workflows/architecture.yml
  - claude/aac-templates/architecture.yml.tmpl
  - docs/architecture-diagrams.md
  - docs/diagrams/README.md
affected_reqs: [REQ-01, REQ-02, REQ-03, REQ-04, REQ-05, REQ-06, REQ-07, REQ-08, REQ-10, REQ-11, REQ-14, REQ-16]
supersedes_in_part: [dec-095, dec-094]
dissent: "Emitting SVG directly from LikeC4's own layouted export would remove d2 and its version pin, give full markup control and match the LikeC4 UI layout; the D2 route keeps a second layout engine whose output differs from what authors see in LikeC4."
---

## Context

`likec4 gen d2` emits only labels, a partial shape map and nesting. It drops colour, icon, description, technology, notation, line style and every view-level style. Restyling the model therefore never reaches the committed renders. A probe of the installed toolchain confirmed this, and the visual audit found every element drawn as the same blue box, a 3.40:1 strip, text at 3 px at docs width, and 16 `[...]` aggregated labels.

The committed-artifact contract (source + generated + rendered SVG committed; pre-commit regeneration; a byte-diff CI gate; an SVG-only dashboard route) is load-bearing and stays. LikeC4 has no native SVG export. Its PNG export needs Playwright and is raster.

`likec4 export json` carries the full model: kinds, metadata, descriptions, technology, relationship kinds, and computed views with nodes, children and edges. Dynamic views add numbered steps.

## Decision

Add **`scripts/regenerate_diagrams.py`**: stdlib-only, Python 3.9-safe, single file. It is the one regeneration path for C4 views.

1. Read each workspace with `likec4 export json --skip-layout`.
2. Resolve every element's category (kind `notation`, overridden by `metadata.category`; see dec-draft-2fbfa6d3).
3. Emit one `<view>.d2` per view:
   - token classes;
   - plain multi-line labels (`name` / `[category · technology]` / responsibility);
   - a title block naming the view title and its C4 type;
   - a legend container labelled `Legend` with one sample per category and line style present;
   - edge labels synthesized deterministically from the underlying relationships, never `[...]`;
   - dashed edges for the `reads` relationship kind; numbered steps for dynamic views.
4. Render with `d2` 0.7.1 and scrub `data-d2-version`. This absorbs `normalize_d2_svg.sh`.
5. Measure the SVG (ratio, rendered text height at 960 px, label overlap) and prune orphaned renders.
6. Fail (exit 1) only on the four regeneration failures: `toolchain-error`, `no-views`, `view-without-render`, `render-without-names`. `--check` renders to a temp dir, byte-compares with the committed renders, and prints one finding per review check (`DRC-01`..`DRC-12`) and view, exiting 1 on drift or a FAIL. It never writes. `--staged` is the pre-commit mode: it stages `rendered/`, and its FAIL findings print as non-blocking warnings. Review checks never run inside the CI drift-gate job, which must pass whenever the renders match.

The pre-commit shim, Praxion's CI drift gate, the managed-project CI template and onboarding all call it. The CI diff step also fails on untracked renders.

**Pins:** likec4 **1.59.4** (from 1.56.0); d2 **0.7.1**, kept. Dark-mode renders are deferred: opaque white canvas. The acceptance driver flattens `@media` rules, so a class-scoped dark layer would corrupt the text-only reading.

**Companion drafts** (interface designer, complementary, not competing):
- `dec-draft-854e860b` fixes this command's interface: flags, exit codes, failure and finding formats, and the review-check table.
- `dec-draft-026e4301` fixes the light-only token values and the per-category marks the emitter applies.

## Considered Options

### Option 1: Rich D2 emitter over `export json` (chosen)

**Pros:**
- Carries every semantic into a byte-stable SVG.
- Reuses d2's renderer (shapes, ELK routing, label placement, embedded fonts).
- Keeps the committed `.d2` and the `d2` toolchain that the acceptance contracts and the hook test bind to.
- Probed end to end through the acceptance SVG driver: element marks, legend region, arrows, text height and overlap all read correctly.

**Cons:**
- Praxion owns about 400–600 tested lines.
- d2's ELK layout differs from LikeC4's own.
- Markdown labels are unusable: d2 puts their `foreignObject` outside the shape's group.

### Option 2: Direct SVG emitter over LikeC4's layouted export

**Pros:**
- No d2 and no second pin.
- Full markup control.
- Layout identical to the LikeC4 UI.

**Cons:**
- Praxion owns geometry: shape paths, text wrapping, arrowheads, label placement.
- Breaks the acceptance contracts bound to d2 output and to `d2` on PATH, and the hook test that expects staged `.d2`.
- Larger and riskier code.

### Option 3: `likec4 gen dot` + Graphviz

**Pros:** keeps colours, descriptions and dash styles natively.
**Cons:** no icons, no person shape, no class hook; Graphviz is one more pinned tool.

### Option 4: Native PNG export

**Cons:** raster, not byte-stable, Playwright dependency, and the dashboard route serves SVG only. Fails the committed-artifact contract.

## Consequences

**Positive:**
- Categories, responsibilities, technology, titles, legends and intent labels reach every committed render.
- One command serves contributors, CI, managed projects and reviewing agents.
- The review checks become mechanically decidable from text.

**Negative:**
- A new tested component.
- `rendered/*.d2` grows (classes, small data-URI icons).
- Authors see a different layout in the LikeC4 UI than in the committed render.
- Dark-UI readers get a white card until dark mode lands.

## Disconfirmation

- **Falsifier:** after the view restructure, two or more views still cannot meet the 10 px at 960 px or 0.5–2.5 ratio checks under d2/ELK. Or the drift gate shows cross-machine byte differences with both pins held.
- **Steelmanned runner-up:** a direct SVG emitter over LikeC4's layouted export. LikeC4's layout is tuned for C4 node sizes, and the committed render would match what authors preview. It removes the d2 pin, the d2 quirks (markdown-label grouping, `near` placement) and the `.d2` intermediate. Full markup control makes agent-readability a property of Praxion's own serializer rather than an accident of d2's group structure.
- **Reversal trigger:** the falsifier fires, or a d2 behaviour change blocks a pin bump that a later requirement needs. Then re-open with option 2 and re-bind the acceptance contracts.

## Prior Decision

**dec-095 (narrowed, not replaced).** The toolchain choice stands: LikeC4 DSL + D2-rendered SVG for C4 views, Mermaid for everything else, with Structurizr and Mermaid C4 rejected for the reasons given. Two clauses are narrowed:
1. "native `likec4 gen d2` codegen" → Praxion's renderer emits the D2 from `likec4 export json`.
2. "pin LikeC4 to a known-good `^1.56` major" → likec4 is pinned exactly to 1.59.4.

The D2 v0.7.1 pin stands.

**dec-094 (narrowed, not replaced).** Committing the source, the generated `.d2` and the rendered `.svg` together, with pre-commit regeneration, a graceful skip when the toolchain is absent, and a CI freshness gate, all stand. Narrowed:
- the producer ("Produced by `likec4 gen d2`" → produced by the renderer);
- the layout clauses, already drifted on disk: sources at `<doc-dir>/diagrams/<name>/src/*.c4` and renders at `<doc-dir>/diagrams/<name>/rendered/`;
- the embedding clause: markdown image syntax, with no fenced `c4` source block beside the image, per the diagram rule.

Activation: fired — structural (≥ 5 files, ≥ 2 subsystems) + multiple plausible paths; lens set = Security, Performance, Simplicity, Testability; convergence = stable.
