# uv Package Manager

Extremely fast Python package installer and resolver written in Rust. Complete uv reference for Python projects. Back to [SKILL.md](../SKILL.md).

## Table of Contents

- [Why uv?](#why-uv)
- [Installation](#installation)
- [Project Initialization](#project-initialization)
- [Configuration: pyproject.toml](#configuration-pyprojecttoml)
- [Virtual Environment Management](#virtual-environment-management)
- [Dependency Management](#dependency-management)
- [Running Commands](#running-commands)
- [Python Version Management](#python-version-management)
- [Package Installation](#package-installation)
- [Lockfile Management](#lockfile-management)
- [Project Structure Best Practices](#project-structure-best-practices)
- [Common Tasks](#common-tasks)
- [Working with Workspaces](#working-with-workspaces)
- [Build and Publish](#build-and-publish)
- [Scripts and Tools](#scripts-and-tools)
- [Cache Management](#cache-management)
- [CI/CD Integration](#cicd-integration)
- [Advanced Features](#advanced-features)
- [Migration from Other Tools](#migration-from-other-tools)
- [Troubleshooting](#troubleshooting)
- [Performance Tips](#performance-tips)
- [Best Practices](#best-practices)
- [Comparison: uv vs pip](#comparison-uv-vs-pip)
- [Additional Resources](#additional-resources)

## Why uv?

- **Blazing fast**: 10-100x faster than pip
- **Drop-in replacement**: Compatible with pip, pip-tools, and virtualenv
- **Unified tool**: Package management, virtual environments, and project scaffolding
- **Dependency resolution**: Smart resolver with better error messages
- **Python version management**: Install and manage Python versions

## Installation

```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Or with Homebrew
brew install uv

# Windows (PowerShell)
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

# With pip (if you must)
pip install uv
```

## Project Initialization

**New project**:
```bash
uv init my-project
cd my-project
```

**Initialize in existing directory**:
```bash
uv init
```

**With template**:
```bash
uv init --package my-package     # Create a package
uv init --app my-app            # Create an application
```

Creates `pyproject.toml`, `README.md`, and basic structure.

## Configuration: pyproject.toml

```toml
[project]
name = "my-project"
version = "0.1.0"
description = "Project description"
authors = [
    { name = "Your Name", email = "email@example.com" }
]
requires-python = ">=3.11"
dependencies = [
    "requests>=2.31.0",
    "pandas>=2.0.0",
]

# PEP 621 standard approach — works with any tool, including uv
[project.optional-dependencies]
dev = [
    "pytest>=7.4.0",
    "mypy>=1.7.0",
    "ruff>=0.1.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

# uv-native approach — preferred for uv-only projects. Use one or the other,
# not both. [tool.uv] dev-dependencies takes precedence when present.
[tool.uv]
dev-dependencies = [
    "pytest>=7.4.0",
    "mypy>=1.7.0",
    "ruff>=0.1.0",
]

[tool.uv.sources]
# Optional: specify package sources
my-internal-package = { git = "https://github.com/org/repo" }
```

## Virtual Environment Management

**Create virtual environment**:
```bash
uv venv                           # Create .venv
uv venv --python 3.12            # Specific Python version
uv venv custom-name              # Custom name
```

**Activate environment**:
```bash
# Linux/macOS
source .venv/bin/activate

# Windows
.venv\Scripts\activate

# Or use uv run (no activation needed)
uv run python script.py
```

## Dependency Management

**Add dependencies**:
```bash
uv add requests pandas            # Add to dependencies
uv add --dev pytest mypy ruff    # Add to dev dependency group
uv add "numpy>=1.24,<2"          # With version constraint
```

**Install dependencies**:
```bash
uv sync                          # Install all dependencies
uv sync --dev                    # Include dev dependencies
uv sync --frozen                 # Use exact versions from lockfile
```

**Remove dependencies**:
```bash
uv remove numpy
```

**Update dependencies**:
```bash
uv lock                          # Update lockfile
uv lock --upgrade-package numpy  # Update specific package
uv sync                          # Install updated versions
```

**List dependencies**:
```bash
uv pip list                      # List installed packages
uv tree                          # Show dependency tree
```

## Running Commands

**Execute in environment** without activation:
```bash
uv run python script.py
uv run pytest
uv run mypy src/
```

**Run scripts** defined in pyproject.toml:
```toml
[project.scripts]
my-cli = "my_package.cli:main"
```

```bash
uv run my-cli                    # Run the CLI tool
```

## Python Version Management

**Install Python versions**:
```bash
uv python install 3.11
uv python install 3.12
uv python install 3.11 3.12 3.13  # Multiple versions
```

**List available versions**:
```bash
uv python list                   # List installed
uv python list --all-versions   # List all available
```

**Pin Python version**:
```bash
uv python pin 3.12              # Pin to 3.12
uv python pin 3.11.8            # Pin to specific patch
```

Creates `.python-version` file.

## Package Installation

**Install packages** (pip-compatible):
```bash
uv pip install requests
uv pip install -e .              # Install current project in editable mode
uv pip install -r requirements.txt
```

**Compile requirements**:
```bash
# Like pip-compile
uv pip compile pyproject.toml -o requirements.txt
uv pip compile requirements.in -o requirements.txt
```

**Sync from requirements**:
```bash
# Like pip-sync
uv pip sync requirements.txt
```

## Lockfile Management

`uv.lock` ensures reproducible builds. Always commit it to version control.

**Create/update lockfile**:
```bash
uv lock                          # Generate lockfile
uv lock --upgrade               # Upgrade all packages
uv lock --upgrade-package pkg   # Upgrade specific package
```

**Install from lockfile**:
```bash
uv sync                          # Install from lock
uv sync --frozen                # Don't update lock
```

## Project Structure Best Practices

```
project/
├── pyproject.toml            # Project configuration
├── uv.lock                   # Lockfile (commit to git)
├── .python-version           # Pinned Python version
├── README.md
├── .gitignore               # Include .venv/
├── src/
│   └── package_name/
│       ├── __init__.py
│       ├── py.typed
│       └── module.py
└── tests/
    └── test_module.py
```

## Common Tasks

**Development workflow**:
```bash
# Setup new project
uv init my-project
cd my-project

# Set Python version
uv python pin 3.11

# Add dependencies
uv add requests pandas
uv add --dev pytest mypy ruff

# Sync environment
uv sync

# Run tests and checks
uv run pytest
uv run mypy src/
uv run ruff check .
```

**Testing setup**:
```bash
uv add --dev pytest pytest-cov pytest-asyncio
uv run pytest --cov=src tests/
```

**Type checking**:
```bash
uv add --dev mypy
uv run mypy src/
```

**Formatting and linting**:
```bash
uv add --dev ruff
uv run ruff check .
uv run ruff format .
```

## Working with Workspaces

**Monorepo support**:
```toml
# Root pyproject.toml
[tool.uv.workspace]
members = ["packages/*"]

# packages/pkg-a/pyproject.toml
[project]
name = "pkg-a"

# packages/pkg-b/pyproject.toml
[project]
name = "pkg-b"
dependencies = ["pkg-a"]  # Internal dependency
```

```bash
uv sync                          # Syncs entire workspace
```

## Build and Publish

**Build package**:
```bash
uv build                         # Build wheel and sdist
uv build --wheel                # Only wheel
```

**Publish to PyPI**:
```bash
uv publish                       # Publish to PyPI
uv publish --token $PYPI_TOKEN  # With token
```

## Scripts and Tools

**Run inline scripts**:
```python
#!/usr/bin/env -S uv run --script
# /// script
# dependencies = ["requests", "rich"]
# ///

import requests
from rich import print

print(requests.get("https://api.github.com").json())
```

```bash
chmod +x script.py
./script.py                      # uv handles dependencies automatically
```

**Install tools globally**:
```bash
uv tool install ruff
uv tool install pytest
uv tool install black

# Now available system-wide
ruff --version
```

**List and manage tools**:
```bash
uv tool list
uv tool upgrade ruff
uv tool uninstall ruff
```

## Cache Management

**Cache location**:
- Linux: `~/.cache/uv/`
- macOS: `~/Library/Caches/uv/`
- Windows: `%LOCALAPPDATA%\uv\cache\`

**Manage cache**:
```bash
uv cache clean                   # Clean cache
uv cache dir                     # Show cache directory
```

## CI/CD Integration

**GitHub Actions**:
```yaml
# .github/workflows/test.yml
name: Test
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v7
        with:
          enable-cache: true

      - name: Set up Python
        run: uv python install

      - name: Install dependencies
        run: uv sync --all-extras --dev

      - name: Run tests
        run: uv run pytest

      - name: Run type checks
        run: uv run mypy src/
```

## Advanced Features

**Custom indexes**:
```toml
[tool.uv]
index-url = "https://pypi.org/simple"
extra-index-url = ["https://internal.company.com/simple"]
```

**Offline mode**:
```bash
uv sync --offline               # Use only cached packages
```

**Platform-specific dependencies**:
```toml
[project.dependencies]
# All platforms
requests = ">=2.31.0"

[tool.uv.sources.windows-specific]
windows-only = { marker = "sys_platform == 'win32'" }
```

**Resolution strategies**:
```bash
uv lock --resolution highest    # Prefer newest versions
uv lock --resolution lowest     # Prefer oldest compatible
```

## Migration from Other Tools

**From pip + venv**:
```bash
# Replace
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# With
uv venv
uv pip install -r requirements.txt
```

**From poetry**:
```bash
# uv can read poetry's pyproject.toml
uv sync
```

**From pip-tools**:
```bash
# Replace pip-compile
uv pip compile requirements.in -o requirements.txt

# Replace pip-sync
uv pip sync requirements.txt
```

## Troubleshooting

**Issue**: Package not found
```bash
# Check indexes
uv pip index list

# Add custom index
uv pip install --index-url https://custom.index/simple package
```

**Issue**: Version conflicts
```bash
# See resolution tree
uv tree

# Force specific version
uv add "package==1.2.3"
```

**Issue**: Slow resolution
```bash
# Use cache aggressively
uv sync --offline

# Or clear cache and retry
uv cache clean
uv sync
```

**Issue**: Virtual environment issues
```bash
# Remove and recreate
rm -rf .venv
uv venv
uv sync
```

## Performance Tips

1. **Use `uv run`** instead of activating: Faster and more reliable
2. **Enable cache**: Saves bandwidth and time (enabled by default)
3. **Use lockfile**: `uv sync --frozen` skips resolution
4. **Parallel installs**: uv automatically parallelizes
5. **Global tools**: Use `uv tool install` for CLI tools

## Best Practices

1. **Always commit `uv.lock`** for reproducibility
2. **Pin Python version** with `.python-version`
3. **Use `uv run`** instead of activating environments
4. **Organize dependencies**: Use `dev`, `test`, `docs` dependency groups
5. **Version constraints**: Be specific for applications, flexible for libraries
6. **Keep pyproject.toml clean**: Don't specify transitive dependencies
7. **Use workspaces** for monorepos
8. **Install global tools** with `uv tool install`

## Comparison: uv vs pip

| Feature | uv | pip |
|---------|----|----|
| Speed | 10-100x faster | Baseline |
| Resolver | Modern, backtracking | Basic |
| Lockfile | Native support | Requires pip-tools |
| Python management | Built-in | Separate tool |
| Virtual environments | Built-in | Requires venv |
| Compatibility | Drop-in replacement | Standard |

## Additional Resources

- [uv Documentation](https://docs.astral.sh/uv/)
- [uv GitHub](https://github.com/astral-sh/uv)
- [Migration Guide](https://docs.astral.sh/uv/pip/compatibility/)
