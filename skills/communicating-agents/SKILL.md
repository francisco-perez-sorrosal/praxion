---
name: communicating-agents
description: >
  Agent-to-agent communication protocols for multi-agent interoperability: A2A
  (Agent2Agent) protocol — Agent Cards, task-based messaging, discovery, streaming,
  push notifications, SDK implementation in Python and TypeScript, integration with
  ADK, LangGraph, CrewAI, Pydantic AI. Triggers: building multi-agent systems across
  frameworks or organizations, exposing agents via A2A endpoints, implementing agent
  discovery; A2A, agent-to-agent, Agent Card, multi-agent communication, agent
  interoperability, cross-agent protocol. Language modules available for Python and TypeScript.
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

**Satellite files** (loaded on-demand):

- [contexts/a2a-python.md](contexts/a2a-python.md) -- A2A Python SDK implementation guide (`a2a-sdk`)
- [contexts/a2a-typescript.md](contexts/a2a-typescript.md) -- A2A TypeScript SDK implementation guide (`@a2a-js/sdk`)
- [references/a2a-protocol.md](references/a2a-protocol.md) -- Full A2A protocol reference (spec, data model, operations, auth, lifecycle)
- [references/a2a-framework-integrations.md](references/a2a-framework-integrations.md) -- Framework integration patterns (ADK, LangGraph, CrewAI, Pydantic AI, etc.)

## Language Contexts

| Language   | Context File | Tooling |
|------------|-------------|---------|
| Python     | [contexts/a2a-python.md](contexts/a2a-python.md) | `a2a-sdk`, Starlette/Uvicorn |
| TypeScript | [contexts/a2a-typescript.md](contexts/a2a-typescript.md) | `@a2a-js/sdk`, Express |

Load the context matching your language for setup, server/client implementation, streaming, and testing patterns.

## Gotchas
<!-- last-verified: 2026-08-05 -->

- **`InMemoryTaskStore` is dev-only.** Both Python and TypeScript SDKs default to `InMemoryTaskStore`. This loses all tasks on restart -- production requires a persistent backing store (PostgreSQL, MySQL, or SQLite). The minimal server examples in this skill use `InMemoryTaskStore` for brevity; always swap for production.
- **The protocol is past 1.0 -- migrate off v0.3.** A2A is at **v1.0.1** (v1.0.0 shipped 2026-03-12, v1.0.1 on 2026-05-28). v1.0.0 was itself a breaking release: the `kind` discriminator was removed from `Part` and streaming events, OAuth 2.0 implicit and resource-owner-password flows were removed (device code and PKCE added), push-notification config endpoints were pluralized, version prefixes were dropped from HTTP bindings, and `cancelled` was standardized to `canceled`. Both SDKs ship `compat/v0_3/` layers -- if you need one, you are still on the old data model. Pin SDK versions and monitor the [changelog](https://a2a-protocol.org/latest/specification/).
- **Agent Card discovery beyond well-known URI is not standardized.** Only `/.well-known/agent-card.json` is specified. Curated registries, DNS-based discovery, and other mechanisms are proprietary or proposed -- do not depend on them for interop.
- **The JSON-RPC and REST bindings stream over SSE, not WebSocket.** Those two bindings use Server-Sent Events over HTTP (`Content-Type: text/event-stream`); a client library that assumes WebSocket will not work against them. This is not a protocol-wide rule: the gRPC binding uses gRPC server streaming, and v1.0 supports custom protocol bindings, with WebSocket as the spec's own worked example.

## Protocol Selection

| Protocol | Focus | Maturity | When to Use |
|----------|-------|----------|-------------|
| **A2A** | Agent-to-agent task execution | Production-ready (v1.0, Linux Foundation) | Cross-framework agent collaboration, task delegation, agent discovery |
| **MCP** | Agent-to-tool communication | Production-ready (Anthropic) | Connecting agents to tools and data sources (complementary to A2A) |
| **ANP** | Agent discovery, identity, network interop | Early (whitepaper) | Decentralized agent networks with DID-based identity |
| **Agora** | Adaptable agent communication | Research | Academic exploration of agent communication |
| **AG-UI** | Agent-to-frontend | Emerging | Real-time agent UI streaming |

A2A and MCP are complementary: MCP connects agents to tools, A2A connects agents to each other. Build an agent with any framework, expose it via A2A, connect it to tools via MCP.

## A2A Protocol Summary
<!-- last-verified: 2026-08-05 -->

A2A (Agent2Agent) is an open protocol for agent-to-agent communication. Donated to the Linux Foundation (June 2025) with 150+ supporting organizations including AWS, Microsoft, Salesforce, SAP, and IBM.

### Core Concepts
<!-- last-verified: 2026-08-05 -->

**Actors:**

- **User** -- human or automated service defining goals
- **A2A Client** -- application or agent acting on user's behalf
- **A2A Server** -- remote agent exposing an HTTP endpoint

**Data Model:**

| Type | Purpose |
|------|---------|
| **Task** | Stateful work unit with lifecycle: `submitted -> working -> completed/failed/canceled/rejected` (interruptions: `input_required`, `auth_required`). There is no `created` state -- the proto's initial state is `submitted` |
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
<!-- last-verified: 2026-08-05 -->

Agents advertise capabilities via an **Agent Card** -- a JSON document describing identity, endpoint, supported skills, and authentication requirements.

**Discovery strategies:**

1. **Well-Known URI** -- `https://{domain}/.well-known/agent-card.json` (RFC 8615)
2. **Extended Agent Cards** -- authenticated endpoint for sensitive metadata (`GetExtendedAgentCard`)
3. **Curated Registries** -- centralized repositories (not yet standardized)
4. **Direct Configuration** -- hardcoded URLs, config files, environment variables

### Authentication
<!-- last-verified: 2026-08-05 -->

A2A supports multiple authentication schemes declared in the Agent Card:

- API Key, HTTP Bearer, OAuth 2.0, OpenID Connect, Mutual TLS
- Production **MUST** use encrypted communication (HTTPS for HTTP bindings, TLS for gRPC). The spec's version guidance is a SHOULD recommending **TLS 1.3+**, with SSLv3/TLS 1.0/TLS 1.1 disabled -- there is no normative "TLS 1.2+" floor
- Credentials passed via HTTP headers
- v1.0 removed the OAuth 2.0 **implicit** and **resource-owner-password** flows and added **device code** and **PKCE** -- v0.3-era habits will reach for a flow that no longer exists

### Architecture Layers
<!-- last-verified: 2026-08-05 -->

| Layer | Purpose | Details |
|-------|---------|---------|
| Data Model | Protocol Buffers schema | Task, Message, Part, Artifact, AgentCard, TaskStatus |
| Abstract Operations | 11 operations | SendMessage, SendStreamingMessage, GetTask, ListTasks, CancelTask, SubscribeToTask, CRUD PushNotificationConfig, GetExtendedAgentCard |
| Protocol Bindings | Transport | JSON-RPC 2.0, gRPC, HTTP+JSON/REST, plus custom bindings (v1.0+) |

For the complete operation list with parameters and the full data model schema, see [references/a2a-protocol.md](references/a2a-protocol.md).

## SDK Selection
<!-- last-verified: 2026-08-05 -->

| | Python (`a2a-sdk`) | TypeScript (`@a2a-js/sdk`) |
|---|---|---|
| **Install** | `pip install a2a-sdk` / `uv add a2a-sdk` | `npm install @a2a-js/sdk` |
| **Server framework** | Starlette **or** FastAPI (both optional extras -- base install pulls neither) | Express |
| **Transport** | JSON-RPC, HTTP+JSON/REST, gRPC | JSON-RPC, HTTP+JSON/REST, gRPC |
| **Task persistence** | `InMemoryTaskStore` (dev), `DatabaseTaskStore` (prod) | `InMemoryTaskStore` (dev) |
| **Core pattern** | `AgentExecutor.execute(context, event_queue)` | `AgentExecutor.execute(requestContext, eventBus)` |
| **Client** | `ClientFactory` + `ClientConfig` producing a `Client` | `ClientFactory` with auto-discovery |

Both SDKs now build clients through a `ClientFactory`; the old Python `A2AClient` class no
longer exists. On the Python side `starlette`, `sse-starlette`, and `fastapi` all live behind
the `all` extra, so a bare `pip install a2a-sdk` gives you neither server framework.

Both SDKs follow the same pattern: implement `AgentExecutor`, wire it to `DefaultRequestHandler`, mount on HTTP server.

Load the language-specific context for implementation details:

- Python: [contexts/a2a-python.md](contexts/a2a-python.md)
- TypeScript: [contexts/a2a-typescript.md](contexts/a2a-typescript.md)

## Minimal Server Pattern
<!-- last-verified: 2026-08-05 -->

**Python:**

```python
import uvicorn
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentInterface, AgentSkill
from starlette.applications import Starlette

# 1. Implement AgentExecutor (see contexts/a2a-python.md)
# 2. Describe the agent. v1.0 cards declare endpoints via supported_interfaces.
card = AgentCard(
    name="my-agent",
    description="...",
    version="1.0.0",
    default_input_modes=["text/plain"],
    default_output_modes=["text/plain"],
    capabilities=AgentCapabilities(streaming=True),
    supported_interfaces=[
        AgentInterface(
            protocol_binding="JSONRPC",
            url="http://localhost:8000",
            protocol_version="1.0",
        )
    ],
    skills=[AgentSkill(id="echo", name="Echo", description="...", tags=["example"])],
)

# 3. Wire the handler, build routes, mount them on any ASGI app
handler = DefaultRequestHandler(
    agent_executor=my_executor, task_store=InMemoryTaskStore(), agent_card=card
)
routes = [*create_agent_card_routes(card), *create_jsonrpc_routes(handler, "/")]

uvicorn.run(Starlette(routes=routes), host="0.0.0.0", port=8000)
```

**TypeScript:**

```typescript
import express from 'express';
import { AGENT_CARD_PATH } from '@a2a-js/sdk';
import { DefaultRequestHandler, InMemoryTaskStore } from '@a2a-js/sdk/server';
import { agentCardHandler, jsonRpcHandler, UserBuilder } from '@a2a-js/sdk/server/express';

// 1. Implement AgentExecutor (see contexts/a2a-typescript.md)
// 2. DefaultRequestHandler takes positional args: card, store, executor
const handler = new DefaultRequestHandler(agentCard, new InMemoryTaskStore(), myExecutor);

// 3. Both Express handlers take an options object, not a bare argument
const app = express();
app.use(`/${AGENT_CARD_PATH}`, agentCardHandler({ agentCardProvider: handler }));
app.use(jsonRpcHandler({ requestHandler: handler, userBuilder: UserBuilder.noAuthentication }));
app.listen(8000);
```

`userBuilder` is required — supply `UserBuilder.noAuthentication` for unauthenticated
development servers and a real builder in production.

## Framework Integrations
<!-- last-verified: 2026-08-05 -->

Verify before you build on a row here -- this table was materially wrong once, and vendor
blogs describe integrations that no first-party code backs. Each row below states the
artifact the claim rests on.

| Framework | Integration Level | Basis |
|-----------|------------------|-------|
| Google ADK | Native A2A server/client | First-party `google.adk.a2a` module in `google/adk-python` |
| CrewAI | First-party `crewai.a2a` module (wrapper, auth, types) | Source tree `lib/crewai/src/crewai/a2a/` |
| Semantic Kernel | A2A agent, .NET and Python | `dotnet/src/Agents/A2A/` + `agent_framework.a2a.A2AAgent` |
| AWS Bedrock AgentCore | Deployment target -- Runtime lists A2A among supported protocols | AWS AgentCore developer guide |
| Pydantic AI | **Moved out.** `agent.to_a2a()` was deprecated in v1 and **removed in v2** -- use the standalone [`fasta2a`](https://github.com/pydantic/fasta2a) package | `pydantic-ai-slim` 2.x contains no `to_a2a` and no a2a module |
| LangGraph | **No first-party A2A support found.** Its platform docs describe exposing agents over **MCP**, not A2A | LangGraph Platform docs; no `a2a` paths in `langchain-ai/langgraph` |
| AutoGen | **No first-party A2A support found.** | No `a2a` module in `microsoft/autogen`; A2A absent from its documentation |

The two negative rows were previously listed as "A2A endpoint via LangSmith" and "A2A
connector". Neither is supported by first-party code or documentation. Bridging either
framework to A2A today means writing the adapter yourself against `a2a-sdk`.

For integration patterns and code examples, see [references/a2a-framework-integrations.md](references/a2a-framework-integrations.md).

## Testing

- **Mokksy** -- mock A2A server for testing client code
- **A2A Inspector** -- protocol-level debugging (`github.com/a2aproject/a2a-inspector`)
- **In-process servers** -- start server in test, call with client for integration tests
- **Mock LLM calls** -- isolate protocol logic from model inference

## Production Considerations

- `InMemoryTaskStore` is development-only -- use PostgreSQL, MySQL, or SQLite stores for production
- Protocol is at v1.0.x -- pin SDK versions and read release notes before upgrading across minors
- Agent Card discovery beyond well-known URI is not yet standardized
- Production **MUST** use HTTPS/TLS; TLS 1.3+ is recommended and SSLv3/TLS 1.0/1.1 should be disabled

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
