# External API Documentation

How to use Praxion to retrieve current, curated API documentation for external libraries during development. This prevents the agent from hallucinating endpoints, using deprecated methods, or guessing at parameter names.

## The Problem

LLMs have a knowledge cutoff. When you ask the agent to write code against an external API — Stripe, OpenAI, AWS SDK, FastAPI, Supabase — it works from training data that may be months stale. The result: fabricated endpoints, wrong parameter names, deprecated auth patterns, and silent integration failures.

## The Solution

Praxion includes the `external-api-docs` skill, which teaches agents a structured methodology for retrieving current API documentation from curated registries before writing integration code.

The default provider is [context-hub](https://github.com/andrewyng/context-hub) (`chub`) — a curated registry of ~600+ LLM-optimized API documentation packages maintained by Andrew Ng's team.

## Setup

### If you ran the Praxion installer

**No additional setup needed.** The installer configures everything:

- **Claude Code** (`./install.sh`): Step 6 offers to configure the context-hub MCP server in `~/.claude/settings.json`. Telemetry is disabled by default.
- **Cursor** (`./install.sh cursor`): The `mcp.json` template includes context-hub automatically.

Both use `npx -y @aisuite/chub mcp`, which auto-downloads on first use. The only prerequisite is **Node.js 18+** (which `npx` requires).

Verify the MCP server is working by asking the agent: "What chub tools are available?"

### Manual setup (without installer)

If you skipped the installer step or want to set up manually:

1. Ensure Node.js 18+ is installed
2. Add the MCP server to your tool's config:

```json
{
  "mcpServers": {
    "chub": {
      "command": "npx",
      "args": ["-y", "@aisuite/chub", "mcp"],
      "env": {
        "CHUB_TELEMETRY": "0",
        "CHUB_FEEDBACK": "1"
      }
    }
  }
}
```

Config file locations:
- **Claude Code**: `~/.claude/settings.json` (under `mcpServers`)
- **Claude Desktop**: `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS)
- **Cursor**: `~/.cursor/mcp.json` (global) or `.cursor/mcp.json` (per-project)

See the skill's [MCP setup reference](../skills/external-api-docs/references/mcp-setup.md) for full details.

### (Optional) Global CLI install

For using context-hub directly from the terminal (outside the agent):

```bash
npm install -g @aisuite/chub
```

### (Optional) Persistent telemetry opt-out

The MCP server disables telemetry via environment variables. For CLI usage, add to your shell profile:

```bash
export CHUB_TELEMETRY=0
export CHUB_FEEDBACK=1
```

`CHUB_TELEMETRY=0` disables passive usage analytics (PostHog). `CHUB_FEEDBACK=1` enables the `chub feedback` command for rating docs — an explicit agent action, not passive tracking. Set to `0` to disable if you don't want to send ratings to context-hub.

## How It Works

Once `chub` is installed, the `external-api-docs` skill activates automatically when the agent detects external API work. No explicit invocation needed — just work naturally.

### Automatic activation

The skill triggers when you:

- Ask the agent to write integration code ("integrate with the Stripe API")
- Debug an API error ("this endpoint returns 422 but I'm sending the right params")
- Evaluate a library ("what auth methods does the Supabase SDK support?")
- Request current docs ("look up the FastAPI response model syntax")

### What the agent does

```
1. Search     →  chub search "stripe" --json
2. Fetch      →  chub get stripe/api --lang python
3. Read       →  Selective sections from the fetched doc
4. Code       →  Write integration code grounded in current docs
5. Annotate   →  Note any gotchas for future sessions
```

The agent fetches large docs to a file and reads selectively, preserving the context window for other skills and your conversation.

## Workflow Examples

### Example 1: Writing an API integration

```
You:   "Add Stripe payment processing to the checkout endpoint"

Agent: [skill activates, searches chub for Stripe docs]
       [fetches stripe/api --lang python to tmp/api-docs/]
       [reads the relevant sections on PaymentIntents]
       [writes code using current endpoint signatures and auth patterns]
```

### Example 2: Debugging a stale API call

```
You:   "The OpenAI chat completion is returning errors after their latest update"

Agent: [skill activates, fetches openai/chat-api --lang python]
       [compares current API signatures against the code]
       [identifies the deprecated parameter and suggests the fix]
```

### Example 3: Evaluating an SDK

```
You:   "What auth methods does Supabase support for server-side use?"

Agent: [skill activates, searches chub for Supabase]
       [fetches the auth section of the docs]
       [presents a summary of server-side auth options with trade-offs]
```

### Example 4: Pipeline usage (researcher agent)

During a full pipeline run, the researcher agent uses context-hub when investigating external APIs:

```
You:   "Research what's needed to integrate with the Shopify Storefront API"

Agent: [launches researcher]
       [researcher activates external-api-docs skill]
       [searches chub for Shopify docs, fetches relevant entries]
       [incorporates current API details into RESEARCH_FINDINGS.md]
```

## Annotations: The Learning Loop

When the agent discovers something the docs got wrong or a non-obvious gotcha, it annotates the entry:

```bash
chub annotate stripe/api "Note: v2 PaymentIntents require idempotency keys for retries. Omitting causes silent duplicate charges."
```

This annotation auto-appends to every future fetch of that entry. Over time, your local annotations accumulate corrections and tips specific to your usage, making each fetch more valuable than the last.

## Fallback Hierarchy

When context-hub doesn't have coverage for a library, the agent falls back in order:

1. **context-hub** — curated, LLM-optimized docs (highest signal)
2. **Local annotations** — your past learnings about this API
3. **Memory MCP** — cross-session intelligence from prior work
4. **Web search** — official docs, GitHub READMEs
5. **Training data** — last resort; agent flags uncertainty

## Token Budget Awareness

API docs can be large (10K-50K+ tokens). The skill teaches agents to manage this:

- Fetch the entry file for an overview (~3K-10K tokens)
- Use `--file` for targeted reference files (~1K-5K tokens each)
- Write to disk (`-o`) for large docs and read selectively
- Never fetch `--full` unless explicitly approved

This preserves the context window for Praxion's behavioral skills and your conversation.

## Trust Tiers

Not all context-hub content is equal:

| Tier | Meaning | When to prefer |
|------|---------|----------------|
| `official` | Written by the vendor (e.g., Stripe writes Stripe docs) | Always — highest accuracy |
| `maintainer` | Written by core team or verified maintainer | Default choice |
| `community` | Community-contributed | Use with caution; cross-check critical details |

Filter with `chub search "stripe" --source official,maintainer` to exclude lower-confidence entries.

## Provider Architecture

context-hub is the default provider, but the skill is designed to support additional providers in the future. The methodology (search, fetch targeted content, file-based context, annotate, fallback) is provider-independent. If a better registry emerges, it slots in alongside or instead of context-hub without changing the workflow.

## Further Reading

- [Skill reference](../skills/external-api-docs/SKILL.md) — full methodology and pipeline integration
- [context-hub CLI reference](../skills/external-api-docs/references/context-hub.md) — commands, config, telemetry controls
- [MCP setup](../skills/external-api-docs/references/mcp-setup.md) — server configuration per tool
- [context-hub repo](https://github.com/andrewyng/context-hub) — source, content contributions, community
