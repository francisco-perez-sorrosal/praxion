# Python Project Management

Managing Python projects with modern package managers. Defaults to **pixi** unless uv is explicitly requested.

## When to Use

- Setting up a new Python project
- Managing dependencies (add, remove, update)
- Configuring `pyproject.toml` and dependency groups
- Choosing between pixi and uv
- Working with lockfiles (`pixi.lock`, `uv.lock`)
- CI/CD integration for Python projects

## Activation

Auto-triggers on project management tasks: initializing Python projects, managing dependencies, choosing package managers.

Trigger explicitly by mentioning "pixi", "uv", "pyproject.toml", "dependency management", or "python project management".

## Skill Contents

- `SKILL.md` — tool selection decision table, project init, dependency management, CI/CD snippets, pyproject.toml shared config, best practices
- `references/pixi.md` — complete pixi reference: conda+PyPI ecosystem, environments, tasks, ML workflows, troubleshooting
- `references/uv.md` — complete uv reference: fast installs, Python version management, workspaces, build/publish

## Related Skills

- [`python-development`](../python-development/SKILL.md) — type hints, testing with pytest, code quality tools, language patterns
- [`cicd`](../cicd/SKILL.md) — GitHub Actions CI/CD pipeline design beyond the quick-start snippets
