---
name: python-prj-mgmt
description: >
  Python project management with pixi and uv: project initialization, dependency
  management, pyproject.toml, lockfiles (pixi.lock, uv.lock), virtual environments,
  workspaces, CI/CD integration, conda vs PyPI packages. Defaults to pixi unless uv
  is explicitly requested. Triggers: setting up Python projects, managing
  dependencies, choosing between package managers.
allowed-tools: [Read, Write, Edit, Glob, Grep, Bash]
compatibility: Claude Code
staleness_sensitive_sections:
  - "Project Initialization"
  - "Dependency Management"
  - "Running Commands"
  - "CI/CD Integration"
  - "Package Manager Comparison"
  - "Command Quick Reference"
---

# Python Project Management

Managing Python projects with modern package managers and dependency tools. **Default: pixi — use pixi unless uv is explicitly requested.**

**Satellite files** (loaded on-demand):

- [references/pixi.md](references/pixi.md) -- pixi package manager: init, dependencies, tasks, environments, CI/CD
- [references/uv.md](references/uv.md) -- uv package manager: init, dependencies, workspaces, publishing

## Quick Reference

**Python Coding**: See the [Python Development](../python-development/SKILL.md) skill for type hints, testing patterns, code quality, and language best practices.

**Package Managers**:
- [pixi](references/pixi.md) - **Default** - conda+PyPI ecosystem, tasks, multi-language support
- [uv](references/uv.md) - Extremely fast PyPI-only installer and resolver

## When to Use Which

| Use **pixi** (default) when | Use **uv** (when requested) when |
|---|---|
| Multi-ecosystem projects (Python + system libraries) | Pure Python projects |
| ML/Data science (PyTorch, TensorFlow, NumPy, SciPy) | Need blazing fast installs (10-100x faster than pip) |
| Projects needing conda packages | pip/pip-tools migration |
| Cross-platform reproducibility | Minimal dependencies |
| Projects requiring C extensions or compiled libraries | Projects that don't need conda ecosystem |
| Teams already using conda/mamba | |

## Project Initialization
<!-- last-verified: 2026-05-01 -->

| | pixi (default) | uv |
|---|---|---|
| **Command** | `pixi init my-project --format pyproject` | `uv init my-project` |
| **Creates** | `pyproject.toml`, `src/my_project/`, `tests/`, `pixi.lock` | `pyproject.toml`, `README.md`, `.python-version` |
| **Gotcha** | Missing `--format pyproject` creates `pixi.toml` instead | Not pinning Python version — use `uv python pin` |

## Project Structure

```
project/
├── pyproject.toml          # Project metadata, dependencies, tool configs
├── pixi.lock              # Lockfile (pixi) or uv.lock (uv)
├── README.md              # Documentation
├── src/
│   └── package_name/
│       ├── __init__.py
│       ├── module.py
│       └── py.typed      # Type checking marker
├── tests/
│   ├── __init__.py
│   ├── conftest.py       # Pytest fixtures
│   └── test_module.py
└── .gitignore
```

## Dependency Management
<!-- last-verified: 2026-05-01 -->

| | pixi (default) | uv |
|---|---|---|
| **Add PyPI package** | `pixi add --pypi requests pandas` | `uv add requests pandas` |
| **Add conda package** | `pixi add numpy scipy pytorch` | N/A — PyPI only |
| **Add dev dependency** | `pixi add --pypi --feature dev pytest ruff mypy` | `uv add --dev pytest ruff mypy` |
| **Install / sync** | `pixi install` | `uv sync` |
| **Check latest version** | `pixi search <pkg>` (conda-forge) or `pixi search --channel pypi <pkg>` | `uv pip index versions <pkg>` |
| **Gotcha** | Mixing conda and PyPI incorrectly — use `--pypi` flag explicitly; set `system-requirements.cuda` for GPU; avoid mixing conda-forge with legacy pytorch channel | Forgetting to sync after adding dependencies |

### Freshness before pinning

Do not hardcode version constraints from memory — training-data cutoffs make remembered numbers stale, and a silently-old pin can propagate through lockfiles for months. Before adding a dependency:

- **Prefer resolver-picks-latest.** `pixi add <pkg>` and `uv add <pkg>` resolve to the latest compatible version at the moment of the call. Let them.
- **When an explicit constraint is required**, check first: `pixi search <pkg>` (conda-forge) or `uv pip index versions <pkg>` (PyPI) lists available versions; quote the current latest. Prefer ranges (`>=X.Y`) over exact pins unless reproducibility demands otherwise.
- **On inherited projects**, a quick `pixi update --dry-run` or `uv lock --upgrade --dry-run` surfaces how stale the lockfile is before you touch it.

This complements the `external-api-docs` skill (which handles *documentation* staleness) — together they cover both "is my API signature current?" and "is my pinned version current?".

## Running Commands
<!-- last-verified: 2026-05-01 -->

| | pixi (default) | uv |
|---|---|---|
| **Run script** | `pixi run python script.py` | `uv run python script.py` |
| **Run tests** | `pixi run pytest` | `uv run pytest` |
| **Type check** | `pixi run mypy src/` | `uv run mypy src/` |
| **Interactive shell** | `pixi shell` | Not needed — `uv run` auto-activates |
| **Gotcha** | — | Using venv activation instead of `uv run` (slower) |

## CI/CD Integration
<!-- last-verified: 2026-05-01 -->

GitHub Actions — pixi (default) and uv side-by-side:

```yaml
# pixi
- uses: prefix-dev/setup-pixi@v0.9.4
  with: { pixi-version: latest, cache: true }
- run: pixi install
- run: pixi run pytest
- run: pixi run mypy src/

# uv
- uses: astral-sh/setup-uv@v7
  with: { enable-cache: true }
- run: uv python install
- run: uv sync --all-extras --dev
- run: uv run pytest
- run: uv run mypy src/
```

## pyproject.toml Configuration

Both pixi and uv use `pyproject.toml` as the primary configuration file, following Python standards (PEP 621, PEP 735). The shared structure is identical; tool-specific sections differ.

### Shared pyproject.toml

```toml
[project]
name = "my-project"
version = "0.1.0"
description = "Project description"
authors = [{ name = "Your Name", email = "email@example.com" }]
requires-python = ">=3.11"
dependencies = [
    "requests>=2.31.0",
    "pandas>=2.0.0",
]

[dependency-groups]
dev = ["pytest>=7.4", "mypy>=1.7", "ruff>=0.1"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

For tool-specific `pyproject.toml` sections (`[tool.pixi.*]`, `[tool.uv]`), see the corresponding reference files: [pixi.md](references/pixi.md) and [uv.md](references/uv.md).

## Package Manager Comparison
<!-- last-verified: 2026-05-01 -->

| Feature | pixi | uv |
|---------|------|-----|
| **Speed** | Fast (parallel downloads) | Extremely fast (10-100x pip) |
| **Ecosystem** | conda + PyPI | PyPI only |
| **Config** | pyproject.toml | pyproject.toml |
| **Lockfile** | pixi.lock | uv.lock |
| **Python mgmt** | Via conda | Built-in (uv python) |
| **Multi-language** | Yes (R, C++, etc.) | Python only |
| **System libs** | Excellent (conda) | Limited (PyPI) |
| **ML frameworks** | Excellent | Good |
| **Pure Python** | Good | Excellent |
| **Maturity** | Mature (conda ecosystem) | New but stable |

## Command Quick Reference
<!-- last-verified: 2026-05-01 -->

For complete command references, see [pixi.md](references/pixi.md) and [uv.md](references/uv.md). The most common commands:

| Task | pixi | uv |
|------|------|-----|
| Initialize | `pixi init --format pyproject` | `uv init` |
| Add dependency | `pixi add --pypi pkg` | `uv add pkg` |
| Add conda dependency | `pixi add pkg` | N/A |
| Add dev dependency | `pixi add --pypi --feature dev pkg` | `uv add --dev pkg` |
| Install/sync | `pixi install` | `uv sync` |
| Run command | `pixi run cmd` | `uv run cmd` |
| Update lockfile | `pixi update` | `uv lock` |
| Dependency tree | `pixi tree` | `uv tree` |

## Best Practices

1. **Commit lockfiles** (`pixi.lock` or `uv.lock`) for reproducibility
2. **Use pyproject.toml** for all configuration
3. **Set Python version** explicitly in `requires-python`
4. **Organize dependencies** with dependency groups (dev, test, docs)
5. **Define tasks** for common operations (pixi)
6. **Version constraints**: Be specific for applications, flexible for libraries
7. **Keep configs clean**: Don't specify transitive dependencies

## Reference Files

- [pixi Reference](references/pixi.md) — Complete pixi guide: environments, tasks, ML workflows, troubleshooting
- [uv Reference](references/uv.md) — Complete uv guide: workspaces, build/publish, Python version management

## Related Skills

- [`python-development`](../python-development/SKILL.md) — type hints, testing with pytest, code quality tools, language patterns
- [`cicd`](../cicd/SKILL.md) — GitHub Actions CI/CD pipeline design beyond the quick-start snippets above
