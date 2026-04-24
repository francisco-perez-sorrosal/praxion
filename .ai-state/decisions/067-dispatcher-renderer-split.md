---
id: dec-draft-acb60f8e
title: test-coverage skill as dispatcher + renderer, not tool installer
status: proposed
category: architectural
date: 2026-04-24
summary: The test-coverage skill locates, invokes, and renders project coverage, but never installs coverage tooling. Projects own their tools as real dependencies.
tags: [skill, coverage, testing, architecture, scope]
made_by: user
pipeline_tier: standard
affected_files:
  - skills/test-coverage/SKILL.md
  - skills/test-coverage/references/python.md
  - commands/project-coverage.md
  - scripts/project_metrics/cli.py
  - pyproject.toml
---

## Context

Praxion needs a single place for coverage *reading, invocation, and rendering* so that `/project-coverage`, `/project-metrics`, the verifier, and any future caller produce consistent output. The obvious temptation is to make the skill "own" coverage end-to-end — including tool installation — so that activating the skill on a fresh project would Just Work.

That temptation was examined and rejected. Two reasons:

1. **Tool installation is project-owned, not skill-owned.** A skill that installs `pytest-cov` (or any other coverage tool) would either mutate the project's `pyproject.toml` / `package.json` without consent, or ship its own isolated install that diverges from what `pytest` uses at run time. Both outcomes are worse than asking the project to declare the tool as a real dependency.
2. **The existing `CoverageCollector` contract (pinned by the prior graceful-degradation ADR) is READ-ONLY — it never drives measurement itself.** Making the skill a tool installer would reintroduce exactly the coupling that ADR rejected, just one layer up. The skill must honor the same boundary.

The agent *can* still invoke the project's coverage target when asked — but only because the project has already defined what that target is (a pixi task, a `pytest --cov` config, a Makefile target). The skill dispatches; it does not install.

## Decision

The `test-coverage` skill has exactly three responsibilities:

1. **Locate** the project's canonical coverage target via a convention-based probe order.
2. **Invoke** that target when called (the caller owns the freshness decision).
3. **Render** the resulting artifact consistently across surfaces (terminal, Markdown section, verifier report fragment).

Tool installation is explicitly out of scope. The skill's Python reference documents the *default configuration* that Praxion (and any pytest-cov-using project) can adopt, but provisioning `pytest-cov` itself is the project's job.

## Considered Options

### Option A — Dispatcher + renderer (chosen)

- **Pros.** Clear scope; honors the existing collector's read-only pin; avoids mutating project config or shipping parallel installs; makes multi-language future-proofing mechanical (each language reference documents its own conventions independently).
- **Cons.** Requires projects to declare their own coverage dependency; on a truly empty project the skill produces "no target found" rather than bootstrapping one.

### Option B — Full-stack ownership (rejected)

The skill installs `pytest-cov` (or the language-equivalent) on activation, writes config, runs coverage, renders.

- **Pros.** Zero-config on a fresh project.
- **Cons.** Silently mutates `pyproject.toml`; competes with the project's own tool choice; every upgrade of `pytest-cov` becomes a Praxion-facing concern; violates the read-only collector boundary.

### Option C — Render-only (rejected as too narrow)

The skill only parses and renders existing artifacts; invocation is always the caller's job.

- **Pros.** Simplest possible surface.
- **Cons.** Every caller re-implements target discovery; `/project-coverage` becomes "read whatever's on disk" which is not what the command needs; verifier cannot produce fresh numbers even when it judges fresh numbers necessary.

## Consequences

**Positive.**
- Clear boundary; the skill does one well-defined job across four integration surfaces.
- Extending to TypeScript / Go / Rust is additive — a new `references/<lang>.md` file with the same three-section structure; no skill-level logic changes.
- Tool ownership stays with the project, matching the existing collector's contract.

**Negative.**
- On a project that has not declared `pytest-cov`, the skill's invocation branch fails with "no target found"; a first-time user needs one setup step. Mitigated by the Python reference providing a copy-pasteable config block.
- Multi-caller rendering consistency now lives in a single place (the skill's render functions). Changing the rendering format means coordinating three surfaces at once. Treat this as a feature, not a bug — it prevents silent drift.
