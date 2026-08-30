---
name: rust-development
description: >
  Rust development conventions: type-driven API design (newtypes, builders,
  typestate), error-handling doctrine (thiserror for libraries, anyhow for
  applications), Cargo workspace/lint/toolchain configuration, and a
  mechanical-vs-judgment split distinguishing what cargo/clippy/rustfmt enforce
  from what needs agent review. Triggers: writing Rust code, configuring
  Cargo.toml lints or workspace, rustfmt/clippy setup, choosing thiserror vs
  anyhow, cargo-nextest test runs, reviewing unsafe code, Rust CI pipeline
  design, picking a crate for a new capability (async runtime, web framework,
  serialization, database).
allowed-tools: [Read, Write, Edit, Glob, Grep, Bash]
compatibility: Claude Code
staleness_sensitive_sections:
  - "Essential Crates"
  - "Toolchain and Workspace"
staleness_threshold_days: 90
---

# Modern Rust Development

Conventions for Rust development following the language's codified canon (API Guidelines,
Effective Rust, the Cargo/Clippy/rustfmt books) and 2026 ecosystem defaults.

**Satellite files** (loaded on-demand):

- [references/type-and-api-design.md](references/type-and-api-design.md) -- newtypes, builders,
  typestate, sealed traits, `#[non_exhaustive]`, generics vs `dyn`, conversion-prefix conventions
- [references/error-and-panic.md](references/error-and-panic.md) -- library/application error
  fork, `thiserror`/`anyhow`, panic-vs-`Result` contract, doc-comment error contracts
- [references/toolchain-and-workspace.md](references/toolchain-and-workspace.md) -- workspace
  manifests, `rust-toolchain.toml`, `[lints]` mechanics, MSRV, supply chain, caching
- [references/essential-crates.md](references/essential-crates.md) -- curated crate catalog by
  archetype (serialization, async, web, database, CLI, errors, testing)
- [references/unsafe-and-concurrency.md](references/unsafe-and-concurrency.md) -- `unsafe`
  protocol, Miri, `Send`/`Sync`, `Arc<Mutex<T>>` discipline, cancellation safety
- [references/project-scaffolding.md](references/project-scaffolding.md) -- what a well-formed
  Rust repo contains, tiered by unconditional vs project-property-conditional

## Gotchas

Non-obvious pitfalls that cause silent failures or confusing errors:

- **`cargo-nextest` cannot run doctests.** It is a process-per-test runner with real speedups
  (1.37x-3.38x measured), but a nextest-only CI pipeline silently stops testing your rustdoc
  examples. Always pair it with `cargo test --doc` as a second step.
- **Stable `rustfmt` silently ignores nightly-only keys.** `group_imports`, `imports_granularity`,
  and `wrap_comments` are the most-wanted `rustfmt.toml` keys, but they only take effect on a
  nightly toolchain. A `rustfmt.toml` full of these keys produces a config that stable `cargo fmt`
  warns about and ignores -- it looks configured but enforces nothing. A defensible stable-only
  default is `edition` + `style_edition` and nothing else.
- **`[lints]` and `-D warnings` are complementary, not alternatives.** The `[lints]` table (Cargo
  >=1.74) sets policy for lints you opt into; `-D warnings` in CI promotes *every* remaining
  warning -- including rustc defaults and future new lints -- to an error. Do both. And when a
  lint *group* (`clippy::all`, `clippy::pedantic`) is overridden by an individual lint, the group
  needs a **negative `priority`** (lower priority is emitted first) or the override silently loses:
  `all = { level = "warn", priority = -1 }`.
- **`actions-rs/*` is archived.** The entire GitHub Actions organization is unmaintained, uses
  deprecated Node 12 and `set-output`. Never scaffold `actions-rs/toolchain`, `actions-rs/cargo`,
  or `actions-rs/clippy-check`. Use `dtolnay/rust-toolchain` + plain `cargo` run steps instead.
- **`[patch]`, `[replace]`, and `[profile.*]` in a workspace-member manifest are silently
  ignored.** These three tables are only honoured in the *root* manifest of a workspace. Putting
  one in a member's `Cargo.toml` compiles fine and does nothing -- a quiet footgun for anyone
  used to per-crate configuration.

## Crate Role

Nearly every doctrine below forks on the crate's **role** -- a single ruleset is wrong half the
time. Determine the role before applying a check:

| Role | Error type | Visibility default | MSRV/semver stance |
|---|---|---|---|
| **Library** (published or consumed by other crates) | Concrete, `#[non_exhaustive]` enum/struct implementing `std::error::Error`; `thiserror` for boilerplate | Minimize (`pub(crate)` workhorse); every `pub` item is a semver commitment | `rust-version` declared and honored; `cargo-semver-checks` before publish |
| **Application** (binary, `main.rs` is the caller) | Opaque, context-carrying `anyhow::Error` | Whatever the binary needs internally | MSRV matters only for the toolchain deploying it, not for downstream consumers |
| **Internal workspace crate** (never published, consumed only by siblings) | Either doctrine is defensible -- default to the library doctrine unless the crate is pure glue | `pub(crate)` at the crate level is meaningless across workspace members; use module-level `pub(crate)` inside each crate | No external MSRV contract; the workspace's own toolchain pin governs |

## Mechanical vs. Judgment

Rust has an unusually codified canon (the API Guidelines' C-XXX checklist is literally citable),
which means far more of it is mechanically enforceable than in most languages. Delegate the left
column to tools; spend agent attention on the right column.

| Mechanical (delegate to a tool, never re-implement) | Judgment (agent review; often routes to a per-project ADR) |
|---|---|
| Formatting -- `cargo fmt --check` | Type-design smells: `bool` param -> enum, `pub` field with a documented invariant -> private + validating constructor, correlated field pair -> enum (see [type-and-api-design.md](references/type-and-api-design.md)) |
| Lints -- `cargo clippy --all-targets -- -D warnings` | Error granularity: how many variants, whether to split by fallible operation (contested -- C2) |
| Doc examples compile & run -- `cargo test --doc` | `anyhow` vs concrete error types in a library boundary (contested -- C3) |
| UB in `unsafe` paths -- `cargo miri test` (gated on presence of `unsafe`) | Workspace layout: flat `crates/` vs single package with modules (contested -- see [project-scaffolding.md](references/project-scaffolding.md)) |
| MSRV declared and CI-verified -- `rust-version` + a pinned toolchain job | `clippy::pedantic` adoption -- not enabled by default; routes to a per-project ADR |
| Manifest metadata / publish-readiness -- `clippy::cargo` group | Concurrency review: lock ordering, cancellation safety, whether a channel would remove a mutex entirely |

## Code Style

**Formatter**: `rustfmt`, configured via the shipped stable-only baseline at
[`assets/rustfmt.toml`](assets/rustfmt.toml) (`edition` + `style_edition` only -- see the
stable/nightly Gotcha above for why more keys are a trap).

**Linter**: `clippy`, configured via the shipped baseline at
[`assets/cargo-lints.toml`](assets/cargo-lints.toml) -- `[lints.rust]` + `[lints.clippy]` in both
package form and `[workspace.lints.*]` + `lints.workspace = true` form. `correctness` stays at its
deny-by-default level; four warn groups are pre-populated; `unsafe_code` policy is commented with
its two legitimate settings; `pedantic` is deliberately **not** enabled (contested, routes to a
per-project ADR).

**Toolchain pin**: [`assets/rust-toolchain.toml`](assets/rust-toolchain.toml) -- `channel =
"stable"`, `components = ["rustfmt", "clippy"]`, `profile = "minimal"`. Comment records the
pin-vs-float trade-off (byte-reproducible builds vs. an aging compiler) as a per-project decision.

## Quick Commands

```bash
# Code quality (order matters: format -> lint -> test)
cargo fmt --all                              # Format
cargo clippy --all-targets -- -D warnings    # Lint (all warnings as errors in CI)
cargo test --doc                             # Doc-tests (nextest cannot run these)

# Testing
cargo nextest run                            # Fast, process-per-test runner (CI + large suites)
cargo test                                   # Fine for a small crate; runs doctests too

# Supply chain
cargo deny check                             # advisories + bans + licenses + sources
```

### Pipeline-Agent Compact Mode

When invoked from a pipeline agent (`implementer`, `test-engineer`, or any subagent operating
under a `maxTurns` budget), prefer compact tool output. Verbose output compounds in cumulative
agent context -- every passing-test line written on turn N rides along inside turn N+1's input.

```bash
# Compact defaults — use these in pipeline runs
cargo nextest run --no-fail-fast             # Terse pass/fail summary, not per-test noise
cargo clippy --all-targets --message-format=short -- -D warnings  # One line per finding

# Escalate only when investigating a specific failure
cargo test --doc <test_name> -- --nocapture  # Single doctest deep-dive
cargo nextest run -- <test_name>             # Verbose for one targeted test
```

## Related Skills

- [`data-structure-design`](../data-structure-design/SKILL.md) -- the Data-Structures-First pillar;
  its `references/rust-patterns.md` leaf is the Rust-specific smell-to-remedy table this skill's
  Crate Role and Mechanical-vs-Judgment tables summarize at a higher level.
- [`test-coverage`](../test-coverage/SKILL.md) -- `references/rust.md` leaf covers `cargo-llvm-cov`
  and the nightly-only branch/doctest-coverage limitation.
- [`testing-strategy`](../testing-strategy/SKILL.md) -- `references/rust-testing.md` leaf covers
  `proptest`, `insta`, `trybuild`, `loom`/`shuttle`, `criterion`/`divan`.
- [`architectural-fitness-functions`](../architectural-fitness-functions/SKILL.md) --
  `contexts/rust.md` covers visibility-as-fitness-function and `cargo-deny` policy enforcement.
- [`cicd`](../cicd/SKILL.md) -- the 5-job Rust CI shape (fmt / clippy / test+doctest / deny / MSRV).

**Why this skill is unified rather than split** (unlike `python-development` +
`python-prj-mgmt`): Cargo is a single toolchain that owns build, dependency management, testing,
and packaging at once -- there is no separate project-management concern to split out the way pixi
or uv exists alongside Python's `pyproject.toml`. This is a deliberate asymmetry with the Python
and TypeScript skill pairs, not an oversight.
