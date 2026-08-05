---
name: likec4-querying
description: >
  Decision rubric and recipes for querying LikeC4 architecture models: `likec4`
  MCP tools vs. reading `.c4` files directly. Path-scoped to
  architecture-authoring surfaces. Triggers: authoring/modifying
  DESIGN.md, .c4 files, diagram sources, exploring LikeC4 model for
  design decisions.
allowed-tools: [Read, Glob, Grep, Bash]
compatibility: Claude Code
paths: ["**/*.c4", "**/DESIGN.md", "docs/architecture.md", "docs/diagrams/**"]
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
quick reference for all 18 MCP tools, so agents choose the right path on the first try.

**Satellite files** (loaded on-demand):

- [`references/mcp-tool-recipes.md`](references/mcp-tool-recipes.md) — full tool catalog:
  input shape + worked example for each of the 18 MCP tools

## Decision Rubric
<!-- last-verified: 2026-08-05 -->

| Task signal | Tool | Reason |
|-------------|------|--------|
| Single small `.c4` file (≤200 lines), full read needed | Direct `Read` | Lower latency; full text fits in context without an MCP round-trip |
| Multiple `.c4` files; need elements across projects | `list-projects` + `read-project-summary` | Aggregates elements and views; avoids reading every file individually |
| **Known set of element ids** to fetch | `batch-read-elements` | Up to 50 ids in one round-trip — cheaper than `read-project-summary`, which returns the whole model |
| Find element by name, kind, or tag in unknown location | `search-element` | Avoids reading every `.c4` file; indexed search |
| Get all upstream or downstream dependencies of element X | `query-incomers-graph` / `query-outgoers-graph` | One call replaces repeated `Read` + parse; BFS-optimized for recursive traversal |
| **Survey everything under a parent element** | `subgraph-summary` | Returns every descendant with depth, tags, metadata, and relationship counts in one call — much cheaper than `read-element` per descendant |
| Find the relationship path between two specific elements | `find-relationship-paths` | BFS traversal is already in the tool; reimplementing it by hand wastes tokens |
| **Compare two elements** side by side | `element-diff` | Properties, tags, metadata, and relationships diffed server-side |
| Filter elements by metadata key (e.g., `code_module=X`) | `query-by-metadata` | Server-side indexed filter; faster than grep-and-parse |
| Filter elements by tag boolean expression | `query-by-tags` | Server-side boolean filter; handles `allOf`, `anyOf`, `noneOf` |
| **Match tags by shape** (`schedule_*`, `*_asil_*`) | `query-by-tag-pattern` | Prefix / contains / suffix matching — distinct from `query-by-tags`, which takes exact tags with boolean logic |
| Edit a `.c4` file (write content) | Direct `Read` + `Edit` | The **query** tools are read-only; `.c4` source text is only writable through the file |

## MCP Tool Quick Reference
<!-- last-verified: 2026-08-05 -->

**18 tools.** Every tool below carries `readOnlyHint` and `idempotentHint` **except
`apply-semantic-layout`**, which writes a snapshot — see Common Pitfalls.

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
| `query-by-tag-pattern` | Tag **pattern** matching — prefix / contains / suffix; for structured taxonomies (`schedule_*`, `*_asil_*`) |
| `batch-read-elements` | Read details for multiple elements in one call (**max 50 ids**) |
| `element-diff` | Compare two elements side by side: properties, tags, metadata, relationships |
| `subgraph-summary` | Compact summary of all descendants of a parent: depth, tags, metadata, relationship counts (`maxDepth` default 10, max 20; capped at 200 descendants) |
| `apply-semantic-layout` | Apply semantic layout to a **view** (LLM-driven via MCP sampling). **Not read-only** — saves a snapshot |

## Common Pitfalls

- **The *query* tools are read-only — but the tool surface is not.** To write or edit a `.c4`
  file you still need `Read` + `Edit`; no MCP tool produces a writable view of the source
  text. The exception to the blanket claim is `apply-semantic-layout`, which operates on a
  **view** (not on `.c4` source), is the only tool without a `readOnlyHint` annotation, and
  saves a snapshot. Note the server's own `instructions` string still asserts "All tools are
  read-only and idempotent" — that prose is stale upstream; the per-tool annotations are
  authoritative.

- **`read-project-summary` is expensive for narrow lookups.** It returns the entire project
  model. For a single element or a narrow tag query, use `read-element`, `search-element`,
  or `query-by-tags` instead. When you already know which elements you want,
  `batch-read-elements` fetches up to 50 by id in one round-trip.

- **`find-relationship-paths` is already bounded — don't over-set `maxDepth`.** The default is
  **3** and the server **caps it at 5**; the parameter is rejected above that. (An earlier
  version of this skill said the default was unbounded and advised 4–6, which both
  misdescribed the default and exceeded the maximum.) Results are additionally limited to 100
  paths. `subgraph-summary` is the one to watch for breadth: default `maxDepth` 10, max 20,
  truncated at 200 descendants — use `metadataKeys` to trim the response.

- **MCP may lag behind unsaved edits.** If you have just edited a `.c4` file in this session
  and the MCP server has not reloaded, its view of the model may be stale. Verify or re-read
  the source file when consistency with recent edits matters.

- **MCP is session-provided, not always available.** In Praxion's current configuration, the
  `likec4` MCP server is injected at session start. When MCP tools are absent (e.g., running
  outside Claude Code, or in a project without the server configured), fall back to direct
  `.c4` reads for all queries.

## Reference

Full input shapes and worked examples for all 18 tools:
[`references/mcp-tool-recipes.md`](references/mcp-tool-recipes.md)

Re-verify when the LikeC4 MCP tool surface changes (run `list-projects` or inspect the MCP
server's tool list in the session reminder to detect additions or removals).

## Related Skills

- [`software-planning`](../software-planning/SKILL.md) — when architectural analysis of LikeC4 query results feeds into system design decisions.
