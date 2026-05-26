# MCP Server -- Protocol Patterns and Resources

Deep-dive content for the [mcp-crafting](../SKILL.md) skill. Load on demand. Back to [SKILL.md](../SKILL.md).

## Table of Contents

- [Bundles (.mcpb) -- Manifest Deep Dive](#bundles-mcpb----manifest-deep-dive)
- [Security](#security)
- [Team Sharing (.mcp.json)](#team-sharing-mcpjson)
- [Community Resources](#community-resources)

## Bundles (.mcpb) -- Manifest Deep Dive

MCP Bundles (`.mcpb`) are ZIP archives for distributing MCP servers as installable packages. Formerly called DXT (Desktop Extensions). Users install by double-clicking, dragging into Claude Desktop, or via Developer > Extensions > Install Extension.

**Repository**: [modelcontextprotocol/mcpb](https://github.com/modelcontextprotocol/mcpb)

### Manifest Specification (v0.4)

Full spec: [MANIFEST.md](https://github.com/modelcontextprotocol/mcpb/blob/main/MANIFEST.md)

**Required fields:**

| Field | Type | Description |
| ----- | ---- | ----------- |
| `manifest_version` | string | `"0.3"` or `"0.4"` |
| `name` | string | Machine-readable identifier |
| `version` | string | Semver (e.g., `"1.0.0"`) |
| `description` | string | Brief explanation |
| `author` | object | `{ "name": "...", "email": "...", "url": "..." }` (name required) |
| `server` | object | Runtime configuration |

**Optional fields:** `display_name`, `long_description`, `icon`/`icons`, `repository`, `homepage`, `documentation`, `support`, `screenshots`, `tools`, `tools_generated`, `prompts`, `prompts_generated`, `keywords`, `license`, `privacy_policies`, `compatibility`, `user_config`, `localization`, `_meta`.

### Complete Manifest Example

```json
{
  "manifest_version": "0.4",
  "name": "my-analytics-server",
  "version": "1.0.0",
  "display_name": "Analytics Server",
  "description": "Query analytics data from your dashboard",
  "author": {
    "name": "Your Name",
    "email": "you@example.com",
    "url": "https://example.com"
  },
  "server": {
    "type": "uv",
    "entry_point": "src/server.py"
  },
  "user_config": {
    "api_key": {
      "type": "string",
      "title": "API Key",
      "description": "Your analytics API key",
      "required": true,
      "sensitive": true
    },
    "base_url": {
      "type": "string",
      "title": "Base URL",
      "description": "Analytics endpoint URL",
      "required": false,
      "default": "https://api.analytics.example.com"
    }
  },
  "tools": [
    {
      "name": "query_metrics",
      "description": "Query metrics from the analytics dashboard"
    }
  ],
  "compatibility": {
    "platforms": ["darwin", "win32", "linux"],
    "runtimes": {
      "python": ">=3.11"
    }
  },
  "keywords": ["analytics", "metrics", "dashboard"],
  "license": "MIT"
}
```

### Variable Substitution in `mcp_config`

For server types that use `mcp_config` (e.g., `python` traditional type), variable substitution is available:

```json
{
  "server": {
    "type": "python",
    "entry_point": "server/main.py",
    "mcp_config": {
      "command": "python3",
      "args": ["${__dirname}/server/main.py"],
      "env": {
        "PYTHONPATH": "${__dirname}/lib",
        "API_KEY": "${user_config.api_key}"
      }
    }
  }
}
```

Available variables: `${__dirname}` (bundle root), `${user_config.KEY}` (user settings), `${HOME}`, `${locale}`.

### Bundle Directory Structure -- Node.js

Node.js bundles have zero-install friction and are recommended for widest reach:

```text
my-server.mcpb (ZIP)
├── manifest.json
├── server/
│   └── index.js
├── node_modules/
└── package.json
```

For language-specific bundle structures, see the corresponding language context file (e.g., `contexts/python.md`).

### mcpb CLI

Install the CLI: `npm install -g @anthropic-ai/mcpb`

Commands: `mcpb init` (scaffold a new bundle), `mcpb pack` (build the `.mcpb` archive).

### Official Examples

See [mcpb/examples](https://github.com/modelcontextprotocol/mcpb/tree/main/examples) for `hello-world-node`, `hello-world-uv`, `file-manager-python`, and more.

### Bundle Resources

- [Adopting the MCP Bundle Format](http://blog.modelcontextprotocol.io/posts/2025-11-20-adopting-mcpb/) -- MCP Blog announcement
- [Building Desktop Extensions with MCPB](https://support.claude.com/en/articles/12922929-building-desktop-extensions-with-mcpb) -- Claude Help Center
- [Desktop Extensions](https://www.anthropic.com/engineering/desktop-extensions) -- Anthropic Engineering blog
- [@anthropic-ai/mcpb](https://www.npmjs.com/package/@anthropic-ai/mcpb) -- npm CLI package

## Security

### The Lethal Trifecta (Simon Willison)

Three conditions that combine to create extreme risk:

1. **Access to private data** -- the server reads sensitive information
2. **Exposure to malicious instructions** -- prompt injection via untrusted content
3. **Ability to exfiltrate** -- the server can send data externally

When all three are present, a prompt injection attack can steal data through the tool.

### Known Attack Vectors

- **Rug Pull / Silent Redefinition** -- MCP tools can mutate their own definitions post-installation
- **Cross-Server Tool Shadowing** -- a malicious server overrides calls to trusted servers
- **Tool Poisoning** -- malicious instructions embedded in tool descriptions (visible to LLM, not users)

### Mitigations

- Alert users on tool description changes
- Keep humans in the loop for tool invocations
- Use OAuth with scoped, time-limited tokens
- Start read-only -- whitelist operations, restrict filesystem paths
- Parameterize queries -- never build commands from raw LLM output
- Taint tracking: block or require approval when tainted state reaches exfiltration-capable actions

See the [official security guidance](https://modelcontextprotocol.io/specification/draft/basic/security_best_practices).

## Team Sharing (.mcp.json)

Commit `.mcp.json` to the project root for team-wide MCP server configuration in Claude Code:

```json
{
  "mcpServers": {
    "my-tool": {
      "command": "node",
      "args": ["server/index.js"],
      "env": {
        "API_KEY": ""
      }
    }
  }
}
```

Team members approve on first use. Scope levels: `local` (default, private), `project` (`.mcp.json`, shareable), `user` (all projects).

See your language context for the appropriate `command` and `args` values.

## Community Resources

### Official

- [MCP Specification](https://modelcontextprotocol.io/specification/2025-06-18)
- [MCP Blog](https://blog.modelcontextprotocol.io/)
- [Anthropic MCP Course (Skilljar)](https://anthropic.skilljar.com/introduction-to-model-context-protocol)

### Security

- [Simon Willison: MCP Prompt Injection](https://simonwillison.net/2025/Apr/9/mcp-prompt-injection/)
- [The Lethal Trifecta for AI Agents](https://simonw.substack.com/p/the-lethal-trifecta-for-ai-agents)
- [MCP Security Best Practices (Spec)](https://modelcontextprotocol.io/specification/draft/basic/security_best_practices)

### Curated Lists

- [awesome-mcp-servers (punkpeye)](https://github.com/punkpeye/awesome-mcp-servers)
- [awesome-mcp-servers (wong2)](https://github.com/wong2/awesome-mcp-servers)
- [Docker MCP Toolkit](https://docs.docker.com/ai/mcp-catalog-and-toolkit/get-started/)
