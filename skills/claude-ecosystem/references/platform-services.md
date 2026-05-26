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

Cache repeated message prefixes to reduce latency and cost. The API stores cacheable content blocks server-side and serves them on cache hits. See [api-features.md](api-features.md) for the `cache_control` parameter and block placement.

### TTL Tiers

| TTL | Cost Model | Activation |
|-----|-----------|------------|
| 5 minutes | Write: 25% premium over base input. Read: ~90% reduction | Default -- set `cache_control: { type: "ephemeral" }` |
| 1 hour | Write: 25% premium over base input. Read: ~90% reduction | Set `cache_control: { type: "ephemeral", ttl: "ephemeral_1h" }` |

**Cache write** occurs on the first request with a new prefix. **Cache read** occurs on subsequent requests with the same prefix within the TTL window. Each cache hit resets the TTL timer.

### Workspace Isolation

The 1-hour cache is scoped to the API workspace. Different API keys within the same workspace share cache entries. Keys in different workspaces never share cache, even with identical content. The 5-minute cache has the same isolation model.

### Implementation Patterns

**Multi-turn conversations:** Place system prompt and few-shot examples in early message blocks with `cache_control`. These remain cached across turns while user messages change.

**RAG with stable document sets:** Cache the document context. Only the query varies per request, so subsequent queries against the same documents hit the cache.

**Batch + cache combination:** When running batches against shared context, the first request in the batch writes the cache. Subsequent requests in the same batch benefit from cache reads, compounding the 50% batch discount with the 90% cache read discount.

### Minimum Block Sizes

Content must meet a minimum token count to be cacheable:

| Model | Minimum Tokens |
|-------|---------------|
| Opus, Sonnet | 1,024 |
| Haiku | 2,048 |

Content below these thresholds is silently ignored for caching (no error, just no cache). Maximum 4 cache breakpoints per request.

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
