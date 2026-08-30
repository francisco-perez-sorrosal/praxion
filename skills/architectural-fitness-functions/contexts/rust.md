# Rust Architectural Fitness Functions

Rust-specific implementation guide for architectural fitness functions. Load alongside
the generic [Architectural Fitness Functions](../SKILL.md) skill.

**Related skills:**
- [Rust Development](../../rust-development/SKILL.md) -- toolchain, lints, `[lints]` mechanics
- [testing-strategy Rust leaf](../../testing-strategy/references/rust-testing.md) -- nextest, doc-tests, compile-fail testing in context

## Table of Contents

- [Tooling Overview](#tooling-overview)
- [Visibility Is a Layering Mechanism Only at Crate Granularity](#visibility-is-a-layering-mechanism-only-at-crate-granularity)
- [Compile-Time API Guarantees](#compile-time-api-guarantees)
- [Dependency-Policy Fitness Functions — `cargo-deny` Bans](#dependency-policy-fitness-functions--cargo-deny-bans)
- [Feature-Matrix Verification — `cargo-hack --each-feature`](#feature-matrix-verification--cargo-hack---each-feature)
- [Workspace Dependency-Graph Assertions](#workspace-dependency-graph-assertions)
- [Citation Locations — Rust](#citation-locations--rust)
- [Authoring Workflow — Rust](#authoring-workflow--rust)
- [References](#references)

## Tooling Overview

Rust has no established graph-rule tool equivalent to `import-linter` (Python) or
`dependency-cruiser` (TypeScript) for intra-crate module boundaries. The decision rubric
in [SKILL.md](../SKILL.md) still applies, but its answer for Rust differs by granularity:

| Invariant | Available mechanism | Precondition |
|---|---|---|
| "Module A must not import module B" (single crate) | assertion-based test only — no graph-rule tool fills this gap | none — this is the default case |
| "Crate A must not depend on crate B" (workspace) | `pub(crate)`/`pub(super)` visibility, backed by an assertion test over `cargo metadata` | multi-crate workspace |
| Dependency policy (banned/duplicate/unlicensed crates) | `cargo-deny` bans | none |
| Feature additivity across the matrix | `cargo-hack --each-feature`, scheduled job | non-trivial feature matrix |
| "This misuse must not compile" | rustdoc `compile_fail` doc-test (default); `trybuild` (conditioned) | see below |
| Everything else (naming, doc contracts, filesystem conventions) | assertion-based test (`#[test]` in `fitness/tests/*.rs` or a dedicated `fitness` workspace member) | none |

## Visibility Is a Layering Mechanism Only at Crate Granularity

Rust visibility (`pub`, `pub(crate)`, `pub(super)`, `pub(in path)`) is scoped to the
**module tree**, and it is **not directional**. Within a single crate, every
`pub(crate)` item is reachable from every other module in that crate, in any direction.
`pub(crate)` cannot express "the domain module must not import the infra module" —
it can only express "this item is invisible outside the crate," which says nothing
about which modules inside the crate may reach it.

Visibility becomes a *layering* mechanism only at **crate** granularity, in a
multi-crate workspace: a dependency edge between two workspace members is enforced by
Cargo itself (member A cannot use member B's items unless A depends on B), and
`pub(crate)` within member B then keeps those items out of every other member's reach
by construction. That guarantee presupposes the workspace already exists — and a crate
split bought only for this purpose imports a real cost: a change low in the dependency
graph forces recompilation of everything above it, so a boundary nobody otherwise needs
has bought a rebuild cost and nothing else.

**Consequence for a single-crate project — the common case a scaffolder emits:**
visibility provides no substitute for an import-boundary check. There is no
Rust-native mechanism that expresses "module `domain` must not import module
`infra`" within one crate. An assertion-based fitness test (parsing `use` statements
via `syn`, or scanning source text for a forbidden import path) is not a fallback for
a missing graph-rule tool here — it is the *only* available mechanism, exactly as it
is for any invariant the language cannot express structurally.

Do not reach for a crate split as a way to buy this enforcement "for free" — see
[Workspace Dependency-Graph Assertions](#workspace-dependency-graph-assertions) below
for the precondition that should already hold before a workspace exists at all.

## Compile-Time API Guarantees

Two mechanisms assert "this misuse must not compile," at different cost:

| Mechanism | Asserts | Cost |
|---|---|---|
| rustdoc `compile_fail` doc-test | Compilation fails — nothing about the exact diagnostic | Low — runs with `cargo test --doc`, no extra tooling, no toolchain sensitivity |
| `trybuild` | Compilation fails **with a specific stderr message**, snapshot-compared | Higher — stderr snapshots are compiler-version-sensitive; expect churn across stable releases unless the job pins its toolchain |

**Default:** rustdoc `compile_fail` is the low-maintenance choice for "this type
cannot be constructed in an invalid state" / "this trait cannot be implemented outside
the crate" style guarantees. It costs nothing beyond a doc comment and asserts exactly
what most fitness invariants need — that the misuse does not compile — without
committing to exact compiler output.

**`trybuild` is conditioned, not a default:** reach for it specifically for
proc-macro and diagnostic-UX crates, where the diagnostic text *is* the product being
tested (a proc-macro's error message is user-facing API surface in the same sense a
library function's return type is). Its operative caveat is toolchain-pin
sensitivity — an unpinned `trybuild` job has a scheduled failure on the next stable
Rust release, because the expected-stderr snapshot was generated against one compiler
version. Pin the toolchain for the job specifically, or accept periodic snapshot
regeneration as a maintenance cost.

## Dependency-Policy Fitness Functions — `cargo-deny` Bans

`cargo-deny`'s `bans` check (config-driven via `deny.toml`) is a dependency-policy
fitness function: it enforces banned crates, duplicate-version limits, and permitted
sources across the full dependency graph, and fails the build when violated. Bootstrap
with `cargo deny init`, run via `cargo deny check` (or `EmbarkStudios/cargo-deny-action`
in CI). This complements the `advisories` and `licenses` checks the same tool provides
— all four run from one config file and one invocation.

## Feature-Matrix Verification — `cargo-hack --each-feature`

`cargo-hack --each-feature` builds and tests every feature in isolation (plus the
default set and `--no-default-features`), catching the "it compiles for me because my
feature combination happens to work" class of bug. This is a **feature-matrix
verification tool, not a graph-rule invariant** — it says nothing about which module
imports which; it says every feature combination compiles on its own. Because it
temporarily rewrites manifests and processes workspace members sequentially, it is
slow and belongs on a scheduled or pre-release job, not a per-PR gate — emit it only
when the crate has a non-trivial feature matrix, especially one that is published.

## Workspace Dependency-Graph Assertions

**Multi-crate precondition:** the checks below apply only once a workspace has more
than one crate. A single-package project has no crate-to-crate graph to assert over —
see [Visibility Is a Layering Mechanism Only at Crate Granularity](#visibility-is-a-layering-mechanism-only-at-crate-granularity)
above for what to do instead.

Where a workspace does exist, a workspace-graph assertion test (parse
`cargo metadata --format-version 1`, assert the expected crate-to-crate dependency
edges and the absence of forbidden ones) is the Rust analogue of the
`independence`/`layers` contract types Python and TypeScript express through
`import-linter`/`dependency-cruiser`. Write it as an ordinary `#[test]` in the
project's fitness test suite, following the citation and authoring conventions below.

## Citation Locations — Rust

Rust has no single idiomatic equivalent of a Python module docstring or a
JavaScript object's `comment` field for every rule shape, so the citation location
depends on which mechanism carries the check:

| Rule type | Citation location | Example |
|-----------|-------------------|---------|
| Assertion-based fitness test (`#[test]`) | `///` doc comment directly above the test function | `/// Cites: dec-NNN (layered architecture) — domain must not import infra.` |
| `deny.toml` ban entry | `deny.toml` comment line preceding the `[[bans.deny]]` entry | `# dec-NNN — banned: superseded by workspace-internal replacement` |
| Workspace-graph assertion test | Same as assertion-based test above — `///` doc comment | `/// Cites: dec-NNN — crate `infra` must not depend on crate `domain`.` |

The citation regex (same as Python's and TypeScript's meta-citation rule):

```
dec-\d{3,}|CLAUDE\.md§[A-Z][A-Za-z ]+
```

Write the citation **before** the test body — it forces upfront justification, the
same discipline the Python and TypeScript contexts apply.

## Authoring Workflow — Rust

1. **Choose the mechanism** per the [Tooling Overview](#tooling-overview) table above:
   assertion-based test (the default for single-crate invariants), `cargo-deny` bans
   (dependency policy), `cargo-hack --each-feature` (feature matrix), or a
   workspace-graph assertion test (multi-crate only).

2. **Write the citation first** — as a `///` doc comment above the test function, or a
   comment line in `deny.toml` — before writing the check logic.

3. **Write the check**:
   - Assertion-based: an ordinary `#[test]` fn in the fitness test suite, parsing
     source text, `syn`-derived ASTs, or `cargo metadata` JSON as needed.
   - Dependency policy: a `[[bans.deny]]` (or `skip`/`allow`) entry in `deny.toml`.
   - Feature matrix: a scheduled CI job running `cargo hack --each-feature`.

4. **Run the checks**:

   ```bash
   cargo test --workspace           # assertion-based fitness tests
   cargo deny check                 # dependency-policy checks
   cargo hack --each-feature check  # feature-matrix verification (scheduled, not per-PR)
   ```

5. **No meta-citation rule ships for Rust in this pass.** The Python and TypeScript
   contexts each have an automated citation scanner (`test_meta_citation.py`, and its
   `dependency-cruiser`/ESLint equivalent); a Rust port is a natural follow-on but is
   not part of this leaf. Review citations by hand until one lands.

## References

| Reference | When to consult |
|-----------|-----------------|
| [`../SKILL.md`](../SKILL.md) | Decision rubric, citation contract, waiver pattern (language-agnostic) |
| [Rust Development](../../rust-development/SKILL.md) | `[lints]` mechanics, workspace manifest structure |
| [`rust-development/references/toolchain-and-workspace.md`](../../rust-development/references/toolchain-and-workspace.md) | Workspace layout, `resolver = "3"`, feature additivity |
