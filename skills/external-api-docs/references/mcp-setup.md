# MCP Server Setup

context-hub's MCP server is the **preferred integration path**. It gives agents native access to `chub_search`, `chub_get`, and other tools without shelling out to the CLI. The Praxion installer configures this automatically.

**After running `./install.sh`:** The MCP server is already configured. No manual setup needed.

**Manual setup** is only needed if you skipped the installer step or want to add it to a different environment.

## Claude Code

Add to project settings (`.claude/settings.local.json`) or global settings (`~/.claude/settings.json`):

```json
{
  "mcpServers": {
    "chub": {
      "command": "npx",
      "args": ["-y", "@aisuite/chub", "mcp"],
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
      "args": ["-y", "@aisuite/chub", "mcp"],
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
      "args": ["-y", "@aisuite/chub", "mcp"],
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

| Tool | Description |
|------|-------------|
| `chub_search` | Search the registry for docs and skills |
| `chub_get` | Fetch a specific doc or skill by ID |
| `chub_list` | List all available entries |
| `chub_annotate` | Add a local annotation to an entry |
| `chub_feedback` | Rate an entry (requires feedback API enabled) |

And one MCP resource:

| Resource | Description |
|----------|-------------|
| `chub://registry` | Full registry metadata |

## Verification

After setup, verify the MCP server is running by asking the agent to list available tools. The `chub_search` and `chub_get` tools should appear.

If the server fails to start, check:

1. Node.js 18+ is installed and on PATH
2. `npx` can resolve `@aisuite/chub` (network access for first download)
3. No port conflicts (the MCP server uses stdio transport, not HTTP)
