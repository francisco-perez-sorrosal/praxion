# Memory MCP Server

Persistent memory management via MCP (Model Context Protocol) server with dual-layer storage. Curated memories in JSON (`memory.json`) and automatic observations in JSONL (`observations.jsonl`). Provides tools for storing, recalling, searching, and analyzing user preferences, project conventions, and assistant learnings across sessions.

## Development

- Python 3.13+, managed with **uv** (see `pyproject.toml`)
- Source: `src/memory_mcp/` (9 modules: schema, store, search, dedup, consolidation, lifecycle, observations, narrative, server)
- Tests: `tests/` — 329 tests across 13 files, run with `uv run pytest`
- Lint/format: `uv run ruff check --fix` and `uv run ruff format`
- Storage: JSON file at path specified by `MEMORY_FILE` env var (default: `.ai-state/memory.json`); JSONL at `OBSERVATIONS_FILE` (default: `.ai-state/observations.jsonl`)
- Schema: v2.0 (auto-migration from v1.x implemented in `store.py::_auto_migrate_if_needed`; runs on every constructor open)

## Module Layout

- `schema.py` — v2.0 dataclasses (`MemoryEntry`, `Source`, `Link`, `Observation`), `generate_summary()`, `VALID_TYPES`, constants
- `store.py` — `MemoryStore` class: CRUD, file I/O, locking, browse_index, consolidation
- `search.py` — scoring functions, multi-term matching, Markdown-KV formatting
- `dedup.py` — dedup candidates, value similarity, word extraction, stop words
- `consolidation.py` — action validation (`validate_actions`), atomic execution (`apply_actions`)
- `lifecycle.py` — read-only analysis (stale entries, archival candidates, confidence)
- `observations.py` — `ObservationStore`: JSONL I/O, rotation, querying with process-safe locking
- `narrative.py` — `build_timeline()`, `build_session_narrative()`: Markdown formatters for observation data
- `server.py` — FastMCP tool/resource registration (18 tools, 2 resources)

## Relevant Skills

- `python-development` for Python conventions and testing patterns
- `mcp-crafting` for MCP protocol concepts, tool definitions, and transport configuration

## Plugin Integration

Registered in `.claude-plugin/plugin.json` under `mcpServers.memory`. Runs via `uv run --project` with `MEMORY_FILE` pointing to `.ai-state/memory.json`.

Six hooks integrate with Claude Code's event system:
- `inject_memory.py` (SubagentStart) — injects memory context (Markdown-KV with importance tiers, agent-type routing) and ADR decision context (from `DECISIONS_INDEX.md`, filtered to accepted/proposed, with soft cap budget). ADR-first budget allocation within MAX_INJECT_CHARS (ADRs consume up to a 2,000-char soft cap first; memory fills the remainder — see dec-023)
- `validate_memory.py` (SubagentStop) — warns parent when agents write LEARNINGS.md without calling remember()
- `capture_memory.py` (PostToolUse) — captures tool events as JSONL observations
- `capture_session.py` (SessionStart, Stop, SubagentStart, SubagentStop) — captures lifecycle events as JSONL observations
- `promote_learnings.py` (PreToolUse) — warns before LEARNINGS.md cleanup when unpromoted entries exist
- `memory-protocol.md` (always-loaded rule) — guides when/how to call remember() with type guidance
