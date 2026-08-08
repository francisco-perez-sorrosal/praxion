# Plugin Manifest Schema Notes

Undocumented but strict constraints enforced by the Claude Code plugin validator. Sourced from [everything-claude-code](https://github.com/affaan-m/everything-claude-code/tree/main/.claude-plugin).

## Component Fields Must Be Arrays

`commands`, `skills`, and `agents` must always be arrays, never strings:

```json
"commands": ["./.claude/commands/"]   // correct
"commands": "./.claude/commands/"     // fails on marketplace install
```

## Agents Require Explicit File Paths

Directory paths are rejected for agents. Enumerate each file:

```json
"agents": ["./agents/planner.md", "./agents/reviewer.md"]   // correct
"agents": ["./agents/"]                                       // fails
```

## Plugin Hooks Auto-Fire from `hooks/hooks.json`

Plugin hooks are auto-discovered and executed when placed at `<plugin-root>/hooks/hooks.json`. This is the **plugin root** directory (where `plugin.json` lives inside `.claude-plugin/`), **not** inside `.claude-plugin/` itself.

```
my-plugin/                     ← plugin root
├── .claude-plugin/plugin.json
└── hooks/hooks.json           ← hooks go HERE
```

**Wrong** (never discovered by Claude Code):
```
my-plugin/
└── .claude-plugin/
    └── hooks/hooks.json       ← NOT here
```

Reference: the official `hookify` plugin uses `<plugin-root>/hooks/hooks.json`.

**`${CLAUDE_PLUGIN_ROOT}` resolution:** Resolves to the installed plugin's root directory in the cache (e.g., `~/.claude/plugins/cache/bit-agora/praxion/0.1.1.dev0/`). Scripts at `hooks/send_event.py` are referenced as `${CLAUDE_PLUGIN_ROOT}/hooks/send_event.py`.

## Do Not Declare Hooks in plugin.json

Adding `"hooks"` to the manifest causes a duplicate file error. The hooks config lives separately in `hooks/hooks.json` at the plugin root.

## mcpServers Auto-Registers MCP Servers

The `mcpServers` key in `plugin.json` registers MCP servers automatically when the plugin loads. Format matches Claude Desktop config — **only stdio transport is supported** (`command` + `args`). There is no `url` field for HTTP transport.

```json
"mcpServers": {
  "server-name": {
    "command": "uv",
    "args": ["run", "--project", "${CLAUDE_PLUGIN_ROOT}/subdir", "python", "-m", "my_module"]
  }
}
```

Reference: [claude-mermaid](https://github.com/veelenga/claude-mermaid/tree/main/.claude-plugin) uses this for npm-based MCP servers. For Python projects, `uv run --project` handles dependency installation on first launch.

**Hybrid stdio+HTTP pattern:** Since only stdio is supported, a server that also needs HTTP (e.g., for hook event ingestion) can start an HTTP server in a daemon thread before entering the stdio transport. The `task-chronograph` server uses this approach — its `__main__.py` launches uvicorn in a background thread, then calls `mcp.run()` on stdio. The plugin registers the stdio transport; the HTTP API (for receiving hook events and relaying OTel spans to Phoenix) comes as a side effect. The root route redirects to Phoenix UI at `localhost:6006`. See `task-chronograph-mcp/README.md` for details.

**Note:** `${CLAUDE_PLUGIN_ROOT}` resolution in `mcpServers` args is assumed based on its behavior in hook commands — verify after plugin reinstall.

## Version Field Is Mandatory

Omitting `version` causes installation failures during marketplace deployment.

## Validator Quirks

- Local validation may pass while marketplace installation fails
- Error messages are generic (e.g., `agents: Invalid input`) without indicating the root cause
- Prefer explicit file paths over directory paths when in doubt

## Pre-Edit Checklist

1. All component fields are arrays
2. Agents use explicit file paths (not directories)
3. `version` field is present
4. No `hooks` field in the manifest
5. Run `claude plugin validate .` from the repo root
