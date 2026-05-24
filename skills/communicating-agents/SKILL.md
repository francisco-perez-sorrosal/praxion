---
name: communicating-agents
description: >
  Agent-to-agent communication protocols for multi-agent interoperability: A2A
  (Agent2Agent) protocol — Agent Cards, task-based messaging, discovery, streaming,
  push notifications, SDK implementation in Python and TypeScript, integration with
  ADK, LangGraph, CrewAI, Pydantic AI. Triggers: building multi-agent systems across
  frameworks or organizations, exposing agents via A2A endpoints, implementing agent
  discovery; A2A, agent-to-agent, Agent Card, multi-agent communication, agent
  interoperability, cross-agent protocol.
allowed-tools: [Read, Write, Edit, Glob, Grep, Bash]
compatibility: Claude Code
staleness_sensitive_sections:
  - "Gotchas"
  - "A2A Protocol Summary"
  - "Core Concepts"
  - "Agent Discovery"
  - "Authentication"
  - "Architecture Layers"
  - "SDK Selection"
  - "Minimal Server Pattern"
  - "Framework Integrations"
staleness_threshold_days: 60
---

# Communicating Agents

Protocols for agent-to-agent communication -- enabling agents built with different frameworks, languages, or organizations to discover each other and collaborate on tasks.

**Satellite files** (loaded on-demand): `contexts/` is a project convention for language-specific implementation guides — functionally equivalent to `references/` but semantically distinct (task-oriented vs. lookup).

- [contexts/a2a-python.md](contexts/a2a-python.md) -- A2A Python SDK implementation guide (`a2a-sdk`)
- [contexts/a2a-typescript.md](contexts/a2a-typescript.md) -- A2A TypeScript SDK implementation guide (`@a2a-js/sdk`)
- [references/a2a-protocol.md](references/a2a-protocol.md) -- Full A2A protocol reference (spec, data model, operations, auth, lifecycle)
- [references/a2a-framework-integrations.md](references/a2a-framework-integrations.md) -- Framework integration patterns (ADK, LangGraph, CrewAI, Pydantic AI, etc.)

## Gotchas
<!-- last-verified: 2026-05-01 -->

- **`InMemoryTaskStore` is dev-only.** Both Python and TypeScript SDKs default to `InMemoryTaskStore`. This loses all tasks on restart -- production requires a persistent backing store (PostgreSQL, MySQL, or SQLite). The minimal server examples in this skill use `InMemoryTaskStore` for brevity; always swap for production.
- **Protocol is pre-1.0 -- expect breaking changes.** A2A is at v0.3. The spec, data model, and SDK APIs may change before 1.0. Pin SDK versions and monitor the [changelog](https://a2a-protocol.org/latest/specification/).
- **Agent Card discovery beyond well-known URI is not standardized.** Only `/.well-known/agent-card.json` is specified. Curated registries, DNS-based discovery, and other mechanisms are proprietary or proposed -- do not depend on them for interop.
- **Streaming requires SSE -- not WebSocket.** A2A streaming uses Server-Sent Events (SSE) over HTTP, not WebSocket. Client libraries that assume WebSocket will not work.

## Protocol Selection

| Protocol | Focus | Maturity | When to Use |
|----------|-------|----------|-------------|
| **A2A** | Agent-to-agent task execution | Production-ready (v0.3, Linux Foundation) | Cross-framework agent collaboration, task delegation, agent discovery |
| **MCP** | Agent-to-tool communication | Production-ready (Anthropic) | Connecting agents to tools and data sources (complementary to A2A) |
| **ANP** | Agent discovery, identity, network interop | Early (whitepaper) | Decentralized agent networks with DID-based identity |
| **Agora** | Adaptable agent communication | Research | Academic exploration of agent communication |
| **AG-UI** | Agent-to-frontend | Emerging | Real-time agent UI streaming |

A2A and MCP are complementary: MCP connects agents to tools, A2A connects agents to each other. Build an agent with any framework, expose it via A2A, connect it to tools via MCP.

## A2A Protocol Summary
<!-- last-verified: 2026-05-01 -->

A2A (Agent2Agent) is an open protocol for agent-to-agent communication. Donated to the Linux Foundation (June 2025) with 150+ supporting organizations including AWS, Microsoft, Salesforce, SAP, and IBM.

### Core Concepts
<!-- last-verified: 2026-05-01 -->

**Actors:**

- **User** -- human or automated service defining goals
- **A2A Client** -- application or agent acting on user's behalf
- **A2A Server** -- remote agent exposing an HTTP endpoint

**Data Model:**

| Type | Purpose |
|------|---------|
| **Task** | Stateful work unit with lifecycle: `created -> working -> completed/failed/canceled/rejected` (interruptions: `input_required`, `auth_required`) |
| **Message** | Single communication turn (role: `user` or `agent`) |
| **Part** | Content container: `text`, `raw` bytes, `url` reference, or `data` (structured JSON) |
| **Artifact** | Tangible deliverable output from task processing |
| **AgentCard** | JSON metadata for discovery (identity, capabilities, skills, security, endpoint) |
| **contextId** | Server-generated identifier grouping related tasks |

**Interaction Patterns:**

1. **Request/Response (Polling)** -- `SendMessage`, then poll with `GetTask` for long-running work
2. **Streaming (SSE)** -- `SendStreamingMessage` for real-time incremental results via persistent HTTP connection
3. **Push Notifications** -- Async webhook notifications for extended operations; client registers a callback URL

### Agent Discovery
<!-- last-verified: 2026-05-01 -->

Agents advertise capabilities via an **Agent Card** -- a JSON document describing identity, endpoint, supported skills, and authentication requirements.

**Discovery strategies:**

1. **Well-Known URI** -- `https://{domain}/.well-known/agent-card.json` (RFC 8615)
2. **Extended Agent Cards** -- authenticated endpoint for sensitive metadata (`GetExtendedAgentCard`)
3. **Curated Registries** -- centralized repositories (not yet standardized)
4. **Direct Configuration** -- hardcoded URLs, config files, environment variables

### Authentication
<!-- last-verified: 2026-05-01 -->

A2A supports multiple authentication schemes declared in the Agent Card:

- API Key, HTTP Bearer, OAuth 2.0, OpenID Connect, Mutual TLS
- TLS 1.2+ required for production
- Credentials passed via HTTP headers

### Architecture Layers
<!-- last-verified: 2026-05-01 -->

| Layer | Purpose | Details |
|-------|---------|---------|
| Data Model | Protocol Buffers schema | Task, Message, Part, Artifact, AgentCard, TaskStatus |
| Abstract Operations | 11 operations | SendMessage, SendStreamingMessage, GetTask, ListTasks, CancelTask, SubscribeToTask, CRUD PushNotificationConfig, GetExtendedAgentCard |
| Protocol Bindings | Transport | JSON-RPC 2.0, gRPC (v0.3+), HTTP+JSON/REST |

For the complete operation list with parameters and the full data model schema, see [references/a2a-protocol.md](references/a2a-protocol.md).

## SDK Selection
<!-- last-verified: 2026-05-01 -->

| | Python (`a2a-sdk`) | TypeScript (`@a2a-js/sdk`) |
|---|---|---|
| **Install** | `pip install a2a-sdk` / `uv add a2a-sdk` | `npm install @a2a-js/sdk` |
| **Server framework** | Starlette/Uvicorn | Express |
| **Transport** | JSON-RPC, HTTP+JSON/REST, gRPC | JSON-RPC, HTTP+JSON/REST, gRPC |
| **Task persistence** | `InMemoryTaskStore` (dev), SQL stores (prod) | `InMemoryTaskStore` (dev) |
| **Core pattern** | `AgentExecutor.execute(context, event_queue)` | `AgentExecutor.execute(requestContext, eventBus)` |
| **Client** | `A2AClient` with transport factories | `ClientFactory` with auto-discovery |

Both SDKs follow the same pattern: implement `AgentExecutor`, wire it to `DefaultRequestHandler`, mount on HTTP server.

Load the language-specific context for implementation details:

- Python: [contexts/a2a-python.md](contexts/a2a-python.md)
- TypeScript: [contexts/a2a-typescript.md](contexts/a2a-typescript.md)

## Minimal Server Pattern
<!-- last-verified: 2026-05-01 -->

**Python:**

```python
from a2a.server.request_handler import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.server.apps import A2AStarletteApplication
from a2a.types import AgentCard
import uvicorn

# 1. Implement AgentExecutor (see contexts/a2a-python.md)
# 2. Create handler and app
handler = DefaultRequestHandler(agent_executor=my_executor, task_store=InMemoryTaskStore())
card = AgentCard(name="my-agent", description="...", url="http://localhost:8000", version="1.0")
app = A2AStarletteApplication(agent_card=card, http_handler=handler)

uvicorn.run(app.build(), host="0.0.0.0", port=8000)
```

**TypeScript:**

```typescript
import express from 'express';
import { DefaultRequestHandler, InMemoryTaskStore } from '@a2a-js/sdk/server';
import { agentCardHandler, jsonRpcHandler } from '@a2a-js/sdk/server/express';

// 1. Implement AgentExecutor (see contexts/a2a-typescript.md)
// 2. Create handler and mount middleware
const handler = new DefaultRequestHandler({ agentExecutor: myExecutor, taskStore: new InMemoryTaskStore() });
const app = express();
app.get('/.well-known/agent-card.json', agentCardHandler(agentCard));
app.post('/', jsonRpcHandler(handler));
app.listen(8000);
```

## Framework Integrations
<!-- last-verified: 2026-05-01 -->

Several AI frameworks provide built-in A2A support:

| Framework | Integration Level |
|-----------|------------------|
| Google ADK | Native A2A server/client |
| LangGraph | A2A endpoint via LangSmith |
| CrewAI | A2A adapter |
| Pydantic AI | `agent.to_a2a()` one-liner |
| Semantic Kernel | A2A plugin |
| AutoGen | A2A connector |
| AWS Bedrock AgentCore | Native deployment |

For integration patterns and code examples, see [references/a2a-framework-integrations.md](references/a2a-framework-integrations.md).

## Testing

- **Mokksy** -- mock A2A server for testing client code
- **A2A Inspector** -- protocol-level debugging (`github.com/a2aproject/a2a-inspector`)
- **In-process servers** -- start server in test, call with client for integration tests
- **Mock LLM calls** -- isolate protocol logic from model inference

## Production Considerations

- `InMemoryTaskStore` is development-only -- use PostgreSQL, MySQL, or SQLite stores for production
- Protocol is at v0.3 -- breaking changes possible before 1.0
- Agent Card discovery beyond well-known URI is not yet standardized
- Configure proper TLS and authentication for production deployments

## Resources

- [A2A Specification](https://a2a-protocol.org/latest/specification/)
- [Key Concepts](https://a2a-protocol.org/latest/topics/key-concepts/)
- [Agent Discovery](https://a2a-protocol.org/latest/topics/agent-discovery/)
- [Python SDK](https://github.com/a2aproject/a2a-python) -- [API docs](https://a2a-protocol.org/latest/sdk/python/api/)
- [JS/TS SDK](https://github.com/a2aproject/a2a-js)
- [Sample Agents](https://github.com/a2aproject/a2a-samples)
- [A2A Inspector](https://github.com/a2aproject/a2a-inspector)

## Related Skills

- **`agentic-sdks`** -- Building agents with OpenAI Agents SDK or Claude Agent SDK (agent loops, tools, multi-agent orchestration within a single framework). Complementary: build an agent with `agentic-sdks`, then expose it via A2A using this skill.
