# Python MCP Development

Python-specific implementation guide for MCP servers. Load alongside
the generic [MCP Server Development](../SKILL.md) skill.

**Related skills:**
- [Python Development](../../python-development/SKILL.md) -- type hints, testing, code quality, async patterns
- [Python Project Management](../../python-prj-mgmt/SKILL.md) -- uv/pixi setup, dependency management

## Table of Contents

- [SDK Landscape](#sdk-landscape)
- [Quickstart](#quickstart)
- [Core Primitives -- Python Implementation](#core-primitives----python-implementation)
  - [Tools](#tools)
  - [Structured Output](#structured-output)
  - [Resources](#resources)
  - [Prompts](#prompts)
- [Transports -- Python Configuration](#transports----python-configuration)
  - [Mounting on Starlette](#mounting-on-starlette)
- [Server Composition](#server-composition)
- [Lifespan -- Startup/Shutdown Resources](#lifespan----startupshutdown-resources)
- [Logging Setup](#logging-setup)
- [Testing](#testing)
  - [pytest with In-Memory Client](#pytest-with-in-memory-client)
  - [MCP Inspector](#mcp-inspector)
- [Client Integration -- Python Examples](#client-integration----python-examples)
- [Project Structure](#project-structure)
- [Deployment](#deployment)
- [CLI Quick Reference](#cli-quick-reference)
- [Bundles -- Python Examples](#bundles----python-examples)
- [Common Pitfalls -- Python-Specific](#common-pitfalls----python-specific)
- [Resources](#resources-1)

## SDK Landscape
<!-- last-verified: 2026-05-25 -->

Two options for building MCP servers in Python:

| Option | Package | When to Use |
|--------|---------|-------------|
| **Official SDK** | `mcp[cli]` | Default choice. Bundled FastMCP at `mcp.server.fastmcp` |
| **FastMCP standalone** | `fastmcp` | Need composition, proxying, or advanced features beyond the SDK |

**Version pinning** (production):
```toml
# Official SDK v1.x (current; latest 1.27.x — recommended for production)
dependencies = ["mcp[cli]>=1.25,<2"]

# FastMCP standalone v3 (current stable line; latest 3.3.x)
dependencies = ["fastmcp>=3,<4"]
```

The SDK requires **Python 3.10+**. Target **3.13+** for new projects.

### SDK Version Details

| SDK | Version | Status |
|-----|---------|--------|
| `mcp` | v1.x | **Production recommended** (latest 1.27.x). Pin `>=1.25,<2` |
| `mcp` | v2 | In development; not yet released on PyPI |
| `fastmcp` | v3.x | **Current stable** (latest 3.3.x). Pin `>=3,<4` |
| `fastmcp` | v2.x | Legacy/maintenance — prior stable line |

The official `mcp` v1.x will receive bug fixes and security updates for 6+ months after v2 ships.

**v1 vs v2 key differences:**

| Aspect | v1.x | v2 |
|--------|------|-----|
| High-level API | `FastMCP` at `mcp.server.fastmcp` | `MCPServer` at `mcp.server.mcpserver` |
| Structured output | Not built-in | Native Pydantic, TypedDict, dataclass |
| Transports | stdio, SSE | stdio, Streamable HTTP |
| Elicitation | Not available | Form mode and URL mode |

**FastMCP standalone history:**

- **FastMCP 1.0** -- incorporated into the official SDK in 2024 (as `mcp.server.fastmcp`)
- **FastMCP 2.x** -- prior stable standalone line, extended beyond the SDK
- **FastMCP 3.x** -- current stable (latest 3.3.x); adds providers, transforms, hot reload, background tasks

Migration from SDK-bundled to standalone is often just changing the import:
```python
# From SDK-bundled:
from mcp.server.fastmcp import FastMCP
# To standalone:
from fastmcp import FastMCP
```

## Quickstart

```bash
uv init --package mcp-server-demo
cd mcp-server-demo
uv add "mcp[cli]"
```

```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("Demo")

@mcp.tool()
def add(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b

@mcp.resource("greeting://{name}")
def get_greeting(name: str) -> str:
    """Get a personalized greeting."""
    return f"Hello, {name}!"

@mcp.prompt()
def review_code(code: str, language: str = "python") -> str:
    """Generate a code review prompt."""
    return f"Please review this {language} code:\n\n```{language}\n{code}\n```"

if __name__ == "__main__":
    mcp.run(transport="streamable-http")
```

Run and test:
```bash
uv run mcp dev src/server.py          # Inspector at localhost:6274
uv run mcp run src/server.py          # Direct execution (stdio)
```

## Core Primitives -- Python Implementation

### Tools

Tools perform computation and side effects. The LLM invokes them.

```python
from mcp.server.fastmcp import Context, FastMCP
from mcp.server.session import ServerSession

mcp = FastMCP("Tools Example")

@mcp.tool()
def search_database(query: str, limit: int = 10) -> list[dict]:
    """Search the database with a query string."""
    return db.execute(query, limit=limit)

@mcp.tool()
async def long_task(name: str, ctx: Context[ServerSession, None], steps: int = 5) -> str:
    """Task with progress reporting."""
    for i in range(steps):
        await ctx.report_progress(progress=(i + 1) / steps, total=1.0)
        await ctx.info(f"Step {i + 1}/{steps}")
    return f"Task '{name}' completed"
```

### Structured Output

Return Pydantic models, TypedDicts, or dataclasses for typed results:

```python
from pydantic import BaseModel, Field

class WeatherData(BaseModel):
    temperature: float = Field(description="Temperature in Celsius")
    humidity: float = Field(description="Humidity percentage")
    condition: str

@mcp.tool()
def get_weather(city: str) -> WeatherData:
    """Get weather for a city."""
    return WeatherData(temperature=22.5, humidity=45.0, condition="sunny")
```

### Resources

Resources provide data to LLMs (like GET endpoints). No significant side effects.

```python
@mcp.resource("config://settings")
def get_settings() -> str:
    """Application settings."""
    return '{"theme": "dark", "debug": false}'

@mcp.resource("file://docs/{path}")
def read_doc(path: str) -> str:
    """Read a document by path."""
    return Path(f"docs/{path}").read_text()
```

### Prompts

Prompts define structured interaction patterns for LLMs.

```python
@mcp.prompt()
def analyze_data(dataset: str, focus: str = "trends") -> str:
    """Generate a data analysis prompt."""
    return f"Analyze the '{dataset}' dataset, focusing on {focus}."
```

## Transports -- Python Configuration

| Transport | Use Case | Command |
|-----------|----------|---------|
| **stdio** | Local development, Claude Desktop | `mcp.run()` (default) |
| **Streamable HTTP** | Production, remote clients | `mcp.run(transport="streamable-http")` |

SSE is deprecated. Use streamable HTTP for all new HTTP-based servers.

### Mounting on Starlette

Multiple servers on a single Starlette application:

```python
from starlette.applications import Starlette
from starlette.routing import Mount

app = Starlette(routes=[
    Mount("/api", api_mcp.streamable_http_app()),
    Mount("/admin", admin_mcp.streamable_http_app()),
])
```

## Server Composition

### FastMCP import and mount

Two composition methods for breaking large servers into modules:

```python
from fastmcp import FastMCP

main = FastMCP("Main")
analytics = FastMCP("Analytics")

# import_server — one-time copy with prefix (static)
main.import_server(analytics, prefix="analytics")

# mount — live link with delegation (dynamic)
main.mount("analytics", analytics)
```

### Proxy Pattern

Bridge transports or aggregate remote servers behind a local entry point:

```python
from fastmcp import FastMCP, Client

proxy = FastMCP.as_proxy(Client("http://remote-server/mcp"))
```

### Multiple Servers on Starlette (named paths)

```python
from starlette.applications import Starlette
from starlette.routing import Mount
from mcp.server.fastmcp import FastMCP

echo = FastMCP("Echo")
math = FastMCP("Math")

app = Starlette(routes=[
    Mount("/echo", echo.streamable_http_app()),
    Mount("/math", math.streamable_http_app()),
])
# Clients connect to /echo/mcp and /math/mcp
```

## Lifespan -- Startup/Shutdown Resources

```python
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

@dataclass
class AppContext:
    db: Database

@asynccontextmanager
async def app_lifespan(server: FastMCP) -> AsyncIterator[AppContext]:
    db = await Database.connect()
    try:
        yield AppContext(db=db)
    finally:
        await db.disconnect()

mcp = FastMCP("My App", lifespan=app_lifespan)

@mcp.tool()
def query(ctx: Context[ServerSession, AppContext]) -> str:
    """Query using the shared database connection."""
    return ctx.request_context.lifespan_context.db.query()
```

## Logging Setup

For **stdio servers**, `print()` corrupts JSON-RPC messages. Always log to stderr:

```python
import logging
import sys

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)
```

For HTTP servers, standard output logging is fine.

## Testing

### pytest with In-Memory Client

Test tools directly without subprocess overhead:

```python
import pytest
from mcp.server.fastmcp import FastMCP

@pytest.fixture
async def client():
    from fastmcp import Client  # or test with call_tool directly
    async with Client(mcp) as c:
        yield c

@pytest.mark.asyncio
async def test_add_tool(client):
    result = await client.call_tool("add", {"a": 2, "b": 3})
    assert result[0].text == "5"
```

Add to `pyproject.toml`:
```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
```

### MCP Inspector

```bash
uv run mcp dev src/server.py                    # Bundled Inspector
npx -y @modelcontextprotocol/inspector          # Standalone Inspector
```

Generic Inspector documentation is in the [MCP Server Development](../SKILL.md) skill.

## Client Integration -- Python Examples

**Claude Desktop -- automatic registration:**
```bash
uv run mcp install src/server.py --name "My Server"
```

**Claude Desktop -- manual** (`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS):
```json
{
  "mcpServers": {
    "my-server": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/server", "mcp", "run", "server.py"]
    }
  }
}
```

**Claude Code:**
```bash
# stdio server
claude mcp add my-server -- uv run /path/to/server.py

# Scope: user (all projects), local (default, this project), project (.mcp.json, shareable)
claude mcp add my-server --scope project -- uv run server.py
```

## Project Structure

```
mcp-server-myproject/
├── pyproject.toml
├── README.md
├── src/
│   └── mcp_server_myproject/
│       ├── __init__.py
│       ├── server.py          # FastMCP instance + primitives
│       └── py.typed
└── tests/
    ├── conftest.py
    └── test_server.py
```

**pyproject.toml essentials:**
```toml
[project]
name = "mcp-server-myproject"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = ["mcp[cli]>=1.25,<2"]

[project.scripts]
mcp-server-myproject = "mcp_server_myproject.server:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[dependency-groups]
dev = ["pytest>=8.0", "pytest-asyncio>=0.24", "ruff>=0.7", "pyright>=1.1"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
```

## Deployment

### Docker

```dockerfile
FROM python:3.13-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY . .
CMD ["uv", "run", "mcp", "run", "server.py"]
```

Key practices:
- Multi-stage builds for smaller images
- Multi-platform images (amd64 + arm64)
- Never hardcode API keys -- use environment variables or Docker secrets
- Set memory and CPU limits

### PyPI Distribution

Distribute as a standard Python package:

```toml
[project.scripts]
mcp-server-myproject = "mcp_server_myproject.server:main"
```

Install with `uv tool install mcp-server-myproject` or `pip install mcp-server-myproject`.

### CI/CD (GitHub Actions)

```yaml
- uses: astral-sh/setup-uv@v7
  with:
    enable-cache: true

- run: uv sync --all-extras --dev
- run: uv run pytest
- run: uv run ruff check .
- run: uv run pyright src/
```

## CLI Quick Reference

```bash
uv run mcp dev server.py             # Dev mode with Inspector
uv run mcp run server.py             # Run directly (stdio)
uv run mcp install server.py         # Register with Claude Desktop
```

## Bundles -- Python Examples

**Python bundle (uv runtime -- recommended):**

```text
my-server.mcpb (ZIP)
├── manifest.json
├── pyproject.toml        # Dependencies declared here
└── src/
    └── server.py
```

**manifest.json:**

```json
{
  "manifest_version": "0.4",
  "name": "my-mcp-server",
  "version": "1.0.0",
  "description": "My MCP server",
  "author": { "name": "Your Name" },
  "server": {
    "type": "uv",
    "entry_point": "src/server.py"
  }
}
```

The `uv` server type lets the host manage Python and dependencies automatically -- no need to bundle packages. For compiled dependencies, this is the only portable Python option.

**Python bundle (traditional -- pre-bundled packages):**

```text
my-server.mcpb (ZIP)
├── manifest.json
├── server/
│   ├── main.py
│   └── utils.py
├── lib/                  # Pre-bundled packages
└── requirements.txt
```

**Key considerations for Python bundles:**

- **`uv` type is experimental** (v0.4+) but is the only portable option for compiled dependencies
- **Traditional `python` type** cannot portably bundle compiled packages (e.g., pydantic, numpy)
- **Node.js is recommended** by the spec for widest compatibility -- it ships with Claude Desktop
- The MCP Python SDK has no built-in bundle support -- use the `@anthropic-ai/mcpb` npm CLI
- `.mcpbignore` works like `.gitignore` to exclude files from the archive

## Common Pitfalls -- Python-Specific

- **Use `logging` to stderr, not `print()`** -- `print()` in stdio servers corrupts JSON-RPC messages
- **Not testing with pytest** -- use in-memory clients, not manual chat testing
- **Missing `asyncio_mode`** -- add `asyncio_mode = "auto"` to `pyproject.toml` `[tool.pytest.ini_options]`

## Resources

### Official Python

- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk) -- Official SDK repository
- [Build a Server Tutorial](https://modelcontextprotocol.io/docs/develop/build-server) -- Official quickstart
- [create-python-server Template](https://github.com/modelcontextprotocol/create-python-server)

### FastMCP

- [FastMCP Documentation](https://gofastmcp.com/) -- Standalone framework documentation
- [FastMCP GitHub](https://github.com/jlowin/fastmcp)
- [FastMCP Testing Patterns](https://gofastmcp.com/patterns/testing)
- [Stop Vibe-Testing Your MCP Server](https://www.jlowin.dev/blog/stop-vibe-testing-mcp-servers)

### Tutorials

- [Real Python: MCP Server Tutorial](https://realpython.com/python-mcp/)
- [DigitalOcean: MCP Server -- Everything I Wish I'd Known on Day One](https://www.digitalocean.com/community/tutorials/mcp-server-python)
- [Microsoft MCP for Beginners](https://github.com/microsoft/mcp-for-beginners)
- [15 Best Practices for Building MCP Servers in Production](https://thenewstack.io/15-best-practices-for-building-mcp-servers-in-production/)
