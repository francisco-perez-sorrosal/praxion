---
name: likec4-diagramming
description: "Author, review and query LikeC4 architecture models: category style kit, legends, review checks, regen loop, `likec4` MCP tools vs reading `.c4` directly. Triggers: authoring/modifying DESIGN.md, .c4 files, diagram sources, reviewing architecture diagrams, exploring the model for design decisions."
allowed-tools: [Read, Glob, Grep, Bash]
compatibility: Claude Code
paths: ["**/*.c4", "**/DESIGN.md", "docs/architecture.md", "docs/diagrams/**"]
staleness_sensitive_sections: ["Decision Rubric", "MCP Tool Quick Reference"]
staleness_threshold_days: 60
---

# LikeC4 Diagramming

A LikeC4 model is the single source of structural truth; the committed SVG renders are
projections of it. This skill covers the whole loop: authoring a view so it reads
professionally, checking it against the review checks, regenerating the renders, and
querying the model (MCP tools or raw `.c4` reads) while you work.

**Satellite files** (loaded on-demand):

- [`references/review-checks.md`](references/review-checks.md) — the review-check list; the only home of thresholds
- [`references/render-and-regen.md`](references/render-and-regen.md) — the pinned toolchain, the one regeneration command, the hook and the CI gate
- [`references/mcp-tool-recipes.md`](references/mcp-tool-recipes.md) — the 20 MCP tools: quick-reference table, input shapes, worked examples

## Authoring loop

1. **Read the project's style kit first.** `docs/diagrams/<name>/src/_spec.c4` declares the kinds, their
   category vocabulary and the must-pass list. Treat it as the sibling you imitate; a project without one
   gets it from `/onboard-project --with aac`.
2. **Draft the view.** Edit the `.c4` with `Read` + `Edit`. With the `likec4` MCP present, iterate on an
   element view with `preview-view` (DSL text in, nothing written to disk).
3. **Regenerate.** `python3 scripts/regenerate_diagrams.py` rewrites `rendered/`; see
   [`render-and-regen.md`](references/render-and-regen.md).
4. **Check.** `python3 scripts/regenerate_diagrams.py --check` byte-compares the renders and prints one
   finding per review check and view. Then apply every check in [`review-checks.md`](references/review-checks.md)
   to each view you touched, and record any you could not run.
5. **Commit source and renders together.** The `diagram-regen` pre-commit hook stages `rendered/` for you.

## Categories

An element's category is the `notation` of its kind, overridden by `metadata { category '<name>' }` when
one kind spans several categories. Every element resolves to exactly one category, and the category must
name a style token; an element that does not draws as "Uncategorised" and fails the colour-free check.
New models use kinds alone (the LikeC4 idiom, which also fills LikeC4's native legend); the override is
the escape hatch for a kind like Praxion's `component`.

| Vocabulary | Categories |
|---|---|
| Kit floor (onboarded projects) | Person, System in scope, External system, Container, Component, Data store |
| Praxion | Person, System in scope, External system, Knowledge asset, Runtime agent, Pipeline document, Persistent store, Tooling, Layer |

A project adds a category in `<diagram-root>/style.json` rather than editing the command.

## View recipe

- One view, one abstraction level, one C4 type: a single `c4_*` tag, or a dynamic view. Title it with the
  subject, never a bare "Overview".
- Read arrows as sentences from source to target; label every one with intent, never "uses" or "calls".
- Give every element a `summary` (its responsibility) and a `technology` where one applies.
- Show a parent as an enclosing frame or not at all; never draw a box and its own ancestor box together.
- Split a view before it fills with arrows: the proportion and fan-in checks bind, and a crowded view that
  cannot meet them is a missing view.
- Relationships that only read use the `reads` kind, so the legend can tell flows from writes.

## Decision Rubric
<!-- last-verified: 2026-10-04 -->

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
| Edit a `.c4` file (write content) | Direct `Read` + `Edit` | The **query** tools never write `.c4` source; it is only writable through the file |

The tool table is in [`references/mcp-tool-recipes.md`](references/mcp-tool-recipes.md#mcp-tool-quick-reference).

## Gotchas

- **Not every tool is read-only.** `apply-semantic-layout` saves a snapshot and carries no `readOnlyHint`.
  The server's own instructions still claim "All tools are read-only" — the per-tool annotations are
  authoritative.
- **`preview-view` is LikeC4's own drawing, not the committed render.** It checks structure and element
  references, not styling, and it rejects `dynamic view` and `deployment view` text.
- **`read-project-summary` is expensive for narrow lookups.** Use `read-element`, `search-element` or
  `query-by-tags` for a single element or a narrow tag query.
- **MCP lags behind unsaved edits and may be absent.** Re-read the source when recent edits matter; with no
  MCP in the session, fall back to direct `.c4` reads for every query.
- **A stale render is a defect, not style drift.** Regenerate after every model edit; the CI drift gate
  fails on any difference between `rendered/` and a fresh regeneration.
- **The version pins are exact** and stated once, in
  [`render-and-regen.md`](references/render-and-regen.md); a different local version regenerates different
  bytes.

## Related Skills

- [`software-planning`](../software-planning/SKILL.md) — when architectural analysis of LikeC4 query results feeds into system design decisions.
- [`doc-management`](../doc-management/SKILL.md) — Mermaid conventions for the non-C4 diagrams that stay in Markdown.
