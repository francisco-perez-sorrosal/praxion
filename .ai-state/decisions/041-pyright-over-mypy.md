---
id: dec-041
title: pyright over mypy for MCP server type checking
status: accepted
category: implementation
date: 2026-04-13
summary: Pyright selected as the Python type checker for memory-mcp and task-chronograph-mcp; basic mode, staged rollout
tags: [type-checking, python, ci, mcp, tooling]
made_by: agent
agent_type: systems-architect
pipeline_tier: standard
affected_files:
  - memory-mcp/pyproject.toml
  - task-chronograph-mcp/pyproject.toml
  - .github/workflows/test.yml
affected_reqs:
  - REQ-TC-01
  - REQ-TC-02
  - REQ-TC-03
---

## Context

Phase 3.4 of the ROADMAP introduces static type checking to `memory-mcp` and `task-chronograph-mcp`. Both codebases use modern Python type syntax extensively (`X | None`, `dataclasses`, `typing.Protocol`) but have never been validated — there is no mypy, no pyright, no CI enforcement anywhere in the repo.

The existing CI workflow (dec-024) runs `ruff format --check`, `ruff check`, and `pytest` per MCP matrix cell. Adding a type-check step inherits this matrix for free.

The tool choice is therefore greenfield — no incumbent to preserve compatibility with, no existing config to extend.

## Decision

Use **pyright** as the Python type checker. Configure `typeCheckingMode = "basic"` (not `strict`). Add as a `dev` dependency in both MCP `pyproject.toml` files. Add a CI step between `ruff check` and `pytest`. Roll out in three stages to avoid a large type-fix PR stalling on review:

1. **Observe**: add pyright + CI step with `continue-on-error: true`; measure gap count.
2. **Fix**: separate PR fixing the surfaced type errors; type-correctness only, no refactoring.
3. **Enforce**: flip `continue-on-error: false`.

## Considered Options

### Option 1 — mypy

The incumbent Python type checker; extensive ecosystem; widely documented; bundled with most Python tooling guides.

- Pros: Most Python developers expect it; extensive stub ecosystem; familiar error messages; Python-native.
- Cons: Slower (seconds per run on MCP-sized codebases); less aggressive inference on `X | None` union narrowing; weaker tagged-union support; requires more explicit annotations for equivalent signal.

### Option 2 — pyright (chosen)

Microsoft's TypeScript-style inference engine; powers Pylance in VS Code; distributed as a Node.js package but callable from Python toolchains via `uv run pyright`.

- Pros: ~5-10× faster on MCP-sized codebases; superior inference on the `X | None` + union patterns already in use; better tagged-union narrowing; editor parity (Pylance is pyright); runs fine in CI with the Node runtime GitHub Actions provides for free.
- Cons: Microsoft tool for a Python project (minor cultural mismatch); Node dependency at install time; some Python contributors may expect mypy; smaller stub ecosystem for niche libraries.

### Option 3 — Both (tier one with mypy, gate with pyright, or vice versa)

- Pros: Catches errors one tool might miss.
- Cons: Double the CI time, double the noise, double the config surface; bike-shedding over which tool's error is "right" when they disagree. Not justified for a codebase this size.

## Consequences

**Positive**:
- CI gains type coverage without a speed regression (< 30 s added per cell).
- The existing `X | None` / dataclass idioms get full inference coverage with minimal annotation work.
- Editor integration is trivial (Pylance already uses pyright).
- Setting the basic/strict knob in `pyproject.toml` lets individual modules opt into stricter checking over time.
- Staged rollout protects against a large type-fix PR blocking other work.

**Negative**:
- Contributors expecting mypy need to adjust.
- Node runtime dependency at install time (acceptable — already present in CI).
- `basic` mode misses some bugs that `strict` would catch; tightening to `strict` is a follow-up ROADMAP item.

**Precedent**: This decision sets the default type checker for any future Python code added to the Praxion repo (new scripts, the eval package, hooks). Switching to mypy later is a one-line dev-dep swap, but the expectation is that pyright stays unless a concrete reason emerges.
