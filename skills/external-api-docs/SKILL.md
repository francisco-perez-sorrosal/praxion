---
name: external-api-docs
description: Retrieving current, curated API documentation for external libraries and
  SDKs during development. Covers search strategies, token-aware fetching, annotation
  persistence, and provider fallback hierarchy. Use when writing code against an external
  API (Stripe, OpenAI, Anthropic Claude API, AWS, FastAPI, Supabase, etc.), debugging
  an integration issue, evaluating an SDK's capabilities, looking up current endpoint
  signatures or parameters, or when the agent may hallucinate API details due to training
  data staleness. Also activates for external API reference, SDK documentation, library
  docs lookup, current API signatures, and integration reference.
allowed-tools: [Read, Bash, Glob, Grep]
compatibility: Claude Code, Cursor
metadata:
  default-provider: context-hub
  mcp-tools: chub_search, chub_get, chub_list, chub_annotate, chub_feedback
---

# External API Documentation

Retrieve accurate, current API documentation for external libraries transparently during agent-assisted development. This skill acts as a **passthrough** to curated documentation registries -- agents check for available docs before writing integration code, fetch them if available, and fall back gracefully if not.

**Satellite files** (loaded on-demand):

- [references/context-hub.md](references/context-hub.md) -- context-hub (chub) provider: CLI reference, setup, configuration, telemetry controls
- [references/mcp-setup.md](references/mcp-setup.md) -- MCP server configuration for Claude Code, Cursor, and Claude Desktop

## Gotchas

- **Large docs blow up context.** A single API reference can be 10K-50K+ tokens. When using CLI, fetch to file (`-o`) and read selectively. When using MCP tools, the content arrives in the tool response -- summarize or extract only what is needed before proceeding.
- **Curated does not mean correct.** Community-contributed docs may be outdated, incomplete, or vendor-biased. Cross-check critical details (auth flows, error codes, rate limits) against the official source when the stakes are high. Prefer entries marked `official` or `maintainer` over `community`.
- **Annotations are local and single-slot.** Each annotation overwrites the previous one for that entry -- there is no annotation history. Write comprehensive notes, not incremental updates.
- **Node.js required.** Both the MCP server and CLI need Node.js 18+. The Praxion installer configures the MCP server via `npx` (auto-downloads on first use). If Node.js is unavailable, fall back to web search.

## Automatic Behavior

This skill changes how the agent approaches external API work. When this skill is active and the task involves an external API, **proactively check for curated docs before writing code**. Do not wait for the user to ask.

**Trigger conditions** -- check for docs when:

1. **Writing integration code** against an API not yet referenced in this session
2. **Debugging an API error** where the response doesn't match expectations
3. **Evaluating an SDK** for capabilities, auth patterns, or versioning
4. **API has changed recently** -- the library is actively developed and training data may be stale

**Skip conditions** -- do NOT fetch docs when:

- Standard library functions (Python stdlib, Node.js built-ins)
- APIs already fetched in this session (avoid redundant lookups)
- Simple, well-known patterns where confidence is high

## Retrieval: MCP Tools (Preferred)

When the `chub` MCP server is configured (default after Praxion install), use MCP tools directly. These are native tools -- no shell required, no telemetry (disabled at the MCP server level).

### Step 1: Check Availability

Call `chub_search` with the library or API name:

```
chub_search({ query: "stripe", type: "docs" })
```

If results are returned, proceed to Step 2. If no results, skip to the Fallback Hierarchy.

### Step 2: Fetch Targeted Content

Call `chub_get` with the entry ID from search results:

```
chub_get({ id: "stripe/api", language: "python" })
```

For a specific reference file within the doc:

```
chub_get({ id: "stripe/api", file: "references/webhooks.md" })
```

### Step 3: Use the Content

The MCP tool returns the content directly. Extract only what is needed for the immediate task:

- **Endpoint signatures** -- parameter names, types, required vs optional
- **Auth patterns** -- how to authenticate, token formats, header names
- **Error codes** -- what responses to handle, retry semantics
- **Rate limits** -- request budgets, backoff strategies

Do not paste the entire doc response into your work. Summarize or quote the relevant sections.

### Step 4: Annotate Discoveries

When you find a gotcha, correction, or non-obvious pattern, persist it:

```
chub_annotate({ id: "stripe/api", note: "v2 PaymentIntents require idempotency keys for retries. Omitting causes silent duplicate charges." })
```

Annotations auto-append to future fetches of that entry, improving quality over time.

### Step 5: Give Feedback

After using a doc, **always** rate it. This is how the ecosystem improves — maintainers use feedback to fix problems and prioritize updates. Every rating must include a label and a concrete comment. Be honest and straight to the point.

**Comment quality matters.** Vague comments ("good docs", "didn't work") waste maintainer time. State exactly what was correct or what was wrong, with specifics: endpoint names, parameter mismatches, version numbers, missing sections.

```
chub_feedback({ id: "stripe/api", vote: "up", label: "accurate", comment: "PaymentIntents create/confirm flow matches v2024-12 API. Python examples run without modification." })
chub_feedback({ id: "openai/chat", vote: "down", label: "outdated", comment: "Documents gpt-4o as latest model but gpt-5.4 is current. Structured outputs section missing the 'strict' parameter added in 2025." })
chub_feedback({ id: "anthropic/sdk", vote: "down", label: "incomplete", comment: "No coverage of streaming tool_use responses. Only shows non-streaming examples." })
chub_feedback({ id: "fastapi/docs", vote: "up", label: "good-examples", comment: "Dependency injection examples cover all three scopes (request, session, app). Error handling patterns are production-ready." })
```

Available labels:

| Positive | Negative |
|----------|----------|
| `accurate`, `well-structured`, `helpful`, `good-examples` | `outdated`, `inaccurate`, `incomplete`, `wrong-examples`, `wrong-version`, `poorly-structured` |

**When to downvote:** wrong model names, deprecated endpoints, missing parameters, incorrect auth flows, code examples that fail, version mismatches between docs and current API. Always include what is wrong and what the correct state is.

**Visibility requirement.** Feedback is sent to an external service (context-hub). After submitting, **always report what was sent** to the user in a visible block:

```
[CHUB FEEDBACK SENT] stripe/api — UP (accurate)
"PaymentIntents create/confirm flow matches v2024-12 API. Python examples run without modification."
```

```
[CHUB FEEDBACK SENT] openai/chat — DOWN (outdated)
"Documents gpt-4o as latest model but gpt-5.4 is current. Structured outputs section missing the 'strict' parameter added in 2025."
```

Never send feedback silently. The user must see every rating submitted to a third-party system.

## Retrieval: CLI Fallback

When MCP tools are not available (server not configured, running in a context without MCP), use the CLI via Bash. All commands disable telemetry (`CHUB_TELEMETRY=0`) and enable feedback (`CHUB_FEEDBACK=1`).

### Search

```bash
CHUB_TELEMETRY=0 CHUB_FEEDBACK=1 chub search "<library>" --json
```

`chub search` with no query lists all available entries.

### Fetch

```bash
CHUB_TELEMETRY=0 CHUB_FEEDBACK=1 chub get <author/entry-id> --lang <language>
```

### Fetch to File (for large docs)

```bash
CHUB_TELEMETRY=0 CHUB_FEEDBACK=1 chub get <author/entry-id> -o tmp/api-docs/
```

Then read only the relevant sections using the Read tool.

### Annotate

```bash
CHUB_TELEMETRY=0 CHUB_FEEDBACK=1 chub annotate <author/entry-id> "<note>"
```

List existing annotations:

```bash
CHUB_TELEMETRY=0 CHUB_FEEDBACK=1 chub annotate --list
```

### Feedback

```bash
CHUB_TELEMETRY=0 CHUB_FEEDBACK=1 chub feedback <author/entry-id> up --label accurate "PaymentIntents flow matches v2024-12 API, Python examples run clean"
CHUB_TELEMETRY=0 CHUB_FEEDBACK=1 chub feedback <author/entry-id> down --label outdated "Documents gpt-4o as latest but gpt-5.4 is current, missing strict param in structured outputs"
```

### Quick Reference

| Goal | MCP tool | CLI equivalent |
|------|----------|----------------|
| Find a doc | `chub_search({ query: "stripe" })` | `chub search "stripe" --json` |
| List all docs | `chub_list()` | `chub search` (no query) |
| Fetch Python docs | `chub_get({ id: "stripe/api", language: "python" })` | `chub get stripe/api --lang py` |
| Fetch specific file | `chub_get({ id: "stripe/api", file: "references/webhooks.md" })` | `chub get stripe/api --file references/webhooks.md` |
| Save to file | N/A (MCP returns content directly) | `chub get stripe/api -o docs.md` |
| Save a note | `chub_annotate({ id: "stripe/api", note: "..." })` | `chub annotate stripe/api "..."` |
| List notes | N/A | `chub annotate --list` |
| Rate a doc | `chub_feedback({ id: "stripe/api", vote: "up" })` | `chub feedback stripe/api up` |

## Fallback Hierarchy

When the curated registry has no coverage for a library, fall back in this order:

1. **Curated registry** (context-hub via MCP or CLI) -- highest signal, LLM-optimized
2. **Local annotations** -- past learnings about this API from prior sessions
3. **Memory MCP** -- cross-session intelligence about API patterns and gotchas
4. **Web search** -- official documentation sites, GitHub repos
5. **Training data** -- last resort; flag uncertainty to the user

Each level down trades curation quality for breadth. Always prefer curated sources when available. When falling back to training data, inform the user: "No curated docs available for [library]; using training data which may be stale."

## Provider Architecture

This skill defines the **methodology** for external API documentation retrieval. The actual retrieval is delegated to a provider. Currently supported:

| Provider | Type | Coverage | Setup |
|----------|------|----------|-------|
| **[context-hub](references/context-hub.md)** (default) | MCP + CLI | ~600+ curated API doc packages | Praxion installer (Step 6) or `npm install -g @aisuite/chub` |

The provider model is extensible. Future providers follow the same pattern: check availability → fetch targeted content → use selectively → annotate discoveries. The fallback hierarchy always applies regardless of provider.

--> See [references/context-hub.md](references/context-hub.md) for CLI reference, configuration, and telemetry controls.

--> See [references/mcp-setup.md](references/mcp-setup.md) for MCP server configuration details per tool.

## Pipeline Integration

This skill activates transparently during any pipeline stage that involves external APIs. The agent proactively checks for docs -- no explicit request needed.

| Agent | Automatic behavior |
|-------|-------------------|
| researcher | Checks chub when investigating external API capabilities; incorporates findings into `RESEARCH_FINDINGS.md` |
| systems-architect | Checks chub when evaluating API constraints for design decisions; validates assumptions against current docs |
| implementer | Checks chub before writing integration code; fetches endpoint signatures, auth patterns, error codes |
| test-engineer | Checks chub for expected response shapes and edge cases when writing integration tests |

Any Praxion component that has access to MCP tools or Bash can use this skill. The retrieval is transparent -- the agent decides when to check, fetches what it needs, and proceeds with grounded knowledge.

## API Version Drift Detection

When fetching docs, **compare the documented API version against the version the project actually uses**. This prevents writing code against a newer API than the project depends on, and flags upgrade opportunities.

### Detection Protocol

1. **Read the project's dependency version** — check `pyproject.toml`, `package.json`, `Cargo.toml`, `go.mod`, `requirements.txt`, or lock files for the library's pinned version
2. **Check the fetched doc's version** — context-hub docs include version metadata; also check with `chub_search` results which versions are available
3. **Compare** — if the documented version is newer than the project version, flag it

### Flagging Format

When drift is detected, emit a structured warning:

```
[API VERSION DRIFT] <library>: project uses v<old>, curated docs cover v<new>.
Breaking changes may exist between versions.
Action: verify code against v<old> docs, or consider upgrading to v<new>.
```

### Where to Record

| Agent | Where to record drift | Action |
|-------|----------------------|--------|
| implementer | `LEARNINGS.md` under `### API Version Drift` | Write code against the project's actual version; log the drift for the architect |
| systems-architect | `SYSTEMS_PLAN.md` under `### Prerequisites` or `## Risk Assessment` | Flag as a risk or prerequisite; recommend upgrade if warranted |
| researcher | `RESEARCH_FINDINGS.md` under `### Dependencies` | Note version differences between project and current docs |
| Any agent | Memory MCP | Store persistent note: `remember({ key: "<library>-version-drift", value: "...", tags: ["api-drift", "<library>"], importance: 7 })` |

### Dependency Priority

Not all drift deserves the same attention. Assess the dependency's role in the project before flagging:

| Priority | Signal | Action on drift |
|----------|--------|----------------|
| **Critical** | Core domain dependency — deep integration, many modules | Actively flag; architect evaluates upgrade |
| **High** | Significant integration — multiple modules, data/auth | Flag; recommend upgrade if it affects current work |
| **Medium** | Moderate use — few modules, replaceable | Note in Risk Assessment; no user interruption |
| **Low** | Peripheral — one use site, utilities, dev tooling | Ignore unless it causes a concrete problem |

The systems-architect applies this priority when deciding whether to stop and ask the user. See the architect agent for the full decision protocol.

### When to Act vs. When to Flag

- **Flag only** (default): Log the drift, proceed with the project's current version. The user or architect decides whether to upgrade.
- **Act immediately**: Only when the project version has a known security vulnerability or the API endpoint has been removed/deprecated. In this case, inform the user directly.
- **Upgrade recommendation**: When drift is detected across 3+ Critical/High libraries in the same project, recommend a dependency audit as a dedicated task.

## Complementary Skills

This skill provides **current factual reference** (what the API looks like right now). Domain-specific skills provide **architectural guidance** (which API to use, how to design around it). Use both together for the best results.

| Domain Skill | What it provides | What external-api-docs adds |
|-------------|-----------------|---------------------------|
| [claude-ecosystem](../claude-ecosystem/SKILL.md) | Model selection, SDK choice, feature map, platform architecture | Current Claude API endpoint signatures, parameter details, recent changes |
| [agentic-sdks](../agentic-sdks/SKILL.md) | Agent SDK patterns, multi-agent orchestration, tool integration | Current SDK method signatures and initialization patterns |
| [api-design](../api-design/SKILL.md) | REST/GraphQL design methodology, OpenAPI specs | Current reference for APIs being integrated into the design |

**When both activate:** If working with the Claude API, `claude-ecosystem` tells you which model and SDK to use; `external-api-docs` fetches the current endpoint details so you write correct code. Neither replaces the other.

## Token Management

External API docs are the largest single-fetch content an agent encounters. Follow these constraints:

- **Entry file only** for overview and navigation (~3K-10K tokens)
- **Specific reference files** for targeted details (~1K-5K tokens each)
- **Never `--full`** unless explicitly needed and the user approves the token cost
- **CLI: file output** (`-o`) for docs over 10K tokens -- read sections on demand
- **MCP: extract, don't paste** -- summarize or quote relevant sections from the tool response
- **One API at a time** -- do not batch-fetch multiple API docs into context simultaneously
