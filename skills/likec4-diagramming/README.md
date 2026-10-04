# likec4-diagramming

Authoring, review and query guidance for LikeC4 architecture models. It covers the loop from drafting a view
in the project's style kit, through the review checks and the one regeneration command, to the committed SVG
renders, and it keeps the decision rubric for choosing between the `likec4` MCP server (parsed model objects,
BFS traversal, cross-project indexing) and direct `.c4` reads (raw DSL text, edit-capable). Path-scoped:
activates when working with `.c4` files, `.ai-state/DESIGN.md` or `docs/diagrams/`.

## When to Use

- Authoring or modifying `.c4` files, diagram sources or `.ai-state/DESIGN.md`
- Reviewing an architecture diagram against the review checks
- Regenerating or debugging the committed renders
- Exploring a LikeC4 model for design decisions or dependency analysis
- Choosing between MCP tools and direct file reads for an architecture query

## Activation

Path-scoped to `**/*.c4`, `**/DESIGN.md`, `docs/architecture.md`, and `docs/diagrams/**`. Activates
automatically when Claude reads files matching these patterns.

## Skill Contents

- `SKILL.md` — authoring loop, category rule and vocabularies, view recipe, query decision rubric, gotchas
- `references/review-checks.md` — the review-check list and every threshold
- `references/render-and-regen.md` — pinned toolchain, the regeneration command, hook and CI gate
- `references/mcp-tool-recipes.md` — quick-reference table and worked examples for all 20 MCP tools

## Quick Start

1. Read the project's `_spec.c4` style kit before editing any `.c4`
2. Draft the view; iterate with `preview-view` when the MCP is present
3. Run `python3 scripts/regenerate_diagrams.py`, then `--check`, and apply each review check to the views you touched

## Related Skills

- [`software-planning`](../software-planning/SKILL.md) — when LikeC4 query results feed into system design decisions
- [`doc-management`](../doc-management/SKILL.md) — Mermaid conventions for non-C4 diagrams
