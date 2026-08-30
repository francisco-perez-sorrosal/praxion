# Rust Development

Conventions for modern Rust development: type-driven API design, error-handling doctrine,
Cargo workspace/lint/toolchain configuration, and a curated crate catalog by project archetype.

## When to Use

- Writing Rust code in any project
- Configuring `Cargo.toml` lints, workspace layout, or a `rust-toolchain.toml` pin
- Setting up `rustfmt`/`clippy`
- Choosing between `thiserror` and `anyhow` for error handling
- Running or configuring `cargo-nextest`
- Reviewing `unsafe` code or concurrency primitives
- Designing a Rust CI pipeline
- Picking a crate for a new capability (async runtime, web framework, serialization, database)

## Activation

Auto-triggers on Rust development tasks: writing code, configuring Cargo.toml, setting up
lints/formatting, reviewing unsafe code, choosing a crate.

Trigger explicitly by mentioning "rust skill", "cargo", "clippy", "rustfmt", "thiserror",
"anyhow", or "cargo-nextest".

## Skill Contents

- `SKILL.md` — core conventions: gotchas, crate-role fork, mechanical-vs-judgment split, code
  style, quick commands
- `references/type-and-api-design.md` — newtypes, builders, typestate, sealed traits,
  `#[non_exhaustive]`, generics vs `dyn`
- `references/error-and-panic.md` — library/application error fork, `thiserror`/`anyhow`,
  panic-vs-`Result` contract
- `references/toolchain-and-workspace.md` — workspace manifests, `rust-toolchain.toml`,
  `[lints]` mechanics, MSRV, supply chain
- `references/essential-crates.md` — curated crate catalog by project archetype
- `references/unsafe-and-concurrency.md` — `unsafe` protocol, Miri, `Send`/`Sync`,
  `Arc<Mutex<T>>` discipline
- `references/project-scaffolding.md` — what a well-formed Rust repo contains
- `assets/rustfmt.toml` — stable-only formatter baseline
- `assets/cargo-lints.toml` — `[lints.rust]`/`[lints.clippy]` policy baseline (package and
  workspace forms)
- `assets/rust-toolchain.toml` — toolchain pin baseline

## Related Skills

- [`data-structure-design`](../data-structure-design/SKILL.md) — the Data-Structures-First
  pillar; its `references/rust-patterns.md` leaf is the Rust-specific smell-to-remedy table
- [`test-coverage`](../test-coverage/SKILL.md) — Rust coverage via `cargo-llvm-cov`
- [`testing-strategy`](../testing-strategy/SKILL.md) — advanced Rust testing: `proptest`,
  `insta`, `trybuild`, `loom`/`shuttle`, `criterion`/`divan`
- [`architectural-fitness-functions`](../architectural-fitness-functions/SKILL.md) —
  visibility-as-fitness-function and dependency policy enforcement for Rust
- [`cicd`](../cicd/SKILL.md) — the 5-job Rust CI shape
