# Observability

Praxion traces every agent session -- pipeline runs, native Claude Code agents, tool calls, decisions, and phase transitions -- via OpenTelemetry. Traces are stored in a local Phoenix daemon and visualized through its web UI.

## Architecture

```
Claude Code Hooks                Phoenix Daemon (persistent)
  SessionStart   ──┐             http://localhost:6006
  SubagentStart    │  HTTP POST  ┌──────────────────────┐
  SubagentStop     ├────────────>│ Chronograph MCP      │
  PostToolUse      │             │   EventStore (RAM)   │──OTLP──> Phoenix
  PostToolUseFailure│            │   OTel Relay         │          ~/.phoenix/
  Stop           ──┘             └──────────────────────┘          phoenix.db
```

Hooks fire on every Claude Code event (stdlib-only, <100ms). The Chronograph MCP server receives them, stores events in memory for real-time agent queries, and exports OTel spans to Phoenix for persistence and visualization.

## Quick Start

```bash
# Install Phoenix daemon (part of ./install.sh code, or standalone)
phoenix-ctl install

# Verify it's running
phoenix-ctl status

# Open the trace UI
open http://localhost:6006
```

Phoenix installs in `~/.phoenix/` with a dedicated Python venv (~300MB). It starts automatically on login via `launchd` and retains traces for 90 days.

## Accessing the Phoenix UI

Navigate to **http://localhost:6006** in your browser.

### One Instance, All Projects

Phoenix runs as a **single daemon** shared across all projects on your machine. Each project gets its own isolated trace namespace -- use the **project dropdown** in the top-left corner to switch between them.

Projects appear automatically when their first session runs. No manual configuration needed. The project name is derived from the project directory basename (e.g., `/home/user/my-api` becomes project `my-api`).

### What You See

- **Trace list** -- each session appears as a trace, sorted by recency
- **Trace waterfall** -- click a trace to see the agent hierarchy: session root, agent spans, tool calls, all with timing bars
- **Span detail** -- click any span for attributes (agent type, tool name, input/output), events (phase transitions, decisions), and error status
- **Filtering** -- filter by span name, attribute values, error status, or time range
- **Session grouping** -- traces from the same `session_id` are correlated

### Trace Types

Traces are tagged with `praxion.trace_type`:

- **`pipeline`** -- a full Praxion SDLC pipeline ran (researcher, architect, planner, implementer, etc.)
- **`native`** -- only native Claude Code agents were used (general-purpose, Explore, Plan, etc.)

Both types are traced with the same fidelity. Filter by `praxion.trace_type` to focus on pipeline vs ad-hoc work.

### Agent Origin

Each agent span carries `praxion.agent_origin`:

- **`praxion`** -- a Praxion pipeline agent (i-am:researcher, i-am:implementer, etc.)
- **`claude-code`** -- a native Claude Code agent (general-purpose, Explore, Plan, etc.)

## Self-Monitoring

When working on the Praxion repository itself, the observability system traces its own pipeline runs. Traces appear under project `praxion` in Phoenix. No special configuration needed -- the same hooks, chronograph, and Phoenix backend that instrument other projects also instrument Praxion.

## Managing Services

### Phoenix Daemon (persistent trace backend)

```bash
phoenix-ctl install    # Install venv + launchd plist, start daemon
phoenix-ctl start      # Start the daemon
phoenix-ctl stop       # Stop the daemon
phoenix-ctl restart    # Stop + start
phoenix-ctl status     # Show PID, memory, ports, UI reachability
phoenix-ctl uninstall  # Stop, remove plist (data preserved at ~/.phoenix/)
```

### Chronograph (event relay)

During normal operation, Claude Code manages the chronograph as an MCP server. For development (picking up code changes without restarting Claude Code):

```bash
chronograph-ctl start    # Start HTTP server from source (background)
chronograph-ctl stop     # Stop the server
chronograph-ctl restart  # Stop + start (picks up code changes)
chronograph-ctl status   # Show PID, memory, event count
chronograph-ctl logs     # Tail the log file
```

## Configuration

| Variable | Default | Purpose |
|----------|---------|---------|
| `PHOENIX_PORT` | `6006` | Phoenix UI and OTLP HTTP port |
| `PHOENIX_GRPC_PORT` | `4317` | OTLP gRPC port |
| `PHOENIX_DEFAULT_RETENTION_POLICY_DAYS` | `90` | Auto-prune traces older than this |
| `PHOENIX_ENDPOINT` | `http://localhost:6006/v1/traces` | Chronograph's OTLP export target |
| `OTEL_ENABLED` | `true` | Set to `false` to disable trace export |

## Ports

| Port | Service |
|------|---------|
| 6006 | Phoenix UI + OTLP HTTP receiver |
| 4317 | Phoenix OTLP gRPC receiver |
| 8765 | Chronograph HTTP API (hook target) |

## Troubleshooting

**Phoenix not running:**

```bash
phoenix-ctl status     # Check if PID is shown
phoenix-ctl start      # Start manually
```

**Port conflict:**

If port 6006 is already in use, set `PHOENIX_PORT` before installing:

```bash
PHOENIX_PORT=6007 phoenix-ctl install
```

**Logs:**

```bash
tail -f ~/.phoenix/phoenix.log   # stdout
tail -f ~/.phoenix/phoenix.err   # stderr
```

**No traces appearing:**

1. Verify Phoenix is running: `phoenix-ctl status`
2. Verify chronograph is running: check MCP server in Claude Code
3. Check `OTEL_ENABLED` is not set to `false`
4. Verify hooks are registered: `./install.sh code --check`

## Backend Portability

The instrumentation layer uses standard OpenTelemetry. To switch from Phoenix to another OTLP-compatible backend (Jaeger, SigNoz, OpenObserve):

1. Set `PHOENIX_ENDPOINT` to the new backend's OTLP HTTP endpoint
2. No changes to hooks, chronograph, or MCP tools needed
