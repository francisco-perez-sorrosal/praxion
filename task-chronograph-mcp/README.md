# Task Chronograph

Agent pipeline observability for Praxion. Traces every session -- pipeline runs, native Claude Code agents, tool calls, decisions, and phase transitions -- via OpenTelemetry, with persistent storage in [Arize Phoenix](https://github.com/Arize-ai/phoenix).

Used by **Claude Code** (plugin) and **Cursor** (via `./install.sh cursor`).

## Architecture

A single MCP server process runs two transports in parallel:

```
Claude Code Hooks (stdlib, <100ms)
  SessionStart, SubagentStart, SubagentStop,
  PostToolUse, PostToolUseFailure, Stop
      │
      │  HTTP POST to localhost:8765/api/events
      ▼
┌─────────────────────────────┐        ┌─────────────────────┐
│ Chronograph MCP Server      │        │ Phoenix Daemon      │
│ (daemon thread: uvicorn)    │        │ (persistent, launchd)│
│                             │        │                     │
│ HTTP API: /api/events       │─OTLP──>│ localhost:6006      │
│ EventStore (in-memory)      │        │ ~/.phoenix/phoenix.db│
│ OTel Relay (otel_relay.py)  │        │ 90-day retention    │
│                             │        └─────────────────────┘
│ (main thread: mcp stdio)   │
│ MCP Tools:                  │
│   get_pipeline_status       │
│   get_agent_events          │
│   report_interaction        │
└─────────────────────────────┘
```

**Dual storage**: EventStore (in-memory) serves real-time MCP queries. Phoenix (SQLite) persists traces for historical analysis and visualization. Either can fail independently.

## Quick Start

The `i-am` plugin auto-registers the MCP server. Phoenix is installed separately:

```bash
phoenix-ctl install          # Install Phoenix daemon (~300MB)
open http://localhost:6006   # Trace UI
```

To run the chronograph standalone (without the plugin):

```bash
cd task-chronograph-mcp
uv run python -m task_chronograph_mcp
```

## Hook Events

9 hook events are registered, forwarding to `send_event.py`:

| Hook Event | Event Type | OTel Span |
|---|---|---|
| `SessionStart` | session_start | Root SESSION span (CHAIN) |
| `Stop` | session_stop | End SESSION span |
| `SubagentStart` | agent_start | AGENT child span |
| `SubagentStop` | agent_stop | End AGENT span |
| `PreToolUse` (all tools) | tool_start | Opens a TOOL span (held open, not emitted yet) |
| `PostToolUse` | tool_use | Closes the paired TOOL span with real duration |
| `PostToolUseFailure` | error | Closes the paired TOOL span with ERROR status |
| `PreToolUse` (Bash) | -- | Code quality gate (sync) |
| `PreCompact` | -- | Pipeline state snapshot (sync) |

PostToolUse additionally detects PROGRESS.md writes and emits phase_transition events.

Pair correlation uses Claude Code's `tool_use_id`. When `PreToolUse` fires without a `tool_use_id` (or never fires), `PostToolUse` falls back to emitting an instant span -- Phoenix still sees the event, just without a duration.

The hook script uses only Python stdlib and exits 0 unconditionally -- it never blocks agent execution.

## MCP Tools

- **`get_pipeline_status`** -- current state of all agents, interaction timeline, and delegation hierarchy
- **`get_agent_events`** -- filtered event history for a specific agent (with optional label filter)
- **`report_interaction`** -- record an interaction between pipeline participants

## OTel Span Model

Traces use [OpenInference](https://github.com/Arize-ai/openinference) semantic conventions:

```
SESSION (CHAIN) ← root, trace_id from session_id hash
├── researcher (AGENT, origin: praxion, fork_group: U1, sibling_index: 0)
│   ├── Read (TOOL, real duration)
│   ├── Bash (TOOL, real duration)
│   └── [event: phase_transition] Phase 2/5
├── implementer (AGENT, origin: praxion, fork_group: U1, sibling_index: 1)
│   └── Edit (TOOL, real duration)
└── verifier (AGENT, origin: praxion, fork_group: U2, sibling_index: 0)
```

### Span attribute reference

Every TOOL span carries:

| Attribute | Source | Purpose |
|---|---|---|
| `tool.name` | hook payload | Phoenix-displayed span name |
| `tool.id` | `tool_use_id` from Claude Code | Correlates with upstream Anthropic tool-use objects |
| `input.value`, `output.value` | hook payload (truncated, redacted) | Phoenix renders with JSON/text formatting |
| `praxion.io.input_size_bytes`, `praxion.io.output_size_bytes` | raw size *before* truncation | Real size signal survives summary truncation |
| `praxion.hook_event` | `PreToolUse` / `PostToolUse` / `PostToolUseFailure` | Which hook produced this span |
| `praxion.mcp_server`, `praxion.mcp_tool` | MCP tool name classification | Filter MCP server invocations |

Every AGENT span carries:

| Attribute | Source | Purpose |
|---|---|---|
| `agent.name`, `graph.node.id`, `graph.node.parent_id` | event | OpenInference hierarchy |
| `praxion.agent_type`, `praxion.agent_origin`, `praxion.trace_type` | agent_type classification | Filter praxion vs native, pipeline vs ad-hoc |
| `praxion.fork_group` | time-clustered UUID | Query parallel subagent cohorts |
| `praxion.sibling_index` | position in cluster | Ordering within a fan-out |
| `praxion.git.branch`, `praxion.git.worktree_name`, `praxion.git.sha` | git subprocess | Bisect telemetry by git state |
| `praxion.pipeline_tier` | `.ai-state/calibration_log.md` last row | Compare telemetry across tiers |
| `user.id` | `git config user.email` | Phoenix filters by user |

Every agent-summary span (emitted at `SubagentStop`) additionally carries:

| Attribute | Purpose |
|---|---|
| `praxion.agent.duration_ms` | End-to-end wall-clock duration |
| `praxion.agent.tools_used` (list) | Which tools this agent exercised (deduped) |
| `praxion.agent.skills_used` (list) | Which skills this agent activated |
| `praxion.agent.delegated_to` (list) | Agent types this agent spawned |
| `llm.token_count.{prompt,completion,total}` | Parsed from the subagent's JSONL transcript (if available) |
| `llm.model_name`, `llm.system`, `llm.provider` | Inferred from the transcript's assistant messages |

Phoenix computes LLM cost locally from tokens + model name -- no external call. See [Privacy and cost knobs](#privacy-and-cost-knobs) to suppress LLM attribute emission.

## Configuration

| Variable | Default | Description |
|---|---|---|
| `CHRONOGRAPH_PORT` | `8765` | Chronograph HTTP API port |
| `CHRONOGRAPH_WATCH_DIR` | *(unset)* | Directory for PROGRESS.md file watching |
| `CHRONOGRAPH_STRIP_LLM_ATTRS` | *(unset)* | Set to `1` to suppress `llm.*` span attributes (token counts, model, system). Structural telemetry stays intact. |
| `PHOENIX_ENDPOINT` | `http://localhost:6006/v1/traces` | OTLP export target |
| `PHOENIX_PROJECT_NAME` | `praxion-default` | Fallback project name |
| `OTEL_ENABLED` | `false` | Set to `true` to enable OTel export |

### Privacy and cost knobs

Span attributes themselves never trigger external API calls -- emitting them is free. Three real cost/privacy surfaces to be aware of:

1. **`CHRONOGRAPH_STRIP_LLM_ATTRS=1`** -- suppresses LLM-level attributes (`llm.token_count.*`, `llm.model_name`, `llm.system`, `llm.provider`) at parse time. Use when you want structural telemetry (agent hierarchy, tool calls, durations, fork groups) without per-agent model metadata.

2. **Phoenix's PXI assistant** -- the built-in "chat with your traces" feature (Phoenix v14.3+) calls an LLM against an API key you configure in Phoenix. Toggle it off in Phoenix settings if you don't want Phoenix making LLM calls on your behalf.

3. **Evaluators you explicitly run** -- e.g., `praxion-evals` / `trajectory_eval.py` run real LLM calls against configured provider keys. Those are opt-in, never triggered automatically.

## Development

```bash
cd task-chronograph-mcp
uv run python -m pytest -q    # 152 tests
uv run ruff check              # Lint
uv run ruff format             # Format
```

### Gotchas

- **Phoenix storage**: Default `PHOENIX_SQL_DATABASE_URL` writes to a temp folder — data lost on restart. Always set `PHOENIX_WORKING_DIR` and `PHOENIX_SQL_DATABASE_URL` to a stable path (`~/.phoenix/`).
- **launchd plists**: `$HOME` must be expanded to a literal path at generation time — launchd does not expand shell variables.
- **`InMemorySpanExporter`**: Lives at `opentelemetry.sdk.trace.export.in_memory_span_exporter`, not `opentelemetry.sdk.trace.export`.
- **Hook matchers**: Empty string `""` matches all tools. The `format_python.py` hook uses `"Write|Edit"` in its own entry and is unaffected by the observability hook's empty matcher.
- **Frozen Event dataclass**: New fields must have defaults to avoid breaking existing callers.
- **Test lifespan**: `test_server.py` uses `_core_lifespan` (not `app_lifespan`) because MCP session manager doesn't work with pytest-asyncio.
- **`arize-phoenix-evals`**: Uses Elastic-2.0 license (not MIT/Apache). Fine for self-hosted tooling but blocks offering evaluations as a service.
- **OpenInference span.kind**: The only required attribute. Phoenix renders recognized attributes (`input.value`, `output.value`, `tool.name`, `session.id`) with special UI treatment.
- **Phoenix UI limitations**: No alerting, no custom dashboards, no configurable views. Trace-first with a fixed layout.
