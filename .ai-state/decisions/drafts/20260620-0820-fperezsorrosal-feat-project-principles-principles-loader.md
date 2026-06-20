---
id: dec-draft-b6b91e14
title: Introduce `scripts/principles_loader.py` pure-function helper for principles YAML parsing
status: proposed
category: implementation
date: 2026-06-20
summary: >
  Add a stdlib-only, side-effect-free principles_loader module (load_principles + scope_matches)
  following the spec_drift.py style, fixture-tested via TDD, to encapsulate the toleration
  contract (absent/empty/malformed → []) and scope-matching logic for both planner and verifier consumers.
tags: [principles, parser, testing, simplicity]
made_by: agent
agent_type: implementation-planner
branch: feat-project-principles
pipeline_tier: standard
affected_files:
  - scripts/principles_loader.py
  - tests/test_principles_loader.py
  - tests/fixtures/principles/
re_affirms: dec-draft-6e600ec9
---

## Context

The `principles.yaml` consumer contract includes a non-trivial toleration contract (absent/empty/malformed YAML → return `[]`, never raise), scope-matching logic (`fnmatch`-based with `"*"` default, list-of-globs support), and a severity-coercion rule (unknown severity → coerce to `advisory` + surface a WARN note). These behaviors have edge cases (scope-miss no-op, empty principles list, multiple-glob scope) that benefit from isolation in a testable pure function rather than being embedded inline in agent prose (which has no test surface).

The `scripts/spec_drift.py` precedent establishes this pattern for similar advisory-detection helpers in Praxion: a pure entry-point function, side-effect-free, no global state, fixture-tested in `tests/test_spec_drift.py`.

## Decision

Introduce `scripts/principles_loader.py` with two public functions:
- `load_principles(path: Path) -> list[dict]` — tolerant YAML reader (absent/empty/malformed → `[]`)
- `scope_matches(scope: str | list[str], changed_files: list[str]) -> bool` — `fnmatch`-based

Both consumers (planner + verifier) reference this module conceptually (the verifier's agent prose describes the load → scope-match → classify pattern; the planner's threading logic does the same). The module is stdlib-only (`yaml`, `pathlib`, `fnmatch`) — no new dependency.

Developed TDD: failing tests first (RED, ImportError), then implementation (GREEN). Fixture matrix covers the 8 AC5-critical scenarios.

## Considered Options

### Option 1 — Inline YAML read in agent prose only (no script)
- **Pros**: zero new files; agent prose already describes the toleration contract.
- **Cons**: no test surface for the edge cases; the toleration + scope-match + coercion logic is non-trivial enough to produce subtle bugs (e.g., `scope: "*"` not matching all files, malformed YAML crashing instead of returning `[]`). Rejected.

### Option 2 — Add a script with a test module (CHOSEN)
- **Pros**: pure-function isolation, fixture-tested, matches `spec_drift.py` house style, covers AC5 edge cases explicitly.
- **Cons**: one more file pair; tiny overhead. Accepted — Simplicity First says "smallest solution that meets the behavior" not "fewest files regardless of risk."

## Consequences

**Positive:**
- AC5 (absent/empty/malformed no-op) is machine-verified, not prose-only.
- Scope-matching and severity-coercion edge cases are documented via executable fixture tests.
- Future consumers (e.g., a CLI or dashboard tool) can import the same module.

**Negative / accepted:**
- Two new files (`scripts/principles_loader.py`, `tests/test_principles_loader.py`). Minimal overhead.

## Prior Decision

Re-affirms `dec-draft-6e600ec9` (standalone Shape B artifact design). The loader is an implementation detail of that design — it does not change the artifact's schema, placement, or gate semantics.
