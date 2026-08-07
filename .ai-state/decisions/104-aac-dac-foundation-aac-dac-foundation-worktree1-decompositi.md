---
id: dec-104
title: AaC+DaC Worktree 1 decomposition — fitness tests in separate invocation, import-linter in dev group
status: accepted
category: implementation
date: 2026-04-30
summary: 'fitness/tests/ runs via separate pytest invocation (not added to testpaths); import-linter added to dev dependency group (not a separate fitness group); both decisions operationalize dec-101 within Praxion pyproject.toml constraints.'
tags: [aac, fitness-functions, import-linter, pytest, decomposition, implementation-planning]
made_by: agent
agent_type: implementation-planner
pipeline_tier: standard
re_affirms: dec-101
affected_files:
  - fitness/tests/
  - pyproject.toml
---

## Context

The AaC+DaC v1 implementation (Worktree 1, Phases 0-3) must operationalize dec-101's fitness infrastructure within Praxion's existing `pyproject.toml` structure. Two concrete sub-decisions arise during step decomposition that are not fully specified in dec-101:

1. **Where does `fitness/tests/` run?** Praxion's `[tool.pytest.ini_options] testpaths = ["tests", "scripts"]` could be extended to include `fitness/tests/`, or `fitness/tests/` could require a separate invocation.
2. **Which dependency group receives `import-linter`?** The dev group exists already; a `fitness`-specific group would be more semantically precise but adds overhead.

## Decision

**`fitness/tests/` runs via separate invocation** (`uv run pytest fitness/tests/`) — NOT added to `testpaths`. Rationale: dec-101 explicitly states "a `pixi run fitness` (or project-defined equivalent) wraps both invocations" and "Different report (`pixi run fitness`) signals different category." Adding `fitness/tests` to `testpaths` would merge architecture-test failures into the same report as behavior-test failures, defeating the design intent. The Praxion project uses `uv`, not `pixi`; the equivalent wrapper is `uv run pytest fitness/tests/`.

**`import-linter` is added to the `dev` dependency group** (`uv add --group dev import-linter`). Rationale: Praxion has one `dev` group; creating a separate `fitness` group is over-engineering for a single tool with no production deployment footprint. All dev tooling (pytest, pytest-cov, import-linter) lives in `dev`.

## Considered Options

### Option 1 — Add fitness/tests to testpaths

**Pros:** Single invocation discovers all tests.

**Cons:** Mixes architecture-test failures with behavior-test failures in the same report. Defeats dec-101's "different report signals different category" design intent. Makes `uv run pytest` unexpectedly slower once the fitness suite grows.

### Option 2 — Separate invocation (chosen)

**Pros:** Separate report surface for architecture tests. Consistent with dec-101's design intent. `uv run pytest tests/` stays fast for behavior tests; `uv run pytest fitness/tests/` is the architecture test surface.

**Cons:** Contributors must remember two invocations. Mitigated by `fitness/README.md` documenting the command.

### Option 3 — Separate fitness dependency group

**Pros:** Semantically precise (`import-linter` is clearly a fitness-only tool).

**Cons:** Adds a new `[dependency-groups]` section to `pyproject.toml` for a single tool. All dev tooling is already in `dev`. Over-engineering for the current scale. `import-linter` would need to be explicitly installed in any dev context anyway (no reason to separate it).

## Consequences

**Positive:**

- Architecture tests and behavior tests remain visually and operationally distinct.
- `pyproject.toml` stays clean (one dev group).
- `fitness/README.md` documents the invocation so the two-command workflow is discoverable.

**Negative:**

- Contributors working in `fitness/` must know to run `uv run pytest fitness/tests/` separately. Mitigated by README and integration checkpoints in the plan.

**Operational:**

- Step 2.1's done-criteria include `uv run import-linter --config fitness/import-linter.cfg` passing (verifies import-linter is installed).
- Step 2.5 integration checkpoint runs both `uv run pytest tests/` and `uv run pytest fitness/tests/` to confirm no regressions.
