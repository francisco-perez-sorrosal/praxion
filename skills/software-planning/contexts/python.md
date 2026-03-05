# Python Planning Context

Language-specific planning guidance for Python projects. Load alongside the [Software Planning](../SKILL.md) skill when planning Python work.

**Related skills**:
- [Python Development](../../python-development/SKILL.md) — Type hints, testing patterns, code quality
- [Python Project Management](../../python-prj-mgmt/SKILL.md) — pixi/uv, dependencies, environments

## Project Setup Steps

When a plan involves creating or initializing a Python project, include an early step for environment setup. Decide on the package manager based on project needs:

| Need | Tool | Reference |
|------|------|-----------|
| ML/data science, conda packages, compiled libs | pixi (default) | [pixi docs](../../python-prj-mgmt/pixi.md) |
| Pure Python, fast installs, minimal setup | uv | [uv docs](../../python-prj-mgmt/uv.md) |

**Typical setup step**:

```markdown
### Step 1: Initialize project with pixi

**Implementation**: `pixi init <project> --format pyproject`, add core dependencies, configure dev tools (ruff, mypy, pytest)
**Done when**: `pixi run pytest` exits cleanly with zero tests collected
```

## Quality Gates

Every plan step that produces code should pass these checks before requesting commit approval. Use `<tool>` as placeholder for your package manager (pixi or uv).

```bash
<tool> run ruff format .         # Format (fix mode)
<tool> run ruff check --fix .    # Lint (fix mode)
<tool> run mypy src/             # Type check (or pyright)
<tool> run pytest                # Tests
```

Include quality gates in the plan's commit checklist — they augment the generic checklist from the software planning skill.

## Step Templates

Common step shapes for Python projects. Adapt to your plan's granularity.

### Add a dependency

```markdown
### Step N: Add <library> for <purpose>

**Implementation**: `<tool> add [--pypi] <library>`, import and wire into <module>
**Testing**: Verify import works, add smoke test if integration is non-trivial
**Done when**: Existing tests pass, new dependency resolves cleanly
```

### Create a new module

```markdown
### Step N: Create <module_name> module

**Implementation**: Create `src/<package>/<module_name>.py` with type-annotated public API
**Testing**: Unit tests in `tests/test_<module_name>.py` for critical paths
**Done when**: `mypy` passes, tests cover primary behavior
```

### Add CLI / entry point

```markdown
### Step N: Add CLI entry point

**Implementation**: Create CLI module using argparse/click/typer, wire to package entry point in pyproject.toml
**Testing**: Test argument parsing and basic invocation
**Done when**: `<tool> run python -m <package>` runs successfully
```

### Refactor / extract module

```markdown
### Step N: Extract <concern> from <source> into <target>

**Implementation**: Move related functions/classes, update imports, verify no circular dependencies
**Testing**: Existing tests pass without modification (behavior preservation)
**Done when**: `ruff check` clean, `mypy` passes, all tests green
```

## Testing Patterns for Plan Steps

When writing the **Testing** field of a plan step, choose the appropriate level:

| Step type | Testing approach |
|-----------|-----------------|
| New module with logic | Unit tests with pytest, parametrize for edge cases |
| Integration / wiring | Smoke test that exercises the integration path |
| Data validation | Parametrized tests covering valid, invalid, and boundary inputs |
| API endpoint | Request/response tests with test client |
| Refactoring | Existing tests must pass unchanged |
| Dependency addition | Import smoke test, integration test if non-trivial |
| Configuration | Validate config loads correctly with test fixtures |

Reference the [Python Development](../../python-development/SKILL.md) skill for pytest patterns (fixtures, parametrize, markers).

## Common Plan Shapes

Starter outlines for typical Python projects. Each is a sequence of plan steps — adapt and split further based on the [step size heuristics](../SKILL.md#step-size-heuristics).

### Library

1. Initialize project (pyproject.toml, src layout, dev tools)
2. Define core data types (dataclasses/Pydantic models with type hints)
3. Implement primary module with public API
4. Add tests for critical paths
5. Add secondary modules as needed
6. Document public API (docstrings, README usage)

### CLI Application

1. Initialize project with entry point
2. Define configuration (dataclass/Pydantic for settings)
3. Implement core logic as testable module (no CLI coupling)
4. Add CLI layer (argparse/click/typer) wiring to core
5. Add integration tests for CLI invocation
6. Handle error cases and user-facing messages

### Data Pipeline

1. Initialize project with data dependencies (pandas, polars, etc.)
2. Define input/output schemas (Pydantic models or dataclasses)
3. Implement extraction step
4. Implement transformation step with validation
5. Implement load/output step
6. Add end-to-end test with fixture data

### API Service

1. Initialize project with web framework (FastAPI, Flask)
2. Define request/response models (Pydantic)
3. Implement core domain logic (framework-independent)
4. Add API routes wiring to domain logic
5. Add request validation and error handling
6. Add API tests with test client
