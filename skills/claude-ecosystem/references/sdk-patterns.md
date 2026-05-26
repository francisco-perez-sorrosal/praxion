# SDK Patterns

Practical SDK idioms for the [claude-ecosystem](../SKILL.md) skill. Covers Python SDK, TypeScript SDK, Agent SDK (both), version compatibility, and common gotchas. Load on demand.

## Contents

- [Python SDK](#python-sdk)
- [TypeScript SDK](#typescript-sdk)
- [Agent SDK](#agent-sdk)
- [Version Compatibility](#version-compatibility)
- [Common Gotchas](#common-gotchas)

## Python SDK

Package: `anthropic`. Python 3.9+. Install: `pip install anthropic`.

```python
import anthropic

client = anthropic.Anthropic()            # sync -- reads ANTHROPIC_API_KEY from env
async_client = anthropic.AsyncAnthropic() # async -- same env var, use with asyncio

# Basic message
message = client.messages.create(
    model="claude-sonnet-4-5-20250514",
    max_tokens=1024,
    messages=[{"role": "user", "content": "Explain quicksort."}],
)
print(message.content[0].text)

# Streaming (sync -- async uses `async with` / `async for`)
with client.messages.stream(
    model="claude-sonnet-4-5-20250514", max_tokens=1024,
    messages=[{"role": "user", "content": "Write a haiku."}],
) as stream:
    for text in stream.text_stream:
        print(text, end="", flush=True)
```

### Tool Use

```python
tools = [{
    "name": "get_weather",
    "description": "Get current weather for a location.",
    "input_schema": {
        "type": "object",
        "properties": {"location": {"type": "string", "description": "City name"}},
        "required": ["location"],
    },
}]

message = client.messages.create(
    model="claude-sonnet-4-5-20250514", max_tokens=1024,
    tools=tools, messages=[{"role": "user", "content": "Weather in Tokyo?"}],
)
if message.stop_reason == "tool_use":
    tool_block = next(b for b in message.content if b.type == "tool_use")
    # Execute tool, then send tool_result message back to continue the conversation
```

### Extended Thinking

```python
message = client.messages.create(
    model="claude-opus-4-6-20250610", max_tokens=16000,
    thinking={"type": "enabled", "budget_tokens": 10000},
    messages=[{"role": "user", "content": "Solve this step by step..."}],
)
for block in message.content:
    if block.type == "thinking":
        print(f"Thinking: {block.thinking}")
    elif block.type == "text":
        print(f"Answer: {block.text}")
```

### Error Handling

```python
from anthropic import APIError, RateLimitError, APIConnectionError
client = anthropic.Anthropic(max_retries=3)  # default: 2 retries, exponential backoff
try:
    message = client.messages.create(...)
except RateLimitError:       # 429 -- back off or queue
    pass
except APIConnectionError:   # network issue -- retry or fail gracefully
    pass
except APIError as e:        # all other API errors (400, 500, etc.)
    print(f"Status {e.status_code}: {e.message}")
```

### Prompt Caching

Add `"cache_control": {"type": "ephemeral"}` to any content block in `system` or `messages` to cache it. Check `usage.cache_creation_input_tokens` and `usage.cache_read_input_tokens` in the response. See [platform-services.md](platform-services.md) for TTL and cost details.

## TypeScript SDK

Package: `@anthropic-ai/sdk`. Install: `npm install @anthropic-ai/sdk`. Same API shape as Python -- key differences shown below.

```typescript
import Anthropic, { APIError, RateLimitError } from "@anthropic-ai/sdk";
const client = new Anthropic(); // reads ANTHROPIC_API_KEY from env

const message = await client.messages.create({
  model: "claude-sonnet-4-5-20250514", max_tokens: 1024,
  messages: [{ role: "user", content: "Explain quicksort." }],
});
console.log(message.content[0].text);

// Streaming -- event-based
const stream = client.messages.stream({ model: "claude-sonnet-4-5-20250514", max_tokens: 1024,
  messages: [{ role: "user", content: "Write a haiku." }] });
for await (const event of stream) {
  if (event.type === "content_block_delta" && event.delta.type === "text_delta")
    process.stdout.write(event.delta.text);
}

// Error handling -- same exception hierarchy as Python SDK
try { await client.messages.create({ ... }); }
catch (error) {
  if (error instanceof RateLimitError) { /* 429 */ }
  else if (error instanceof APIError) { console.error(`${error.status}: ${error.message}`); }
}
```

Tool use and extended thinking follow the same structure as Python (camelCase keys, `as const` for type literals in `input_schema`).

## Agent SDK

Package: `claude-agent-sdk` (Python) / `@anthropic-ai/claude-agent-sdk` (TypeScript). The Agent SDK powers Claude Code -- use it instead of the raw Messages API for agentic applications that need tool loops, conversation state, or MCP server connections.

### When to Use Agent SDK vs Messages API

| Scenario | Use |
|----------|-----|
| Single request-response | Messages API (Python/TS SDK) |
| Multi-turn with tool loops | Agent SDK |
| MCP server integration | Agent SDK (built-in MCP client) |
| Maximum API control | Messages API |
| Building a coding agent | Agent SDK (bash, editor, file tools built in) |

**For Agent SDK implementation patterns** (tools, hooks, subagents, sessions, MCP integration, code examples), load the [agentic-sdks](../../agentic-sdks/SKILL.md) skill which covers both Claude Agent SDK and OpenAI Agents SDK with language-specific contexts for Python and TypeScript.

## Version Compatibility

| SDK | Min Runtime | Notes |
|-----|-------------|-------|
| Python SDK (`anthropic`) | Python 3.9+ | Typed models, sync/async |
| TypeScript SDK (`@anthropic-ai/sdk`) | Node.js 18+ | ESM and CJS |
| Agent SDK Python (`claude-agent-sdk`) | Python 3.10+ | Requires 3.10 for match/type unions |
| Agent SDK TS | Node.js 18+ | Mirrors Python Agent SDK |
| Claude Code | Node.js 18+ | Installed via npm, bundles Agent SDK |

**API versioning:** Date-based `anthropic-version` header (e.g., `2023-06-01`). SDKs pin a default; set explicitly only when targeting specific API behavior.

**Beta features:** Access via `betas` parameter or `anthropic-beta` header. Current betas: interleaved thinking, 1M context, MCP connector, Files API. Multiple headers combine additively.

## Common Gotchas

- **`max_tokens` is required.** No default -- every `messages.create` call must set it.
- **Content is a list of blocks.** `message.content` contains `text`, `tool_use`, `thinking` blocks. Always iterate or index.
- **Stop reason matters.** `"end_stop"` = done, `"tool_use"` = tool call pending, `"max_tokens"` = truncated.
- **Tool use requires a response loop.** Send `tool_result` back after executing. Model cannot proceed without it.
- **System prompt is not in messages.** Use the `system` parameter, not `role: "system"`.
- **Extended thinking changes content structure.** Interleaved `thinking` and `text` blocks in `message.content`.
- **Prompt caching minimums.** 1024 tokens (Opus/Sonnet) or 2048 tokens (Haiku) per cached block.
- **Streaming events.** Most code needs only `content_block_delta` from the six event types.

For general Python patterns (async, testing, project structure), consult the [python-development](../../python-development/SKILL.md) skill.
