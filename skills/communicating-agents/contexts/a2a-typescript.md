# A2A Protocol -- TypeScript SDK

TypeScript-specific implementation guide. Load alongside the generic [Communicating Agents](../SKILL.md) skill.

## Setup

```bash
npm install @a2a-js/sdk
# Express for HTTP server
npm install express @types/express
# Optional: gRPC support
npm install @grpc/grpc-js @bufbuild/protobuf
```

Requires Node 20+ (`engines.node: ">=20"`).

## Module Exports

| Import Path | Contents |
|-------------|----------|
| `@a2a-js/sdk` | Types and interfaces |
| `@a2a-js/sdk/server` | Server utilities |
| `@a2a-js/sdk/server/express` | Express middleware |
| `@a2a-js/sdk/server/grpc` | gRPC service |
| `@a2a-js/sdk/client` | Client classes |
| `@a2a-js/sdk/client/grpc` | gRPC client transport |

## Core Classes

| Class | Module | Purpose |
|-------|--------|---------|
| `AgentExecutor` | `@a2a-js/sdk/server` | Interface -- implement `execute()` and `cancelTask()` |
| `DefaultRequestHandler` | `@a2a-js/sdk/server` | Routes requests to executor. **Positional** args: `(agentCard, taskStore, agentExecutor)` |
| `InMemoryTaskStore` | `@a2a-js/sdk/server` | Dev-only task persistence |
| `ExecutionEventBus` | `@a2a-js/sdk/server` | Publish messages, artifacts, status updates |
| `AgentEvent` | `@a2a-js/sdk/server` | Factory for bus events -- `AgentEvent.task()`, `.statusUpdate()` |
| `ClientFactory` | `@a2a-js/sdk/client` | Instantiate, then `createFromUrl()` / `createFromAgentCard()` |
| `UserBuilder` | `@a2a-js/sdk/server/express` | Builds the caller identity; `noAuthentication` for dev |
| `GrpcTransportFactory` | `@a2a-js/sdk/client/grpc` | Explicit gRPC transport |

**Express middleware functions** -- all take an **options object**, not a bare argument:

| Function | Purpose |
|----------|---------|
| `agentCardHandler({ agentCardProvider })` | `GET /.well-known/agent-card.json` |
| `jsonRpcHandler({ requestHandler, userBuilder })` | JSON-RPC endpoint; `userBuilder` is required |
| `restHandler({ ... })` | REST-style endpoints |
| `grpcService(handler)` | gRPC service definition |

Import `AGENT_CARD_PATH` from `@a2a-js/sdk` rather than hardcoding the well-known path.

## Server Implementation

### Step 1: Implement AgentExecutor

Three v1.0 shapes to note before reading the code: the `kind` discriminator is **gone** (use
the `AgentEvent` factories), a `Part` carries a ts-proto `content` oneof rather than a bare
`{ text }`, and `cancelTask` receives a **taskId**, not a `RequestContext`.

```typescript
import { v4 as uuidv4 } from 'uuid';
import {
  AgentEvent,
  AgentExecutor,
  ExecutionEventBus,
  RequestContext,
} from '@a2a-js/sdk/server';
import { Role, TaskState } from '@a2a-js/sdk';

class MyAgentExecutor implements AgentExecutor {
  private readonly cancelledTasks = new Set<string>();

  async execute(
    requestContext: RequestContext,
    eventBus: ExecutionEventBus
  ): Promise<void> {
    // v1.0 names it userMessage; taskId and contextId come off the context
    const { userMessage, taskId, contextId } = requestContext;

    const userText = userMessage.parts
      .filter((p) => p.content?.$case === 'text')
      .map((p) => p.content.value)
      .join('');

    const result = await this.process(userText);

    // Publish a status update carrying the reply
    eventBus.publish(
      AgentEvent.statusUpdate({
        taskId,
        contextId,
        status: {
          state: TaskState.TASK_STATE_COMPLETED,
          message: {
            role: Role.ROLE_AGENT,
            messageId: uuidv4(),
            parts: [
              {
                content: { $case: 'text', value: result },
                metadata: undefined,
                filename: '',
                mediaType: 'text/plain',
              },
            ],
            taskId,
            contextId,
            extensions: [],
            metadata: {},
            referenceTaskIds: [],
          },
          timestamp: new Date().toISOString(),
        },
        metadata: {},
      })
    );
  }

  // Signature is (taskId, eventBus) -- record the id and check it at yield points
  cancelTask = async (taskId: string, _eventBus: ExecutionEventBus): Promise<void> => {
    this.cancelledTasks.add(taskId);
  };

  private async process(text: string): Promise<string> {
    return `Processed: ${text}`;
  }
}
```

Every streaming turn must open with a `Task` or `Message` event -- publish
`AgentEvent.task(taskSnapshot)` first when starting a new task.

### Step 2: Define the Agent Card

```typescript
import { A2A_PROTOCOL_VERSION, AgentCard } from '@a2a-js/sdk';

const agentCard: AgentCard = {
  name: 'my-agent',
  description: 'An agent that processes text requests',
  version: '1.0.0',
  // v1.0 replaced the single `url` field with an ordered interface list
  supportedInterfaces: [
    {
      url: 'http://localhost:9000/',
      protocolBinding: 'JSONRPC',
      tenant: '',
      protocolVersion: A2A_PROTOCOL_VERSION,
    },
  ],
  defaultInputModes: ['text/plain'],
  defaultOutputModes: ['text/plain'],
  skills: [
    {
      id: 'text-processing',
      name: 'Text Processing',
      description: 'Processes text input and returns results',
      tags: ['text'],
      inputModes: ['text/plain'],
      outputModes: ['text/plain'],
      securityRequirements: [],
    },
  ],
  capabilities: {
    streaming: true,
    pushNotifications: false,
    extensions: [],
    extendedAgentCard: false,
  },
  securitySchemes: {},
  securityRequirements: [],
};
```

### Step 3: Create and Run the Server

```typescript
import express from 'express';
import { AGENT_CARD_PATH } from '@a2a-js/sdk';
import {
  DefaultRequestHandler,
  InMemoryTaskStore,
} from '@a2a-js/sdk/server';
import {
  agentCardHandler,
  jsonRpcHandler,
  UserBuilder,
} from '@a2a-js/sdk/server/express';

const executor = new MyAgentExecutor();

// Positional args -- card, store, executor. Not an options object.
const handler = new DefaultRequestHandler(agentCard, new InMemoryTaskStore(), executor);

const app = express();

// The handler doubles as the AgentCardProvider
app.use(`/${AGENT_CARD_PATH}`, agentCardHandler({ agentCardProvider: handler }));
app.use(jsonRpcHandler({ requestHandler: handler, userBuilder: UserBuilder.noAuthentication }));

app.listen(9000, () => {
  console.log('A2A server running on port 9000');
});
```

Swap `UserBuilder.noAuthentication` for a real builder in production -- it is the seam where
the caller's identity enters the request pipeline.

## Client Usage

### Discover and Call an Agent

`ClientFactory` is a class you instantiate -- there is no static `create()`. It exposes
`createFromUrl(baseUrl, path?)` and `createFromAgentCard(card)`, both returning a `Client`.

```typescript
import { ClientFactory } from '@a2a-js/sdk/client';
import { Role } from '@a2a-js/sdk';

async function callAgent() {
  const factory = new ClientFactory();

  // Resolves the agent card and negotiates a transport
  const client = await factory.createFromUrl('http://localhost:9000');

  const response = await client.sendMessage({
    message: {
      role: Role.ROLE_USER,
      parts: [{ content: { $case: 'text', value: 'Hello, agent!' } }],
    },
  });
  console.log(response);
}
```

### Poll for Task Completion

`TaskState` members carry the protobuf `TASK_STATE_` prefix in TypeScript too.

```typescript
import { Client } from '@a2a-js/sdk/client';
import { TaskState } from '@a2a-js/sdk';

async function pollTask(client: Client, taskId: string) {
  const terminalStates = new Set([
    TaskState.TASK_STATE_COMPLETED,
    TaskState.TASK_STATE_FAILED,
    TaskState.TASK_STATE_CANCELED,
    TaskState.TASK_STATE_REJECTED,
  ]);

  while (true) {
    const task = await client.getTask({ id: taskId });
    if (terminalStates.has(task.status.state)) {
      return task;
    }
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
}
```

## Streaming (SSE)

### Server-Side Streaming

Publish events incrementally via the `ExecutionEventBus`. The framework handles SSE transport when the client uses `SendStreamingMessage`.

```typescript
class StreamingExecutor implements AgentExecutor {
  private readonly cancelledTasks = new Set<string>();

  async execute(
    requestContext: RequestContext,
    eventBus: ExecutionEventBus
  ): Promise<void> {
    const { userMessage, taskId, contextId } = requestContext;

    for await (const chunk of this.processStreaming(userMessage)) {
      // Check the cancellation flag at every yield point
      if (this.cancelledTasks.has(taskId)) return;

      eventBus.publish(
        AgentEvent.statusUpdate({
          taskId,
          contextId,
          status: {
            state: TaskState.TASK_STATE_WORKING,
            message: {
              role: Role.ROLE_AGENT,
              messageId: uuidv4(),
              parts: [{ content: { $case: 'text', value: chunk } }],
              taskId,
              contextId,
              extensions: [],
              metadata: {},
              referenceTaskIds: [],
            },
            timestamp: new Date().toISOString(),
          },
          metadata: {},
        })
      );
    }
  }

  cancelTask = async (taskId: string, _eventBus: ExecutionEventBus): Promise<void> => {
    this.cancelledTasks.add(taskId);
  };

  private async *processStreaming(message: Message) {
    // Your streaming logic here
    yield 'Processing...';
    yield 'Done.';
  }
}
```

Cancellation is cooperative: `cancelTask` only records the id, and `execute` must check it.
Without that check a client `cancelTask` call blocks in `DefaultRequestHandler` until a
terminal event is published.

### Client-Side Streaming

```typescript
import { Client } from '@a2a-js/sdk/client';

async function streamFromAgent(client: Client) {
  const stream = client.sendStreamingMessage({
    message: {
      role: Role.ROLE_USER,
      parts: [{ content: { $case: 'text', value: 'Generate a report' } }],
    },
  });

  for await (const event of stream) {
    console.log(event);
  }
}
```

## Task and Artifact Handling

### Structured Data

A `Part`'s `content` oneof selects one of `text`, `raw`, `url`, or `data`:

```typescript
const dataPart = {
  content: { $case: 'data', value: { result: 42, confidence: 0.95 } },
};
```

### Artifacts

Publish tangible deliverables through `AgentEvent.artifactUpdate(...)`. The bus exposes four
factories -- `message`, `task`, `statusUpdate`, `artifactUpdate` -- and each wraps its payload
as `{ kind, data }`. Hand-building that envelope is what breaks: the payload field is `data`,
not a per-kind name like `artifact`.

```typescript
eventBus.publish(
  AgentEvent.artifactUpdate({
    taskId,
    contextId,
    artifact: {
      artifactId: uuidv4(),
      name: 'report.md',
      parts: [{ content: { $case: 'text', value: '# Generated Report\n\n...' } }],
    },
    metadata: {},
  })
);
```

## gRPC Transport

### Server

```typescript
import { grpcService } from '@a2a-js/sdk/server/grpc';

const service = grpcService(handler);
// Mount on a gRPC server
```

### Client

```typescript
import { GrpcTransportFactory } from '@a2a-js/sdk/client/grpc';

const factory = new ClientFactory({ transports: [new GrpcTransportFactory()] });
const client = await factory.createFromUrl('http://localhost:9000');
```

## REST Endpoints

Mount REST-style endpoints alongside JSON-RPC:

```typescript
import { restHandler } from '@a2a-js/sdk/server/express';

app.use('/api', restHandler(handler));
// Exposes: GET /api/tasks/:id, POST /api/messages, etc.
```

## Resources

- [JS/TS SDK repo](https://github.com/a2aproject/a2a-js)
- [Sample agents](https://github.com/a2aproject/a2a-samples)
