---
name: python-development
description: >
  Python development conventions: type hints, pytest, code quality tools (ruff,
  mypy, pyright), data modeling (dataclasses, Pydantic), async patterns, error
  handling, structural pattern matching, version-specific idioms (3.10-3.14+), and
  a curated battle-tested library catalog by project archetype. Triggers: writing
  Python code, implementing tests, configuring linting/formatting, choosing between
  dataclasses and Pydantic, pytest fixtures and parametrize, ruff formatting/linting,
  mypy type checking, pytest configuration, picking a library for a new capability
  (web framework, ORM, CLI parsing, dataframes, async task queue, logging, config).
allowed-tools: [Read, Write, Edit, Glob, Grep, Bash]
compatibility: Claude Code
staleness_sensitive_sections:
  - "Python Version Guidelines"
  - "Library Catalog by Archetype"
staleness_threshold_days: 90
---

# Modern Python Development

Comprehensive guidance for Python development following pragmatic, production-ready practices.

**Satellite files** (loaded on-demand):

- [references/testing-and-tooling.md](references/testing-and-tooling.md) -- pytest patterns, pyproject.toml config, pre-commit setup
- [references/patterns-and-examples.md](references/patterns-and-examples.md) -- dataclasses, Pydantic, protocols, context managers, pattern matching, async, error handling
- [references/essential-libraries.md](references/essential-libraries.md) -- curated, battle-tested libraries by project archetype (web API, CLI, data/ML, async services, general-purpose, scripting)
- For advanced pytest strategy (conftest architecture, hypothesis, fixture composition, coverage philosophy), see the [testing-strategy](../testing-strategy/SKILL.md) skill

## Gotchas

Non-obvious pitfalls that cause silent failures or confusing errors:

- **ruff format vs lint line-length conflict.** `ruff format` enforces its own line length independently of `[tool.ruff] line-length`. If `line-length` in `[tool.ruff]` and `[tool.ruff.format]` differ (or if `[tool.ruff.lint]` selects `E501`), formatting and linting fight each other in a cycle. Set the same `line-length` under `[tool.ruff]` and either ignore `E501` in lint (let the formatter own line wrapping) or ensure both agree on the limit.
- **mypy strict mode false positives with third-party libraries.** Enabling `strict = true` globally triggers errors in untyped third-party packages (`error: ... has no attribute ...`, missing type stubs). Fix with per-module overrides in `pyproject.toml` (`[[tool.mypy.overrides]]` with `module` and `ignore_missing_imports = true`), not blanket `# type: ignore` comments that suppress real errors.
- **pytest fixture scope pollution.** A `session`-scoped fixture that mutates state (e.g., populates a database, modifies a class attribute) bleeds across tests, causing order-dependent failures. Default to `function` scope. Use `session` only for truly read-only, expensive setup (e.g., spinning up a test server), and pair it with cleanup in a finalizer or `yield`.
- **pytest-asyncio mode configuration.** `pytest-asyncio` defaults to `auto` mode in recent versions but older pinned versions default to `strict`, requiring explicit `@pytest.mark.asyncio` on every async test. Set `asyncio_mode = "auto"` in `[tool.pytest.ini_options]` to avoid silent test skipping where async tests appear to pass (collected but never awaited).
- **`from __future__ import annotations` breaks runtime type access.** This import makes all annotations strings (PEP 563), which breaks code that inspects types at runtime -- Pydantic v1, `dataclasses.fields()` type checks, `isinstance` on `get_type_hints()`. Pydantic v2 handles it, but verify before adding the import to modules that use runtime type introspection.

## Core Principles

**Pragmatic Python**: Write code that is clear, maintainable, and purposeful. Every line should have a reason to exist.

**Type Safety**: Use type hints throughout. They serve as inline documentation and catch errors early.

**Testing**: Test critical paths and edge cases. Use pytest with clear test names that describe behavior.

**Code Quality**: Maintain consistency with automated tools. Let tools handle formatting.

**Project Management**: Commands in this skill use `<tool>` as a placeholder for your project management tool (pixi or uv). See the [Python Project Management](../python-prj-mgmt/SKILL.md) skill for environment setup, dependency management, and choosing between pixi (default) and uv.

## Python Version Guidelines
<!-- last-verified: 2026-07-29 -->

**Target the latest stable CPython for new projects** (3.14 as of this verification date)
unless a dependency forces a lower floor. **For libraries**, support 3.10+ unless specific
constraints require older versions.

Idiom-changing features by version — adopt each once the project's minimum supported
version allows it; earlier projects keep the prior idiom rather than backporting syntax:

| Version | What changed idiomatically |
|---|---|
| 3.10 | Structural pattern matching (`match`/`case`); `X \| Y` union syntax; `X \| None` instead of `Optional[X]` |
| 3.11 | Exception groups + `except*` (PEP 654) — first-class handling of multiple unrelated exceptions, notably from `asyncio.TaskGroup` failures; `tomllib` added to stdlib |
| 3.12 | **PEP 695 generic syntax** — `class Box[T]`, `def first[T](xs: list[T]) -> T`, `type Alias[T] = ...` — eliminates `TypeVar`/`Generic` boilerplate and scopes type params to the declaring class/function. The biggest idiom shift since union syntax. On 3.10/3.11, keep using `TypeVar`/`Generic` |
| 3.14 | Template strings (`t"..."`, PEP 750) — a `t"..."` literal returns a structured `Template` object (static parts + interpolations) instead of a plain `str`, enabling safe custom string-processing (SQL-injection-safe query builders, HTML-escaping templaters) without eval-like hacks |

**Free-threading (PEP 703/779) and the JIT are deployment/compatibility concerns, not
coding idioms.** Both remain non-default, opt-in builds as of 3.14 — treat them as "does
this project's C-extension dependency graph tolerate the free-threaded/JIT binary?", not
as a reason to change how code is written, unless the project explicitly targets
high-core-count CPU-bound parallelism.

## Project Structure

```text
project/
├── pyproject.toml          # Project metadata and dependencies
├── README.md              # Project documentation
├── src/
│   └── package_name/
│       ├── __init__.py
│       ├── module.py
│       └── py.typed      # Marker for type checking
├── tests/
│   ├── __init__.py
│   ├── conftest.py       # Pytest fixtures
│   └── test_module.py
└── .gitignore
```

## Type Hints

**Always use type hints** for function signatures and class attributes:

```python
from collections.abc import Sequence
from typing import Protocol

def process_items(items: Sequence[str], *, limit: int = 10) -> list[str]:
    """Process items with an optional limit."""
    return list(items[:limit])

class Processor(Protocol):
    """Protocol for processors."""
    def process(self, data: str) -> str: ...
```

**Modern type hint patterns** (Python 3.10+):
- Use `list[T]`, `dict[K, V]`, `set[T]` instead of `List`, `Dict`, `Set`
- Use `X | Y` instead of `Union[X, Y]`
- Use `X | None` instead of `Optional[X]`
- Use `collections.abc` types for function parameters (more flexible)

**Type checking**: Use mypy or pyright:
```bash
<tool> run mypy src/
<tool> run pyright src/
```

## Code Style

**Formatter + linter**: Use ruff for both. The **canonical baseline** is shipped
as a single source of truth at [`assets/ruff-baseline.toml`](assets/ruff-baseline.toml)
and installed into a project's `pyproject.toml` by `/onboard-project` Phase 8e
(and `/new-project`) — every Python project gets it, idempotently, so the
linter/formatter mandate in [`coding-style.md`](../../rules/swe/coding-style.md)
is never vacuous. The baseline is:

```toml
[tool.ruff]
line-length = 100
target-version = "py311"   # safe modern floor — bump to the project's minimum

[tool.ruff.lint]
select = ["E", "F", "I", "N", "UP", "B", "A", "C4", "PT"]
ignore = ["E501"]  # Line length handled by formatter

[tool.ruff.format]
quote-style = "double"
indent-style = "space"
```

Edit the asset, not this excerpt, when changing the baseline — they must agree.
Every project also gets a universal `.editorconfig` (charset, newline, indent)
from the same onboarding phase; see [`coding-style.md`](../../rules/swe/coding-style.md)
§ Baseline Configuration.

## Testing with pytest

Use pytest with clear test names that describe behavior. One test file per module, fixtures for shared setup, parametrize for multiple similar tests.

--> See [references/testing-and-tooling.md](references/testing-and-tooling.md) for detailed examples, parametrize patterns, and running commands.

## Common Patterns

Key patterns: **dataclasses** (frozen) for internal data, **Pydantic** for external input validation, **Protocols** for structural typing, **context managers** for resource lifecycle, **structural pattern matching** (3.10+).

Use dataclasses for simple containers with no validation; Pydantic when parsing external input, needing type coercion, or building APIs.

--> See [references/patterns-and-examples.md](references/patterns-and-examples.md) for code examples and the full dataclasses-vs-Pydantic decision guide.

## Essential Libraries

Don't reinvent common functionality — a curated, battle-tested library likely already
solves it well. Check the catalog before hand-rolling something in the HTTP client, ORM,
validation, CLI, dataframe, logging, or config-management space.

--> See [references/essential-libraries.md](references/essential-libraries.md) for the
full catalog, organized by project archetype (web API, CLI, data/ML, async services,
general-purpose, scripting).

## Async Patterns

Use `async/await` with `httpx` for HTTP, `asynccontextmanager` for resource lifecycle. Test with `pytest-asyncio`. Common libraries: `asyncio`, `httpx`, `aiohttp`, `anyio`.

--> See [references/patterns-and-examples.md](references/patterns-and-examples.md#async-patterns) for async code examples.

## Code Quality Tools

Configure mypy (strict mode), pytest, and coverage in `pyproject.toml`. Use pre-commit hooks with ruff and mypy for automated quality gates.

The **canonical mypy baseline** is shipped as a single source of truth at
[`assets/mypy-baseline.toml`](assets/mypy-baseline.toml) and appended to a
project's `pyproject.toml` by `/onboard-project` Phase 8e (and `/new-project`)
when no `[tool.mypy]`/`[tool.pyright]` section exists — so the type-check mandate
in [`coding-style.md`](../../rules/swe/coding-style.md) § Baseline Configuration is
never vacuous, and the agent-readiness type-check criterion passes. The same phase
installs the canonical `.pre-commit-config.yaml` (file hygiene + ruff hooks + a
secret scanner). Edit those assets, not per-project copies, to evolve the baseline.

--> See [references/testing-and-tooling.md](references/testing-and-tooling.md#code-quality-tools) for full `pyproject.toml` configuration and pre-commit setup.

## Error Handling

Be explicit about error conditions. Create domain-specific exception classes, chain exceptions with `from`, and distinguish recoverable from fatal errors.

--> See [references/patterns-and-examples.md](references/patterns-and-examples.md#error-handling) for error handling examples.

## Development Workflow

1. **Initialize project** (see [Python Project Management](../python-prj-mgmt/SKILL.md))
2. **Set up tools**: ruff, mypy/pyright, pytest
3. **Write tests first** for critical functionality
4. **Implement** with type hints
5. **Run checks**: `<tool> run ruff format . && <tool> run ruff check --fix . && <tool> run mypy src/ && <tool> run pytest`
6. **Iterate** in small increments

## Quick Commands

For package management commands, see the [Python Project Management](../python-prj-mgmt/SKILL.md) skill.

```bash
# Code quality (order matters: format -> lint -> typecheck)
<tool> run ruff format .            # Format
<tool> run ruff check --fix .       # Lint (fix mode)
<tool> run mypy src/                # Type check

# Testing
<tool> run pytest                   # Run tests
<tool> run pytest --cov             # With coverage
<tool> run pytest -x                # Stop on first failure
<tool> run pytest --lf              # Run last failed
```

### Pipeline-Agent Compact Mode

When invoked from a pipeline agent (`implementer`, `test-engineer`, or any subagent operating under a `maxTurns` budget), prefer compact tool output. Verbose output compounds in cumulative agent context — every passing-test line written on turn N rides along inside turn N+1's input, making every later round-trip more expensive and pulling the agent closer to runtime-level token thresholds.

```bash
# Compact defaults — use these in pipeline runs
<tool> run pytest --tb=short -q                              # Tests: short tracebacks, suppress per-test dots/passes
<tool> run ruff check --fix --output-format concise .         # Lint: one line per finding, no source preview
<tool> run ruff format .                                      # Format: already terse — no flag change needed
<tool> run mypy src/                                          # Type check: terse by default — no flag change needed

# Escalate only when investigating a specific failure
<tool> run pytest --tb=long path/to/test_module.py::test_name  # Single failure deep-dive
<tool> run pytest -v path/to/test_module.py                    # Verbose for one targeted file
```

**Cost-of-verbosity reference**: a 50-test suite with `pytest -v` emits roughly 3–5k tokens; the same suite with `--tb=short -q` emits roughly 300–800 tokens for the same outcome. The savings compound on every subsequent agent turn that carries the test-run history. `ruff check --output-format concise` typically halves lint output relative to the default `full` format on codebases with many findings.

## Related Skills

- [`python-prj-mgmt`](../python-prj-mgmt/SKILL.md) — pixi and uv: project initialization, dependency management, environment setup. Use it to add whatever this skill's [essential-libraries.md](references/essential-libraries.md) recommends
- [`testing-strategy`](../testing-strategy/SKILL.md) — advanced pytest patterns: conftest architecture, hypothesis, fixture composition, coverage philosophy
