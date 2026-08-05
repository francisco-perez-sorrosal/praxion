# MCP SDK v1.x — Legacy Line and Migration

Support policy and v1→v2 migration for the official MCP SDKs. Load on demand from
[contexts/python.md](../contexts/python.md) or [contexts/typescript.md](../contexts/typescript.md).
Back to [SKILL.md](../SKILL.md).

Both official SDKs went v2-stable in late July 2026 alongside the **2026-07-28** MCP
specification. v1.x did not become wrong — it became *legacy*. This file states what that
means concretely so a decision to stay on v1 is a decision, not an accident.

## Support Status

| SDK | v1 latest | v1 status | v2 stable since |
|---|---|---|---|
| `mcp` (Python) | 1.29.0 | Critical bug fixes + security patches on the `v1.x` branch | 2.0.0 — 2026-07-28 |
| `@modelcontextprotocol/sdk` (TypeScript) | 1.30.0 | Bug fixes + security updates for **at least 6 months** after v2's release | 2.0.0 — 2026-07-27 |

The TypeScript window is explicit and dates from 2026-07-27, so it runs through **at least
~2027-01**. The Python project commits to critical fixes without publishing an end date —
which is weaker, not stronger: an unbounded promise with no date is harder to plan against
than a bounded one.

**Neither line receives new protocol features.** v1 implements the pre-2026-07-28 spec
revision. Anything the current revision added is v2-only.

## When staying on v1 is correct

- An existing server works and nothing needs the new spec revision.
- A dependency pins `mcp<2` or `@modelcontextprotocol/sdk@^1` — migrate when it moves.
- You need a framework adapter not yet ported.

## When to move

- New servers — start on v2.
- You need anything from the 2026-07-28 spec revision.
- **TypeScript specifically:** v2's Standard Schema support (Zod v4, Valibot, ArkType)
  dissolves the Zod v3/v4 dual-copy problem that constrains v1. If that split is causing
  pain, migration is the fix.

## Python: v1 → v2

The high-level API moved and was renamed.

| | v1.x | v2 |
|---|---|---|
| Import | `from mcp.server.fastmcp import FastMCP` | `from mcp.server import MCPServer` |
| Construct | `mcp = FastMCP("Demo")` | `mcp = MCPServer("Demo")` |
| Client | — | `from mcp import Client` |
| Structured output | Not built-in | Native Pydantic / TypedDict / dataclass |
| Transports | stdio, SSE | stdio, Streamable HTTP |
| Elicitation | Not available | Form mode and URL mode |

`@mcp.tool()`, `@mcp.resource(...)`, and `@mcp.prompt()` keep their decorator shape, so
straightforward servers often migrate by changing the import and the class name.

**Do not confuse two different migrations.** Moving from the SDK-bundled FastMCP to the
standalone `fastmcp` package is an import swap on the *v1* API:

```python
from mcp.server.fastmcp import FastMCP   # SDK-bundled (v1)
from fastmcp import FastMCP              # standalone
```

That is unrelated to the v1→v2 SDK migration above, and standalone `fastmcp` tracks its own
version line (3.x current).

## TypeScript: v1 → v2

v2 **split the monolith into per-role packages**, so this is a package change, not a
semver bump. There is no 2.x published under the `@modelcontextprotocol/sdk` name.

| | v1.x | v2 |
|---|---|---|
| Server package | `@modelcontextprotocol/sdk` | `@modelcontextprotocol/server` |
| Client package | `@modelcontextprotocol/sdk` | `@modelcontextprotocol/client` |
| Server import | `@modelcontextprotocol/sdk/server/mcp.js` | `@modelcontextprotocol/server` |
| Stdio import | `@modelcontextprotocol/sdk/server/stdio.js` | `@modelcontextprotocol/server/stdio` |
| Adapters | in-package | `@modelcontextprotocol/node` / `express` / `hono` / `fastify` |
| Schema | Zod (`^3.25 \|\| ^4`) | Standard Schema — Zod v4, Valibot, ArkType, … |

Note the `.js` extension disappears from the v2 import paths — v2 exposes subpath exports
rather than deep file paths, so the ESM `.js`-suffix rule does not apply to SDK imports (it
still applies to your own relative imports).

## Verification

Version claims here are registry-checked, not remembered. Re-check before relying on them:

```bash
curl -s https://pypi.org/pypi/mcp/json | jq -r .info.version
curl -s https://registry.npmjs.org/@modelcontextprotocol/sdk | jq -r '."dist-tags".latest'
curl -s https://registry.npmjs.org/@modelcontextprotocol/server | jq -r '."dist-tags".latest'
```
