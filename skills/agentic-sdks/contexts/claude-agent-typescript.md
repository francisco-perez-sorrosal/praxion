# Claude Agent SDK -- TypeScript

TypeScript-specific implementation guide. Load alongside the generic [Agentic SDKs](../SKILL.md) skill.

## Setup

```bash
npm install @anthropic-ai/claude-agent-sdk
```

Requires Node.js 18+. The Claude Code CLI is bundled with the package. Set `ANTHROPIC_API_KEY` environment variable.

## Core Abstractions

### query() -- One-Shot Queries

```typescript
import { query } from "@anthropic-ai/claude-agent-sdk";

for await (const message of query({
  prompt: "Find and fix the bug in auth.py",
  options: { allowedTools: ["Read", "Edit", "Bash"] },
})) {
  console.log(message);
}
```

**With full options:**

```typescript
import { query, Options } from "@anthropic-ai/claude-agent-sdk";

const options: Options = {
  systemPrompt: "You are a code reviewer.",
  maxTurns: 5,
  allowedTools: ["Read", "Glob", "Grep"],
  permissionMode: "bypassPermissions",
  cwd: "/path/to/project",
  model: "claude-sonnet-5-5",
  settingSources: ["project"],  // Load CLAUDE.md
};

for await (const message of query({ prompt: "Review this codebase", options })) {
  if (message.type === "assistant") {
    for (const block of message.message.content) {
      if (block.type === "text") console.log(block.text);
    }
  }
}
```

### Query Object Methods

```typescript
const q = query({ prompt: "Analyze this code", options });

// Streaming iteration
for await (const message of q) {
  // process messages
}

// Runtime control (streaming input mode)
await q.interrupt();
await q.setPermissionMode("acceptEdits");
await q.setModel("claude-opus-5-5");
await q.setMaxThinkingTokens(10000);

// Inspection
const commands = await q.supportedCommands();
const models = await q.supportedModels();
const mcpStatus = await q.mcpServerStatus();
const account = await q.accountInfo();

// File checkpointing (requires enableFileCheckpointing: true)
await q.rewindFiles(userMessageUuid);
```

### Options

```typescript
const options: Options = {
  // Core
  systemPrompt: "Custom system prompt",
  maxTurns: 10,
  cwd: "/path/to/project",
  model: "claude-sonnet-5-5",

  // Tools
  allowedTools: ["Read", "Write", "Edit", "Bash", "Glob", "Grep", "Task"],
  permissionMode: "acceptEdits",

  // MCP
  mcpServers: { "my-server": serverConfig },

  // Subagents
  agents: { "reviewer": { description: "...", prompt: "...", tools: [...] } },

  // Hooks
  hooks: { PreToolUse: [{ matcher: "Bash", hooks: [checkCmd] }] },

  // Structured output
  outputFormat: { type: "json_schema", schema: mySchema },

  // Settings
  settingSources: ["project"],

  // Advanced
  enableFileCheckpointing: true,
  maxBudgetUsd: 1.0,
  betas: ["context-1m-2025-08-07"],
  sandbox: { enabled: true, autoAllowBashIfSandboxed: true },
  plugins: [{ type: "local", path: "./my-plugin" }],
};
```

## Custom Tools (In-Process MCP)

```typescript
import { tool, createSdkMcpServer, query } from "@anthropic-ai/claude-agent-sdk";
import { z } from "zod";

const searchDocs = tool(
  "search_docs",
  "Search documentation by query",
  { query: z.string(), limit: z.number().default(10) },
  async (args) => ({
    content: [{ type: "text" as const, text: `Found results for: ${args.query}` }],
  })
);

const getUser = tool(
  "get_user",
  "Get user by ID",
  { userId: z.string() },
  async (args) => ({
    content: [{ type: "text" as const, text: JSON.stringify({ id: args.userId }) }],
  })
);

const server = createSdkMcpServer({
  name: "my-tools",
  version: "1.0.0",
  tools: [searchDocs, getUser],
});

for await (const msg of query({
  prompt: "Search for auth docs",
  options: {
    mcpServers: { tools: server },
    allowedTools: ["mcp__tools__search_docs", "mcp__tools__get_user"],
  },
})) {
  console.log(msg);
}
```

## Subagents

```typescript
for await (const message of query({
  prompt: "Use the code-reviewer to review this codebase",
  options: {
    allowedTools: ["Read", "Glob", "Grep", "Task"],
    agents: {
      "code-reviewer": {
        description: "Expert code reviewer for quality and security.",
        prompt: "Analyze code quality and suggest improvements.",
        tools: ["Read", "Glob", "Grep"],
        model: "sonnet",
      },
    },
  },
})) {
  if ("result" in message) console.log(message.result);
}
```

Track subagent messages via `parent_tool_use_id` field.

## Hooks

```typescript
import { query, HookCallback, HookCallbackMatcher } from "@anthropic-ai/claude-agent-sdk";

const blockDangerous: HookCallback = async (input) => {
  if (input.hook_event_name !== "PreToolUse") return {};
  const preInput = input as { tool_name: string; tool_input: any };
  if (preInput.tool_name !== "Bash") return {};

  const command = preInput.tool_input?.command ?? "";
  if (command.includes("rm -rf")) {
    return {
      hookSpecificOutput: {
        hookEventName: "PreToolUse",
        permissionDecision: "deny",
        permissionDecisionReason: "Blocked: rm -rf",
      },
    };
  }
  return {};
};

const auditLog: HookCallback = async (input) => {
  const postInput = input as { tool_name: string; tool_input: any };
  const filePath = postInput.tool_input?.file_path ?? "unknown";
  await appendFile("./audit.log", `${new Date().toISOString()}: ${filePath}\n`);
  return {};
};

for await (const msg of query({
  prompt: "Refactor the auth module",
  options: {
    permissionMode: "acceptEdits",
    hooks: {
      PreToolUse: [{ matcher: "Bash", hooks: [blockDangerous] }],
      PostToolUse: [{ matcher: "Edit|Write", hooks: [auditLog] }],
    },
  },
})) {
  console.log(msg);
}
```

**Hook events:** `PreToolUse`, `PostToolUse`, `PostToolUseFailure`, `Stop`, `SubagentStart`, `SubagentStop`, `SessionStart`, `SessionEnd`, `UserPromptSubmit`, `PreCompact`, `Notification`, `PermissionRequest`.

## Session Management

```typescript
let sessionId: string | undefined;

// Capture session ID
for await (const msg of query({ prompt: "Read auth.py", options })) {
  if (msg.type === "system" && msg.subtype === "init") {
    sessionId = msg.session_id;
  }
}

// Resume session
for await (const msg of query({
  prompt: "Now fix the bug",
  options: { resume: sessionId },
})) {
  if ("result" in msg) console.log(msg.result);
}

// Fork session
for await (const msg of query({
  prompt: "Try different approach",
  options: { resume: sessionId, forkSession: true },
})) {
  console.log(msg);
}
```

## Custom Permissions

```typescript
import { CanUseTool } from "@anthropic-ai/claude-agent-sdk";

const canUseTool: CanUseTool = async (toolName, input, { signal }) => {
  if (toolName === "Bash" && String(input.command).includes("rm")) {
    return { behavior: "deny", message: "Deletion not allowed" };
  }
  return { behavior: "allow", updatedInput: input };
};

for await (const msg of query({
  prompt: "Clean up the project",
  options: { canUseTool },
})) {
  console.log(msg);
}
```

## Message Types

```typescript
import type {
  SDKMessage,
  SDKAssistantMessage,
  SDKResultMessage,
  SDKSystemMessage,
} from "@anthropic-ai/claude-agent-sdk";

for await (const msg of query({ prompt: "Hello", options })) {
  switch (msg.type) {
    case "assistant":
      for (const block of msg.message.content) {
        if (block.type === "text") console.log(block.text);
        if (block.type === "tool_use") console.log(`Tool: ${block.name}`);
      }
      break;
    case "result":
      if (msg.subtype === "success") {
        console.log(`Result: ${msg.result}`);
        console.log(`Cost: $${msg.total_cost_usd.toFixed(4)}`);
        console.log(`Turns: ${msg.num_turns}`);
        if (msg.structured_output) console.log("Structured:", msg.structured_output);
      } else {
        console.error(`Error: ${msg.subtype}`, msg.errors);
      }
      break;
    case "system":
      if (msg.subtype === "init") console.log(`Session: ${msg.session_id}`);
      break;
  }
}
```

## Sandbox Configuration

```typescript
for await (const msg of query({
  prompt: "Build and test the project",
  options: {
    sandbox: {
      enabled: true,
      autoAllowBashIfSandboxed: true,
      network: { allowLocalBinding: true },
    },
  },
})) {
  console.log(msg);
}
```

## Error Handling

```typescript
import {
  ClaudeSDKError,
  CLINotFoundError,
  CLIConnectionError,
  ProcessError,
} from "@anthropic-ai/claude-agent-sdk";

try {
  for await (const msg of query({ prompt: "Hello", options })) {
    // process
  }
} catch (error) {
  if (error instanceof CLINotFoundError) {
    console.error("Install Claude Code CLI");
  } else if (error instanceof ProcessError) {
    console.error(`Process failed: exit code ${error.exitCode}`);
  }
}
```

## Common Pitfalls

- Not setting `settingSources: ["project"]` when CLAUDE.md is needed
- Forgetting `Task` in `allowedTools` when using subagents
- MCP tool names follow `mcp__<server>__<tool>` -- must match in `allowedTools`
- `query()` returns `AsyncGenerator` -- must iterate to get results
- Subagents cannot spawn subagents (single level of delegation)
- Using `permissionMode: "bypassPermissions"` without `allowDangerouslySkipPermissions: true`
