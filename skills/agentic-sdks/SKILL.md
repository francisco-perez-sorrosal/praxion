---
name: agentic-sdks
description: Building AI agents with production SDKs -- OpenAI Agents SDK and Claude
  Agent SDK. Covers agent architecture, tool integration, multi-agent orchestration,
  safety guardrails, tracing, context management, streaming, and MCP integration.
  Use when building autonomous agents, implementing multi-agent workflows, choosing
  between agent frameworks, integrating tools or MCP servers, or implementing agent
  safety patterns. Language modules available for Python and TypeScript.
allowed-tools: [Read, Write, Edit, Glob, Grep, Bash]
compatibility: Claude Code
---

# Agentic SDKs

Build production AI agents using the OpenAI Agents SDK or Claude Agent SDK. Both frameworks provide agent loops, tool integration, multi-agent orchestration, and observability -- but with distinct architectures and design philosophies.

**Satellite files** (loaded on-demand):

- [references/openai-agents.md](references/openai-agents.md) -- full OpenAI Agents SDK reference: Agent, Runner, tools, handoffs, guardrails, tracing, MCP
- [references/claude-agent.md](references/claude-agent.md) -- full Claude Agent SDK reference: query, ClaudeSDKClient, hooks, subagents, permissions, built-in tools

**Language contexts** (load per framework + language):

- [contexts/openai-agents-python.md](contexts/openai-agents-python.md) -- OpenAI Agents SDK for Python
- [contexts/openai-agents-typescript.md](contexts/openai-agents-typescript.md) -- OpenAI Agents SDK for TypeScript
- [contexts/claude-agent-python.md](contexts/claude-agent-python.md) -- Claude Agent SDK for Python
- [contexts/claude-agent-typescript.md](contexts/claude-agent-typescript.md) -- Claude Agent SDK for TypeScript

**Related skills:**

- For Claude model selection, API features, and Messages SDK patterns, see the `claude-ecosystem` skill

## Gotchas

- **Context object invisible to LLM (OpenAI)**: `RunContextWrapper.context` is dependency injection for tools and hooks only -- the model never sees it. To pass information to the LLM, put it in the prompt or instructions, not the context object.
- **Claude SDK loads no project settings by default**: `setting_sources` / `settingSources` defaults to empty. CLAUDE.md, skills, and `.claude/settings.json` are silently ignored unless you explicitly set `["project"]`.
- **Context type must unify across a run (OpenAI)**: All agents, tools, guardrails, and hooks in a single `Runner.run()` call must share the same generic context type parameter. Mixing types causes runtime errors with no clear diagnostic.
- **MCP tool names require triple-underscore prefix (Claude)**: Custom MCP tools must be referenced as `mcp__<server>__<tool>` in `allowed_tools`. A mismatch silently makes the tool unavailable -- no error, just invisible to the agent.
- **Zod v4 required at runtime (OpenAI TS)**: The TypeScript SDK validates schemas using the Zod v4 API. Installing Zod v3 (the common default) causes silent schema failures at runtime, not at import time.

## Framework Selection

### Use OpenAI Agents SDK When

- Building with OpenAI models (GPT-4o, GPT-5, o-series)
- Need handoff-based multi-agent orchestration (peer-to-peer delegation)
- Want provider-agnostic framework (supports non-OpenAI models via LiteLLM/Vercel AI SDK)
- Need voice/realtime agent capabilities
- Want hosted tools (web search, file search, code interpreter, image generation)
- Need explicit guardrail system with tripwire pattern

### Use Claude Agent SDK When

- Building with Claude models (Opus, Sonnet, Haiku)
- Need built-in filesystem and code execution tools (Read, Write, Edit, Bash, Glob, Grep)
- Want the same agent loop that powers Claude Code
- Need hierarchical subagent orchestration with context isolation
- Want hook-based lifecycle control with permission decisions
- Need session persistence, forking, and file checkpointing

## Architecture Comparison

| Concept | OpenAI Agents SDK | Claude Agent SDK |
| --- | --- | --- |
| **Core entry point** | `Agent` class + `Runner.run()` | `query()` function / `ClaudeSDKClient` |
| **Agent loop** | Runner executes until final output | Built-in loop handles tool calls autonomously |
| **Tool definition** | `@function_tool` decorator | `@tool` decorator + `create_sdk_mcp_server()` |
| **Built-in tools** | Hosted (web search, file search, code interpreter) | Filesystem (Read, Write, Edit, Bash, Glob, Grep, WebSearch, WebFetch) |
| **Custom tools** | Function tools + hosted MCP + local MCP | In-process SDK MCP servers + external MCP |
| **Multi-agent** | Handoffs (peer delegation) + agents-as-tools | Subagents via Task tool (hierarchical) |
| **Safety** | Input/output/tool guardrails with tripwires | Hooks (PreToolUse, PostToolUse) + permission modes |
| **Context sharing** | `RunContextWrapper` (typed dependency injection) | Session management + `ClaudeAgentOptions` |
| **Structured output** | `output_type` (Pydantic/dataclass/TypedDict) | `output_format` (JSON Schema) |
| **Tracing** | Built-in with OpenAI dashboard + 20+ integrations | OpenTelemetry spans + third-party integrations |
| **Streaming** | `Runner.run_streamed()` | `AsyncIterator[Message]` (always streaming) |
| **Session persistence** | SQLiteSession / RedisSession / custom | Session ID resume + fork |
| **MCP integration** | 5 server types (hosted, streamable HTTP, SSE, stdio, manager) | stdio, SSE, HTTP, in-process SDK servers |
| **Languages** | Python 3.10+, TypeScript/Node 22+ | Python 3.10+, TypeScript/Node 18+ |

## Common Agent Patterns

Both SDKs support these fundamental patterns with different implementations.

### Triage/Router Pattern

A central agent routes requests to specialized agents based on intent.

**OpenAI**: Router agent with `handoffs=[specialist_a, specialist_b]`. Control transfers completely.

**Claude**: Orchestrator uses subagents via Task tool. Orchestrator maintains control and synthesizes results.

### Pipeline Pattern

Sequential processing through multiple specialized stages.

**OpenAI**: Chain handoffs: agent_a hands off to agent_b, which hands off to agent_c.

**Claude**: Orchestrator spawns subagents sequentially, passing outputs as inputs to the next.

### Parallel Fan-Out

Multiple agents work on independent subtasks simultaneously.

**OpenAI**: Use agents-as-tools pattern -- central agent invokes multiple specialized agents as tools.

**Claude**: Orchestrator spawns multiple subagents in parallel via concurrent Task tool calls.

### Human-in-the-Loop

Gate agent actions on human approval.

**OpenAI**: MCP `require_approval` parameter, custom tool guardrails.

**Claude**: `canUseTool` callback, hook-based `PreToolUse` with `permissionDecision: "deny"`.

## Tool Integration Patterns

### Function Tools

Both frameworks wrap native functions as agent tools with automatic schema generation.

**OpenAI**: `@function_tool` decorator. Schema from type hints + docstrings. Supports Pydantic `Field` constraints.

**Claude**: `@tool` decorator with explicit name, description, and schema. Returns MCP `CallToolResult`.

### MCP Integration

Both support Model Context Protocol for external tool connectivity.

**OpenAI**: Five server types with `cache_tools_list`, `require_approval`, `tool_filter`, and `tool_meta_resolver`. Hosted MCP pushes execution to API infrastructure.

**Claude**: stdio, SSE, HTTP, and in-process SDK servers. In-process servers eliminate IPC overhead. Mixed server support (SDK + external in same config).

## Safety Patterns

### OpenAI Guardrails

Three-layer system: input guardrails (pre-execution), output guardrails (post-execution), tool guardrails (per-tool). Tripwire pattern raises exceptions to halt execution.

### Claude Hooks + Permissions

Event-driven system: `PreToolUse`, `PostToolUse`, `Stop`, `SessionStart`, etc. Hooks return permission decisions (`allow`, `deny`, `ask`). Four permission modes: `default`, `acceptEdits`, `bypassPermissions`, `plan`.

## Resources

### OpenAI Agents SDK

- [Python SDK docs](https://openai.github.io/openai-agents-python/)
- [TypeScript SDK docs](https://openai.github.io/openai-agents-js/)
- [Python repo](https://github.com/openai/openai-agents-python)
- [TypeScript repo](https://github.com/openai/openai-agents-js)

### Claude Agent SDK

- [SDK overview](https://platform.claude.com/docs/en/agent-sdk/overview)
- [Python repo](https://github.com/anthropics/claude-agent-sdk-python)
- [TypeScript repo](https://github.com/anthropics/claude-agent-sdk-typescript)
- [Demo applications](https://github.com/anthropics/claude-agent-sdk-demos)
- [Engineering blog](https://claude.com/blog/building-agents-with-the-claude-agent-sdk)
