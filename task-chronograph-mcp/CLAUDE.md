# Task Chronograph MCP Server

Agent pipeline observability via MCP server with OpenTelemetry export to Phoenix. Tracks agent lifecycle events (session, subagent, tool use) and exports traces for visualization.

## Development

- Python 3.13+, managed with **uv** (see `pyproject.toml`)
- Source: `src/task_chronograph_mcp/`
- Tests: `tests/` — run with `uv run pytest`
- Lint/format: `uv run ruff check --fix` and `uv run ruff format`
- Type check: `uv run pyright src/` (see ADR `dec-041`)
- OTel dependencies: `opentelemetry-api`, `opentelemetry-sdk`, `opentelemetry-exporter-otlp-proto-http`, `openinference-semantic-conventions`, `arize-phoenix-otel`
- Development runner: `scripts/chronograph-ctl` (runs from source, not plugin cache)

## Relevant Skills

- `python-development` for Python conventions and testing patterns
- `mcp-crafting` for MCP protocol concepts and transport configuration

## Plugin Integration

Registered in `.claude-plugin/plugin.json` under `mcpServers.task-chronograph`. Runs via `uv run --project` with `OTEL_ENABLED=true`. In production, the plugin's MCP instance handles hook ingestion and OTel export. Use `chronograph-ctl` for development/debugging from source.
