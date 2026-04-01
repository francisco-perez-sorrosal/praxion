# Memory MCP Server

Persistent memory management via MCP (Model Context Protocol) server with JSON storage. Provides tools for storing and recalling user preferences, project conventions, and assistant learnings across sessions.

## Development

- Python 3.13+, managed with **uv** (see `pyproject.toml`)
- Source: `src/memory_mcp/`
- Tests: `tests/` — run with `uv run pytest`
- Lint/format: `uv run ruff check --fix` and `uv run ruff format`
- Storage: JSON file at path specified by `MEMORY_FILE` env var (default: `.ai-state/memory.json`)

## Relevant Skills

- `python-development` for Python conventions and testing patterns
- `mcp-crafting` for MCP protocol concepts, tool definitions, and transport configuration

## Plugin Integration

Registered in `.claude-plugin/plugin.json` under `mcpServers.memory`. Runs via `uv run --project` with `MEMORY_FILE` pointing to `.ai-state/memory.json`.
