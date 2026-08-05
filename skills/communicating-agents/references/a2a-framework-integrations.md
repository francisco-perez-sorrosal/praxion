# A2A Framework Integrations

Integration patterns for exposing framework-built agents via A2A. Load alongside the [Communicating Agents](../SKILL.md) skill.

## Integration Landscape

Verified 2026-08-05 against first-party source trees and vendor documentation. Rows marked
**unverified** were asserted by an earlier revision without a checkable basis -- treat them as
open questions, not as facts.

| Framework | Integration Type | Effort | Basis |
|-----------|-----------------|--------|-------|
| Google ADK | Native | Minimal | First-party `google.adk.a2a` module (`google/adk-python`) |
| CrewAI | First-party module | Low | `crewai.a2a` -- wrapper, auth, types, templates |
| Semantic Kernel | Agent type | Medium | `dotnet/src/Agents/A2A/` (.NET) and `agent_framework.a2a.A2AAgent` (Python) |
| AWS Bedrock AgentCore | Deployment target | Low | AgentCore Runtime lists A2A among supported protocols |
| Pydantic AI | **Moved out** | Low | `to_a2a()` removed in v2; use the standalone `fasta2a` package |
| LangGraph | **None found** | — | No `a2a` module; its platform docs expose agents over MCP, not A2A |
| AutoGen | **None found** | — | No `a2a` module in `microsoft/autogen`; A2A absent from its docs |
| LlamaIndex | *unverified* | — | Not checked against upstream |
| Google Cloud Run / Vertex AI | *unverified* | — | Not checked against upstream |

Bridging LangGraph or AutoGen to A2A today means writing the adapter yourself against
`a2a-sdk` -- wrap the framework's entrypoint in an `AgentExecutor` and serve it with the
routes shown in [contexts/a2a-python.md](../contexts/a2a-python.md).

## Google ADK (Agent Development Kit)

Native A2A support -- ADK agents can act as both A2A servers and clients.

### Exposing an ADK Agent via A2A

```python
from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.a2a import A2AServer

agent = Agent(
    name="my-adk-agent",
    model="gemini-2.0-flash",
    instruction="You are a helpful assistant.",
)

# Wrap ADK agent as A2A server
runner = Runner(agent=agent, app_name="my-app", session_service=...)
server = A2AServer(runner=runner)
server.start(port=8000)
```

### Calling an A2A Agent from ADK

```python
from google.adk.tools.a2a_tool import A2ATool

# Register remote A2A agent as a tool
remote_tool = A2ATool(
    agent_card_url="https://remote-agent.example.com/.well-known/agent-card.json"
)

orchestrator = Agent(
    name="orchestrator",
    model="gemini-2.0-flash",
    tools=[remote_tool],
)
```

### Sample Agents

The `a2a-samples` repo includes several ADK examples:
- **Expense Reimbursement** -- multi-step approval workflow
- **Purchasing Concierge** -- ADK client orchestrating multiple A2A agents

## LangGraph

**No first-party A2A integration exists.** An earlier revision of this file claimed LangGraph
agents "deployed via LangSmith get A2A endpoints automatically" -- that is not supported by
any upstream source. `langchain-ai/langgraph` contains no `a2a` module, and the LangGraph
Platform documentation describes exposing agents as **MCP** tools over Streamable HTTP, never
A2A. LangSmith is the observability and deployment product, not an A2A gateway.

### Exposing a LangGraph agent anyway

Write the adapter yourself: implement an `AgentExecutor` whose `execute()` invokes your
compiled graph, then serve it with `create_jsonrpc_routes`. The graph's streaming events map
onto `TaskUpdater.update_status(...)` calls.

The `a2a-samples` repo does ship LangGraph-based sample agents (e.g. a currency agent), which
demonstrate exactly this hand-written pattern -- they are samples built *on* `a2a-sdk`, not
evidence of framework-native support.

## CrewAI

A2A adapter wraps CrewAI crews as A2A-compatible agents.

### Exposing a Crew via A2A

```python
from crewai import Agent, Crew, Task
# CrewAI provides an A2A adapter that wraps the crew
# See a2a-samples/crewai for the full pattern

crew = Crew(
    agents=[...],
    tasks=[...],
)

# Wrap with A2A adapter (exact API depends on CrewAI version)
# The adapter handles:
# - Agent Card from crew metadata
# - Task mapping (A2A Task <-> CrewAI Task)
# - Message routing to appropriate crew agents
```

### Sample

- **Burger Agent** -- CrewAI crew wrapped as A2A agent in `a2a-samples`

## Pydantic AI

A2A support was **spun out of Pydantic AI** into the standalone
[`fasta2a`](https://github.com/pydantic/fasta2a) package. `Agent.to_a2a()` still works in
Pydantic AI 1.x but emits a deprecation warning, and it is **removed in v2** -- which has
shipped, so on a current install the method does not exist.

```bash
pip install 'fasta2a[pydantic-ai]'   # or: uv add 'fasta2a[pydantic-ai]'
```

```python
from pydantic_ai import Agent
from fasta2a.pydantic_ai import agent_to_a2a

agent = Agent("openai:gpt-5.5")
app = agent_to_a2a(agent)

# Run with uvicorn
import uvicorn
uvicorn.run(app, host="0.0.0.0", port=8000)
```

`agent_to_a2a()` keeps the previous conveniences -- Agent Card generated from agent metadata,
Pydantic AI tools mapped to A2A skills, task lifecycle and streaming handled.

**Migrating:** replace `agent.to_a2a()` with `agent_to_a2a(agent)` and add the `fasta2a`
dependency. There is no compatibility shim in Pydantic AI v2.

## Semantic Kernel

A2A arrives as an **agent type**, not a plugin. There is no `A2APlugin` class -- the .NET
tree ships `A2AAgent`, `A2AHostAgent`, `A2AAgentThread`, and `A2AAgentExtensions` under
`dotnet/src/Agents/A2A/`, and Python exposes `agent_framework.a2a.A2AAgent`.

The two directions:

- **Consume** a remote A2A agent -- construct an `A2AAgent` from a URL, `AgentCard`, or an
  existing A2A client; it converts framework `ChatMessage`s to A2A messages and back.
- **Expose** a Semantic Kernel agent over A2A -- use `A2AHostAgent`.

Check the current constructor overloads against
[`dotnet/src/Agents/A2A/`](https://github.com/microsoft/semantic-kernel/tree/main/dotnet/src/Agents/A2A)
or the Python `agent_framework` API reference before writing against them -- the surface is
moving as Semantic Kernel folds into Microsoft Agent Framework.

## AutoGen

**No first-party A2A integration exists.** An earlier revision claimed an "A2A connector".
`microsoft/autogen` contains no `a2a` module, and A2A is absent from AutoGen's documentation.

Note the distinction from Semantic Kernel above: Microsoft ships A2A support in **Semantic
Kernel / Microsoft Agent Framework**, not in AutoGen. If you need A2A from an AutoGen agent,
either bridge through Agent Framework or write an `AgentExecutor` adapter directly.

## LlamaIndex

*Unverified.* An earlier revision asserted "A2A integration for LlamaIndex agents" with no
checkable basis. Not investigated in the 2026-08-05 pass -- verify against upstream before
relying on it.

## AWS Bedrock AgentCore

Deploy agents as A2A-compatible services on AWS infrastructure.

- Native deployment target for A2A agents
- Handles scaling, security, and networking
- Integrates with AWS IAM for authentication

## Community Alternatives

### FastA2A (Pydantic team)

No longer a "community alternative" -- `fasta2a` is where Pydantic AI's own A2A support now
lives (see [Pydantic AI](#pydantic-ai) above). The distribution and import name is
`fasta2a`, not `fast_a2a`.

```python
from fasta2a import FastA2A

app = FastA2A(
    name="my-agent",
    description="A fast A2A agent",
)

@app.skill("process")
async def process(message: str) -> str:
    return f"Processed: {message}"
```

### python-a2a

Community A2A implementation with a simplified API.

```python
from python_a2a import A2AServer

server = A2AServer(name="my-agent")

@server.handler
async def handle(message):
    return f"Response to: {message.text}"
```

## Integration Patterns

### Framework Agent as A2A Server

The most common pattern: wrap an existing framework agent to accept A2A requests.

```
External A2A Client --> A2A Adapter --> Framework Agent --> LLM/Tools
```

**Adapter responsibilities:**
1. Parse A2A `SendMessage` into framework-native input
2. Map framework output to A2A `Message`/`Artifact`
3. Manage task lifecycle (state transitions, history)
4. Serve Agent Card for discovery

### A2A Agent as Framework Tool

Register remote A2A agents as tools within your framework:

```
Framework Orchestrator --> A2A Client --> Remote A2A Agent
```

**Pattern:** Create a tool/function that wraps `A2AClient.send_message()`, letting the orchestrator delegate to remote agents transparently.

### Multi-Framework Orchestration

Combine agents from different frameworks via A2A:

```
ADK Orchestrator (A2A Client)
  |-> LangGraph Agent (A2A Server)
  |-> CrewAI Crew (A2A Server)
  |-> Custom Agent (A2A Server)
```

Each agent exposes its Agent Card. The orchestrator discovers capabilities and routes tasks based on skill matching.

## Resources

- [A2A Samples](https://github.com/a2aproject/a2a-samples) -- reference implementations for all major frameworks
- [Google ADK docs](https://google.github.io/adk-docs/)
- [FastA2A](https://github.com/pydantic/FastA2A)
