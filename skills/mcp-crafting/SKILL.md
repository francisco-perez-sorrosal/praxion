---
name: mcp-crafting
description: >
  Building MCP (Model Context Protocol) servers with official SDKs: protocol
  concepts (tools, resources, prompts), transports (stdio, streamable HTTP),
  bundles (.mcpb), MCP Inspector testing, client integration with Claude Desktop
  and Claude Code, logging, error handling, security. Language modules for
  Python (FastMCP) and TypeScript (@modelcontextprotocol/sdk). Triggers:
  creating MCP servers, defining MCP tools/resources, configuring transports,
  packaging bundles, testing servers, integrating with Claude; MCP tool
  definition, MCP resource exposure, FastMCP server patterns.
allowed-tools: [Read, Write, Edit, Glob, Grep, Bash]
compatibility: Claude Code
staleness_sensitive_sections:
  - "Before You Build: Do You Need MCP?"
  - "Transports"
  - "Bundles (.mcpb) -- Packaging for Distribution"
  - "Code Execution with MCP (Emerging)"
  - "Resources"
staleness_threshold_days: 60
---

# MCP Server Development

Build [Model Context Protocol](https://modelcontextprotocol.io) servers that expose tools, resources, and prompts to LLM applications.

**Satellite files** (loaded on-demand):

- [../skill-crafting/references/context-engineering-foundations.md](../skill-crafting/references/context-engineering-foundations.md) -- the shared "why" (every tool's schema is always-loaded context; tool-set bloat costs tokens AND degrades tool-selection accuracy)
- [references/resources.md](references/resources.md) -- full manifest specification, bundle structures, advanced examples
- [../skill-crafting/references/artifact-naming.md](../skill-crafting/references/artifact-naming.md) -- naming conventions for all artifact types

For MCP connector API features (calling MCP servers from the Messages API), consult the `claude-ecosystem` skill.

## Table of Contents

- [Before You Build: Do You Need MCP?](#before-you-build-do-you-need-mcp)
- [Language Contexts](#language-contexts)
- [Core Primitives](#core-primitives)
- [Transports](#transports)
- [Logging](#logging)
- [Client Integration](#client-integration)
- [Error Handling](#error-handling)
- [Token-Efficient Tool Responses](#token-efficient-tool-responses)
- [Testing](#testing)
- [Bundles (.mcpb)](#bundles-mcpb----packaging-for-distribution)
- [Code Execution with MCP (Emerging)](#code-execution-with-mcp-emerging)
- [Common Pitfalls](#common-pitfalls)
- [Resources](#resources)

## Before You Build: Do You Need MCP?
<!-- last-verified: 2026-05-25 -->

MCP is not free. Each connected server injects its tool schemas into context at session start — commonly thousands of tokens before the user says anything — and a larger tool surface measurably *degrades* tool-selection accuracy (the model picks wrong among look-alikes). A single broad query has been measured at ~30× more tokens through an MCP server than through the equivalent CLI.

So, in order:

1. **Can a CLI tool do it?** LLMs already know how to call `some-tool --help`. A well-documented CLI (or a Praxion command/skill that wraps one) is often cheaper and simpler than an MCP server. Reach for MCP when you need a *typed, discoverable* contract a model invokes directly, OAuth-mediated remote access, or resources/prompts — not merely to wrap an API.
2. **If you do build MCP, install few servers and scope narrowly.** Three focused servers beat thirteen; fewer, sharper tools choose better.
3. **At large tool counts, prefer code-execution mode** (see [Code Execution with MCP](#code-execution-with-mcp-emerging)).

Tool-*design* quality (naming, fat-vs-thin, error grammar) is its own discipline — see [`agentic-interface-design`](../agentic-interface-design/SKILL.md) and Anthropic's [Writing effective tools for AI agents](https://www.anthropic.com/engineering/writing-tools-for-agents).

## Language Contexts

| Language | Context File | Related Skills |
|----------|-------------|----------------|
| Python   | [contexts/python.md](contexts/python.md) | python-development, python-prj-mgmt |
| TypeScript | [contexts/typescript.md](contexts/typescript.md) | typescript-development, node-prj-mgmt |

When working in a specific language, load the corresponding context for SDK setup, code examples, testing, and deployment patterns. The contexts carry **version-pinned** SDK guidance (SDK versions, package ranges) — the most drift-prone content in this skill; re-verify with `/refresh-skill mcp-crafting` against current SDK releases before relying on a pin.

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

**Tool *design* quality** — naming a tool well, writing its description so a model comprehends it on every call, deciding fat-vs-thin decomposition, applying progressive disclosure when the surface exceeds ~20 tools, and designing errors the model can self-recover from — is a design discipline distinct from the implementation mechanics on this page. For that craft, see the [`agentic-interface-design`](../agentic-interface-design/SKILL.md) skill (the tool name and description ARE the interface; the description is the primary lever for correcting model behavior). This page covers *how to build* an MCP server; `agentic-interface-design` covers *how good* the tool design is.

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
<!-- last-verified: 2026-05-25 -->

| Transport | Use Case |
|-----------|----------|
| **stdio** | Local development, Claude Desktop |
| **Streamable HTTP** | Production, remote clients |

SSE is deprecated — use streamable HTTP for all new HTTP-based servers. Remote HTTP servers standardize on **OAuth 2.1** for auth (handled in-browser on first use for hosted servers); always use HTTPS, never hardcode tokens. Tools **lazy-load** — the connection opens on first use, not at registration.

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

## Token-Efficient Tool Responses

A tool's return value is context the model pays for on every call. Build for token efficiency (design rationale: [`agentic-interface-design`](../agentic-interface-design/SKILL.md); source: [Writing effective tools for AI agents](https://www.anthropic.com/engineering/writing-tools-for-agents)):

- **Default to filtered, paginated responses.** Provide sensible default limits, range selection, and filtering — don't return everything. Claude Code caps tool responses at **25,000 tokens** by default; on truncation, return guidance steering the model toward narrower queries.
- **Offer a `response_format` (`concise` | `detailed`)** so the agent tunes verbosity — `concise` returns only actionable content; `detailed` adds IDs/metadata for chained calls.
- **Return natural-language identifiers, not opaque UUIDs.** Models reason far better over `name`/`title` than over `a3f9-…`; surface high-signal fields, drop low-signal ones (`mime_type`, `256px_url`).
- **Write errors that steer.** "Found 847 results — too many to return; narrow by date or category" beats an opaque code or traceback.

## Testing

### MCP Inspector

The [MCP Inspector](https://github.com/modelcontextprotocol/inspector) provides interactive testing for any MCP server, regardless of language:

```bash
npx -y @modelcontextprotocol/inspector          # Standalone Inspector
```

Connect to a running server or launch one directly. The Inspector lets you invoke tools, read resources, and test prompts through a web UI at `localhost:6274`.

See language context for in-memory / programmatic testing patterns.

## Bundles (.mcpb) -- Packaging for Distribution
<!-- last-verified: 2026-05-25 -->

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

## Code Execution with MCP (Emerging)
<!-- last-verified: 2026-05-25 -->

A 2026 pattern (Anthropic, [Code execution with MCP](https://www.anthropic.com/engineering/code-execution-with-mcp)): instead of loading every tool's schema and orchestrating call-by-call, the agent **writes code that imports and calls tools** in a sandbox, handling intermediate results at the edge. Reported up to **~98% token reduction** (150k → 2k on a Drive→Salesforce workflow); the win scales with tool count. Four complementary levers: schema compression, **search-first tool discovery** (an optional `search_tools` endpoint loads defs on demand), response filtering, and code-based execution.

For Praxion this is **forward-looking**, not a hard requirement — it needs a sandboxed code-execution environment. When authoring an MCP server today, design tools so they compose cleanly in code (clear types, deterministic returns, idempotency via a `request_id`), so the server is ready if/when code-execution mode is available in the target harness.

## Common Pitfalls

- **Printing to stdout** in stdio servers -- corrupts JSON-RPC. Log to stderr
- **Using SSE transport** -- deprecated. Use streamable HTTP
- **Missing type annotations** -- LLMs cannot understand tool parameters without annotations
- **Mixing primitives** -- tools execute logic (side effects OK), resources expose data (no side effects)
- **Overly broad permissions** -- start read-only, whitelist operations, restrict filesystem paths

See language context for language-specific pitfalls.

## Resources
<!-- last-verified: 2026-05-25 -->

- [MCP Specification](https://modelcontextprotocol.io/specification) -- official protocol spec (versioned by date; verify the current dated version)
- [Writing effective tools for AI agents](https://www.anthropic.com/engineering/writing-tools-for-agents) -- Anthropic-official tool-design guidance (2025-09-11)
- [Code execution with MCP](https://www.anthropic.com/engineering/code-execution-with-mcp) -- the token-reduction pattern (2025-11-04)
- [MCP Inspector](https://github.com/modelcontextprotocol/inspector) -- interactive testing tool
- [Security Best Practices](https://modelcontextprotocol.io/specification/draft/basic/security_best_practices) -- official security guidance
- Context-engineering foundations (tool-set bloat, attention budget): [../skill-crafting/references/context-engineering-foundations.md](../skill-crafting/references/context-engineering-foundations.md)
- See language context for SDK-specific resources; see [references/resources.md](references/resources.md) for advanced patterns and community guides
