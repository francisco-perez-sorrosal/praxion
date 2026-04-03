# Memory MCP Server -- Developer Guide

Architecture and internals for contributors. Read [README.md](README.md) for usage documentation.

## Architecture

A pure stdio MCP server with JSON file persistence. No HTTP server, no database, no background threads. The `i-am` plugin starts the process via `uv run` and communicates over stdin/stdout.

**Why MCP over SKILL.md procedures**: The previous approach had the LLM execute JSON read/write procedures from a skill file. This was fragile (non-deterministic execution), excluded sub-agents (skills require activation), and lacked atomicity. The MCP server provides deterministic Python operations, universal agent access via plugin registration, atomic file writes, and testable code.

```
LLM / Sub-agent  -->  MCP tools (stdio)  -->  MemoryStore  -->  memory.json
                                                    |
                                              lifecycle.py (read-only analysis)
                                              consolidation.py (structured actions)
```

## Module Map

| File | Purpose |
|------|---------|
| `schema.py` | Dataclasses (`MemoryEntry`, `Source`, `Link`), constants (`VALID_CATEGORIES`, `VALID_RELATIONS`, `SCHEMA_VERSION`), `generate_summary()` |
| `store.py` | `MemoryStore` class: CRUD operations, dedup logic, access tracking, link management, browse index, consolidation dispatch, atomic file I/O with locking |
| `search.py` | Scoring functions (text match, tag overlap, importance, recency), multi-term matching, Markdown-KV formatting (`format_markdown_kv_index`, `format_search_results_markdown`) |
| `dedup.py` | Dedup candidate detection, value similarity, word extraction, stop-word filtering, recommendation logic |
| `consolidation.py` | Action validation (`validate_actions`) and atomic execution (`apply_actions`) for merge, archive, adjust_confidence, update_summary |
| `lifecycle.py` | `analyze()` function: staleness detection, archival candidates, confidence adjustment proposals. Pure analysis, never mutates data |
| `server.py` | FastMCP server instance, 16 `@mcp.tool()` definitions, 2 `@mcp.resource()` endpoints, lazy store initialization |
| `__main__.py` | Entry point: imports `mcp` from `server`, calls `mcp.run()` |

## Key Design Decisions

**JSON over SQLite**: The memory file is committed to git and reviewed by humans. SQLite would break `git diff` workflows and require an export step. At <200 entries, JSON scan performance is irrelevant.

**Fresh v1.3 schema (no migrations)**: The store validates `schema_version == "1.3"` on load and raises `ValueError` on mismatch. No migration code from v1.0/v1.1/v1.2 -- the codebase was simplified by dropping legacy migration paths.

**Soft delete over hard delete by default**: `forget()` sets `invalid_at` and `status=superseded` instead of removing entries. This preserves history for temporal queries and consolidation. `hard_delete()` exists for permanent removal of sensitive data.

**Summary field for progressive disclosure**: Each entry has a `summary` field (~100 chars) auto-generated from `value` if not provided. `browse_index` and `search(detail="index")` return summaries in Markdown-KV format, keeping token usage low for large stores.

**Consolidation as structured actions**: Instead of ad-hoc merging, `consolidate()` accepts a JSON array of typed actions that are validated before execution and applied atomically with backup. This makes the operation auditable and recoverable.

**Unidirectional links with reverse lookup**: Links are stored only on the source entry. The `connections` tool scans all entries for incoming links. This avoids bidirectional consistency issues and simplifies `forget` cleanup. At <200 entries, full scan takes microseconds.

**Within-category dedup**: `remember` checks for duplicates in the target category only (by default). Cross-category duplicates are legitimate -- a `tools` entry about "uses pixi" differs from a `project` entry. The `broad=True` flag enables cross-category scan when needed.

**Atomic writes with file locking**: All mutations use `_read_modify_write()`: acquire `fcntl.flock()`, load JSON, apply mutator function, write to temp file, `os.replace()` to target, release lock. Prevents corruption from concurrent agent writes.

**Dedup returns candidates, never auto-merges**: When `remember` finds overlapping entries, it returns candidates with match reasons and a recommendation (ADD/UPDATE/NOOP). The caller decides. Use `force=True` to bypass.

**Reflect is read-only analysis**: The `reflect` tool calls `lifecycle.analyze()` which returns findings without modifying data. The caller acts on findings by calling `forget`, `remember`, or other tools.

## Testing

```bash
uv run pytest -v              # all tests
uv run pytest tests/test_store.py  # specific module
```

232 tests across 10 files:

| File | Covers |
|------|--------|
| `test_store.py` (51) | CRUD cycle, access tracking, atomic writes, session start, export, about_me/about_us, soft delete, hard delete |
| `test_links.py` (31) | Link CRUD, connections (outgoing + incoming), auto-linking on remember, link cleanup on hard_delete, duplicate prevention |
| `test_schema.py` (27) | Dataclass round-trips, summary generation, constants validation |
| `test_search.py` (27) | Multi-signal ranking, weight verification, match reasons, category filtering, multi-term search, Markdown formatting |
| `test_lifecycle.py` (27) | Staleness flags, archival candidates, confidence adjustments, read-only verification |
| `test_dedup.py` (20) | Tag overlap detection, value similarity, force bypass, broad scan, recommendation logic |
| `test_temporal.py` (15) | valid_at/invalid_at timestamps, soft-delete temporal queries, include_historical filtering |
| `test_consolidation.py` (14) | Merge, archive, adjust_confidence, update_summary actions, validation, dry_run, atomic backup |
| `test_progressive_disclosure.py` (11) | Markdown-KV index format, browse_index, search detail modes |
| `test_browse_index.py` (9) | Browse index filtering, soft-deleted entry exclusion, include_historical annotation |

All tests use `tmp_path` fixtures for isolated file I/O.

## How to Extend

**Adding a new tool**:

1. Add the tool method to `MemoryStore` in `store.py`
2. Add the `@mcp.tool()` wrapper in `server.py` that delegates to the store
3. Add tests in `tests/`

**Adding a new schema field**:

1. Add the field to `MemoryEntry` in `schema.py` with a default value
2. Add the field to `MemoryEntry.to_dict()` and `MemoryEntry.from_dict()`
3. Update `schema_resource()` in `server.py` to document the new field
4. Update `skills/memory/references/schema.md`
5. Bump `SCHEMA_VERSION` if needed
