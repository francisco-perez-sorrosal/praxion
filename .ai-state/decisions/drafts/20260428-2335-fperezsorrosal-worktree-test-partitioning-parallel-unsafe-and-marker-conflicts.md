---
id: dec-draft-a295fc62
title: Parallel-unsafe groups isolate at runner level; kebab-id → snake_case marker form; reserved-name set
status: proposed
category: behavioral
date: 2026-04-28
summary: Two coupled decisions on the marker/runner mechanics axis. First, parallel-unsafe groups (parallel_safe=false) run via a separate runner invocation rather than sharing a single invocation with the safe groups — this is the trunk decision. The Python leaf concretization is "two separate pytest invocations chained sequentially." Second, group ids are kebab-case for trunk identity and snake_case for the runtime marker form (so memory-store-core → memory_store_core), with a reserved-name set the schema enforces; sentinel TT05 validates both halves.
tags: [test-topology, parallel-safety, markers, runner-mechanics, naming, sentinel, tt05]
made_by: agent
agent_type: systems-architect
pipeline_tier: standard
affected_files:
  - skills/testing-strategy/references/test-topology.md
  - skills/testing-strategy/references/python-testing.md
  - agents/sentinel.md
---

## Context

Two open questions from `RESEARCH_FINDINGS.md` §E.4 share the same trade-off axis (the marker/runner mechanics interplay) and are resolved together in a single ADR:

- **Q2** — Should `parallel_safe: false` groups run in a separate pytest invocation, or in the same invocation with `xdist_group` markers on the unsafe tests? §C.4 recommended two invocations for clarity.
- **Q6** — What if a group id conflicts with an existing pytest marker (`parametrize`, `skipif`, etc.)? The schema should reserve a kebab-case-with-underscore-substitution form (`memory_store_core`) to avoid this; sentinel TT05 should validate.

The shared axis is "how do group identities materialize at runtime in the runner's invocation form, and what conflicts can arise." Splitting these into two ADRs would have produced two short documents both citing the same concrete pytest mechanics.

## Decision

**Two coupled decisions:**

### D1 — Parallel-unsafe groups isolate at runner level

**Trunk shape:** when a step's selection mixes `parallel_safe: true` and `parallel_safe: false` groups, the runner emits separate runner invocations: one parallel invocation for the safe groups, one sequential invocation for the unsafe groups. Results are aggregated into a single `TEST_RESULTS.md` block per step.

**Python leaf concretization:** two `pytest` commands chained sequentially. Example:

```bash
# Parallel-safe groups (parallel)
uv run pytest -m "memory_store_core or hooks_inject_memory" -n auto --dist loadfile

# Parallel-unsafe groups (sequential)
uv run pytest -m "project_metrics_fixture_rebuild" -n 0
```

The implementer/test-engineer's invocation logic walks the step's `Tests:` field and groups by `parallel_safe`. The order is parallel-first (so the parallel job pays its xdist startup cost while the developer is still reading the output of the prior step), then sequential.

### D2 — Kebab-id → snake_case marker form, with reserved-name set

**Trunk identity rule:** group `id` is kebab-case (`memory-store-core`).

**Leaf marker form:** the Python leaf maps the kebab id to a snake_case marker name (`memory_store_core`) by substituting `-` → `_`. This mapping is mechanical and one-way — the marker name is the only form pytest's `-m` selector accepts.

**Reserved-name set** (the trunk owns this list because it is a global namespace concern, not a Python-specific one):

- `parametrize`, `skipif`, `xfail`, `usefixtures`, `xdist_group`, `parallel_unsafe` — all are pytest builtin or upstream-plugin markers
- `unit`, `integration`, `contract`, `e2e` — reserved for future tier-keyword use; do not use as group ids
- Any identifier that, after kebab-to-snake conversion, would collide with one of the above is rejected

Sentinel **TT05** enforces:

- Every group `id` is kebab-case
- The kebab→snake marker form does not collide with the reserved-name set
- The pyproject `[tool.pytest.ini_options].markers` list includes the snake form for every group with a `pytest-markers` selector
- Mismatches FAIL (not WARN — this would silently break selection under `--strict-markers`)

## Considered Options

### D1 alternatives

#### Option D1-A — Two separate pytest invocations (chosen)

**Pros:**
- Conceptually clean: parallel-safe and unsafe never share a worker pool. The unsafe set runs sequentially without any chance of fixture race conditions.
- Wall-clock loss is bounded: only the unsafe set pays the no-parallelism penalty; the safe set runs at full xdist throughput.
- Reasoning is simple for the implementer and verifier — two commands, two summary lines, two recordings in `TEST_RESULTS.md`.
- Robust to future pytest/xdist behavior changes.

**Cons:**
- Two pytest startup costs (small — milliseconds).
- The `TEST_RESULTS.md` schema must accommodate aggregation across multiple invocations per step. The proposed schema already handles this via the `Per-group results:` block.

#### Option D1-B — Single pytest invocation with `xdist_group` markers on unsafe tests

xdist's `xdist_group` marker pins all marked tests to a single worker. Approach: tag every unsafe-group's tests with `@pytest.mark.xdist_group("unsafe")`, then run a single `pytest -n auto` and let xdist serialize the unsafe ones onto worker `gw0`.

**Rejected.** Three problems:

1. The unsafe groups still race on shared fixtures within the single worker (filesystem state across tests in the unsafe group can still corrupt). `xdist_group` ensures they don't span workers, not that they don't share state.
2. Adding the `xdist_group` marker requires per-test annotation, which couples the topology mechanism (per-group `parallel_safe` flag) to per-test markers (per-test `xdist_group`). Two layers of metadata for one concept.
3. The behavior is harder to verify: a single invocation produces a single results block; isolating "the unsafe tests" in the output requires post-processing. The two-invocation approach is auditable directly.

### D2 alternatives

#### Option D2-A — Kebab-only ids, runner accepts kebabs (i.e., no transformation)

Force the runner to accept kebab-case directly via custom collector or by registering hyphen-bearing markers.

**Rejected.** pytest's marker syntax (PEP 8 identifier names) does not accept hyphens. Working around this requires a custom plugin or per-test annotation gymnastics. The `kebab-id → snake_case` mapping is the simplest sufficient solution.

#### Option D2-B — Snake_case ids in the trunk

Drop kebab-case from the trunk; use snake_case throughout.

**Rejected.** Praxion's existing convention across all artifacts is kebab-case for ids (ADR slugs, draft hashes, idea ledger entries, sentinel report names). Breaking this for test groups would create a single inconsistent surface. The mechanical kebab→snake mapping keeps the trunk consistent and pushes the snake form into the leaf where pytest's identifier rules apply.

#### Option D2-C — Kebab-case ids + snake_case marker form (chosen, as above)

**Pros:**
- Trunk consistency with existing kebab-case conventions (ADRs, ledger ids, etc.).
- Mechanical mapping; sentinel TT05 enforces the absence of conflicts.
- Reserved-name set is documented in the trunk so future leaves (e.g., a Go leaf) inherit the same conflict-avoidance discipline.

**Cons:**
- Two forms of the same id exist (kebab in `TEST_TOPOLOGY.md`, snake in pyproject markers and pytest invocation). Cognitive overhead. Mitigation: TT05's check makes the mapping verifiable; the leaf reference's worked example shows the mapping concretely.

## Consequences

### Positive

- D1 isolates parallel-unsafe groups cleanly; the schema's `parallel_safe: false` flag has a concrete runtime meaning.
- D2 makes group identity portable across leaf languages (each leaf maps kebab to its own runtime form) while pytest's snake-case requirement is honored.
- TT05's check is mechanical and fast — a single pyproject.toml parse plus a kebab→snake transformation per group.
- The reserved-name set is small and stable; future expansions are ADR-mediated.

### Negative

- The marker form `memory_store_core` has no obvious back-link to the kebab id in `TEST_TOPOLOGY.md`. A reader running `pytest -m memory_store_core` and wondering "what group is this?" must do the reverse mapping mentally. Mitigation: the leaf's worked example documents the convention, and the kebab id is human-obvious from the snake form (just substitute `_` → `-`).
- Two pytest invocations per step that mixes safe and unsafe groups — small wall-clock cost, acknowledged.

### Reversibility

D1 is reversible: a future ADR could collapse to single-invocation with `xdist_group` markers if Praxion's pocket layout grows enough that startup cost matters. The schema field `parallel_safe` remains either way; only the leaf's interpretation changes.

D2 is partially reversible: changing the kebab→snake convention would require migrating every group's pyproject marker entry. The reserved-name set is purely additive — adding new reserved names is non-breaking.

## Prior Decision

None.
