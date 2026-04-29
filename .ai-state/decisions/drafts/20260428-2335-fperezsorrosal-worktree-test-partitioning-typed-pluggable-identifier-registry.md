---
id: dec-draft-9de2a93b
title: Typed-pluggable-identifier registries (selector_strategy and parallel_runner) as the trunk's language-additive primitive
status: proposed
category: architectural
date: 2026-04-28
summary: Two trunk-owned registries (selector_strategy and parallel_runner) hosted as Markdown tables in the test-topology trunk reference; new language leaves register additional rows without modifying the trunk schema, satisfying the "additive at the leaves" constraint.
tags: [test-topology, schema, registry, trunk-leaf, language-agnostic, plugin-mechanism]
made_by: agent
agent_type: systems-architect
pipeline_tier: standard
affected_files:
  - skills/testing-strategy/references/test-topology.md
  - skills/testing-strategy/references/python-testing.md
---

## Context

The `HANDOFF_CONSTRAINTS.md` (HR1) directive requires the test-topology trunk schema to pass a "hypothetical Go module" acceptance test: an architect filling in `TEST_TOPOLOGY.md` for a Go module the codebase has never seen must succeed without modifying the trunk schema. The directive's specific guidance — "any group field that names a tool (e.g., `selector_strategy`, `parallel_runner`) is a *typed pluggable identifier* with a per-language registry, not a hardcoded string in the trunk schema" — is the architectural constraint this ADR resolves.

The researcher's draft schema (RESEARCH_FINDINGS.md §C.1.2) used Python-flavored values throughout: `test_globs` field with mixed string forms (`"path/to/test_x.py"` and `"-m marker_name"`), implicit pytest semantics, no abstraction over selectors. This works for a Python-only codebase but cannot scale additively to Go, JS, or Rust without breaking the schema.

Three options for resolving the abstraction:

1. **Hardcoded strings**: trunk owns a fixed enum of selector names; new languages require a trunk-schema rev.
2. **Free-form strings**: trunk has a `selector_strategy` field with no constraint on values; the leaf or the runner interprets them at materialization time.
3. **Typed pluggable identifier registry**: trunk defines the *shape* of the registry (identifier name, argument shape, registered by); leaves contribute rows; the runner dispatches by identifier.

## Decision

**Adopt option 3 — two trunk-owned registries hosted as Markdown tables in the trunk reference file.**

The two registries are:

- **Registry 1 — `selector_strategy`**: identifies how a group's tests are materialized at runtime. Each row names an identifier (e.g., `pytest-globs`, `pytest-markers`, `go-test-packages`), the argument shape that identifier expects, and the leaf that registered it.
- **Registry 2 — `parallel_runner`**: identifies how parallel-safe groups are executed in parallel. Each row names an identifier (e.g., `pytest-xdist-loadfile`, `go-test-parallel`, `none`) and the leaf-equivalent invocation knob.

Per-group `selectors:` field uses a typed envelope `{strategy: <selector_strategy_id>, arg: <identifier-typed argument>}`. A group MAY have multiple `selectors` entries (the runner unions them at materialization).

Per-leaf default `parallel_runner` lives in the leaf reference file's "Defaults" section (not per-group); a group's `parallel_safe: false` flag downgrades that group's invocation to the registry's `none` identifier.

The registry tables live in `skills/testing-strategy/references/test-topology.md` (the trunk reference file). Append-only rows; per-language sections; section ownership is the leaf author for their language's rows.

## Considered Options

### Option A — Hardcoded enum in trunk

Trunk schema declares: `selector_strategy: <pytest-globs | pytest-markers | manual>`. Adding a Go leaf requires a trunk revision: edit the enum, edit the schema, ship a coordinated change.

**Rejected.** Violates HR1 directly: adding a new language is not "purely additive at the leaves" — it requires editing the trunk's enum. The whole point of the constraint is to avoid this.

### Option B — Free-form strings (no registry)

Trunk schema declares: `selector_strategy: <string>` with no constraint. The leaf documents valid values; the runner interprets them; sentinel TT05 cannot validate against the schema (because there is no schema-level set of valid values).

**Rejected.** Loses the type-safety the directive named. Sentinel cannot detect typos (`pytest-glob` vs `pytest-globs`). New leaves cannot be enforced to register cleanly. The schema becomes a hint, not a contract.

### Option C — Typed pluggable identifier registries (chosen)

Trunk declares the registry tables; leaves contribute rows; sentinel TT05 validates that every group's `selector_strategy` value resolves to a registered identifier in Registry 1.

**Selected.**

**Pros:**
- Perfectly additive: a new leaf appends rows; the trunk schema is unchanged.
- Type-safe: every value used in `TEST_TOPOLOGY.md` must appear in a registry, so typos are caught at sentinel validation time (and at runtime via the runner's dispatcher).
- Extensible: new identifier *kinds* (beyond selector and parallel runner) can be added later as additional registries without breaking existing leaves. For example, a future `coverage_collector` registry could distinguish `coverage-py`, `c8`, `tarpaulin`, etc.
- Mirrors a known-working pattern in Praxion: `rules/swe/agent-model-routing.md` has a per-agent tier table that languages and downstream consumers contribute rows into; the same governance pattern (append-only, sentinel-validated, ADR-required for removal) applies cleanly.
- The argument-shape field per row makes the registry self-documenting: a Go leaf author reads `arg: list of pytest path/file glob strings` for `pytest-globs` and immediately knows the new Go entry needs an analogous "argument shape" specification.

**Cons:**
- One additional layer of indirection compared to free-form strings. A reader must consult the registry to learn what a `pytest-globs` value means. Mitigation: the trunk reference file is short (single registry pair, ~1 page), and the leaf reference file's invocation example shows the concrete materialization.
- Concurrent multi-language leaf additions could produce merge conflicts on the registry tables. Mitigation: per-language sections within the registry; rows are append-only; standard git merge resolves; the very-low likelihood of two language leaves landing the same week is acceptable.
- The Argument shape is informally specified (free-form prose). A future maintenance burden may emerge if argument shapes drift across rows. Mitigation: the argument-shape descriptions are short and the registry is small; if the registry grows beyond ~10 rows, a more formal schema (JSON Schema or similar) can be introduced — that's a future concern.

## Consequences

### Positive

- HR1 ("hypothetical Go module" acceptance test) is satisfied by construction. The Go module worked example in `SYSTEMS_PLAN.md` is the proof.
- Sentinel TT05 has a concrete check: every group's `selector_strategy` value must appear as a registered identifier. Unregistered values FAIL.
- The Python leaf is the first registered set: `pytest-globs`, `pytest-markers`, optionally `pytest-keywords`. This sets the precedent for future leaves.
- The architecture-doc Test Topology section has a clean structural story: trunk owns the registry shape, each leaf contributes rows; users browse the registry to see what languages are supported.

### Negative

- Future identifier deprecation requires an ADR. This is the right level of governance — removing a registered identifier is a breaking change for any project using it — but it does add ceremony.
- The registry tables live in the trunk reference file, so any project consuming the i-am plugin inherits all registered rows (including languages they don't use). Token cost: very small (each row is one table line).
- Sentinel TT05 must be designed to handle conditional activation when only some leaves are registered (a Python-only project should not see WARN/FAIL for a missing Go leaf). The TT05 wording in the plan handles this by validating per-pocket-relevant entries only.

### Reversibility

The registry pattern itself is hard to reverse — once leaves register identifiers, removing the registry primitive would break every consuming project. This is acceptable, since the alternative (hardcoded enum or free-form strings) is strictly worse.

Individual identifier rows ARE reversible via the standard ADR-supersession protocol: an ADR proposes removal, a deprecation marker lives in the registry for one minor version, then the row is removed.

## Prior Decision

None — new architectural primitive.
