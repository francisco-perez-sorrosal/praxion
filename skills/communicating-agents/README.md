# Communicating Agents

Agent-to-agent communication protocols for multi-agent interoperability. Currently focused on the A2A (Agent2Agent) protocol, with an extensible structure for future protocols.

## When to Use

- Building multi-agent systems that communicate across frameworks or organizations
- Exposing agents via A2A endpoints for external consumption
- Implementing agent discovery with Agent Cards
- Integrating A2A with AI frameworks (ADK, LangGraph, CrewAI, Pydantic AI)
- Choosing between agent communication protocols (A2A, MCP, ANP)

## Activation

Triggers on: multi-agent communication, agent interoperability, A2A protocol, Agent Cards, agent discovery, agent-to-agent protocols, cross-framework agent collaboration, A2A Python SDK, A2A TypeScript SDK.

## Skill Contents

| File | Purpose |
|------|---------|
| `SKILL.md` | Protocol overview, selection guidance, A2A summary, SDK selection, minimal server patterns |
| `contexts/a2a-python.md` | A2A Python SDK (`a2a-sdk`) implementation: server, client, streaming, push notifications |
| `contexts/a2a-typescript.md` | A2A TypeScript SDK (`@a2a-js/sdk`) implementation: server, client, streaming |
| `references/a2a-protocol.md` | Full A2A protocol reference: spec, data model (Task, Message, Part, Artifact), all 11 operations |
| `references/a2a-framework-integrations.md` | Framework integration patterns: ADK, LangGraph, CrewAI, Pydantic AI, Semantic Kernel, AutoGen |

## Related Skills

- **[agentic-sdks](../agentic-sdks/)** -- Building agents with OpenAI Agents SDK or Claude Agent SDK. Complementary: build an agent with agentic-sdks, then expose it via communicating-agents.
- **[mcp-crafting](../mcp-crafting/)** -- Agent-to-tool communication via MCP (complementary protocol to A2A).
