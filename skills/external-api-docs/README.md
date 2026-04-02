# External API Docs

Retrieve current, curated API documentation for external libraries and SDKs during development. Prevents hallucinated endpoints, stale parameters, and incorrect auth patterns by grounding agent knowledge in curated reference sources.

## When to Use

- Writing integration code against an external API (Stripe, OpenAI, AWS, FastAPI, etc.)
- Debugging API errors where responses don't match expectations
- Evaluating an SDK's capabilities, auth patterns, or versioning
- Looking up current endpoint signatures when training data may be stale

## Activation

Activates automatically when the agent detects external API work: writing integration code, debugging API responses, evaluating SDKs, or when the user asks for current API reference.

Trigger explicitly by mentioning "external API docs" or referencing the skill by name.

## Skill Contents

| File | Purpose |
|------|---------|
| `SKILL.md` | Core methodology: when to fetch, search strategies, token-aware retrieval, annotation persistence, fallback hierarchy, provider architecture |
| `references/context-hub.md` | context-hub provider: installation, configuration, CLI reference, telemetry controls, trust tiers |
| `references/mcp-setup.md` | Optional MCP server configuration for Claude Desktop, Claude Code, and Cursor |
| `README.md` | This file |

## Quick Start

1. Install the default provider: `npm install -g @aisuite/chub`
2. Search for docs: `CHUB_TELEMETRY=0 CHUB_FEEDBACK=1 chub search "stripe"`
3. Fetch a doc: `CHUB_TELEMETRY=0 CHUB_FEEDBACK=1 chub get stripe/api --lang python`

The skill teaches agents to follow this workflow automatically during implementation tasks.

## Related Skills

- [`claude-ecosystem`](../claude-ecosystem/) -- Claude API architecture, model selection, SDK guidance. Use together: `claude-ecosystem` for *what to use*, this skill for *current endpoint details*
- [`agentic-sdks`](../agentic-sdks/) -- Agent SDK patterns and multi-agent orchestration. This skill fetches current SDK signatures
- [`api-design`](../api-design/) -- API design methodology. This skill fetches current reference for APIs being integrated
