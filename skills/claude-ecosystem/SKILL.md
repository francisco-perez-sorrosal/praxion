---
name: claude-ecosystem
description: Anthropic Claude platform knowledge -- Claude API features, Anthropic SDK
  usage patterns, model selection guidance, extended thinking, batch processing, prompt
  caching, structured outputs, token counting, Files API, and ecosystem navigation.
  Use when building applications with the Claude Messages API, choosing between Claude
  models (which model to use), integrating Anthropic client SDKs (Python or TypeScript),
  SDK selection, choosing between Agent SDK and Messages API, Claude API integration,
  or navigating Anthropic documentation.
allowed-tools: [Read, Glob, Grep]
compatibility: Claude Code
---

# Claude Ecosystem

Structured knowledge of the Anthropic/Claude platform -- models, API features, SDKs, and documentation. Use as an ecosystem map to find what is available, choose between options, and locate authoritative sources.

**Satellite files** (loaded on-demand):

- [references/api-features.md](references/api-features.md) -- detailed API feature coverage, usage patterns, availability
- [references/sdk-patterns.md](references/sdk-patterns.md) -- SDK idioms, async patterns, error handling, Agent SDK
- [references/docs-map.md](references/docs-map.md) -- documentation site navigation, repo index, LLM-friendly URLs
- [references/platform-services.md](references/platform-services.md) -- batch processing, prompt caching, Files API, data residency

## Gotchas

- **Prompt caching silently ignores small blocks**: Content below 1024 tokens (Opus/Sonnet) or 2048 tokens (Haiku) is never cached regardless of `cache_control` markers -- no error returned, just no cache. See [references/platform-services.md](references/platform-services.md).
- **1M context requires a beta header**: The default context limit is 200K. Extended context (1M tokens) requires the `interleaved-thinking-2025-05-14` or `extended-context` beta header -- without it, requests exceeding 200K fail.
- **`max_tokens` has no default**: Every `messages.create` call must set `max_tokens` explicitly. Omitting it produces an API error, not a sensible default. See [references/sdk-patterns.md](references/sdk-patterns.md).
- **Extended thinking is incompatible with `temperature`**: When using `thinking.budget_tokens`, temperature must be unset or exactly 1. Any other value produces an error.
- **System prompt is not in the messages array**: Use the top-level `system` parameter. Placing the system prompt as `role: "system"` in `messages` does not work -- it is not a valid role in the Claude Messages API.

## Current Model Lineup

| Model | Model ID | Context | Max Output | Key Strengths |
| --- | --- | --- | --- | --- |
| Opus 4.6 | `claude-opus-4-6-20250610` | 200K | 32K | Highest capability. Complex reasoning, coding, extended thinking, adaptive thinking |
| Sonnet 4.5 | `claude-sonnet-4-5-20250514` | 200K | 16K | Balanced performance and cost. Hybrid extended thinking. Fast |
| Haiku 4.5 | `claude-haiku-4-5-20250514` | 200K | 8K | Fastest and cheapest. Classification, routing, high-volume tasks |

**Extended context (beta):** All models support up to 1M tokens with the `anthropic-beta: interleaved-thinking-2025-05-14` header or equivalent beta flag.

### Model Selection Heuristics

- **Default choice:** Sonnet 4.5 -- best balance of capability, speed, and cost for most tasks
- **Maximum quality:** Opus 4.6 -- when accuracy, nuance, or complex reasoning is critical
- **High volume / low latency:** Haiku 4.5 -- classification, routing, extraction, simple Q&A
- **Extended thinking needed:** Opus 4.6 (recommended) or Sonnet 4.5 -- set `thinking.budget_tokens`
- **Structured outputs:** All models support JSON mode and tool-schema-based structured outputs
- **Cost-sensitive batch workloads:** Any model via Batch API (50% cost reduction)

## API Feature Map

Features organized by category. Status: GA (generally available) or Beta.

### Model Capabilities

| Feature | Status | Description |
| --- | --- | --- |
| Extended thinking | GA | Step-by-step reasoning via `thinking.budget_tokens`. Interleaved thinking (beta) |
| Adaptive thinking | GA | Model dynamically allocates thinking depth (Opus 4.6 recommended) |
| Effort parameter | GA | Control compute effort: `low`, `medium`, `high` (Opus 4.5/4.6) |
| Structured outputs | GA | JSON mode (`response_format`) or strict tool schemas for typed responses |
| Citations | GA | Source-grounded responses with document references |
| PDF support | GA | Native PDF understanding in message content |
| Search results | GA | RAG-style citations from search tool results |
| 1M context window | Beta | Extended context beyond 200K default |

### Server-Side Tools

| Feature | Status | Description |
| --- | --- | --- |
| Web search | GA | Built-in web search tool (`web_search_20250305`) |
| Web fetch | GA | Fetch and parse web page content |
| Code execution | GA | Sandboxed Python execution environment |
| Memory | Beta | Cross-conversation persistence for user preferences |

### Client-Side Tools

| Feature | Status | Description |
| --- | --- | --- |
| Bash | GA | Shell command execution (Claude Code, Agent SDK) |
| Computer use | Beta | GUI interaction via screenshots and mouse/keyboard |
| Text editor | GA | File viewing and editing (Claude Code, Agent SDK) |

### Tool Infrastructure

| Feature | Status | Description |
| --- | --- | --- |
| MCP connector | Beta | Connect to MCP servers directly from Messages API |
| Tool search | GA | Scale to 1000s of tools with semantic search |
| Fine-grained streaming | GA | Granular streaming of tool use and text blocks |
| Programmatic tool calling | GA | Tools invoked from code execution sandbox |

### Context Management

| Feature | Status | Description |
| --- | --- | --- |
| Prompt caching (5m) | GA | Cache prefixes for 5 minutes, ~90% cost reduction on cache hits |
| Prompt caching (1hr) | GA | Extended 1-hour TTL, workspace-level isolation |
| Compaction | GA | Server-side context summarization (Opus 4.6, Haiku 4.5) |
| Token counting | GA | Pre-flight token estimation endpoint |

### Files

| Feature | Status | Description |
| --- | --- | --- |
| Files API | Beta | Upload and manage PDFs, images, and text files for reuse across requests |

See [references/api-features.md](references/api-features.md) for usage details, API shapes, and implementation guidance per feature.

## SDK Quick Reference

| SDK | Repo | Language | Purpose |
| --- | --- | --- | --- |
| Python SDK | [anthropic-sdk-python](https://github.com/anthropics/anthropic-sdk-python) | Python 3.9+ | REST API client. Sync/async, typed models, streaming |
| TypeScript SDK | [anthropic-sdk-typescript](https://github.com/anthropics/anthropic-sdk-typescript) | TypeScript/Node | REST API client for TS/JS applications |
| Agent SDK (Python) | [claude-agent-sdk-python](https://github.com/anthropics/claude-agent-sdk-python) | Python 3.10+ | Agent framework. Powers Claude Code. Bundles CLI |
| Agent SDK (TS) | [claude-agent-sdk-typescript](https://github.com/anthropics/claude-agent-sdk-typescript) | TypeScript | Agent framework for TS applications |
| Claude Code | npm `@anthropic-ai/claude-code` | Node.js | Agentic coding tool with hooks, plugins, skills, MCP |

**Additional SDKs:** Java, Go, Ruby, C#, PHP -- listed on the [Client SDKs docs page](https://platform.claude.com/docs/en/api/client-sdks) but less widely promoted.

### SDK Selection Guidance

- **Building an API integration:** Python SDK or TypeScript SDK -- direct Messages API access with full control
- **Building an agent:** Agent SDK (Python or TS) -- higher-level abstractions for tool use, MCP, multi-turn
- **Extending Claude Code:** Claude Code plugin system -- hooks, skills, commands, MCP servers
- **Prototyping:** Python SDK with sync client -- fastest path to a working call

See [references/sdk-patterns.md](references/sdk-patterns.md) for initialization, streaming, error handling, and Agent SDK patterns.

## Ecosystem Relationships

The **platform knowledge layer** -- what the Claude API offers, which SDK to use, which model fits a task, and where to find documentation. Does not cover how to build specific artifact types or use specific tools.

**Boundaries with related skills and agents:**

| Skill/Agent | Owns | claude-ecosystem Provides |
| --- | --- | --- |
| [agentic-sdks](../agentic-sdks/SKILL.md) | Building agents with OpenAI Agents SDK and Claude Agent SDK (implementation patterns, tools, multi-agent, hooks) | Model selection, SDK selection guidance, API features |
| [mcp-crafting](../mcp-crafting/SKILL.md) | Building MCP servers (transports, tools, resources, prompts) | MCP connector API feature, protocol context |
| claude-code-guide (subagent) | Claude Code operations (hooks, plugins, settings, CLI) | Messages API, SDK patterns underlying Claude Code |
| [python-development](../python-development/SKILL.md) | Python coding patterns, testing, tooling | Anthropic Python SDK specifics |

**Rule of thumb:** If the question is "How do I use feature X in the Claude API?" -- consult this skill. If it is "How do I build an agent with the Claude Agent SDK or OpenAI Agents SDK?" -- consult `agentic-sdks`. If it is "How do I build an MCP server?" -- consult `mcp-crafting`. If it is "How do I configure Claude Code hooks?" -- consult `claude-code-guide`.

## Resources

- [Claude API Documentation](https://platform.claude.com/docs/en/) -- Primary developer docs
- [Claude Code Documentation](https://code.claude.com/docs/en/) -- Claude Code-specific docs
- [API Reference](https://platform.claude.com/docs/en/api/messages) -- REST endpoint reference
- [MCP Specification](https://modelcontextprotocol.io/specification/2025-11-25) -- Model Context Protocol spec
- [Release Notes](https://platform.claude.com/docs/en/release-notes/overview) -- API, Claude Code, and model changelogs
