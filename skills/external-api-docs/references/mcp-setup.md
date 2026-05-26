# MCP Server Setup

context-hub's MCP server is the preferred integration path for the [external-api-docs](../SKILL.md) skill. It gives agents native access to `chub_search`, `chub_get`, and other tools without shelling out to the CLI. The Praxion installer configures this automatically.

**After running `./install.sh`:** The MCP server is already configured. No manual setup needed.

**Manual setup** is only needed if you skipped the installer step or want to add it to a different environment.

## Binary Layout

The `@aisuite/chub` npm package ships **two bin entries**:

| Binary | Purpose |
|--------|---------|
| `chub` | The CLI |
| `chub-mcp` | The MCP stdio server |

There is **no `chub mcp` subcommand** — invoke the MCP server via the dedicated `chub-mcp` bin (use `npx -p @aisuite/chub chub-mcp` to run it via npx).

## Claude Code

Add to project settings (`.claude/settings.local.json`) or global settings (`~/.claude/settings.json`):

```json
{
  "mcpServers": {
    "chub": {
      "command": "npx",
      "args": ["-y", "-p", "@aisuite/chub", "chub-mcp"],
      "env": {
        "CHUB_TELEMETRY": "0",
        "CHUB_FEEDBACK": "1"
      }
    }
  }
}
```

## Claude Desktop

Add to `claude_desktop_config.json`:

- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Linux: `~/.config/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "chub": {
      "command": "npx",
      "args": ["-y", "-p", "@aisuite/chub", "chub-mcp"],
      "env": {
        "CHUB_TELEMETRY": "0",
        "CHUB_FEEDBACK": "1"
      }
    }
  }
}
```

## Cursor

Add to `.cursor/mcp.json` (project) or `~/.cursor/mcp.json` (global):

```json
{
  "mcpServers": {
    "chub": {
      "command": "npx",
      "args": ["-y", "-p", "@aisuite/chub", "chub-mcp"],
      "env": {
        "CHUB_TELEMETRY": "0",
        "CHUB_FEEDBACK": "1"
      }
    }
  }
}
```

## Available MCP Tools

Once configured, the MCP server exposes:

| Tool | Description | Args |
|------|-------------|------|
| `chub_search` | Search the registry for docs and skills | `query?`, `tags?`, `lang?`, `limit?` |
| `chub_get` | Fetch a specific doc or skill by ID | `id`, `lang?`, `version?`, `full?`, `file?` |
| `chub_list` | List all available entries | `tags?`, `lang?`, `limit?` |
| `chub_annotate` | Read, write, clear, or list annotations (modal — see below) | `id?`, `note?`, `clear?`, `list?` |
| `chub_feedback` | Rate an entry (requires feedback API enabled) | `id`, `rating`, `comment?`, `type?`, `lang?`, `version?`, `file?`, `labels?` (array enum) |

`chub_annotate` modes — pick one:

| Mode | Args |
|------|------|
| Read existing | `id` only |
| Write/overwrite | `id` + `note` |
| Clear annotation | `id` + `clear: true` |
| List all annotations | `list: true` (no `id` needed) |

And one MCP resource:

| Resource | Description |
|----------|-------------|
| `chub://registry` | Full registry metadata as JSON (entries with id, name, type, tags, languages) |

## Verification

After setup, verify the MCP server is running by asking the agent to list available tools. The `chub_search` and `chub_get` tools should appear.

To verify the CLI separately and confirm telemetry/feedback wiring, run:

```bash
chub feedback --status
```

It prints whether feedback is enabled, whether telemetry is enabled, the client ID, the endpoint, and the valid feedback labels. This is the canonical way to inspect runtime state in 0.1.4+.

If the server fails to start, check:

1. Node.js 18+ is installed and on PATH
2. `npx` can resolve `@aisuite/chub` (network access for first download)
3. No port conflicts (the MCP server uses stdio transport, not HTTP)
