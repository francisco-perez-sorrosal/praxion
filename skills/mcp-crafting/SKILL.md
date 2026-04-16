---
name: mcp-crafting
description: Building MCP (Model Context Protocol) servers using official SDKs. Covers protocol concepts (tools, resources, prompts), transports (stdio, streamable HTTP), bundles (.mcpb), testing with MCP Inspector, client integration with Claude Desktop and Claude Code, logging, error handling, and security principles. Language modules available for Python (with FastMCP). Use when creating MCP servers, defining MCP tools or MCP resources, configuring transports, packaging bundles, testing MCP servers, or integrating with Claude. Also relevant for MCP tool definition, MCP resource exposure, and FastMCP server patterns.
allowed-tools: [Read, Write, Edit, Glob, Grep, Bash]
compatibility: Claude Code
---

# MCP Server Development

Build [Model Context Protocol](https://modelcontextprotocol.io) servers that expose tools, resources, and prompts to LLM applications.

**Satellite files** (loaded on-demand):

- [references/resources.md](references/resources.md) -- full manifest specification, bundle structures, advanced examples
- [references/python-resources.md](references/python-resources.md) -- Python-specific FastMCP patterns and examples
- [../skill-crafting/references/artifact-naming.md](../skill-crafting/references/artifact-naming.md) -- naming conventions for all artifact types

For MCP connector API features (calling MCP servers from the Messages API), consult the `claude-ecosystem` skill.

## Table of Contents

- [Language Contexts](#language-contexts)
- [Core Primitives](#core-primitives)
- [Transports](#transports)
- [Logging](#logging)
- [Client Integration](#client-integration)
- [Error Handling](#error-handling)
- [Testing](#testing)
- [Bundles (.mcpb)](#bundles-mcpb----packaging-for-distribution)
- [Common Pitfalls](#common-pitfalls)
- [Resources](#resources)

## Language Contexts

| Language | Context File | Related Skills |
|----------|-------------|----------------|
| Python   | [contexts/python.md](contexts/python.md) | python-development, python-prj-mgmt |

When working in a specific language, load the corresponding context for SDK setup, code examples, testing, and deployment patterns.

## Core Primitives

### Tools -- Executable Functions

Tools perform computation and side effects. The LLM invokes them. Define parameters with types, defaults, and descriptions so the LLM understands how to call the tool.

    Tool "search_database":
      Parameters:
        query: string (required) -- search query
        limit: integer (default: 10) -- max results
      Returns: array of objects

    Tool "long_task":
      Parameters:
        name: string (required) -- task identifier
        steps: integer (default: 5) -- number of steps
      Returns: string (completion message)
      Behavior: reports progress after each step

Use tools for: computation, side effects, actions on external systems, anything that changes state.

### Resources -- Data Exposure

Resources provide data to LLMs (like GET endpoints). No significant side effects. Identified by URI templates.

    Resource "config://settings":
      Returns: string (JSON)

    Resource "file://docs/{path}":
      Parameters:
        path: string (URI template variable)
      Returns: string (file content)

Use resources for: read-only data, configuration, file access, database lookups without mutations.

### Prompts -- Reusable Templates

Prompts define structured interaction patterns for LLMs. They accept parameters and return formatted text.

    Prompt "analyze_data":
      Parameters:
        dataset: string (required)
        focus: string (default: "trends")
      Returns: string (prompt text)

Use prompts for: standardized analysis requests, review templates, multi-step workflows.

For prompt-body authoring patterns (few-shot examples, chain-of-thought, structured-output instructions, injection hardening) used inside MCP prompt templates, see the [`llm-prompt-engineering`](../llm-prompt-engineering/SKILL.md) skill.

**Do not mix primitives.** Tools execute logic (side effects OK). Resources expose data (no side effects). Prompts template interactions. If a function reads data and mutates state, make it a tool.

See language context for SDK-specific decorator syntax and code examples.

## Transports

| Transport | Use Case |
|-----------|----------|
| **stdio** | Local development, Claude Desktop |
| **Streamable HTTP** | Production, remote clients |

SSE is deprecated. Use streamable HTTP for all new HTTP-based servers.

See language context for transport configuration code.

## Logging

**Universal rule**: never print to stdout in stdio servers -- it corrupts JSON-RPC messages. Direct all logging output to stderr.

For HTTP servers, standard output logging is acceptable.

See language context for logging setup code.

## Client Integration

### Claude Desktop

Configure servers in the Claude Desktop config file (`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS):

```json
{
  "mcpServers": {
    "my-server": {
      "command": "RUNTIME_COMMAND",
      "args": ["RUNTIME_ARGS"]
    }
  }
}
```

See your language context for the `command` and `args` values appropriate to your runtime.

### Claude Code

```bash
# HTTP server (language-agnostic)
claude mcp add --transport http my-server http://localhost:8000/mcp

# Scope: user (all projects), local (default, this project), project (.mcp.json, shareable)
claude mcp add my-server --scope project -- RUNTIME_COMMAND RUNTIME_ARGS
```

See your language context for the stdio launch command.

## Error Handling

- Validate inputs early -- check types, ranges, required fields before processing
- Catch specific exceptions with targeted responses, fall back to generic handlers
- Return `isError: true` in `CallToolResult` for tool-level failures
- Log full error details to stderr; sanitize responses to avoid leaking internals
- Provide context-aware messages that help the LLM recover ("column 'xyz' not found -- did you mean 'xy'?")

## Testing

### MCP Inspector

The [MCP Inspector](https://github.com/modelcontextprotocol/inspector) provides interactive testing for any MCP server, regardless of language:

```bash
npx -y @modelcontextprotocol/inspector          # Standalone Inspector
```

Connect to a running server or launch one directly. The Inspector lets you invoke tools, read resources, and test prompts through a web UI at `localhost:6274`.

See language context for in-memory / programmatic testing patterns.

## Bundles (.mcpb) -- Packaging for Distribution

MCP Bundles are ZIP archives (`.mcpb` extension) containing a server and a `manifest.json`. They enable one-click installation in Claude Desktop (double-click, drag-and-drop, or Developer menu). Formerly called DXT (Desktop Extensions).

**Repository**: [modelcontextprotocol/mcpb](https://github.com/modelcontextprotocol/mcpb)

### Manifest Overview

Every bundle requires a `manifest.json` with at minimum:

    Manifest fields (required):
      manifest_version: string -- currently "0.4"
      name: string -- unique identifier (lowercase, hyphens)
      version: string -- semver
      description: string -- what the server does
      server:
        type: string -- one of: node, uv, python, binary
        entry_point: string -- path to server entry file

    Manifest fields (optional):
      author: { name, url, email }
      user_config: object -- declares user-configurable fields
      mcp_config: object -- environment variables for the server

### Server Types

| Type     | When to Use                                                            |
| -------- | ---------------------------------------------------------------------- |
| `node`   | **Recommended** -- ships with Claude Desktop, zero install friction    |
| `uv`     | Python servers -- host manages Python/deps via uv (experimental)       |
| `python` | Python with pre-bundled deps -- limited portability for compiled pkgs  |
| `binary` | Pre-compiled executables                                               |

### User Configuration

Declare config fields and Claude Desktop auto-generates a settings UI:

```json
{
  "user_config": {
    "api_key": {
      "type": "string",
      "title": "API Key",
      "required": true,
      "sensitive": true
    }
  }
}
```

Reference via `${user_config.api_key}` in `mcp_config.env`.

### CLI

```bash
npm install -g @anthropic-ai/mcpb
mcpb init                   # Generate manifest.json interactively
mcpb pack                   # Package into .mcpb file
mcpb pack examples/hello-world-uv  # Pack a specific directory
```

See [references/resources.md](references/resources.md) for the full manifest specification, bundle directory structures, and advanced examples. See language context for language-specific bundle patterns.

## Common Pitfalls

- **Printing to stdout** in stdio servers -- corrupts JSON-RPC. Log to stderr
- **Using SSE transport** -- deprecated. Use streamable HTTP
- **Missing type annotations** -- LLMs cannot understand tool parameters without annotations
- **Mixing primitives** -- tools execute logic (side effects OK), resources expose data (no side effects)
- **Overly broad permissions** -- start read-only, whitelist operations, restrict filesystem paths

See language context for language-specific pitfalls.

## Resources

- [MCP Specification](https://modelcontextprotocol.io/specification/2025-06-18) -- Official protocol spec
- [MCP Inspector](https://github.com/modelcontextprotocol/inspector) -- Interactive testing tool
- [Security Best Practices](https://modelcontextprotocol.io/specification/draft/basic/security_best_practices) -- Official security guidance
- See language context for SDK-specific resources
- See [references/resources.md](references/resources.md) for advanced patterns, security deep-dives, and community guides
