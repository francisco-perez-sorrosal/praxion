---
id: dec-024
title: CI test pipeline via GitHub Actions matrix over MCP servers
status: accepted
category: architectural
date: 2026-04-12
summary: Single SHA-pinned test workflow with strategy.matrix.project=[memory-mcp, task-chronograph-mcp] runs ruff + pytest per cell
tags: [ci, github-actions, testing, matrix]
made_by: agent
agent_type: systems-architect
pipeline_tier: standard
affected_files:
  - .github/workflows/test.yml
  - memory-mcp/pyproject.toml
  - task-chronograph-mcp/pyproject.toml
---

## Context

ROADMAP Phase 1.2 recorded a gap: both MCP servers (`memory-mcp`, `task-chronograph-mcp`) ship 631 tests combined, but those tests only run on a developer's workstation before a commit. No CI check gates pushes to `main` or PR merges. A broken server — format drift, a ruff regression, or a failing pytest suite — can land undetected until the next local invocation. The security-review workflow already demonstrates the pattern for SHA-pinned GitHub Actions (`context-security-review.yml`), so the infrastructure decision reduces to: what shape does the test workflow take, and where does it live?

Both servers are Python 3.13 projects managed with `uv`, share the same toolchain (`ruff` format + lint, `pytest` + `pytest-asyncio`), and have independent dependency graphs. Running them in a matrix keeps the workflow YAML small while giving each server its own isolated job (independent caching, independent failure attribution, and parallel execution on the runner pool).

## Decision

Add a single workflow at `.github/workflows/test.yml` that:

- Triggers on `push` to `main` and `pull_request` targeting `main`.
- Declares `strategy.matrix.project: [memory-mcp, task-chronograph-mcp]` so each MCP server runs in an independent job cell.
- Uses `actions/checkout` and `astral-sh/setup-uv` (both SHA-pinned with `# vX.Y.Z` trailing comments).
- Lets `astral-sh/setup-uv` manage Python 3.13 — no separate `actions/setup-python` step.
- Runs the standard quality gate per cell, `working-directory: ${{ matrix.project }}`: `uv sync` → `uv run ruff format --check` → `uv run ruff check` → `uv run pytest`.
- Applies workflow-level `permissions: contents: read`, `timeout-minutes: 15` per job, `fail-fast: false` (one server's failure should not cancel the other's run), and job-level `concurrency` keyed on `github.ref` + `matrix.project` with `cancel-in-progress: true` (stale pushes on the same branch/cell are canceled).

## Considered Options

### Option 1 — Single matrix workflow (chosen)

One `test.yml` with `strategy.matrix.project`. Each server gets its own job cell with its own working directory. Actions SHA-pinned per the repo's security convention.

**Pros:**
- One workflow file to maintain; DRY across servers.
- Matrix cells run in parallel on the runner pool → shortest wall-clock CI time.
- Adding a third server in the future is a one-line change to the matrix list.
- `fail-fast: false` means one server's regression does not mask the other's state.
- Concurrency group keyed on `matrix.project` lets per-server cancellations avoid starving each other.

**Cons:**
- Matrix syntax is slightly less obvious to readers unfamiliar with GitHub Actions.
- Job-level concurrency (where `matrix.project` is available) is the correct scope — workflow-level concurrency cannot reference matrix variables (a common gotcha).

### Option 2 — Two per-server workflows

Separate `test-memory-mcp.yml` and `test-task-chronograph-mcp.yml`.

**Pros:**
- Simpler per-file YAML (no matrix).
- Per-server workflow badges in README trivially composable.

**Cons:**
- Duplicated setup/ruff/pytest blocks → drift risk when bumping action versions or adjusting steps.
- Adding a third server means authoring a third workflow.
- No shared failure-attribution surface (have to open two run pages to see combined status).

### Option 3 — Monorepo single-job workflow

One job, no matrix, `cd memory-mcp && ... && cd ../task-chronograph-mcp && ...`.

**Pros:**
- Simplest YAML possible.

**Cons:**
- Serial execution; longer wall clock.
- A failure in server A leaves server B untested that run — masking regressions.
- Failure attribution requires log scraping (which server failed?).
- No parallelism on the runner pool.

## Consequences

**Positive:**

- CI gates push/PR events; broken servers cannot silently land on `main`.
- Both servers tested in parallel on every relevant event; feedback latency is bounded by the slower cell.
- SHA-pinning matches the repo's security convention (see `context-security-review.yml`) — `dependabot` or a manual version bump will flag the commented version alongside the SHA.
- `fail-fast: false` gives full signal on every run (both cells always report).
- Job-level concurrency keyed on `matrix.project` avoids cross-cell cancellation when only one cell's input changes.

**Negative:**

- Matrix syntax slightly raises the reader's cognitive load on first pass.
- Gotcha footgun for future editors: workflow-level `concurrency:` cannot reference `matrix.*` — must live at job scope.
- Each matrix cell incurs its own `uv sync` cost; no cross-cell cache sharing without additional configuration (acceptable — both servers' `uv.lock` files are small and the cost is bounded).

**Operational:**

- `timeout-minutes: 15` per job caps runaway tests; local pytest runs finish in under 60 seconds today, leaving ample headroom.
- Adding type checking (ROADMAP Phase 3.4) is a single step insertion per cell — the matrix structure extends cleanly.
- Adding a third MCP server requires only appending to `matrix.project`.
- If a server's tests are flaky, the `fail-fast: false` setting prevents masking the stable server's regression reporting.
