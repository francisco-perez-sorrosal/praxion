# A2A Protocol -- Python SDK

Python-specific implementation guide. Load alongside the generic [Communicating Agents](../SKILL.md) skill.

## Setup

```bash
pip install a2a-sdk
# or
uv add a2a-sdk
```

Requires Python 3.10+.

**Extras** (install as needed):

| Extra | Purpose |
|-------|---------|
| `a2a-sdk[http-server]` | Starlette + `sse-starlette` |
| `a2a-sdk[fastapi]` | FastAPI (pulls `http-server` too) |
| `a2a-sdk[grpc]` | gRPC transport support |
| `a2a-sdk[telemetry]` | OpenTelemetry integration |
| `a2a-sdk[encryption]` | Payload encryption |
| `a2a-sdk[signing]` | Agent-card signing (PyJWT) |
| `a2a-sdk[postgresql]` | PostgreSQL task persistence |
| `a2a-sdk[mysql]` | MySQL task persistence |
| `a2a-sdk[sqlite]` | SQLite task persistence |
| `a2a-sdk[sql]` | All three SQL backends |
| `a2a-sdk[db-cli]` | Alembic migrations CLI |
| `a2a-sdk[all]` | Everything |

**A bare `pip install a2a-sdk` gives you no server framework.** Starlette and FastAPI are
both optional -- install `a2a-sdk[http-server]` or `a2a-sdk[fastapi]` before running any
server example here.

## Core Classes

| Class | Module | Purpose |
|-------|--------|---------|
| `AgentExecutor` | `a2a.server.agent_execution` | Abstract base -- implement `execute()` and `cancel()` |
| `DefaultRequestHandler` | `a2a.server.request_handlers` (**plural**) | Routes requests to executor; takes `agent_executor`, `task_store`, `agent_card` |
| `InMemoryTaskStore` | `a2a.server.tasks` | Dev-only task persistence |
| `DatabaseTaskStore` | `a2a.server.tasks` | Production task persistence (SQLAlchemy-backed) |
| `create_agent_card_routes`, `create_jsonrpc_routes`, `create_rest_routes` | `a2a.server.routes` | Build routes to mount on any ASGI app |
| `add_a2a_routes_to_fastapi` | `a2a.server.routes` | FastAPI convenience mount |
| `RequestContext` | `a2a.server.agent_execution` | Request metadata (task ID, context ID, message) |
| `EventQueue` | `a2a.server.events` | Async event publishing for streaming |
| `TaskUpdater` | `a2a.server.tasks` | Publishes status updates and artifacts for a task |
| `create_client`, `ClientConfig`, `ClientFactory` | `a2a.client` | Build a client for calling remote A2A agents |
| `A2ACardResolver` | `a2a.client` | Fetches an `AgentCard` from a base URL |

**Removed in v1.0 -- do not use:** `a2a.server.request_handler` (singular),
`a2a.server.apps`, `A2AStarletteApplication`, and the `A2AClient` class. Servers are now
assembled from `a2a.server.routes` and mounted on your own Starlette/FastAPI app; clients are
built via `create_client()` / `ClientFactory`.

## Server Implementation

### Step 1: Implement AgentExecutor

In v1.0 `Part` is a generated protobuf message, not a Pydantic discriminated union --
build and read parts through the `a2a.helpers` functions rather than constructing
`Part(root=TextPart(...))`, which no longer works.

```python
from a2a.helpers import get_message_text, new_text_message
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue

class MyAgentExecutor(AgentExecutor):
    async def execute(
        self, context: RequestContext, event_queue: EventQueue
    ) -> None:
        """Process incoming request and publish results."""
        # Extract user text -- the helper joins every text Part
        user_text = get_message_text(context.message)

        # Process the request (integrate with your LLM/logic here)
        result = await self._process(user_text)

        # Publish response as a message (defaults to Role.ROLE_AGENT)
        await event_queue.enqueue_event(new_text_message(result))

    async def cancel(
        self, context: RequestContext, event_queue: EventQueue
    ) -> None:
        """Handle task cancellation."""
        raise NotImplementedError("Cancel is not supported.")

    async def _process(self, text: str) -> str:
        # Your agent logic here
        return f"Processed: {text}"
```

For richer progress reporting, wrap the queue in a `TaskUpdater` (`a2a.server.tasks`) and
call `update_status(state=..., message=...)` / `add_artifact(parts=[...])` instead of
enqueuing raw events.

### Step 2: Define the Agent Card

```python
from a2a.types import AgentCapabilities, AgentCard, AgentInterface, AgentSkill

agent_card = AgentCard(
    name="my-agent",
    description="An agent that processes text requests",
    version="1.0.0",
    default_input_modes=["text/plain"],
    default_output_modes=["text/plain"],
    # v1.0 replaced the single `url=` field with an ordered interface list
    supported_interfaces=[
        AgentInterface(
            protocol_binding="JSONRPC",
            url="http://localhost:9000",
            protocol_version="1.0",
        )
    ],
    skills=[
        AgentSkill(
            id="text-processing",
            name="Text Processing",
            description="Processes text input and returns results",
            input_modes=["text/plain"],
            output_modes=["text/plain"],
            tags=["text"],
        )
    ],
    capabilities=AgentCapabilities(streaming=True),
)
```

Note the field rename: a v0.3 card carried a single `url=`; a v1.0 card declares one or more
`AgentInterface` entries in `supported_interfaces`, each naming its protocol binding.

### Step 3: Create and Run the Server

v1.0 removed the all-in-one application class. You now build routes and mount them on an
ASGI app you own -- which is what makes FastAPI a first-class option alongside Starlette.

```python
import uvicorn
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes
from a2a.server.tasks import InMemoryTaskStore
from starlette.applications import Starlette

executor = MyAgentExecutor()
handler = DefaultRequestHandler(
    agent_executor=executor,
    task_store=InMemoryTaskStore(),
    agent_card=agent_card,       # required -- not optional
)

routes = [
    *create_agent_card_routes(agent_card),
    *create_jsonrpc_routes(handler, "/"),
]

uvicorn.run(Starlette(routes=routes), host="0.0.0.0", port=9000)
```

Those routes expose:
- `GET /.well-known/agent-card.json` -- agent discovery
- `POST /` -- JSON-RPC endpoint for all operations

Swap `create_jsonrpc_routes` for `create_rest_routes` to serve the HTTP+JSON/REST binding, or
use `add_a2a_routes_to_fastapi(app, handler, agent_card)` to mount onto an existing FastAPI
application. Install a server framework explicitly -- `pip install a2a-sdk` alone pulls
neither Starlette nor FastAPI.

## Client Usage

### Discover and Call an Agent

The `A2AClient` class was removed in v1.0. Resolve the card first, then build a client with
`create_client()` (or `ClientFactory` when you need custom transports or interceptors).

```python
import httpx
from a2a.client import A2ACardResolver, ClientConfig, create_client
from a2a.helpers import new_text_message
from a2a.types import Role, SendMessageRequest

async def call_agent():
    # 1. Resolve the agent card from its base URL
    async with httpx.AsyncClient() as httpx_client:
        resolver = A2ACardResolver(
            httpx_client=httpx_client,
            base_url="http://localhost:9000",
        )
        card = await resolver.get_agent_card()
    print(f"Connected to: {card.name}")

    # 2. Build a client. streaming=False still yields an async iterator.
    client = await create_client(agent=card, client_config=ClientConfig(streaming=False))

    # 3. Send a message
    request = SendMessageRequest(
        message=new_text_message("Hello, agent!", role=Role.ROLE_USER)
    )
    async for chunk in client.send_message(request):
        print(chunk)

    await client.close()
```

`send_message` returns an async iterator in **both** modes -- `ClientConfig(streaming=...)`
selects the transport, not a different method. Always `await client.close()`.

### Poll for Task Completion

`TaskState` is a protobuf enum, so members carry the `TASK_STATE_` prefix.

```python
import asyncio
from a2a.types import GetTaskRequest, TaskState

TERMINAL = {
    TaskState.TASK_STATE_COMPLETED,
    TaskState.TASK_STATE_FAILED,
    TaskState.TASK_STATE_CANCELED,
    TaskState.TASK_STATE_REJECTED,
}

async def poll_task(client, task_id: str):
    while True:
        task = await client.get_task(GetTaskRequest(id=task_id))
        if task.status.state in TERMINAL:
            return task
        await asyncio.sleep(1)
```

## Streaming (SSE)

### Server-Side Streaming

The executor publishes events incrementally via the `EventQueue`. The framework handles SSE transport automatically when the client uses `SendStreamingMessage`.

```python
from a2a.helpers import new_text_message

class StreamingExecutor(AgentExecutor):
    async def execute(
        self, context: RequestContext, event_queue: EventQueue
    ) -> None:
        # Stream partial results
        for chunk in await self._process_streaming(context.message):
            await event_queue.enqueue_event(new_text_message(chunk))
```

### Client-Side Streaming

Streaming is selected by config, not by a separate method:

```python
from a2a.client import ClientConfig, create_client
from a2a.helpers import new_text_message
from a2a.types import Role, SendMessageRequest

async def stream_from_agent(card):
    client = await create_client(agent=card, client_config=ClientConfig(streaming=True))
    request = SendMessageRequest(
        message=new_text_message("Generate a report", role=Role.ROLE_USER)
    )
    async for event in client.send_message(request):
        print(event)
    await client.close()
```

## Push Notifications

For long-running tasks where the client cannot maintain a persistent connection.

### Server Setup

There is no `a2a.server.push_notifier` module. Push-notification machinery lives in
`a2a.server.tasks`, and the handler takes a **config store** plus a **sender** as two
separate arguments.

```python
from a2a.server.tasks import (
    BasePushNotificationSender,
    InMemoryPushNotificationConfigStore,
    InMemoryTaskStore,
)

config_store = InMemoryPushNotificationConfigStore()

handler = DefaultRequestHandler(
    agent_executor=executor,
    task_store=InMemoryTaskStore(),
    agent_card=agent_card,
    push_config_store=config_store,
    push_sender=BasePushNotificationSender(config_store),
)
```

Use `DatabasePushNotificationConfigStore` in production; it ships behind the same
`a2a-sdk[sql]` extra as `DatabaseTaskStore`.

### Client Registration

The v1.0 push-notification RPCs are pluralized (`CreateTaskPushNotificationConfig`,
`ListTaskPushNotificationConfigs`, …). Register a callback URL through the client's
push-notification-config methods rather than a single setter.

## Task Lifecycle

Tasks transition through states managed by the framework:

```
submitted -> working -> completed
                    \-> failed
                    \-> canceled
                    \-> rejected
                    \-> input_required (awaiting user input)
                    \-> auth_required (awaiting auth)
```

The initial state is `submitted` -- there is no `created` state. Enum members carry the
protobuf prefix: `TaskState.TASK_STATE_SUBMITTED`, `TaskState.TASK_STATE_WORKING`, and so on.
`rejected` is terminal and may be entered directly at task creation.

The `DefaultRequestHandler` manages state transitions automatically. The executor signals completion by:
- Publishing a final `Message` -- task completes
- Raising an exception -- task fails
- Responding to `cancel()` -- task cancels

## Structured Data

A `Part` carries exactly one of `text`, `raw` (bytes), `url`, or `data` (structured JSON).
Build each with its helper:

```python
from a2a.helpers import new_data_message

await event_queue.enqueue_event(
    new_data_message({"result": 42, "confidence": 0.95})
)
```

`new_text_part`, `new_data_part`, `new_raw_part`, and `new_url_part` build individual parts
when you need to mix several in one message via `new_message(parts=[...])`.

## Artifacts

Publish tangible deliverables as artifacts:

```python
from a2a.helpers import new_text_artifact

await event_queue.enqueue_event(
    new_text_artifact(name="report.md", text="# Generated Report\n\n...")
)
```

Inside an executor holding a `TaskUpdater`, prefer `await updater.add_artifact(parts=[...])`
so the artifact is attached to the task rather than emitted as a bare event.

## Testing with Mokksy

Mokksy provides mock A2A servers for testing client code:

```python
import httpx
import pytest
from a2a.client import A2ACardResolver, ClientConfig, create_client

@pytest.fixture
async def mock_server():
    # Start a Mokksy mock server with predefined responses
    # See https://github.com/a2aproject/a2a-python for Mokksy docs
    ...

async def test_client_integration(mock_server):
    async with httpx.AsyncClient() as httpx_client:
        resolver = A2ACardResolver(httpx_client=httpx_client, base_url=mock_server.url)
        card = await resolver.get_agent_card()
    assert card.name == "mock-agent"

    client = await create_client(agent=card, client_config=ClientConfig(streaming=False))
    await client.close()
```

The official samples take a simpler route worth copying: start the real server as a
subprocess in a session-scoped fixture and drive it with a real client -- see
[`test_client.py`](https://github.com/a2aproject/a2a-samples/blob/main/samples/python/agents/helloworld/test_client.py)
in the helloworld sample.

## Production Persistence

Replace `InMemoryTaskStore` with a SQL-backed store:

There is one SQLAlchemy-backed store, `DatabaseTaskStore` -- not per-engine classes. The
engine is chosen by the connection URL and the matching extra (`a2a-sdk[postgresql]`,
`[mysql]`, `[sqlite]`, or `[sql]` for all three).

```python
from a2a.server.tasks import DatabaseTaskStore

task_store = DatabaseTaskStore(connection_string="postgresql+asyncpg://...")
handler = DefaultRequestHandler(
    agent_executor=executor,
    task_store=task_store,
    agent_card=agent_card,
)
```

Importing `DatabaseTaskStore` without the SQL extras installed logs a load failure rather
than raising at import time -- if it is unexpectedly absent, check the extra first.

## Resources

- [Python SDK repo](https://github.com/a2aproject/a2a-python)
- [Python API docs](https://a2a-protocol.org/latest/sdk/python/api/)
- [Sample agents](https://github.com/a2aproject/a2a-samples)
