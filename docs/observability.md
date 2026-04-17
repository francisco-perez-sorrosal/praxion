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
- **Trace waterfall** -- click a trace to see the agent hierarchy: session root, agent spans, tool calls, all with **real wall-clock durations** (paired `PreToolUse`/`PostToolUse` hooks produce one span per tool call with accurate start/end times)
- **Span detail** -- click any span for attributes (agent type, tool name, input/output, I/O byte sizes before truncation, MCP server attribution), events (phase transitions, decisions), and error status
- **Filtering** -- filter by span name, attribute values, error status, or time range
- **Session grouping** -- traces from the same `session_id` are correlated
- **Sessions view (Phoenix v14.6+)** -- paginated list with list-detail turn layout. Requires `arize-phoenix>=14.6` (see `eval/requirements.txt`).

### Useful dashboard queries

Phoenix's filter bar accepts attribute predicates. A few high-leverage queries:

| Question | Query |
|---|---|
| Which subagents ran as a parallel cohort? | `praxion.fork_group = "<uuid>"` |
| What did agent X actually do? | Open its `agent-summary` span -- `praxion.agent.tools_used`, `praxion.agent.skills_used`, `praxion.agent.delegated_to` are deduped lists |
| Which tools took longest? | Sort `TOOL` spans by duration (now that `PreToolUse`/`PostToolUse` produce real start/end times) |
| Which agents spent the most tokens? | Group `agent-summary` spans by `llm.token_count.total` (requires subagent transcript at `SubagentStop`; see Privacy and cost knobs below) |
| What ran on branch X? | Filter spans by `praxion.git.branch = "<branch>"` -- also `praxion.git.worktree_name` and `praxion.git.sha` |
| What was tool input/output size? | `praxion.io.input_size_bytes`, `praxion.io.output_size_bytes` -- raw sizes captured before the 4096-byte summary truncation |

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
| `OTEL_ENABLED` | `false` | Set to `true` to enable trace export |
| `CHRONOGRAPH_STRIP_LLM_ATTRS` | *(unset)* | Set to `1` to suppress `llm.*` span attributes (token counts, model, system, provider). Structural telemetry unaffected. |
| `PRAXION_DISABLE_OBSERVABILITY` | *(unset)* | Set to `1` to stop hooks from posting events entirely. Telemetry goes dark until unset. |

### Privacy and cost knobs

Span attributes themselves cost nothing -- they're bytes on the wire. Three real cost/privacy surfaces:

1. **`CHRONOGRAPH_STRIP_LLM_ATTRS=1`** -- suppresses LLM-level attributes at parse time. Keep this if you want structural telemetry (agent tree, tools, durations, fork groups) but don't want per-agent token/model metadata visible.
2. **Phoenix's PXI assistant** (Phoenix v14.3+) -- built-in chatbot over traces. Uses API keys you configure in Phoenix. Toggle off in Phoenix settings to prevent Phoenix from making LLM calls on your behalf.
3. **Evaluators you explicitly run** -- e.g., `praxion-evals judge --provider openai` or `trajectory_eval.py`. These make real API calls against configured provider keys. Opt-in, never triggered automatically.

None of the span attributes our relay emits trigger external API calls. Phoenix's cost computation (if it appears in the UI) is a local lookup in Phoenix's internal price table, keyed on `llm.model_name` + `llm.token_count.*` -- no network call.

## Ports

| Port | Service |
|------|---------|
| 6006 | Phoenix UI + OTLP HTTP receiver (single instance, all projects) |
| 4317 | Phoenix OTLP gRPC receiver |
| 8765-9764 | Chronograph HTTP API (one per project, derived from project path) |

Each project's chronograph binds to a deterministic port derived from the project directory path (SHA-256 hash mod 1000 + 8765). This allows multiple projects to run simultaneously without port collisions. Both the hook script and the chronograph server use the same derivation, so they always agree.

Override with `CHRONOGRAPH_PORT` env var if needed.

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
3. Check `OTEL_ENABLED` is set to `true` (plugin.json sets this automatically)
4. Verify hooks are registered: `./install.sh code --check`
5. Check that `PRAXION_DISABLE_OBSERVABILITY` is not set to `1` in `.claude/settings.json`

**Tool spans show zero duration:**

The `PreToolUse` observability hook is not firing. Check that `hooks/hooks.json` has an empty-matcher entry for `send_event.py` under `PreToolUse`, and that Claude Code picked up the registration (restart the session after editing `hooks.json`). Without `PreToolUse`, the chronograph falls back to emitting instant spans with no duration.

**No token counts on agent-summary spans:**

Three possible causes:

1. `CHRONOGRAPH_STRIP_LLM_ATTRS=1` is set -- that deliberately suppresses `llm.*` attributes.
2. The subagent transcript file does not exist yet at `SubagentStop` time. Claude Code writes the transcript asynchronously; if you inspect a trace immediately, wait a few seconds and reload.
3. The `agent_transcript_path` metadata is missing from the `SubagentStop` event -- check `send_event.py` is the current version (Phase 3 added this plumbing via `event.metadata.get("agent_transcript_path", "")` in `server.py`).

**No fork_group on sibling subagents:**

Siblings spawned more than 200ms apart get different `fork_group` UUIDs (by design -- the time-clustering heuristic errs on the side of separate cohorts). If you expected siblings to share a fork_group but they don't, check whether the main agent's dispatch was actually synchronous. The clustering window is `FORK_CLUSTER_WINDOW_S` in `otel_relay.py`.

## Backend Portability

The instrumentation layer uses standard OpenTelemetry. To switch from Phoenix to another OTLP-compatible backend (Jaeger, SigNoz, OpenObserve):

1. Set `PHOENIX_ENDPOINT` to the new backend's OTLP HTTP endpoint
2. No changes to hooks, chronograph, or MCP tools needed
