# Platform Services

Operational patterns, cost optimization, and platform-level services for the Claude API. Reference material for the [Claude Ecosystem](../SKILL.md) skill.

**Boundary:** This file covers how to run workloads efficiently -- batching, caching, file management, rate limits, and cost strategies. For API feature parameters and usage patterns, see [api-features.md](api-features.md). For SDK code examples, see [sdk-patterns.md](sdk-patterns.md).

## Contents

- [Batch Processing](#batch-processing)
- [Prompt Caching](#prompt-caching)
- [Files API](#files-api)
- [Data Residency](#data-residency)
- [Rate Limits and Usage](#rate-limits-and-usage)
- [Cost Optimization Patterns](#cost-optimization-patterns)

## Batch Processing

Process large volumes of requests asynchronously at 50% cost reduction. Batches complete within 24 hours (typically much faster) and do not count against real-time rate limits.

### How Batches Work

1. Create a batch with an array of individual message requests, each identified by a `custom_id`
2. The API processes requests in parallel (order not guaranteed)
3. Poll or use a webhook to detect completion
4. Retrieve results -- each response keyed by `custom_id`

**API shape:**

```
POST /v1/messages/batches
{
  "requests": [
    { "custom_id": "req-001", "params": { "model": "...", "messages": [...], "max_tokens": 1024 } },
    { "custom_id": "req-002", "params": { ... } }
  ]
}
```

### Batch Lifecycle

| Status | Meaning |
|--------|---------|
| `in_progress` | Processing requests |
| `ended` | All requests processed (check individual results for success/error) |
| `canceling` / `canceled` | Cancellation requested / complete. Already-processed results remain available |
| `expired` | Batch exceeded 24-hour window (partial results available) |

### When to Use Batches

- **Evaluations and benchmarks** -- run hundreds of test prompts without rate limit pressure
- **Content generation** -- bulk summaries, translations, classifications
- **Data processing** -- extract structured data from large document sets
- **Non-interactive workloads** -- anything that does not need sub-second response times

Batches support all Messages API features including tool use, extended thinking, and structured outputs.

## Prompt Caching
<!-- last-verified: 2026-07-29 -->

Cache repeated message prefixes to reduce latency and cost. The API stores cacheable content blocks server-side and serves them on cache hits. This is the canonical home for Anthropic prompt-caching mechanics and cost model — [api-features.md](api-features.md) covers the `cache_control` parameter shape only and links back here for details.

### TTL Tiers

| TTL | Write cost | Read cost | Activation |
|-----|-----------|-----------|------------|
| 5 minutes | 1.25x base input (25% premium) | 0.1x base input (~90% reduction) | Default -- `cache_control: { "type": "ephemeral" }` |
| 1 hour | 2x base input (100% premium) | 0.1x base input (~90% reduction) | `cache_control: { "type": "ephemeral", "ttl": "1h" }` -- note: no `ephemeral_` prefix on the TTL value |

The 1-hour tier's write premium (100%) is 4x the 5-minute tier's (25%) -- not the same rate applied to a longer window, a common source of drift when copying these numbers. **Cache write** occurs on the first request with a new prefix. **Cache read** occurs on subsequent requests with the same prefix within the TTL window. Each cache hit resets the TTL timer.

### Automatic Caching (recommended starting point)

A single top-level `cache_control` field (not per-block) auto-tracks a growing conversation: the system finds the last cacheable block and advances the breakpoint forward each turn without manual marker updates. Compatible with explicit block-level breakpoints -- automatic caching consumes one of the 4 available breakpoint slots. Default TTL is 5 minutes, settable to 1 hour. Anthropic's own docs now recommend automatic caching as the default; reach for explicit per-block breakpoints only when different sections of the prompt need different change-frequency handling (e.g., a stable system prompt vs. a document set that rotates hourly).

### The 20-Block Lookback Window (highest-value gotcha)

A cache **write** happens only at the exact block marked with `cache_control` -- it hashes everything up to and including that block. A cache **read** walks backward at most **20 blocks** looking for a prior write at that position. It does not scan forward and does not "find" stable content on its own.

**Common failure mode:** static system context occupies blocks 1-5, a per-request block 6 carries a timestamp + user message, and the breakpoint is placed on block 6. Every request writes a new cache entry that is never reused -- the hash differs every time and no earlier position was ever written to. This fails **silently**: no error, just a full-price write on every call.

**Fix:** place the breakpoint on the *last block that stays identical across the calls you want to share a cache* -- in the example, block 5, not block 6. In a growing multi-turn conversation, if a single turn adds 20+ blocks, the lookback window can miss the prior write entirely -- add a second breakpoint closer to that position.

### Cache Invalidation Hierarchy

Cache follows `tools` -> `system` -> `messages` order; a change at one level invalidates that level and everything after it:

| Change | Invalidates |
|--------|-------------|
| Tool definitions (add/remove/reorder) | `tools` + `system` + `messages` (full cache wipe) |
| Toggling web search / citations | `system` + `messages` (not `tools`) |
| `tool_choice` | `messages` only |
| Thinking/effort parameter | `messages` always; `tools`/`system` too on some models |

This is why varying a subagent's tool list mid-pipeline is expensive, not just inelegant -- it forces a full cache rebuild, not a partial one. Praxion's own agents keep static, per-agent tool lists in frontmatter (see the `agent-crafting` skill), which is validated practice under this model, not just tidiness.

**Mid-conversation system updates:** on some (not all) current models, appending `{"role": "system"}` as a message instead of editing the top-level `system` field lets you add instructions without invalidating the cached system-prompt prefix.

### Workspace Isolation

The 1-hour cache is scoped to the API workspace. Different API keys within the same workspace share cache entries. Keys in different workspaces never share cache, even with identical content. The 5-minute cache has the same isolation model.

### Implementation Patterns

**Multi-turn conversations:** Place system prompt and few-shot examples in early message blocks with `cache_control`. These remain cached across turns while user messages change.

**RAG with stable document sets:** Cache the document context. Only the query varies per request, so subsequent queries against the same documents hit the cache.

**Batch + cache combination:** When running batches against shared context, the first request in the batch writes the cache. Subsequent requests in the same batch benefit from cache reads, compounding the 50% batch discount with the 90% cache read discount.

### Minimum Block Sizes

Content must meet a minimum token count to be cacheable, and the minimum is **per-model**, not a flat Opus/Sonnet-vs-Haiku split. As of 2026-07-29:

| Minimum tokens | Models |
|---|---|
| 512 | Claude Opus 5, Claude Fable 5, Claude Mythos 5 |
| 1,024 | Claude Opus 4.8, Claude Sonnet 5, Claude Sonnet 4.6, Claude Sonnet 4.5, Claude Opus 4.1, Claude Opus 4, Claude Sonnet 4 |
| 2,048 | Claude Mythos Preview, Claude Opus 4.7 |
| 4,096 | Claude Opus 4.6, Claude Opus 4.5, Claude Haiku 4.5 |

This table shifts with every model release -- verify current per-model minimums at [platform.claude.com/docs/en/build-with-claude/prompt-caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching) before relying on a specific number. Content below the applicable threshold is silently ignored for caching (no error, just no cache). Maximum 4 cache breakpoints per request.

### Further Reading (third-party, cite before trusting)

- **Anthropic engineering blog, "Lessons from building Claude Code: prompt caching is everything"** (Thariq Shihipar, Apr 2026) -- official production experience: never add/remove tools mid-session; switching models mid-conversation forces a full cache rebuild; non-deterministic tool ordering, timestamps in system prompts, or tool-parameter reordering silently break the cache; append turn updates as messages rather than editing the system prompt; Claude Code treats cache-hit-rate as uptime-grade infra.
- **Simon Willison, "Prompt caching with Claude"** (Aug 2024, updated Jan 2025) -- independent but technically substantive: if your app calls the API less often than once every 5 minutes on average, the write premium means caching *costs* more than it saves; ordinary multi-turn conversation auto-benefits from caching even with zero deliberate engineering; caching reduces compute/token billing only, not wire-transmission cost or client-perceived latency for large payloads.
- **arXiv:2601.06007, "Don't Break the Cache"** (Jan 2026, cross-provider study, 500+ agent sessions) -- caching *everything*, including dynamic tool-call results, can increase latency in some conditions; caching only the system prompt and excluding dynamic tool results from the cached prefix gave the most consistent savings (41-80% across providers). Complicates blanket "cache as much as possible" advice for long-horizon agentic workloads.

## Files API

Upload files to your workspace for reuse across multiple requests. Files persist until explicitly deleted. See [api-features.md](api-features.md) for the message reference syntax.

### File Lifecycle

| Operation | Endpoint | Notes |
|-----------|----------|-------|
| Upload | `POST /v1/files` | Returns `file_id`. Multipart form data |
| List | `GET /v1/files` | Paginated. Filter by `purpose` |
| Retrieve metadata | `GET /v1/files/{file_id}` | Size, type, creation time |
| Delete | `DELETE /v1/files/{file_id}` | Permanent. Requests referencing deleted files fail |

### Supported Formats

| Category | Formats |
|----------|---------|
| Documents | PDF |
| Images | JPEG, PNG, GIF, WebP |
| Text | Plain text, CSV, JSON, XML, HTML, Markdown |

### Cost Optimization with Files

Upload once, reference by ID in many requests. Combine with prompt caching -- a cached file reference avoids both re-upload and re-tokenization costs. Particularly effective for:

- Document analysis pipelines (same PDF, many questions)
- Few-shot example sets shared across requests
- Multi-agent workflows where agents reference the same source material

## Data Residency

**US-only inference:** Restrict all API processing to US data centers. Set the `anthropic-region: us` header (or equivalent SDK parameter) on requests. Available on the direct API -- check provider documentation for Bedrock and Vertex AI equivalents.

Use when regulatory or compliance requirements mandate that data does not leave US jurisdiction. No functional difference in model behavior or feature availability.

## Rate Limits and Usage

### Tier Structure

Rate limits scale with usage tier. Higher tiers unlock increased requests per minute (RPM), tokens per minute (TPM), and tokens per day (TPD). Tiers advance automatically based on cumulative spend.

Exact limits vary by model and tier -- consult the [rate limits documentation](https://platform.claude.com/docs/en/api/rate-limits) for current numbers. Key structural points:

- Limits are **per-model** -- Opus, Sonnet, and Haiku each have independent limits
- Limits are **per-workspace** -- all API keys in a workspace share the same pool
- **Batch requests** do not count against real-time rate limits (separate pool)

### Rate Limit Headers

Every API response includes headers for monitoring:

| Header | Meaning |
|--------|---------|
| `anthropic-ratelimit-requests-limit` | Max RPM for this model |
| `anthropic-ratelimit-requests-remaining` | RPM remaining in current window |
| `anthropic-ratelimit-requests-reset` | When the RPM window resets (ISO 8601) |
| `anthropic-ratelimit-tokens-limit` | Max TPM for this model |
| `anthropic-ratelimit-tokens-remaining` | TPM remaining in current window |
| `anthropic-ratelimit-tokens-reset` | When the TPM window resets (ISO 8601) |
| `retry-after` | Seconds to wait before retrying (on 429 responses) |

### Retry Strategy

On 429 (rate limited) or 529 (overloaded) responses:

1. Read `retry-after` header if present
2. Otherwise, exponential backoff: 1s, 2s, 4s, 8s (cap at 30s)
3. Add jitter (random 0-1s) to avoid thundering herd
4. Maximum 3-5 retries before failing

The Python and TypeScript SDKs implement this automatically (`max_retries` parameter, default 2). See [sdk-patterns.md](sdk-patterns.md) for error handling examples.

## Cost Optimization Patterns

### Model Selection for Cost

| Strategy | Savings | Trade-off |
|----------|---------|-----------|
| Haiku for classification/routing | ~10x cheaper than Opus | Lower capability ceiling |
| Sonnet as default, Opus for hard cases | ~3x cheaper on average | Requires routing logic |
| Effort `low` for simple tasks | Reduced compute per request | Less reasoning depth |

### Combining Discounts

Multiple cost levers stack:

| Combination | Effective Discount | Best For |
|-------------|-------------------|----------|
| Batch only | 50% | Async workloads |
| Cache read only | ~90% on cached portion | Repeated prefixes |
| Batch + cache read | ~95% on cached portion | Bulk processing with shared context |
| Smaller model + batch | 50% + model cost difference | High-volume, moderate-complexity |

### Token Counting for Cost Control

Use the `/v1/messages/count_tokens` endpoint before expensive requests:

- Verify input fits within context limits before sending
- Estimate cost before committing to a large batch
- Optimize cache breakpoint placement by measuring what gets cached
- Compare token counts across prompt variants to find the most efficient framing

### Multi-Cloud Deployment

Claude is available through AWS Bedrock, Google Vertex AI, and Azure AI in addition to the direct API. Pricing, rate limits, and feature availability differ by provider. Consult provider-specific documentation:

- [AWS Bedrock](https://docs.aws.amazon.com/bedrock/latest/userguide/model-parameters-anthropic-claude-messages.html)
- [Google Vertex AI](https://cloud.google.com/vertex-ai/generative-ai/docs/partner-models/use-claude)

The Anthropic Python and TypeScript SDKs include Bedrock and Vertex AI clients (`AnthropicBedrock`, `AnthropicVertex`) for a consistent API surface across providers.
