# Python Development

Conventions for modern Python development: type hints, testing with pytest, code quality tools (ruff, mypy, pyright), data modeling (dataclasses, Pydantic), async patterns, and project structure.

## When to Use

- Writing Python code in any project
- Setting up testing with pytest
- Configuring code quality tools (ruff, mypy, pyright)
- Choosing between dataclasses and Pydantic
- Structuring a Python package with `src` layout
- Debugging pytest fixture scope or asyncio mode issues

## Activation

Auto-triggers on Python development tasks: writing code, implementing tests, configuring linting/formatting, discussing language features.

Trigger explicitly by mentioning "python skill", "pytest", "ruff", "mypy", "pyright", "dataclasses", or "Pydantic".

## Skill Contents

- `SKILL.md` — core conventions: project structure, type hints, code style, async, error handling, gotchas, quick commands
- `references/patterns-and-examples.md` — dataclasses vs Pydantic decision guide, protocols, context managers, structural pattern matching, async, error handling examples
- `references/testing-and-tooling.md` — pytest fixtures, parametrize, ruff/mypy/pyright configuration, pre-commit setup

## Related Skills

- [`python-prj-mgmt`](../python-prj-mgmt/SKILL.md) — pixi/uv setup, dependency management, environment configuration
- [`testing-strategy`](../testing-strategy/SKILL.md) — advanced pytest: conftest architecture, hypothesis, fixture composition, coverage philosophy
- [`refactoring`](../refactoring/SKILL.md) — restructuring code, improving design, reducing coupling
