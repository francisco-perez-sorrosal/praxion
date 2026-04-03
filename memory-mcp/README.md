# Memory MCP Server

Persistent, intelligent memory for AI coding assistants. **Tool-agnostic:** used by **Claude Code** (plugin) and **Cursor** (via `./install.sh cursor`). Stores memories in a JSON file with deduplication-on-write, access tracking, ranked search, lifecycle analysis, temporal supersession, structured consolidation, and cross-reference links.

## Quick Start

The `i-am` plugin auto-registers the MCP server on install. The server starts automatically via stdio transport when Claude Code calls any memory tool -- no manual setup required.

Memory context is automatically injected into every agent's context via the `inject_memory.py` SubagentStart hook. Agents do NOT need to call `session_start()` or `recall()` to see memory data.

To run standalone (without the plugin):

```bash
cd memory-mcp
uv run python -m memory_mcp
```

## MCP Tools

16 tools registered on the `Memory` FastMCP server:

| Tool | Parameters | Description |
|------|-----------|-------------|
| `session_start` | *(none)* | Increment session counter, return memory summary with category counts |
| `remember` | `category`, `key`, `value`, `tags?`, `importance?`, `source_type?`, `confidence?`, `force?`, `broad?`, `summary?` | Store or update a memory entry with dedup-on-write. Auto-generates summary if not provided. |
| `forget` | `category`, `key` | **Soft-delete**: sets `invalid_at` timestamp and status to `superseded`. Entry remains queryable via `include_historical`. |
| `hard_delete` | `category`, `key` | **Permanent removal**: deletes entry and cleans incoming links. Creates backup. |
| `recall` | `category`, `key?` | Retrieve entries with access tracking |
| `search` | `query`, `category?`, `detail?`, `include_historical?` | Multi-signal ranked search. `detail="index"` returns Markdown summaries (default). `detail="full"` returns complete entries. |
| `browse_index` | `include_historical?` | Full memory index as Markdown-KV grouped by category. Most token-efficient view. |
| `consolidate` | `actions` (JSON), `dry_run?` | Execute structured actions (merge, archive, adjust_confidence, update_summary) atomically with backup. |
| `status` | *(none)* | Category counts, total entries, schema version, session count, file size |
| `export_memories` | `output_format?` | Export all memories as markdown (default) or JSON |
| `about_me` | *(none)* | Aggregated user profile from user, relationships, and tools categories |
| `about_us` | *(none)* | Aggregated user-assistant relationship profile |
| `reflect` | *(none)* | Lifecycle analysis: stale entries, archival candidates, confidence adjustments (read-only) |
| `connections` | `category`, `key` | Show outgoing and incoming links for an entry |
| `add_link` | `source_category`, `source_key`, `target_category`, `target_key`, `relation` | Create a unidirectional link between entries |
| `remove_link` | `source_category`, `source_key`, `target_category`, `target_key` | Remove a link between entries |

## MCP Resources

| URI | Description |
|-----|-------------|
| `memory://schema` | Schema version, categories, statuses, relations, field documentation |
| `memory://stats` | Category counts, total entries, session count, file size |

## Schema

**Version**: 1.3

**Categories**: `user`, `assistant`, `project`, `relationships`, `tools`, `learnings`

Each memory entry contains:

| Field | Type | Description |
|-------|------|-------------|
| `value` | string | The memory content |
| `summary` | string | One-line description (~100 chars) for index browsing |
| `created_at` | ISO 8601 | Creation timestamp (UTC) |
| `updated_at` | ISO 8601 | Last modification timestamp (UTC) |
| `valid_at` | ISO 8601 | When entry became valid (set on creation) |
| `invalid_at` | ISO 8601 / null | When entry was soft-deleted (null if active) |
| `tags` | string[] | Tags for categorization and search |
| `importance` | int (1-10) | Priority level, default 5 |
| `confidence` | float (0.0-1.0) | Certainty level, null if unset |
| `source` | `{type, detail}` | Origin: `session`, `user-stated`, `inferred`, or `codebase` |
| `access_count` | int | Times recalled or searched |
| `last_accessed` | ISO 8601 / null | Last access timestamp |
| `status` | string | `active`, `archived`, or `superseded` |
| `links` | array | `[{target: "category.key", relation: "..."}]` |

**Valid relations**: `supersedes`, `elaborates`, `contradicts`, `related-to`, `depends-on`

## Key Features

**Progressive disclosure**: `browse_index()` returns a compact Markdown-KV summary of all entries (~400 tokens for 20 entries). `search(detail="index")` returns ranked Markdown summaries. Full entries available on demand via `detail="full"`. The calling LLM provides semantic search by reading the summaries.

**Temporal supersession**: `forget()` soft-deletes (sets `invalid_at` timestamp) instead of removing entries. Historical queries via `include_historical=True`. `hard_delete()` for permanent removal when needed.

**Structured consolidation**: `consolidate()` accepts a JSON array of actions (merge, archive, adjust_confidence, update_summary) and executes them atomically with pre-mutation backup. Supports `dry_run` for preview.

**Three-layer enforcement**: Memory context is injected into every agent via hook (Layer 1: `inject_memory.py`). An always-loaded rule guides when to call `remember()` (Layer 2: `memory-protocol.md`). A validation hook warns when agents write LEARNINGS.md without calling `remember()` (Layer 3: `validate_memory.py`).

**Dedup-on-write**: `remember` scans for overlapping entries before writing. Returns candidates with ADD/UPDATE/NOOP recommendation. Use `force=True` to bypass.

**Multi-term search**: Queries are tokenized into individual terms. An entry matches if any term matches any field (key, value, tags, summary).

**Access tracking**: `recall` and `search` increment `access_count` and update `last_accessed`. Drives lifecycle analysis and search ranking.

**Ranked search**: Results scored by text match (0.4), tag overlap (0.2), importance (0.25), and recency (0.15). Recency uses exponential decay with ~21-day half-life.

**Cross-reference links**: Unidirectional links with five relation types. Auto-created on `remember` when 2+ tags overlap.

**Atomic writes**: All mutations use write-to-temp + `os.replace()` with `fcntl.flock()`.

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `MEMORY_FILE` | `.ai-state/memory.json` | Path to the JSON memory file |

## Module Layout

```
src/memory_mcp/
  schema.py          -- v1.3 schema, entry dataclass, summary generation
  store.py           -- core CRUD, file I/O, locking, browse, consolidation
  search.py          -- scoring, ranking, text matching, Markdown formatting
  dedup.py           -- candidate detection, recommendation, word extraction
  consolidation.py   -- action validation and atomic execution
  lifecycle.py       -- read-only health analysis (stale, archival, confidence)
  server.py          -- FastMCP tool and resource registration
```

## Development

```bash
cd memory-mcp
uv run pytest -v        # 232 tests across 10 test files
uv run ruff check src/  # lint
uv run ruff format src/ # format
```
