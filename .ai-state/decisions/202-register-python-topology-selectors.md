---
id: dec-202
title: Register Python selector & parallel-runner identifiers in the test-topology registries (M1→M2 for Python)
status: accepted
category: architectural
date: 2026-05-23
summary: Promote the five Python test-topology identifiers (pytest-globs/markers/keywords selectors; pytest-xdist-loadfile/load parallel runners) from indicative to registered in the trunk registries, completing M2 for Python consumer projects.
tags: [test-topology, registry, python, pytest, selector-strategy, parallel-runner, m2, additive-leaf]
made_by: agent
agent_type: systems-architect
branch: pipeline-efficiency-tier-ab
pipeline_tier: standard
affected_files:
  - skills/testing-strategy/references/test-topology.md
  - skills/testing-strategy/references/python-testing.md
re_affirms: dec-091
---

## Context

The test-topology protocol's M2 behavioral wiring shipped (the pipeline agents author and honor `TEST_TOPOLOGY.md`), but the Python language leaf's selector and parallel-runner identifiers were never promoted into the trunk's two registries. The trunk (`skills/testing-strategy/references/test-topology.md`) listed `pytest-globs`, `pytest-markers`, `pytest-keywords` (Registry 1 — selector strategies) and `pytest-xdist-loadfile`, `pytest-xdist-load` (Registry 2 — parallel runners) only under "Indicative Future Identifiers," explicitly "not registered at this milestone," with staleness markers dated 2026-04-29.

Consequence: any Python project adopting the topology hits the trunk's **Additive Leaf Escalation Clause** on every scoped-test step, because its `selectors[].strategy` values do not appear in a registered Registry 1 table. Sentinel TT02 ("every selectors entry has a registered strategy identifier") would FAIL for those values, and the clause routes the gap to the systems-architect with an ADR — which is this decision. Tracked as td-039 (`topology-drift`), surfaced 2026-05-23 by the pipeline-efficiency research (item B5).

The trunk's registries are **append-only** ("rows are not removed; removal requires an ADR and a migration window"). The contracts defined here — argument shapes, materialized invocations, edge-case semantics — become a permanent contract that populated `TEST_TOPOLOGY.md` files across consumer projects will depend on. They can be superseded but never silently removed.

Notably, the Python leaf (`references/python-testing.md` §"Test Topology — Python Leaf") already documented these five identifiers with concrete contracts; the deficiency was purely the trunk registry asymmetry (indicative tables + stale `last-verified` markers) plus missing explicit edge-case semantics. This decision is therefore a **promotion**, not a fresh design: it ratifies the leaf's existing contracts as canonical, defines their edge cases, and reflects them in the trunk's registered tables.

## Decision

Promote the five Python identifiers from indicative → **registered**, completing the M1→M2 transition for Python:

**Registry 1 — Selector strategies:**

| Identifier | Argument shape | Materialized invocation | Edge-case semantics |
|-----------|----------------|------------------------|---------------------|
| `pytest-globs` | List of path/glob strings, 1+ entries (empty list invalid) | `pytest <args>` (positional) | Multiple entries are unioned by pytest (all run). No marker registration required. |
| `pytest-markers` | List of snake_case marker names, 1+ entries (empty list invalid) | `pytest -m "<m1> or <m2> or ..."` | OR-joined into one expression; single entry → `-m "<m1>"`. Each marker must be registered in the pocket's `pyproject.toml` under `--strict-markers`. |
| `pytest-keywords` | A single keyword expression **string** (not a list; empty string invalid) | `pytest -k "<expr>"` (verbatim) | Optional within the leaf; no marker registration. Prefer `pytest-markers` for declared groups; reserve `pytest-keywords` for transient/debug selections. |

**Registry 2 — Parallel runners:**

| Identifier | Invocation | Guidance |
|-----------|-----------|----------|
| `pytest-xdist-loadfile` | `pytest -n auto --dist loadfile` | **Recommended default** for parallel-safe groups. Whole files assigned per worker → file-scoped (and narrower) fixture state never crosses a worker boundary. Safe for `shared_fixture_scope: per-file` or narrower. |
| `pytest-xdist-load` | `pytest -n auto --dist load` | Load-balanced. Less robust when same-file tests share fixture state. Use only for `shared_fixture_scope: none` or `per-test` after measuring a wall-clock benefit. |

`pytest-xdist-loadfile` is the recommended parallel default: keeping a file's tests on one worker eliminates the most common source of flaky parallel runs (per-file fixture state crossing a worker boundary). `parallel_safe: false` groups use the trunk's existing `none` runner (sequential, never passed to xdist).

Registration is recorded in both layers: the **leaf** (`references/python-testing.md`) is the canonical registrar location (Registry 1 and Registry 2 sub-tables, now marked live/registered with explicit edge-case semantics), and the **trunk** (`references/test-topology.md`) mirrors the rows into its registered registry tables for discoverability and sentinel TT02 validation, with `<!-- last-verified: -->` markers bumped to 2026-05-23.

## Considered Options

### Option A — Register all five with the leaf's existing contracts as canonical (chosen)

Ratify the contracts already documented in the Python leaf, add the missing edge-case semantics (empty arg, single vs. multiple entries, list vs. string), and promote the rows into the trunk's registered tables.

- Pro: zero contract drift — the leaf and trunk already agreed on invocations; this makes the agreement load-bearing.
- Pro: unblocks every Python consumer project's scoped-test steps immediately; satisfies TT02.
- Pro: minimal surface — two reference files, no schema change (the trunk schema's `{strategy, arg}` envelope already accommodates these).
- Con: locks in `pytest-keywords` taking a bare string while the other two take lists — a small asymmetry that is now permanent. Accepted: it mirrors pytest's own `-k` (one expression) vs. `-m`/positional (compositional) surface, so the asymmetry reflects the tool, not an arbitrary choice.

### Option B — Register only the selectors now, defer the parallel runners

Register Registry 1 (the three selectors) and leave Registry 2 indicative until a consumer project measures a parallelism need.

- Pro: smaller permanent contract surface.
- Con: a Python group declaring `parallel_safe: true` still has no registered runner to name, so the escalation clause keeps firing for the parallelism axis — only half-fixes td-039. Rejected.

### Option C — Collapse to a single `pytest` selector with a free-form arg

One identifier whose arg is an arbitrary pytest CLI fragment.

- Pro: maximally flexible; one row.
- Con: defeats TT02 (any string "validates"), erases the typed-envelope guarantee from dec-091, and makes tooling unable to reason about selector intent. Rejected — directly contradicts the registry's purpose.

## Consequences

**Positive:**
- Python consumer projects can adopt the topology without per-step architect escalation; the Additive Leaf Escalation Clause no longer fires for these five primitives.
- Sentinel TT02 now passes (not FAILs) for Python `selectors[].strategy` values; `pytest-keywords` correctly maps to the optional/WARN path.
- Trunk and leaf are consistent; staleness markers reflect the change date.
- Completes M2 for Python specifically (M2 behavioral wiring was project-agnostic; this makes it usable in practice for the most common consumer language).

**Negative / accepted:**
- The five contracts are now permanent (append-only registry). A future change to, e.g., the `pytest-keywords` arg shape requires a superseding ADR and a migration window for any populated `TEST_TOPOLOGY.md` depending on it.
- The list-vs-string asymmetry between `pytest-keywords` and the other selectors is locked in (intentional; mirrors pytest's CLI).

**Scope note:** dec-087's pilot deferral is unchanged — Praxion still does not populate its own `TEST_TOPOLOGY.md`. This decision makes the registries usable by consumers; it does not activate a Praxion-internal pilot.

## Prior Decision

This decision **re-affirms** dec-091 (typed-pluggable-identifier registries as the trunk's language-additive primitive) rather than superseding it. dec-091 established the two registries and the rule that "new language leaves register additional rows without modifying the trunk schema." This ADR is the first concrete exercise of that mechanism for a real language leaf: it follows dec-091's contract exactly (rows added to the existing tables, no schema field changed). No part of dec-091 is overturned; the evidence that would justify a future supersession of dec-091 would be a demonstrated case where the `{strategy, arg}` envelope cannot express a needed selector — which this Python registration did not encounter.
