# API Features

Detailed coverage of Claude API features -- parameters, usage patterns, and availability. Reference material for the [Claude Ecosystem](../SKILL.md) skill.

**Boundary:** This file covers features available through the Messages API. It does not cover MCP server development (see [mcp-crafting](../../mcp-crafting/SKILL.md)) or Claude Code hooks/plugins (see `claude-code-guide` subagent).

## Contents

- [Model Capabilities](#model-capabilities)
- [Server-Side Tools](#server-side-tools)
- [Client-Side Tools](#client-side-tools)
- [Tool Infrastructure](#tool-infrastructure)
- [Context Management](#context-management)
- [Files](#files)

## Model Capabilities

### Extended Thinking

Allow the model to reason step-by-step before responding. The thinking process is visible in `thinking` content blocks.

| Parameter | Type | Description |
|-----------|------|-------------|
| `thinking.type` | `"enabled"` | Activate extended thinking |
| `thinking.budget_tokens` | int | Maximum tokens for thinking (1024 to `max_tokens`) |

**Interleaved thinking (beta):** With the `interleaved-thinking-2025-05-14` beta header, thinking blocks appear between tool use steps rather than only before the first response. Requires `stream: true`.

**When to use:** Complex reasoning, multi-step math, code analysis, nuanced decisions. Budget 5K-10K tokens for moderate tasks, 20K+ for deep analysis. Extended thinking is incompatible with `temperature` (must be unset or 1).

### Adaptive Thinking

The model dynamically decides how much thinking depth to allocate based on query complexity. Unlike extended thinking (which reserves a fixed budget), adaptive thinking lets the model scale effort automatically.

**Best model:** Opus 4.6 (recommended). No explicit API parameter -- the model adapts naturally when extended thinking is enabled.

### Effort Parameter

Control how much compute the model spends on a response without managing thinking budgets directly.

| Value | Behavior |
|-------|----------|
| `low` | Minimal reasoning, fastest responses |
| `medium` | Balanced (default behavior) |
| `high` | Maximum reasoning depth |

**Models:** Opus 4.5, Opus 4.6. Set via `effort` parameter on the Messages API. Simpler than configuring `budget_tokens` directly -- use effort for coarse control, extended thinking for fine-grained control.

### Structured Outputs

Two mechanisms for typed, parseable responses:

**JSON mode** -- Set `response_format: { type: "json_object" }` to guarantee valid JSON output. Combine with a system prompt describing the desired schema.

**Tool-schema structured outputs** -- Define a tool with `input_schema` and force it with `tool_choice: { type: "tool", name: "..." }`. The model returns a structured `tool_use` block matching the schema exactly. Supports `additionalProperties: false` for strict validation.

**When to use which:**
- JSON mode: flexible schemas, the model decides structure within constraints
- Tool schemas: exact field control, strict typing, when output feeds directly into code

### Citations

Source-grounded responses that reference specific passages in provided documents. Enable with `citations: { enabled: true }` on the Messages API. The model returns `cite` content blocks with `document_id`, `start_index`, and `end_index` pointing to source material.

**Supported sources:** PDF documents, plain text, custom content blocks. Pair with multi-document input for cross-referencing.

### PDF Support (GA)

Pass PDFs directly in message content as `document` source blocks. The model understands text, layout, tables, and figures natively. Maximum 100 pages per document (recommended). Larger documents work but may degrade quality.

### Search Results

Provide search results in a structured format for RAG-style grounded responses. When combined with citations, the model attributes claims to specific search result passages. Use the `search_results` content type or pair with the web search tool for automatic retrieval.

### 1M Context Window (Beta)

All models support up to 1M tokens with the appropriate beta header (`interleaved-thinking-2025-05-14` or `extended-context`). The default limit is 200K tokens.

**When to use:** Large codebases, long documents, extensive conversation histories. Cost scales linearly with input tokens -- use prompt caching to offset costs on repeated prefixes.

## Server-Side Tools

Tools hosted and executed by Anthropic's infrastructure. Defined in the `tools` array with `type` indicating the tool kind.

### Web Search

Built-in tool (`web_search_20250305`) that searches the web and returns results for the model to synthesize.

```json
{ "type": "web_search_20250305", "name": "web_search", "max_uses": 5 }
```

Set `max_uses` to limit search invocations per request. Results include URLs, snippets, and page content. The model automatically cites sources when citations are enabled. Charged per search invocation.

### Web Fetch

Retrieve and parse a specific URL. Returns page content as text. Use when you have a known URL rather than needing to search. Respects `robots.txt`.

### Code Execution

Sandboxed Python environment (`code_execution_20250522`). The model writes and executes Python code, returning stdout/stderr and generated files (images, CSVs).

**Capabilities:** NumPy, pandas, matplotlib, and standard library. No network access, no persistent state across invocations. 30-second execution timeout.

**When to use:** Data analysis, chart generation, mathematical computation, format conversion. Prefer over asking the model to "calculate" -- execution eliminates arithmetic errors.

### Memory (Beta)

Cross-conversation persistence. The model stores and retrieves user preferences, facts, and context across separate conversations. Managed by Anthropic's infrastructure -- no developer configuration needed for claude.ai. API access requires the memory tool type.

## Client-Side Tools

Tools defined by the API client and executed locally. The API returns `tool_use` blocks; the client executes them and sends results back.

### Bash Tool

Execute shell commands. Used by Claude Code and Agent SDK. Define with `type: "bash_20250124"`. The model generates commands; the client runs them and returns stdout/stderr.

### Computer Use (Beta)

GUI interaction via screenshots and mouse/keyboard actions. The model receives a screenshot, decides actions (click, type, scroll), and the client executes them. Define with `type: "computer_20250124"`. Requires `display_width_px` and `display_height_px` configuration.

**When to use:** Automating GUI workflows, testing web applications, interacting with desktop software. Not suitable for production automation -- designed for development and testing.

### Text Editor Tool

View and edit files. Define with `type: "text_editor_20250124"`. Supports `view`, `create`, `str_replace`, and `insert` commands. Used by Claude Code for file manipulation.

## Tool Infrastructure

### MCP Connector (Beta)

Connect to MCP servers directly from the Messages API without a local client. Pass MCP server configuration in the `mcp_servers` array of the Messages request.

```json
{
  "mcp_servers": [{
    "type": "url",
    "url": "https://mcp-server.example.com/sse",
    "name": "my_server"
  }]
}
```

The API discovers tools from the MCP server and makes them available to the model. Supports `url` type (Streamable HTTP transport). Authorization headers can be passed for authenticated servers.

**Boundary:** This is the API-level connector feature. For building MCP servers, see [mcp-crafting](../../mcp-crafting/SKILL.md).

### Tool Search

Scale to thousands of tools without hitting context limits. When `tool_search` is enabled, the model searches over tool descriptions semantically rather than including all tool definitions in context.

**When to use:** Applications with 50+ tools where including all definitions would consume excessive context. The model retrieves only relevant tool definitions per request.

### Fine-Grained Streaming

Granular streaming events for tool use responses. Stream individual content blocks (`content_block_start`, `content_block_delta`, `content_block_stop`) to display partial tool inputs and text as they generate.

**Key events:** `input_json_delta` for incremental tool input JSON, `thinking_delta` for thinking content, `text_delta` for response text. Essential for responsive UIs during long tool-use sequences.

### Programmatic Tool Calling

Tools invoked from within the code execution sandbox. The model can call defined tools programmatically during code execution, enabling tool-augmented computation. The execution environment makes tool results available as return values.

## Context Management

### Prompt Caching

Cache repeated message prefixes to reduce latency and cost on subsequent requests.

| TTL | Cost (cached read) | Activation |
|-----|-------------------|------------|
| 5 minutes | ~90% reduction vs uncached | Default for `cache_control` blocks |
| 1 hour | ~90% reduction vs uncached | Set `ttl: "ephemeral_1h"` in `cache_control` |

Mark cacheable content boundaries with `cache_control: { type: "ephemeral" }` on content blocks. Place breakpoints at stable prefixes -- system prompts, large document sets, few-shot examples. Maximum 4 cache breakpoints per request.

**Workspace isolation (GA):** 1-hour cache is workspace-scoped. Different API keys in the same workspace share cache, but different workspaces do not.

**When to use:** Any workload with repeated prefixes -- multi-turn conversations, batch processing with shared context, RAG with stable document sets. Cost savings compound across requests.

### Compaction

Server-side context summarization. When conversation context approaches the limit, request compaction to condense earlier messages while preserving key information.

**Models:** Opus 4.6, Haiku 4.5. The API returns a compacted message array that replaces the original context. Use before hitting context limits in long-running conversations.

### Context Editing

Automatically manage conversation context by editing or removing older messages. The model selects which content to keep based on relevance to the current task. Complementary to compaction -- context editing is selective, compaction is wholesale summarization.

### Token Counting

Pre-flight token estimation via the `/v1/messages/count_tokens` endpoint. Pass the same parameters as a Messages request to get token counts without executing the request.

**When to use:** Cost estimation before expensive requests, validating that input fits within context limits, optimizing cache breakpoint placement. Counts include system prompt, messages, tool definitions, and any cached content.

## Files

### Files API (Beta)

Upload and manage files for reuse across multiple requests. Files persist in your workspace and can be referenced by ID in message content.

**Workflow:**
1. Upload via `POST /v1/files` with the file content
2. Reference in messages with `{ "type": "document", "source": { "type": "file", "file_id": "file_..." } }`
3. Delete when no longer needed via `DELETE /v1/files/{file_id}`

**Supported formats:** PDF, plain text, images (JPEG, PNG, GIF, WebP). Maximum file size varies by format.

**When to use:** Documents referenced across multiple conversations or requests. Avoids re-uploading large files on every request -- upload once, reference by ID. Combine with prompt caching for maximum cost efficiency on repeated document analysis.
