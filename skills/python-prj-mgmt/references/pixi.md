# pixi for Python Projects

Fast, cross-platform package manager built on conda. Complete pixi reference for Python projects. Back to [SKILL.md](../SKILL.md).

## Table of Contents

- [Why pixi for Python?](#why-pixi-for-python)
- [Installation](#installation)
- [Project Initialization](#project-initialization)
- [Configuration: pyproject.toml](#configuration-pyprojecttoml)
- [Key Concepts](#key-concepts)
- [Dependency Management](#dependency-management)
- [Package Source Guidance](#package-source-guidance)
- [Running Commands](#running-commands)
- [Multiple Environments with Dependency Groups](#multiple-environments-with-dependency-groups)
- [Platform-Specific Dependencies](#platform-specific-dependencies)
- [PyTorch and ML Workflows](#pytorch-and-ml-workflows)
- [Project Structure](#project-structure)
- [Common Workflows](#common-workflows)
- [Tasks Configuration](#tasks-configuration)
- [Package Interoperability](#package-interoperability)
- [Global Tools](#global-tools)
- [IDE Integration](#ide-integration)
- [CI/CD Integration](#cicd-integration)
- [Caching and Performance](#caching-and-performance)
- [Lockfile Management](#lockfile-management)
- [Troubleshooting](#troubleshooting)
- [Migration from Other Tools](#migration-from-other-tools)
- [Best Practices](#best-practices)
- [Common Pitfalls](#common-pitfalls)
- [Example: Complete Python Project](#example-complete-python-project)
- [Additional Resources](#additional-resources)

## Why pixi for Python?

- **Multi-ecosystem**: Seamlessly mix conda and PyPI packages
- **Fast**: Parallel downloads and installations
- **Reproducible**: Lockfiles ensure consistent environments across platforms
- **Python-native**: Uses `pyproject.toml` for configuration
- **Task runner**: Built-in task management
- **Multiple environments**: Support for test, dev, docs configurations using dependency groups

## Installation

```bash
# macOS/Linux
curl -fsSL https://pixi.sh/install.sh | bash

# Or with Homebrew
brew install pixi

# Windows (PowerShell)
iwr -useb https://pixi.sh/install.ps1 | iex
```

## Project Initialization

**New Python project**:
```bash
pixi init my-project --format pyproject
cd my-project
```

**Initialize existing Python project**:
```bash
pixi init --format pyproject
```

Creates a src-layout structure with:
- `pyproject.toml` - Project configuration
- `src/package_name/` - Source package
- `tests/` - Test directory
- `pixi.lock` - Lockfile

## Configuration: pyproject.toml

**Basic structure**:

```toml
[project]
name = "my-project"
version = "0.1.0"
description = "Project description"
authors = [{ name = "Your Name", email = "email@example.com" }]
requires-python = ">=3.11"
dependencies = [
    # PyPI dependencies (standard PEP 621)
    "requests>=2.31.0",
    "pandas>=2.0.0",
]

[project.optional-dependencies]
# Automatically becomes a pixi feature environment
dev = [
    "pytest>=7.4.0",
    "mypy>=1.7.0",
    "ruff>=0.1.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.pixi.workspace]
channels = ["conda-forge"]
platforms = ["linux-64", "osx-64", "osx-arm64", "win-64"]

[tool.pixi.dependencies]
# Conda dependencies (takes precedence over PyPI)
# Use for system libraries, C extensions, or when conda version preferred

[tool.pixi.pypi-dependencies]
# Editable install of current package
my-project = { path = ".", editable = true }

[tool.pixi.environments]
default = { solve-group = "default" }
dev = { features = ["dev"], solve-group = "default" }

[tool.pixi.tasks]
test = "pytest tests/"
lint = "ruff check ."
format = "ruff format ."
typecheck = "mypy src/"
```

## Key Concepts

**Dependency Sources**:

1. **PyPI dependencies** (default): Listed in `[project.dependencies]` or added with `pixi add --pypi`
2. **Conda dependencies**: Listed in `[tool.pixi.dependencies]` or added with `pixi add` (no flag)
3. **Conda takes precedence**: If a package exists in both, conda version is used when explicitly listed

**Python Version**: The `requires-python` field automatically becomes a conda dependency, ensuring the correct Python version is installed.

**Environments**: Both `[project.optional-dependencies]` and `[dependency-groups]` automatically create pixi feature environments.

## Dependency Management

**Add PyPI packages** (default for Python):
```bash
pixi add --pypi requests pandas
pixi add --pypi "flask[async]>=3.1.0"     # With extras and version
pixi add --pypi --feature dev pytest ruff # Add to dependency group
```

**Add conda packages**:
```bash
pixi add numpy                             # Prefer conda version
pixi add pytorch torchvision              # ML packages often better from conda
pixi add black=25                         # Specific version
```

**Remove dependencies**:
```bash
pixi remove numpy
pixi remove --pypi requests
```

**Update dependencies**:
```bash
pixi update                                # Update all
pixi update numpy                          # Update specific package
```

**List dependencies**:
```bash
pixi list                                  # All installed packages
pixi tree                                  # Dependency tree
```

## Package Source Guidance

**Use PyPI** (`pixi add --pypi`):
- Pure Python packages
- Latest package versions
- Packages not in conda-forge

**Use conda** (`pixi add`):
- System libraries (libxml2, etc.)
- C extensions (numpy, scipy, pandas)
- ML frameworks (pytorch, tensorflow)
- Complex dependencies requiring compiled binaries

**Both work together**: pixi automatically manages dependencies from both ecosystems.

**When to use conda vs PyPI**:
- Use **conda** for: System libraries, C extensions (numpy, scipy), ML frameworks (pytorch, tensorflow), complex dependencies
- Use **PyPI** for: Pure Python packages, latest versions, packages not in conda-forge

## Running Commands

**Execute in pixi environment** (no activation needed):
```bash
pixi run python script.py
pixi run pytest
pixi run mypy src/
```

**Using tasks** (defined in `[tool.pixi.tasks]`):
```bash
pixi run test                              # Runs pytest
pixi run lint                              # Runs ruff check
pixi run format                            # Runs ruff format
```

**Interactive shell**:
```bash
pixi shell                                 # Enter environment
# Now in pixi environment
python script.py
pytest
exit                                       # Leave environment
```

**Run in specific environment**:
```bash
pixi run --environment dev pytest
pixi run -e test pytest --cov
```

## Multiple Environments with Dependency Groups

**Using PEP 735 dependency groups** (recommended):
```toml
[dependency-groups]
test = [
    "pytest>=7.4.0",
    "pytest-cov>=4.1.0",
]
docs = [
    "mkdocs>=1.5.0",
    "mkdocs-material>=9.4.0",
]

[tool.pixi.environments]
default = { solve-group = "default" }
test = { features = ["test"], solve-group = "default" }
docs = { features = ["docs"], solve-group = "default" }
```

**Add to dependency groups**:
```bash
pixi add --pypi --feature test pytest pytest-asyncio
pixi add --pypi --feature docs mkdocs
```

**Run with environment**:
```bash
pixi run -e test pytest
pixi run -e docs mkdocs serve
```

## Platform-Specific Dependencies

**Handle different platforms** in pyproject.toml:
```toml
[tool.pixi.target.linux-64.dependencies]
cuda = "12.5.*"

[tool.pixi.target.osx-arm64.dependencies]
# macOS-specific packages

[tool.pixi.feature.cuda.dependencies]
pytorch-cuda = "12.1"

[tool.pixi.feature.cuda.system-requirements]
cuda = "12"
```

## PyTorch and ML Workflows

**CPU-only setup**:
```bash
pixi add pytorch torchvision torchaudio cpuonly -c pytorch-cpu
```

**GPU setup with CUDA**:
```toml
[tool.pixi.dependencies]
python = ">=3.11"

[tool.pixi.pypi-dependencies]
torch = "==2.1.0"
torchvision = "==0.16.0"
torchaudio = "==2.1.0"
my-project = { path = ".", editable = true }

[tool.pixi.feature.cuda.pypi-dependencies]
# CUDA-specific wheels
torch = { version = "==2.1.0", index = "https://download.pytorch.org/whl/cu121" }

[tool.pixi.feature.cuda.system-requirements]
cuda = "12.1"

[tool.pixi.environments]
default = { solve-group = "default" }
cuda = { features = ["cuda"], solve-group = "default" }
```

**Verify CUDA**:
```bash
pixi info                                  # Shows __cuda virtual package
pixi run python -c "import torch; print(torch.cuda.is_available())"
```

## Project Structure

```
project/
├── pyproject.toml            # Project configuration (replaces pixi.toml)
├── pixi.lock                 # Lockfile (commit to git)
├── .gitignore                # Include .pixi/ directory
├── src/
│   └── package_name/
│       ├── __init__.py
│       ├── py.typed
│       └── module.py
└── tests/
    └── test_module.py
```

## Common Workflows

**Development setup**:
```bash
# Initialize Python project
pixi init my-project --format pyproject
cd my-project

# Add dependencies
pixi add --pypi requests pandas           # PyPI packages
pixi add numpy                            # Conda package (better for numpy)

# Add dev dependencies
pixi add --pypi --feature dev pytest mypy ruff

# Install all dependencies
pixi install

# Run development tasks
pixi run lint
pixi run test
pixi run python -m my_project
```

**Testing setup**:
```bash
pixi add --pypi --feature test pytest pytest-cov pytest-asyncio
pixi run -e test pytest --cov=src tests/
```

**Type checking**:
```bash
pixi add --pypi --feature dev mypy
pixi run mypy src/
```

**Documentation**:
```bash
pixi add --pypi --feature docs mkdocs mkdocs-material
pixi run -e docs mkdocs serve
```

## Tasks Configuration

**Define tasks in pyproject.toml**:
```toml
[tool.pixi.tasks]
# Simple commands
test = "pytest tests/"
lint = "ruff check ."
format = "ruff format ."

# Commands with dependencies
check = { depends-on = ["lint", "test"] }

# Multi-step commands
ci = { cmd = "pytest --cov=src tests/ && ruff check .", depends-on = ["format"] }

# Environment-specific tasks
[tool.pixi.feature.dev.tasks]
dev-server = "python -m my_project --reload"
watch-tests = "pytest-watch"
```

**Run tasks**:
```bash
pixi run test                              # Single task
pixi run check                             # Runs lint, then test
pixi task list                             # Show all tasks
```

## Package Interoperability

**Mixing conda and PyPI**:

When you add a conda package that was previously a PyPI dependency, pixi automatically swaps it:

```bash
# Initially added via PyPI
pixi add --pypi pygments

# Later switch to conda (better performance)
pixi add pygments                          # Replaces PyPI version
```

**Critical**: When using PyPI pytorch, all related packages (torchvision, torchaudio) must also be PyPI. Mixing sources causes conflicts.

## Global Tools

**Install Python tools globally**:
```bash
pixi global install ruff
pixi global install pytest
pixi global install mypy

# Now available system-wide
ruff --version
```

**Manage global tools**:
```bash
pixi global list
pixi global upgrade ruff
pixi global remove ruff
```

## IDE Integration

**VS Code**: Point to `.pixi/envs/default/bin/python`

**PyCharm**: Configure interpreter from `.pixi/envs/default/bin/python`

**Environment activation** (if needed):
```bash
# Shows activation script
pixi shell-hook

# Or use interactive shell
pixi shell
```

## CI/CD Integration

**GitHub Actions**:
```yaml
name: Test
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Setup pixi
        uses: prefix-dev/setup-pixi@v0.9.4
        with:
          pixi-version: latest
          cache: true

      - name: Install dependencies
        run: pixi install

      - name: Run tests
        run: pixi run test

      - name: Run type checks
        run: pixi run typecheck
```

## Caching and Performance

**Cache location**:
- Linux: `~/.cache/rattler/`
- macOS: `~/Library/Caches/rattler/`
- Windows: `%LOCALAPPDATA%\rattler\cache\`

**Clean cache**:
```bash
pixi clean cache
```

**Environment location**: `.pixi/envs/` (not committed to git)

## Lockfile Management

`pixi.lock` ensures reproducible builds across platforms. Always commit it to version control.

**Sync from lockfile**:
```bash
pixi install                               # Install from lock
pixi install --frozen                      # Don't update lock
```

**Update lockfile**:
```bash
pixi update                                # Update all
pixi update numpy                          # Update specific package
```

## Troubleshooting

**Package not found in conda-forge**:
```bash
pixi add --pypi package-name              # Use PyPI instead
```

**Solver takes too long**:
```bash
pixi add "numpy>=1.24,<2"                 # Use stricter constraints
```

**Environment conflicts**:
```bash
rm pixi.lock                              # Remove lockfile
pixi install                              # Rebuild
```

**Verbose output**:
```bash
pixi -v run command                       # Verbose
pixi -vv run command                      # Very verbose
```

**Check system requirements**:
```bash
pixi info                                 # Shows virtual packages like __cuda
```

## Migration from Other Tools

**From pip + venv**:
```bash
pixi init --format pyproject
# Add dependencies from requirements.txt
cat requirements.txt | xargs -n 1 pixi add --pypi
```

**From conda**:
```bash
pixi init --format pyproject
# Manually add dependencies from environment.yml
pixi add package1 package2               # Conda packages
pixi add --pypi pypi-package            # PyPI packages
```

## Best Practices

1. **Use `pyproject.toml`** for Python projects (not `pixi.toml`)
2. **Always commit `pixi.lock`** for reproducibility
3. **Prefer PyPI for pure Python packages**, conda for compiled extensions
4. **Use dependency groups** for organizing optional dependencies
5. **Define tasks** for common operations
6. **Set `requires-python`** explicitly
7. **Keep solve-groups aligned** for compatible dependency resolution
8. **Don't mix PyTorch channels**: Use all-conda-forge or all-PyPI for ML packages
9. **Set `system-requirements.cuda`** if using GPU packages
10. **Use `.pixi/envs/default/bin/python`** for IDE integration

## Common Pitfalls

- **Mixing dependency sources**: When using PyPI torch, all related packages must be PyPI
- **Missing system requirements**: Without `system-requirements.cuda`, defaults to CPU-only
- **Wrong initialization**: Use `--format pyproject` for Python projects
- **Editable install**: Must explicitly declare in `[tool.pixi.pypi-dependencies]`
- **Channel conflicts**: Don't mix conda-forge with legacy pytorch channel

## Example: Complete Python Project

```toml
[project]
name = "my-ml-project"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "numpy>=1.24",
    "pandas>=2.0",
]

[dependency-groups]
dev = ["pytest>=7.4", "mypy>=1.7", "ruff>=0.1"]
ml = ["torch>=2.1", "torchvision>=0.16"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.pixi.workspace]
channels = ["conda-forge"]
platforms = ["linux-64", "osx-64", "osx-arm64"]

[tool.pixi.pypi-dependencies]
my-ml-project = { path = ".", editable = true }

[tool.pixi.environments]
default = { solve-group = "default" }
dev = { features = ["dev"], solve-group = "default" }
ml = { features = ["ml", "dev"], solve-group = "default" }

[tool.pixi.tasks]
test = "pytest tests/"
lint = "ruff check src/"
format = "ruff format src/"
train = "python -m my_ml_project.train"
```

## Additional Resources

- [pixi Python Tutorial](https://pixi.sh/latest/python/tutorial/)
- [pixi pyproject.toml Reference](https://pixi.sh/latest/python/pyproject_toml/)
- [pixi PyTorch Guide](https://pixi.sh/latest/python/pytorch/)
- [pixi Documentation](https://pixi.sh/latest/)
- [conda-forge Packages](https://conda-forge.org/packages/)
