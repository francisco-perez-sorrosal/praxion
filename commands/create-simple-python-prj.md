---
description: Create a basic Python project with pixi or uv package manager
argument-hint: [project-name] [description] [package-manager] [target-dir]
allowed-tools: [Bash(uv:*), Bash(pixi:*), Bash(git:*), Bash(mkdir:*), Bash(ls:*), Bash(touch:*), Write, Read, Edit]
---

# Create Simple Python Project

Create a basic Python project named "$1" using ${3:-pixi} as the package manager in ${4:-$HOME/dev}.

## Requirements

- **Project name**: $1 (required)
- **Project description**: ${2:-A simple Python project scaffolding} (defaults to placeholder if not specified)
- **Package manager**: ${3:-pixi} (defaults to pixi if not specified)
- **Target directory**: ${4:-$HOME/dev} (defaults to $HOME/dev if not specified)
- Valid package managers: pixi, uv

## Guidelines

**Leverage the [Python Project Management](../skills/python-prj-mgmt/SKILL.md) skill** and follow its standard practices for:
- Project initialization and structure (src-layout)
- Package manager usage (pixi or uv)
- pyproject.toml configuration

**Simple project specifics**:

1. **Location**: Create in `${4:-$HOME/dev}/$1`

2. **Project description**: Use `${2:-A simple Python project scaffolding}` for:
   - README.md content
   - pyproject.toml description field

3. **Core dependencies** (minimal set):
   - `pydantic` - data validation
   - `pytest` - testing
   - `ruff` - linting/formatting
   - `mypy` - type checking

4. **Keep it simple**: Basic setup only, no complex scaffolding

5. Configure ruff with basic rules in pyproject.toml

From there on, use the [Python Development](../skills/python-development/SKILL.md) skill for coding best practices.
