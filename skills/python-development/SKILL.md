---
name: python-development
description: Modern Python development conventions covering type hints, testing with pytest, code quality tools (ruff, mypy, pyright), data modeling (dataclasses, Pydantic), async patterns, and error handling. Use when writing Python code, implementing tests, configuring linting or formatting, choosing between dataclasses and Pydantic, working with structural pattern matching, or setting up pytest fixtures and parametrize. Also activates for Python coding tasks, Python testing questions, ruff formatting or linting issues, mypy type checking, and pytest configuration work.
allowed-tools: [Read, Write, Edit, Glob, Grep, Bash]
compatibility: Claude Code
---

# Modern Python Development

Comprehensive guidance for Python development following pragmatic, production-ready practices.

**Satellite files** (loaded on-demand):

- [references/testing-and-tooling.md](references/testing-and-tooling.md) -- pytest patterns, pyproject.toml config, pre-commit setup
- [references/patterns-and-examples.md](references/patterns-and-examples.md) -- dataclasses, Pydantic, protocols, context managers, pattern matching, async, error handling

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

**Target Python 3.13+** for new projects:
- Better error messages
- Faster performance
- Modern type hint syntax (`X | Y`, `Self`)
- Exception groups

**For libraries**, support Python 3.10+ unless specific constraints require older versions.

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

**Formatter**: Use ruff for formatting and linting:

```toml
[tool.ruff]
line-length = 100
target-version = "py313"

[tool.ruff.lint]
select = ["E", "F", "I", "N", "UP", "B", "A", "C4", "PT"]
ignore = ["E501"]  # Line length handled by formatter

[tool.ruff.format]
quote-style = "double"
indent-style = "space"
```

## Testing with pytest

Use pytest with clear test names that describe behavior. One test file per module, fixtures for shared setup, parametrize for multiple similar tests.

--> See [references/testing-and-tooling.md](references/testing-and-tooling.md) for detailed examples, parametrize patterns, and running commands.

## Common Patterns

Key patterns: **dataclasses** (frozen) for internal data, **Pydantic** for external input validation, **Protocols** for structural typing, **context managers** for resource lifecycle, **structural pattern matching** (3.10+).

Use dataclasses for simple containers with no validation; Pydantic when parsing external input, needing type coercion, or building APIs.

--> See [references/patterns-and-examples.md](references/patterns-and-examples.md) for code examples and the full dataclasses-vs-Pydantic decision guide.

## Async Patterns

Use `async/await` with `httpx` for HTTP, `asynccontextmanager` for resource lifecycle. Test with `pytest-asyncio`. Common libraries: `asyncio`, `httpx`, `aiohttp`, `anyio`.

--> See [references/patterns-and-examples.md](references/patterns-and-examples.md#async-patterns) for async code examples.

## Code Quality Tools

Configure mypy (strict mode), pytest, and coverage in `pyproject.toml`. Use pre-commit hooks with ruff and mypy for automated quality gates.

--> See [references/testing-and-tooling.md](references/testing-and-tooling.md#code-quality-tools) for full `pyproject.toml` configuration and pre-commit setup.

## Error Handling

Be explicit about error conditions. Create domain-specific exception classes, chain exceptions with `from`, and distinguish recoverable from fatal errors.

--> See [references/patterns-and-examples.md](references/patterns-and-examples.md#error-handling) for error handling examples.

## Development Workflow

1. **Initialize project** (see [Python Project Management](../python-prj-mgmt/SKILL.md))
2. **Set up tools**: ruff, mypy/pyright, pytest
3. **Write tests first** for critical functionality
4. **Implement** with type hints
5. **Run checks**: `<tool> run ruff check . && <tool> run mypy src/ && <tool> run pytest`
6. **Iterate** in small increments

## Quick Commands

For package management commands, see the [Python Project Management](../python-prj-mgmt/SKILL.md) skill.

```bash
# Code quality
<tool> run ruff check .             # Lint
<tool> run ruff format .            # Format
<tool> run mypy src/                # Type check

# Testing
<tool> run pytest                   # Run tests
<tool> run pytest --cov             # With coverage
<tool> run pytest -x                # Stop on first failure
<tool> run pytest --lf              # Run last failed
```
