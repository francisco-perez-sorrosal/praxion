---
name: create-simple-python-prj
description: Create a basic Python project with pixi or uv package manager
argument-hint: "[project-name] [description] [package-manager] [target-dir]"
allowed-tools: [Bash(uv:*), Bash(pixi:*), Bash(git:*), Bash(mkdir:*), Bash(ls:*), Bash(touch:*), Write, Read, Edit]
disable-model-invocation: true
---

# Create Simple Python Project

Create a basic Python project named "$ARGUMENTS[0]" using the package manager and the target directory resolved below.

## Requirements

Read the typed input, `$ARGUMENTS`, by position:

| Token | Meaning | Resolution |
|---|---|---|
| `$ARGUMENTS[0]` (required) | project name | if this is empty or still a literal placeholder, stop and ask the user for the project name |
| `$ARGUMENTS[1]` (optional) | project description | if this is empty or still a literal placeholder, use `A simple Python project scaffolding` |
| `$ARGUMENTS[2]` (optional) | package manager | if this is empty or still a literal placeholder, use `pixi` |
| `$ARGUMENTS[3]` (optional) | target directory | if this is empty or still a literal placeholder, use `$HOME/dev` |

- Valid package managers: pixi, uv

## Guidelines

**Leverage the [Python Project Management](../python-prj-mgmt/SKILL.md) skill** and follow its standard practices for:
- Project initialization and structure (src-layout)
- Package manager usage (pixi or uv)
- pyproject.toml configuration

**Simple project specifics**:

1. **Location**: Create in `<target directory>/<project name>`

2. **Project description**: Use the resolved project description for:
   - README.md content
   - pyproject.toml description field

3. **Core dependencies** (minimal set):
   - `pydantic` - data validation
   - `pytest` - testing
   - `ruff` - linting/formatting
   - `mypy` - type checking

4. **Keep it simple**: Basic setup only, no complex scaffolding

5. Configure ruff with basic rules in pyproject.toml

From there on, use the [Python Development](../python-development/SKILL.md) skill for coding best practices.
