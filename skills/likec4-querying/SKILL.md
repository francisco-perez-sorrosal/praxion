---
name: likec4-querying
description: >
  Decision rubric and recipes for querying LikeC4 architecture models: `likec4`
  MCP tools vs. reading `.c4` files directly. Path-scoped to
  architecture-authoring surfaces. Triggers: authoring/modifying
  ARCHITECTURE.md, .c4 files, diagram sources, exploring LikeC4 model for
  design decisions.
allowed-tools: [Read, Glob, Grep, Bash]
compatibility: Claude Code
paths: ["**/*.c4", "**/ARCHITECTURE.md", "docs/architecture.md", "docs/diagrams/**"]
staleness_sensitive_sections: ["## Decision Rubric", "## MCP Tool Quick Reference"]
staleness_threshold_days: 60
---

# LikeC4 Querying

## Purpose

LikeC4 architecture models are queryable via the `likec4` MCP server (when present in the
session) or readable as raw `.c4` source files (always available via `Read`). The two
approaches are complementary, not interchangeable: MCP tools return parsed model objects
with cross-project indexing and BFS traversal; direct reads return raw DSL text that
supports edits. This skill provides a clear rubric for when to prefer each approach and a
quick reference for all 13 MCP tools, so agents choose the right path on the first try.

**Satellite files** (loaded on-demand):

- [`references/mcp-tool-recipes.md`](references/mcp-tool-recipes.md) — full tool catalog:
  input shape + worked example for each of the 13 MCP tools

## Decision Rubric
<!-- last-verified: 2026-04-30 -->

| Task signal | Tool | Reason |
|-------------|------|--------|
| Single small `.c4` file (≤200 lines), full read needed | Direct `Read` | Lower latency; full text fits in context without an MCP round-trip |
| Multiple `.c4` files; need elements across projects | `list-projects` + `read-project-summary` | Aggregates elements and views; avoids reading every file individually |
| Find element by name, kind, or tag in unknown location | `search-element` | Avoids reading every `.c4` file; indexed search |
| Get all upstream or downstream dependencies of element X | `query-incomers-graph` / `query-outgoers-graph` | One call replaces repeated `Read` + parse; BFS-optimized for recursive traversal |
| Find the relationship path between two specific elements | `find-relationship-paths` | BFS traversal is already in the tool; reimplementing it by hand wastes tokens |
| Filter elements by metadata key (e.g., `code_module=X`) | `query-by-metadata` | Server-side indexed filter; faster than grep-and-parse |
| Filter elements by tag boolean expression | `query-by-tags` | Server-side boolean filter; handles `allOf`, `anyOf`, `noneOf` |
| Edit a `.c4` file (write content) | Direct `Read` + `Edit` | MCP is read-only; writes must go through the file directly |

## MCP Tool Quick Reference
<!-- last-verified: 2026-04-30 -->

| Tool | Purpose |
|------|---------|
| `list-projects` | List all LikeC4 projects in the workspace |
| `read-project-summary` | Full project spec: all elements, deployment nodes, and views in one call |
| `search-element` | Search elements and deployment nodes by id, title, kind, shape, tags, or metadata |
| `read-element` | Full details for one element: relationships, views it appears in, deployment instances |
| `read-deployment` | Details for a deployment node or deployed instance |
| `read-view` | Full view details including nodes, edges, and source location |
| `find-relationships` | Direct and indirect relationships between two named elements |
| `query-graph` | Element hierarchy queries (ancestors, descendants, siblings) and relationship queries |
| `query-incomers-graph` | Complete upstream dependency graph (recursive incomers) |
| `query-outgoers-graph` | Complete downstream dependent graph (recursive outgoers) |
| `query-by-metadata` | Search elements by metadata key-value with exact/contains/exists matching |
| `query-by-tags` | Advanced tag filtering with boolean logic (allOf, anyOf, noneOf) |
| `find-relationship-paths` | All paths (chains of relationships) between two elements via BFS |

## Common Pitfalls

- **MCP is read-only.** To write or edit a `.c4` file, use `Read` to load it, then `Edit` to
  apply changes. Calling an MCP tool will not produce a writable view of the source text.

- **`read-project-summary` is expensive for narrow lookups.** It returns the entire project
  model. For a single element or a narrow tag query, use `read-element`, `search-element`,
  or `query-by-tags` instead to avoid loading more data than the task needs.

- **Bound `find-relationship-paths` with `max-depth`.** The BFS traversal can fan out widely
  in highly-connected models. Set `maxDepth` (default is unbounded) to a practical limit
  (e.g., 4–6) to avoid runaway token consumption.

- **MCP may lag behind unsaved edits.** If you have just edited a `.c4` file in this session
  and the MCP server has not reloaded, its view of the model may be stale. Verify or re-read
  the source file when consistency with recent edits matters.

- **MCP is session-provided, not always available.** In Praxion's current configuration, the
  `likec4` MCP server is injected at session start. When MCP tools are absent (e.g., running
  outside Claude Code, or in a project without the server configured), fall back to direct
  `.c4` reads for all queries.

## Reference

Full input shapes and worked examples for all 13 tools:
[`references/mcp-tool-recipes.md`](references/mcp-tool-recipes.md)

Re-verify when the LikeC4 MCP tool surface changes (run `list-projects` or inspect the MCP
server's tool list in the session reminder to detect additions or removals).

## Related Skills

- [`software-planning`](../software-planning/SKILL.md) — when architectural analysis of LikeC4 query results feeds into system design decisions.
