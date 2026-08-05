# TypeScript MCP Development

TypeScript-specific implementation guide for MCP servers. Load alongside
the generic [MCP Server Development](../SKILL.md) skill. Back to [SKILL.md](../SKILL.md).

**Related skills:**
- [TypeScript Development](../../typescript-development/SKILL.md) -- tsconfig, toolchain, testing patterns
- [Node.js Project Management](../../node-prj-mgmt/SKILL.md) -- pnpm setup, volta, dependency management

## Table of Contents

- [SDK Landscape (TypeScript)](#sdk-landscape-typescript)
- [Quickstart](#quickstart)
- [Core Primitives -- TypeScript Implementation](#core-primitives----typescript-implementation)
  - [Tools](#tools)
  - [Resources](#resources)
  - [Prompts](#prompts)
- [Transports -- TypeScript Configuration](#transports----typescript-configuration)
  - [Stdio Transport](#stdio-transport)
  - [Streamable HTTP Transport](#streamable-http-transport)
- [Server Lifecycle](#server-lifecycle)
- [Logging Setup](#logging-setup)
- [Testing](#testing)
  - [Vitest Unit Tests](#vitest-unit-tests)
  - [MCP Inspector](#mcp-inspector)
- [Client Integration -- TypeScript Examples](#client-integration----typescript-examples)
- [Project Structure](#project-structure)
- [Zod Version Note](#zod-version-note)
- [SDK v2 Migration Note](#sdk-v2-migration-note)
- [Common Pitfalls -- TypeScript-Specific](#common-pitfalls----typescript-specific)
- [Further Reading](#further-reading)

## SDK Landscape (TypeScript)
<!-- last-verified: 2026-08-05 -->

Two options for building MCP servers in TypeScript:

| Option | Package | When to Use |
|--------|---------|-------------|
| **Official SDK v2** | `@modelcontextprotocol/server` + `/client` | Default for new servers — current stable line |
| **Official SDK v1** | `@modelcontextprotocol/sdk` | Legacy monolithic package; still supported |
| **FastMCP (TS port)** | `fastmcp` | Community port; decorator-style API; simpler for small servers |

**v2 went stable on 2026-07-27 under new package names.** There is no 2.x release under the
`@modelcontextprotocol/sdk` name at all — the v2 line split into per-role packages, so
"upgrade to v2" means changing package names, not bumping a range.

**Version pinning** (production):
```json
{
  "dependencies": {
    "@modelcontextprotocol/server": "^2",
    "zod": "^4"
  }
}
```

```json
{
  "dependencies": {
    "@modelcontextprotocol/sdk": "^1",
    "zod": "^3.25 || ^4"
  }
}
```

The v1 SDK accepts `zod@^3.25 || ^4.0` — pinning `"zod": "^3"` is over-restrictive and
needlessly forces the v3/v4 split described in [Zod Version Note](#zod-version-note).

The SDK requires **Node 18+**. Target **Node 22 LTS** for new projects (see [node-prj-mgmt](../../node-prj-mgmt/SKILL.md)).

### SDK Version Details

| SDK | Version | Status |
|-----|---------|--------|
| `@modelcontextprotocol/server`, `/client` | v2.x | **Current stable** (2.0.0, 2026-07-27) |
| `@modelcontextprotocol/node`, `/express`, `/hono`, `/fastify` | v2.x | Optional transport + framework adapters (2.0.0) |
| `@modelcontextprotocol/sdk` | v1.x | **Legacy, still supported** (latest 1.30.0). Bug fixes and security updates for **at least 6 months after v2's release** (i.e. through ~2027-01) |
| `fastmcp` | v4.x | Stable community alternative (latest 4.12.x) |

Full v1.x guidance and the v1→v2 migration path live in
[references/v1-legacy.md](../references/v1-legacy.md), loaded on demand.

---

## Quickstart

> **API line: v1.x** (`@modelcontextprotocol/sdk`). Every example from here down targets the
> v1 API, which remains supported for at least 6 months past v2's 2026-07-27 release — see
> [SDK Landscape (TypeScript)](#sdk-landscape-typescript) and
> [references/v1-legacy.md](../references/v1-legacy.md). On v2 the imports move to
> `@modelcontextprotocol/server` and lose the `.js` suffix; see
> [SDK v2 Migration Note](#sdk-v2-migration-note) for a v2 quickstart.

```bash
mkdir mcp-server-demo && cd mcp-server-demo
pnpm init
pnpm add @modelcontextprotocol/sdk zod
pnpm add -D typescript @types/node tsx vitest
```

```typescript
// src/server.ts
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";

const server = new McpServer({ name: "Demo", version: "1.0.0" });

server.tool("add", { a: z.number(), b: z.number() }, async ({ a, b }) => ({
  content: [{ type: "text", text: String(a + b) }],
}));

const transport = new StdioServerTransport();
await server.connect(transport);
```

```json
// package.json scripts
{
  "scripts": {
    "dev": "npx @modelcontextprotocol/inspector tsx src/server.ts",
    "start": "node dist/server.js",
    "build": "tsc"
  }
}
```

---

## Core Primitives -- TypeScript Implementation

### Tools

Tools perform computation and side effects. The LLM invokes them. Define parameters
with Zod schemas — the SDK infers TypeScript types automatically.

```typescript
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";

const server = new McpServer({ name: "Tools Example", version: "1.0.0" });

// Simple synchronous tool
server.tool(
  "search_database",
  { query: z.string(), limit: z.number().int().default(10) },
  async ({ query, limit }) => ({
    content: [{ type: "text", text: JSON.stringify(await db.search(query, limit)) }],
  }),
);

// Tool with error handling
server.tool(
  "read_file",
  { path: z.string().describe("Absolute path to the file") },
  async ({ path }) => {
    try {
      const content = await fs.readFile(path, "utf8");
      return { content: [{ type: "text", text: content }] };
    } catch (err) {
      return {
        isError: true,
        content: [{ type: "text", text: `Failed to read ${path}: ${String(err)}` }],
      };
    }
  },
);
```

**Python FastMCP → TypeScript SDK mapping**:

| Python FastMCP | TypeScript SDK |
|---------------|----------------|
| `@mcp.tool()` | `server.tool(name, schema, handler)` |
| `@mcp.resource("uri://{var}")` | `server.resource("uri://{var}", handler)` |
| `@mcp.prompt()` | `server.prompt(name, schema, handler)` |
| `mcp.run()` | `server.connect(transport)` |
| Pydantic for validation | Zod for validation |

### Resources

Resources provide data to LLMs. No significant side effects.

```typescript
// Static resource
server.resource("config://settings", async () => ({
  contents: [{ uri: "config://settings", text: JSON.stringify(config), mimeType: "application/json" }],
}));

// Resource template with URI variable
server.resource("file://docs/{path}", async (uri) => {
  const filePath = uri.pathname.replace("/docs/", "");
  const content = await fs.readFile(filePath, "utf8");
  return {
    contents: [{ uri: uri.toString(), text: content, mimeType: "text/plain" }],
  };
});
```

### Prompts

Prompts define structured interaction patterns.

```typescript
server.prompt(
  "review_code",
  { code: z.string(), language: z.string().default("typescript") },
  async ({ code, language }) => ({
    messages: [
      {
        role: "user",
        content: {
          type: "text",
          text: `Please review this ${language} code:\n\n\`\`\`${language}\n${code}\n\`\`\``,
        },
      },
    ],
  }),
);
```

---

## Transports -- TypeScript Configuration

### Stdio Transport

Use for local integration with Claude Desktop and Claude Code.

```typescript
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";

const server = new McpServer({ name: "My Server", version: "1.0.0" });

// ... register tools, resources, prompts ...

const transport = new StdioServerTransport();
await server.connect(transport);
```

**Claude Desktop config** (`~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "my-server": {
      "command": "node",
      "args": ["/absolute/path/to/dist/server.js"]
    }
  }
}
```

**Claude Code registration**:

```bash
claude mcp add my-server --scope project -- node /absolute/path/to/dist/server.js
```

### Streamable HTTP Transport

Use for remote / HTTP-accessible servers.

```typescript
import express from "express";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/streamableHttp.js";

const app = express();
app.use(express.json());

const server = new McpServer({ name: "HTTP Server", version: "1.0.0" });
// ... register tools, resources, prompts ...

app.post("/mcp", async (req, res) => {
  const transport = new StreamableHTTPServerTransport({ sessionIdGenerator: undefined });
  await server.connect(transport);
  await transport.handleRequest(req, res, req.body);
});

app.listen(8000);
```

**Claude Code registration**:

```bash
claude mcp add --transport http my-server http://localhost:8000/mcp
```

**Note on web framework choice**: Express is shown above; Hono and Fastify are equally valid.
The v1 SDK does not include framework-specific adapters — v2 alpha will add
`@modelcontextprotocol/express`, `@modelcontextprotocol/hono`, and
`@modelcontextprotocol/fastify`. For now, wire the transport manually as shown.

---

## Server Lifecycle

The explicit `server.connect(transport)` call is the key difference from Python
FastMCP's `mcp.run()`. The sequence is:

1. Construct `McpServer` with name and version
2. Register all tools, resources, and prompts
3. Construct the transport
4. Call `await server.connect(transport)` — this starts the message loop

For stdio servers, the process stays alive until the parent process closes the pipe.
For HTTP servers, the transport handles each request independently (stateless by default).

```typescript
// Minimal complete server
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";

async function main() {
  const server = new McpServer({ name: "My Server", version: "1.0.0" });

  server.tool("ping", {}, async () => ({
    content: [{ type: "text", text: "pong" }],
  }));

  await server.connect(new StdioServerTransport());
}

main().catch(console.error);
```

---

## Logging Setup

**Stdio servers**: never write to stdout — it corrupts JSON-RPC messages. Use stderr only.

```typescript
// Safe logging in stdio servers
process.stderr.write(`[DEBUG] tool called: ${name}\n`);

// Or use a logger directed to stderr:
import { createLogger, transports } from "winston";
const logger = createLogger({
  transports: [new transports.Stream({ stream: process.stderr })],
});
```

**HTTP servers**: standard stdout/file logging is fine.

---

## Testing

### Vitest Unit Tests

Prefer **Vitest** over Jest for TypeScript MCP servers (ts-jest is unmaintained; native
ESM support is better in Vitest). Test tool handlers directly without requiring a running
server — they are plain async functions.

```typescript
// src/tools/calculator.ts
import { z } from "zod";
export const addSchema = { a: z.number(), b: z.number() };
export async function addHandler({ a, b }: { a: number; b: number }) {
  return { content: [{ type: "text" as const, text: String(a + b) }] };
}
```

```typescript
// src/tools/calculator.test.ts
import { describe, it, expect } from "vitest";
import { addHandler } from "./calculator.js";

describe("add tool", () => {
  it("returns the sum", async () => {
    const result = await addHandler({ a: 2, b: 3 });
    expect(result.content[0].text).toBe("5");
  });

  it("handles negative numbers", async () => {
    const result = await addHandler({ a: -1, b: 1 });
    expect(result.content[0].text).toBe("0");
  });
});
```

**Vitest config** (`vitest.config.ts`):

```typescript
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    globals: false,
    include: ["src/**/*.test.ts"],
  },
});
```

**pnpm scripts**:

```json
{
  "scripts": {
    "test": "vitest run",
    "test:watch": "vitest"
  }
}
```

### MCP Inspector

For interactive / end-to-end testing, use the MCP Inspector (language-agnostic):

```bash
npx @modelcontextprotocol/inspector node dist/server.js   # after build
# OR
npx @modelcontextprotocol/inspector tsx src/server.ts     # during development
```

Inspector opens at `localhost:6274` — invoke tools, read resources, and test prompts
through the web UI.

---

## Client Integration -- TypeScript Examples

**MCP TypeScript client** (for testing or building agent integrations):

```typescript
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";

const transport = new StdioClientTransport({
  command: "node",
  args: ["dist/server.js"],
});

const client = new Client({ name: "test-client", version: "1.0.0" });
await client.connect(transport);

const tools = await client.listTools();
const result = await client.callTool({ name: "add", arguments: { a: 2, b: 3 } });

await client.close();
```

---

## Project Structure

```
mcp-server/
├── src/
│   ├── server.ts          # Entry point — McpServer setup and transport connect
│   ├── tools/             # One file per tool (or domain group)
│   │   ├── calculator.ts
│   │   └── calculator.test.ts
│   ├── resources/         # Resource handlers
│   └── prompts/           # Prompt handlers
├── dist/                  # Compiled output (gitignored)
├── package.json
├── tsconfig.json
└── vitest.config.ts
```

**Recommended `tsconfig.json`** (extend `@tsconfig/node22`):

```json
{
  "extends": "@tsconfig/node22/tsconfig.json",
  "compilerOptions": {
    "outDir": "dist",
    "rootDir": "src"
  },
  "include": ["src"]
}
```

For pnpm setup, volta pinning, and workspace configuration, see
[node-prj-mgmt/contexts/typescript.md](../../node-prj-mgmt/contexts/typescript.md).

---

## Zod Version Note

**Cross-skill version split** — and it is narrower than it looks. The MCP TS SDK **v1**
accepts `zod@^3.25 || ^4.0`, so it does not by itself force Zod v3; a project hits the split
only when something pins `zod@^3` (a pin this skill previously recommended, now corrected).
OpenAI Agents SDK JS requires Zod v4.

Two ways out, in order of preference:

1. **Move to SDK v2**, which supports Standard Schema (Zod v4, Valibot, ArkType) and drops
   the coupling entirely — see [SDK v2 Migration Note](#sdk-v2-migration-note).
2. **Stay on v1 and widen the pin** to `"zod": "^3.25 || ^4"` so a single v4 copy resolves.

If you genuinely need two Zod copies to coexist, see
[`node-prj-mgmt/contexts/typescript.md` § Zod v3/v4 coexistence](../../node-prj-mgmt/contexts/typescript.md)
for the canonical `pnpm overrides` fix.

---

## SDK v2 Migration Note
<!-- last-verified: 2026-08-05 -->

**v2 is the stable release line** as of 2026-07-27, released alongside the 2026-07-28 MCP
specification. It ships as separate packages rather than one monolith:

- `@modelcontextprotocol/server` — build MCP servers
- `@modelcontextprotocol/client` — build MCP clients
- `@modelcontextprotocol/node` — Node.js adapters
- `@modelcontextprotocol/express` / `hono` / `fastify` — framework adapters

v2 supports **Standard Schema** — Zod v4, Valibot, ArkType, or any compatible library — which
dissolves the Zod v3/v4 split that constrains v1.

### v2 quickstart

```typescript
import { McpServer } from '@modelcontextprotocol/server';
import { StdioServerTransport } from '@modelcontextprotocol/server/stdio';
import * as z from 'zod/v4';

const server = new McpServer({ name: 'greeting-server', version: '1.0.0' });

server.registerTool(
    'greet',
    {
        description: 'Greet someone by name',
        inputSchema: z.object({ name: z.string() })
    },
    async ({ name }) => ({
        content: [{ type: 'text', text: `Hello, ${name}!` }]
    })
);
```

Note stdio is imported from the `@modelcontextprotocol/server/stdio` subpath, not from a
separate transport package.

### Praxion adoption posture

The previous promotion trigger — *v2 reaches stable **AND** at least one Praxion-managed TS
project uses v2 in production* — has **half fired**. Condition 1 is met; condition 2 is a
Praxion-internal gate that has not yet been satisfied.

So: **v2 for new servers**, and existing v1 servers migrate deliberately rather than
reflexively. What changed is the justification — "v1 because v2 isn't stable" is no longer a
true statement, and any decision to stay on v1 needs a current reason (a pinned dependency, a
migration cost, an unported adapter), not that one.

---

## Common Pitfalls -- TypeScript-Specific

- **`.js` extensions in imports**: TypeScript + ESM requires `.js` suffixes in relative
  imports (`./tools/calculator.js`), even when the source is `.ts`. The compiler
  resolves them correctly at build time.
- **Stdout pollution in stdio servers**: any `console.log()` corrupts JSON-RPC. Use
  `console.error()` or write directly to `process.stderr`.
- **Not awaiting `server.connect()`**: the transport message loop is async — omitting
  `await` causes the process to exit before serving any requests.
- **Mixing Zod v3 and v4 APIs**: if you install Zod v4 and the MCP SDK's Zod v3 dep
  resolves to a separate copy, schema objects from different versions are not
  interchangeable. See [Zod Version Note](#zod-version-note).
- **Missing `--module nodenext` or `--moduleResolution node16`**: the SDK uses ESM
  with sub-path exports — without proper module resolution settings, imports like
  `@modelcontextprotocol/sdk/server/mcp.js` will fail. `@tsconfig/node22` sets this
  correctly.

---

## Further Reading

- [MCP TypeScript SDK — GitHub](https://github.com/modelcontextprotocol/typescript-sdk)
- [Build an MCP server — modelcontextprotocol.io](https://modelcontextprotocol.io/docs/develop/build-server)
- [MCP Inspector](https://github.com/modelcontextprotocol/inspector)
- [FastMCP (TypeScript) — npm](https://www.npmjs.com/package/fastmcp)
- See [../SKILL.md](../SKILL.md) for transport concepts and security principles
- See [references/resources.md](../references/resources.md) for bundle (.mcpb) patterns
