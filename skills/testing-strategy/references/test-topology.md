<!--
  Section ownership:
  - Schema fields (§"Test Group Schema")         : STABLE — changes require an ADR
  - Tier vocabulary (§"Tier Vocabulary")          : STABLE — changes require an ADR
  - Registry 1 / selector_strategy (§"Selector Strategy Registry")   : APPEND-ONLY — new language leaves add rows; rows are not removed
  - Registry 2 / parallel_runner   (§"Parallel Runner Registry")      : APPEND-ONLY — same append-only rule
  - shared_fixture_scope enum (§"shared_fixture_scope Enum")          : STABLE — changes require an ADR
  - Protocol conventions (§"Document Conventions")                    : STABLE — editorial improvements via PR, no ADR required

  Editing protocol:
  - Stable sections: editorial changes may be made without an ADR; semantic/structural changes require one.
  - Append-only sections: append rows at the bottom of the table; do NOT remove or rename existing rows.
    Once a registry identifier ships into the field it may be referenced by populated TEST_TOPOLOGY.md
    files in consumer projects. Removal requires an ADR and a migration window.
  - After editing a registry table, update its staleness marker: <!-- last-verified: YYYY-MM-DD -->
-->

# Test Topology — Language-Agnostic Trunk Schema

This file is the **language-agnostic source of truth** for the test-topology protocol. It defines the group schema, tier vocabulary, identifier registries, and document conventions that apply regardless of which programming language, test framework, or parallel runner a project uses. Architects and tooling (planners, sentinel checks) read this file directly. Implementers read this file for the schema contract and their language's leaf reference file for concrete framework wiring. The protocol lives in the existing `testing-strategy` skill so it composes naturally with the skill's existing tier-selection and isolation guidance — see [`../SKILL.md`](../SKILL.md).

---

## Test Group Schema

A **test group** is a logical unit of tests that covers one or more named architectural subsystems. Each group is declared in the project's `.ai-state/TEST_TOPOLOGY.md` file using the following schema.

```yaml
# Trunk schema for a test group (language-agnostic).
# Concrete instances live in .ai-state/TEST_TOPOLOGY.md sections.

id: <kebab-case>
# required
# Unique topology key for this group. Kebab-case. Becomes the identifier-name
# source for runtime selectors (language leaves derive their selector argument
# from this id, e.g. snake_case form for markers). Must not collide with the
# reserved-name set (see §"Reserved Name Set").

title: <short human label>
# required
# One-phrase human label for dashboards and reports.

subsystems:
  - <subsystem-name>
# required, 1 or more entries
# Each entry must resolve to a component with "Status: Built" in
# .ai-state/ARCHITECTURE.md §3 (Components). The binding is checked by
# sentinel TT01. Use the component's canonical name from that table exactly.

tier: <unit | integration | contract | e2e>
# required
# Which tier of the test pyramid this group sits on.
# See §"Tier Vocabulary" for definitions.

selectors:
  - strategy: <selector_strategy_id>
    arg: <identifier-typed argument>
# required, 1 or more entries
# What the runner uses to materialize this group into a concrete test run.
# Each entry is a typed envelope: `strategy` is a registered identifier from
# Registry 1 (§"Selector Strategy Registry"); `arg` shape is governed by that
# identifier's contract. A group MAY have multiple selector entries; the runner
# unions them at materialization time.

file_dependencies:
  - <path-or-glob>
# required, 1 or more entries
# Source paths or globs whose change should fire this group (used by future
# change-detection tooling). Globs are filesystem-relative from the project
# root. Absolute path semantics are not allowed.

integration_boundaries:
  - <other-group-id>
# optional, 0 or more entries
# Group ids whose tests must also run when this group fires at phase tier.
# Closure semantics: one-hop direct at phase tier (group ids listed here are
# included; their further boundaries are NOT); transitive at pipeline tier
# (full suite runs regardless); none at step tier.
# See §"integration_boundaries Closure Semantics" for the full rule.

parallel_safe: <true | false>
# required
# Honest declaration of whether this group's tests can run concurrently with
# other workers without shared-state interference.
# - true: the runner MAY assign tests to parallel workers.
# - false: the runner MUST run this group's tests sequentially in an isolated
#   invocation (separate runner call, no shared workers with safe groups).
# See §"parallel_safe Semantics" for the full runner contract.

shared_fixture_scope: <none | per-test | per-file | per-process | per-suite>
# required
# Abstract scope of the most expensive shared setup this group relies on.
# The language leaf maps these abstract values to its framework's keywords.
# See §"shared_fixture_scope Enum" for value semantics.

expected_runtime_envelope:
  p50_seconds: <number>
  p95_seconds: <number>
# optional at M1 and M2; required from M3 (when sentinel TT04 activates)
# Declared wall-clock envelope for this group under normal conditions.
# See §"expected_runtime_envelope Policy" for the opt-in rationale.

shared_state: <none | tmp_path | network | filesystem | external_service>
# optional, informational
# Coarse hint about what shared resource this group touches. Used to reason
# about isolation requirements and parallelism boundaries. Language leaves
# may extend this enum additively via the registry (future work).

notes: <free-form short prose>
# optional
# One sentence of context, caveats, or TODOs.
```

### Field-Level Trunk / Leaf Classification

| Field | Layer | Notes |
|-------|-------|-------|
| `id` | Trunk | Kebab-case. Leaf may derive an additional form (e.g., snake_case for markers). |
| `title` | Trunk | Human label; no tooling concepts. |
| `subsystems` | Trunk | Forward reference into `.ai-state/ARCHITECTURE.md` §3 — language-neutral. |
| `tier` | Trunk | Unit / integration / contract / e2e vocabulary is universal. |
| `selectors` — structure | Trunk | The list shape and the `{strategy, arg}` envelope are trunk-owned. |
| `selectors` — strategy values | Leaf | The set of valid `strategy` identifiers is per-language via Registry 1. |
| `file_dependencies` | Trunk | Glob/path semantics are universal. |
| `integration_boundaries` | Trunk | Closure semantics defined in this file; language-neutral. |
| `parallel_safe` | Trunk | Abstract boolean flag; the leaf maps it to the runner's scheduler. |
| `shared_fixture_scope` | Trunk | Five abstract scope values replace any framework-specific keywords. |
| `expected_runtime_envelope` | Trunk | Wall-clock seconds are language-neutral. |
| `shared_state` | Trunk | Coarse abstract enum; leaves may extend additively. |
| `notes` | Trunk | Free prose. |

---

## Tier Vocabulary

These four values are the only valid choices for the `tier` field. They map to the standard test-pyramid levels described in the testing-strategy skill's "Test Strategy Selection" section.

| Value | Scope | Typical runtime |
|-------|-------|----------------|
| `unit` | Single function, class, or module; no real I/O | Milliseconds |
| `integration` | Multiple components or real I/O (DB, file system, network) | Seconds |
| `contract` | Service-boundary agreements; schema or event-format compatibility | Seconds |
| `e2e` | Full stack; user-visible behavior; real deployment surface | Seconds to minutes |

These values are shared across all languages. The language leaf does not redefine them.

---

## Selector Strategy Registry (Registry 1)

The `selector_strategy` registry maps the abstract `strategy` identifier in the `selectors` field to the concrete invocation each runner uses to materialize the group. This registry is the load-bearing mechanism that keeps the trunk schema language-additive: new language leaves register their tooling identifiers here without modifying the trunk schema fields.

<!-- Section is APPEND-ONLY. New language leaves add rows at the bottom of the table.
     Existing rows must not be removed; removal requires an ADR and a migration window.
     After adding rows, update the staleness marker below. -->

| Identifier | Argument shape | Registered by | Concrete meaning |
|-----------|----------------|---------------|-----------------|
| `manual` | List of explicit test identifiers | Trunk (default) | Explicitly enumerated test cases. Used for ad-hoc curation or when no automated selector fits. Rare. |

<!-- last-verified: 2026-04-29 -->

### Indicative Future Identifiers

The following identifiers are illustrative — they show the additive pattern language leaves follow. They are **not registered at this milestone** and must not be used in `TEST_TOPOLOGY.md` files until the corresponding leaf file ships.

| Identifier (future) | Registered by (future) | Indicative concrete meaning |
|--------------------|-----------------------|-----------------------------|
| `pytest-globs` | Python leaf | `pytest <args>` where args is a list of path/glob strings |
| `pytest-markers` | Python leaf | `pytest -m "<m1> or <m2>"` where args is a list of marker name strings |
| `pytest-keywords` | Python leaf (optional) | `pytest -k "<expr>"` where args is a keyword expression |
| `go-test-packages` | Go leaf | `go test <args>` where args is a list of package paths |
| `vitest-projects` | TypeScript leaf | `vitest run --project <args>` |
| `cargo-test-filters` | Rust leaf | `cargo test <filter>` where args is a list of filter strings |

Python projects register `pytest-globs`, `pytest-markers`, and `pytest-keywords` via the Python leaf reference file at `references/python-testing.md`. A Go project would register `go-test-packages` via a future `references/go-testing.md`. No trunk file needs modification.

---

## Parallel Runner Registry (Registry 2)

The `parallel_runner` registry records the runners a language leaf supports. Unlike Registry 1, this registry is recorded per-leaf in the leaf reference file's "Defaults" section. It is mirrored here for discoverability and sentinel validation.

<!-- Section is APPEND-ONLY. Same rules as Registry 1.
     After adding rows, update the staleness marker below. -->

| Identifier | Registered by | Concrete meaning |
|-----------|---------------|-----------------|
| `none` | Trunk (default) | Sequential — no parallel runner. All tests in the group run in a single process. |

<!-- last-verified: 2026-04-29 -->

### Indicative Future Identifiers

| Identifier (future) | Registered by (future) | Indicative concrete meaning |
|--------------------|-----------------------|-----------------------------|
| `pytest-xdist-loadfile` | Python leaf | `pytest -n auto --dist loadfile` — workers are assigned by file; file-scoped fixture state is stable |
| `pytest-xdist-load` | Python leaf | `pytest -n auto --dist load` — load-balanced; less robust when tests in the same file share fixture state |
| `go-test-parallel` | Go leaf | `go test -parallel N` |
| `vitest-threads` | TypeScript leaf | Vitest worker threads parallelism |
| `cargo-test-jobs` | Rust leaf | `cargo test -- --test-threads N` |

---

## shared_fixture_scope Enum

The five abstract values below represent scope granularity levels independent of any framework's keyword vocabulary. Each language leaf maps these abstract values to its framework's equivalents in the leaf reference file's "scope mapping table."

| Value | Semantics |
|-------|----------|
| `none` | No shared fixture state. Each test is fully isolated; no setup runs across test boundaries. |
| `per-test` | Setup and teardown run once per test case. Equivalent to the most granular scope each framework supports. |
| `per-file` | Setup runs once per test file (or equivalent module). Shared across all tests in one file but not across files. |
| `per-process` | Setup runs once per worker process. Shared across all files assigned to one worker; care required when tests from different files share this state. |
| `per-suite` | Setup runs once per entire test run. Shared across every test in the suite; this scope is the most likely source of inter-test interference. |

These values are purely descriptive of scope semantics. The runner enforcement rule is: if a group declares `shared_fixture_scope: per-suite` and `parallel_safe: false`, the runner must execute that group in an isolated sequential invocation (see §"parallel_safe Semantics").

---

## integration_boundaries Closure Semantics

The `integration_boundaries` field lists the group ids whose tests must also fire when the declaring group fires. The set of groups that actually runs depends on the **execution tier** at the time of invocation:

| Tier | Closure rule |
|------|-------------|
| `step` | No closure. Only the declared group runs. |
| `phase` | One-hop direct. The declared group plus every group listed in its `integration_boundaries` run. Their further boundaries are not followed. |
| `pipeline` | Transitive (full suite). All groups run, regardless of declared boundaries. This matches the integration-checkpoint step that closes every Standard/Full-tier pipeline. |

**Rationale for one-hop at phase tier:** Transitive closure at phase tier defeats the purpose of having a distinct `pipeline` tier — both would fire the full graph. One-hop closure gives a meaningful three-level gradient (small / medium / full) without three equivalent behaviors. If M2 pilots reveal that one hop is too narrow for cross-pocket coupling, the closure depth can be made configurable via an additive `boundary_depth` field; default `1` preserves today's behavior.

**Worked example with abstract group ids:**

Suppose group `A` declares:
```yaml
integration_boundaries:
  - B
```
And group `B` declares:
```yaml
integration_boundaries:
  - C
```

Execution outcomes:
- `Tests: groups=[A] tier=step` → runs **A only**.
- `Tests: groups=[A] tier=phase` → runs **A and B**. C is not included (one-hop only).
- `Tests: groups=[A] tier=pipeline` → runs **A, B, C, and all other groups** (full suite).

---

## parallel_safe Semantics

`parallel_safe` is a declaration by the group author about whether the group's tests can be assigned to parallel workers alongside other groups' tests.

| Value | Meaning | Runner obligation |
|-------|---------|-----------------|
| `true` | Tests in this group are safe for concurrent execution with other tests. They do not share global in-process state, port numbers, file paths, or external resources in a way that would cause interference. | The runner MAY assign tests from this group to any available worker without special sequencing. |
| `false` | Tests in this group require exclusive resource access, modify global in-process state, or rely on single-threaded execution semantics. | The runner MUST execute this group's tests in a separate, sequential invocation isolated from groups with `parallel_safe: true`. The runner MUST NOT mix tests from safe and unsafe groups in the same worker pool invocation. |

The concrete mechanism for runner isolation (separate invocation, specific scheduler option, etc.) is language-leaf-specific and documented in the leaf reference file. The trunk only specifies the abstract behavioral contract.

---

## expected_runtime_envelope Policy

The `expected_runtime_envelope` field records the declared wall-clock p50 and p95 for a group under normal conditions.

**Current policy:** This field is **optional at M1 and M2**. Its absence is not a lint or sentinel failure at these milestones.

**Rationale for opt-in:** At M1 (trunk-only, no behavioral pilot), no per-group runtime measurements exist in any project. Forcing the field would require inventing fictional baselines rather than measuring real ones. Sentinel check TT04 (runtime drift) self-deactivates when fewer than seven metrics reports with per-group data are available, making the absent field safe.

**Future policy (M3):** When sentinel TT04 activates (the milestone when the refactor-trigger circuit goes live), `expected_runtime_envelope` becomes required for every group that has been running for more than three pipeline cycles. At that point, sentinel TT04 files a `topology-drift` ledger row for groups whose p95 chronically exceeds the declared envelope by more than 50%.

---

## Protocol Activation Policy

The test-topology protocol activates at **Standard and Full tiers only**.

- **Lightweight tier**: the protocol does not activate. Lightweight's contract is minimal overhead — no canonical artifacts, no agent pipeline. If a Lightweight task touches more than one group, the existing escalation-to-Standard rule covers it.
- **Spike tier**: not applicable (exploratory; no topology expected).
- **Direct tier**: not applicable (single-file fix; no topology expected).

The `Tests:` field in `IMPLEMENTATION_PLAN.md` and `WIP.md` is optional at the schema level. Its absence means "protocol inactive — full suite runs" (today's default behavior). This makes the protocol additive: existing pipelines that do not use it continue working unchanged.

---

## Topology Regeneration Policy

`TEST_TOPOLOGY.md` is **not regenerated automatically** at any pipeline boundary.

Refresh is triggered by one of two events:

1. **Human-initiated**: the architect or test-engineer runs `/refresh-topology` (a future command; not yet available at M1).
2. **Sentinel-triggered**: sentinel TT03 accumulates 3 or more open `topology-drift` ledger rows and emits a WARN with "Run `/refresh-topology` — 3+ topology-drift items accumulated."

**Rationale for no automatic regeneration:** The `TEST_TOPOLOGY.md` file uses section ownership (architect owns the Subsystems table; test-engineer owns groups; planner owns `integration_boundaries`). Per-pipeline auto-regeneration would nullify section ownership — whichever agent regenerates the file becomes the de-facto owner of everything. The same model applies to `TECH_DEBT_LEDGER.md`: append-only with explicit refresh, not auto-regenerate.

---

## selector=manual Justification

When a step declares `selector=manual`, the planner or implementer must provide a `reason` value from the following closed set:

| Reason value | When to use |
|-------------|------------|
| `scope-mismatch` | The declared topology groups do not cleanly cover the files this step touches. |
| `cross-pocket-bridge` | The step touches code shared across multiple pockets in a way that no single group covers. |
| `topology-stale` | The topology has not been refreshed since the relevant subsystems changed. |
| `tier-escalation-debug` | The implementer is manually running a wider scope to debug a failure. |
| `other` | None of the above. Requires an accompanying `note=...` one-line explanation. |

The `reason` field is parseable by tooling. High rates of `other` reason values signal that the enum needs expansion.

---

## Reserved Name Set

The following identifiers must not be used as group `id` values. They are either used by upstream test tooling as special arguments, or they conflict with the tier vocabulary.

The trunk maintains this set at the level of universal conflicts. Language leaves append language-specific reserved names in their leaf reference file; the Python leaf's reserved set is a superset of this trunk set.

**Trunk reserved names (all languages):**

- Tier keywords: `unit`, `integration`, `contract`, `e2e`

Any name that conflicts with a widely-used test framework's built-in argument syntax in any supported language is a candidate for inclusion here. If you encounter a conflict in practice, file an objection and propose an addition via an ADR.

---

## Additive Leaf Escalation Clause

When a language leaf needs a selector strategy or parallel runner identifier that does not exist in the trunk's registries, the leaf author must **escalate to the architect** rather than hardcoding behavior in the leaf.

The correct path:
1. Open an objection noting the missing primitive.
2. Propose the new identifier (name, argument shape, registered-by, concrete meaning) to the architect.
3. The architect records the decision as an ADR and appends the row to the appropriate registry table in this file.
4. The leaf file then references the newly registered identifier.

Patching the leaf with hardcoded behavior that bypasses the registry silently breaks the protocol's additive guarantee and makes sentinel TT02 blind to that selector.

---

## Document Conventions

### Tests: Field in IMPLEMENTATION_PLAN.md Steps

Implementation steps that use the test-topology protocol add an optional `Tests:` field to their entry in `IMPLEMENTATION_PLAN.md` and `WIP.md`:

```
Tests: groups=[<group_id>, ...] tier=<step|phase|pipeline> selector=<auto|manual> [reason=<enum> when selector=manual] [note=<text> when reason=other]
```

**Schema:**
- `groups` — list of group ids from `TEST_TOPOLOGY.md` that this step's changes affect.
- `tier` — which execution tier applies: `step` (narrow), `phase` (medium), or `pipeline` (full).
- `selector` — `auto` means the runner derives the invocation from the group's `selectors` entries; `manual` means the implementer specifies the invocation directly.
- `reason` — required when `selector=manual`; must be one of the values in §"selector=manual Justification".
- `note` — required when `reason=other`; one-line free-form explanation.

**Absence means protocol inactive.** A step without a `Tests:` field runs the full suite (today's default behavior). The field is strictly optional at the schema level.

### TEST_RESULTS.md Per-Group Block

When the test-topology protocol is active for a step, the `TEST_RESULTS.md` entry for that step may include optional topology lines after the standard pass/fail/skip counts:

```
Tier: <step|phase|pipeline>
Groups: [<group_id>, ...]
Parallelism: <parallel-safe | sequential | mixed>
Per-group results:
  <group_id>: pass=N fail=N skip=N duration=<s>
```

These lines are **optional and backward-compatible**. Existing `TEST_RESULTS.md` consumers that do not know about test-topology continue to work without modification. Producers that have topology data available should include these lines to enable TT04 monitoring.

---

## Forward Pointers — Language Leaf Reference Files

This trunk file defines the protocol contract. Concrete tooling examples for each language live in the corresponding leaf reference file:

- **Python**: `references/python-testing.md` — registers `pytest-globs`, `pytest-markers`, and `pytest-keywords` as selector strategy identifiers; registers `pytest-xdist-loadfile` and `pytest-xdist-load` as parallel runner identifiers; provides the `shared_fixture_scope` mapping table to pytest scope keywords; documents the marker registration recipe and the filelock-based session-fixture pattern for parallel-unsafe groups.

Future leaf reference files follow the same pattern: one file per language, registering that language's identifiers in the two registries, mapping the abstract schema fields to the framework's concrete equivalents, and providing worked invocation examples for the implementer and test-engineer.

---

## Go Module — Portability Proof

The schema below shows a hypothetical Go group populated using only the trunk schema. No Python knowledge is required to read or fill in this entry. `go-test-packages` would be registered in Registry 1 by a future Go leaf file (`references/go-testing.md`); the trunk schema fields themselves require no modification.

```yaml
# Hypothetical Go group — no Python knowledge required.
# go-test-packages would be registered in Registry 1 by a future Go leaf.
id: aggregator-core
title: Aggregator core — windowing and rollups
subsystems: [aggregator]
tier: unit
selectors:
  - strategy: go-test-packages
    arg: ["./pkg/aggregator/...", "./pkg/aggregator/internal/windowing/..."]
file_dependencies:
  - "pkg/aggregator/*.go"
  - "pkg/aggregator/internal/windowing/*.go"
integration_boundaries:
  - aggregator-storage
parallel_safe: true
shared_fixture_scope: none
expected_runtime_envelope:
  p50_seconds: 0.1
  p95_seconds: 0.5
```

What a Go architect needs to do to use this schema:

1. Register `go-test-packages` in Registry 1 (one row in this file's table).
2. Create `references/go-testing.md` with runner identifiers and invocation examples.
3. No changes to trunk schema fields, no changes to closure semantics, no changes to sentinel TT01–TT05 wording.
