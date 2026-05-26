# likec4-querying

Decision rubric and tool reference for querying LikeC4 architecture models. Helps agents
choose between the `likec4` MCP server (parsed model objects, BFS traversal, cross-project
indexing) and direct `.c4` file reads (raw DSL text, edit-capable) so the right approach
is used on the first try. Path-scoped: activates when working with `.c4` files or
`ARCHITECTURE.md`.

## When to Use

- Authoring or modifying `.c4` files or `ARCHITECTURE.md`
- Exploring a LikeC4 model for design decisions or dependency analysis
- Choosing between MCP tools and direct file reads for an architecture query
- Working under `docs/diagrams/`

## Activation

Path-scoped to `**/*.c4`, `**/ARCHITECTURE.md`, `docs/architecture.md`, and
`docs/diagrams/**`. Activates automatically when Claude reads files matching these
patterns.

## Skill Contents

- `SKILL.md` — decision rubric (MCP vs. direct read), MCP tool quick reference (13 tools), common pitfalls
- `references/mcp-tool-recipes.md` — full input shapes and worked examples for all 13 MCP tools

## Quick Start

When working with a LikeC4 model:

1. Check whether the task requires a write (always use `Read` + `Edit` — MCP is read-only)
2. For narrow lookups on a single small file, use direct `Read`
3. For cross-project or multi-element queries, prefer the MCP tools — see the decision rubric in `SKILL.md`

## Related Skills

- [`software-planning`](../software-planning/SKILL.md) — when LikeC4 query results feed into system design decisions
