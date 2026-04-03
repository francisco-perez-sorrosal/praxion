# Memory MCP Server

Persistent memory management via MCP (Model Context Protocol) server with JSON storage. Provides tools for storing and recalling user preferences, project conventions, and assistant learnings across sessions.

## Development

- Python 3.13+, managed with **uv** (see `pyproject.toml`)
- Source: `src/memory_mcp/` (7 modules: schema, store, search, dedup, consolidation, lifecycle, server)
- Tests: `tests/` — 232 tests across 10 files, run with `uv run pytest`
- Lint/format: `uv run ruff check --fix` and `uv run ruff format`
- Storage: JSON file at path specified by `MEMORY_FILE` env var (default: `.ai-state/memory.json`)
- Schema: v1.3 (fresh start, no migration code from earlier versions)

## Module Layout

- `schema.py` — v1.3 dataclass (`MemoryEntry`), `generate_summary()`, constants
- `store.py` — `MemoryStore` class: CRUD, file I/O, locking, browse_index, consolidation
- `search.py` — scoring functions, multi-term matching, Markdown-KV formatting
- `dedup.py` — dedup candidates, value similarity, word extraction, stop words
- `consolidation.py` — action validation (`validate_actions`), atomic execution (`apply_actions`)
- `lifecycle.py` — read-only analysis (stale entries, archival candidates, confidence)
- `server.py` — FastMCP tool/resource registration (16 tools, 2 resources)

## Relevant Skills

- `python-development` for Python conventions and testing patterns
- `mcp-crafting` for MCP protocol concepts, tool definitions, and transport configuration

## Plugin Integration

Registered in `.claude-plugin/plugin.json` under `mcpServers.memory`. Runs via `uv run --project` with `MEMORY_FILE` pointing to `.ai-state/memory.json`.

Three enforcement hooks ensure agents use memory:
- `inject_memory.py` (SubagentStart) — injects Markdown-KV summary into every agent's context
- `validate_memory.py` (SubagentStop) — warns parent when agents write LEARNINGS.md without calling remember()
- `memory-protocol.md` (always-loaded rule) — guides when/how to call remember()
