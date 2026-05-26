# Agentic SDKs

Building production AI agents with the OpenAI Agents SDK and Claude Agent SDK. Framework-agnostic patterns with language-specific implementation guides.

## When to Use

- Building autonomous agents with tool use and multi-agent orchestration
- Choosing between OpenAI Agents SDK and Claude Agent SDK
- Integrating MCP servers into agent workflows
- Implementing agent safety (guardrails, hooks, permission modes)
- Setting up streaming, session persistence, or handoff-based delegation

## Activation

Triggers on: building autonomous agents, multi-agent workflows, choosing agent frameworks, integrating MCP servers, agent safety patterns, OpenAI Agents SDK, Claude Agent SDK, agent tool integration.

## Skill Contents

| File | Purpose |
|------|---------|
| `SKILL.md` | Framework selection, architecture comparison, common agent patterns, tool integration patterns |
| `contexts/openai-agents-python.md` | OpenAI Agents SDK for Python: setup, Agent, Runner, function tools, handoffs, guardrails |
| `contexts/openai-agents-typescript.md` | OpenAI Agents SDK for TypeScript: setup, typed agents, Zod schemas, streaming |
| `contexts/claude-agent-python.md` | Claude Agent SDK for Python: query(), hooks, subagents, permissions, MCP |
| `contexts/claude-agent-typescript.md` | Claude Agent SDK for TypeScript: ClaudeSDKClient, tool decorator, session management |
| `references/openai-agents.md` | Full OpenAI Agents SDK reference: all parameters, advanced patterns, deployment |
| `references/claude-agent.md` | Full Claude Agent SDK reference: all configuration, hooks, subagent orchestration |

## Related Skills

- **[claude-ecosystem](../claude-ecosystem/)** -- Claude API and Messages SDK patterns (model selection, API features)
- **[llm-prompt-engineering](../llm-prompt-engineering/)** -- Prompt-body authoring patterns for agent instructions and per-turn prompts
- **[mcp-crafting](../mcp-crafting/)** -- Building MCP servers for agent tool integration
- **[communicating-agents](../communicating-agents/)** -- Agent-to-agent protocols (A2A) for cross-framework interoperability
