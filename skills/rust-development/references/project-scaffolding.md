# Project Scaffolding

Part of the [Rust Development](../SKILL.md) skill. Covers what a well-formed 2026 Rust repository
contains, tiered by unconditional (Tier 1) vs project-property-conditional (Tier 2), plus the
handful of layout questions that stay open rather than settled.

## Tier 1 — Always

| File | Content |
|---|---|
| `Cargo.toml` (root) | `[workspace]` (virtual manifest if multi-crate) with `resolver = "3"`, `members`, `[workspace.package]` (edition/license/repository/rust-version), `[workspace.dependencies]`, `[workspace.lints.rust]` + `[workspace.lints.clippy]` |
| `Cargo.toml` (members) | `[lints] workspace = true`; inherit shared fields with `field.workspace = true` |
| `Cargo.lock` | committed for binaries and workspaces; optional but recommended for pure libraries when pinning a toolchain |
| `rust-toolchain.toml` | `channel`, `components = ["rustfmt", "clippy"]`, `profile = "minimal"` — see [`assets/rust-toolchain.toml`](../assets/rust-toolchain.toml) |
| `rustfmt.toml` | `edition` + `style_edition` only, unless the project accepts a nightly fmt job — stable `rustfmt` cannot enforce `group_imports`/`imports_granularity` (see the parent skill's Gotchas) |
| `.gitignore` | `/target`, `**/*.rs.bk` |
| `README.md` | build/test/lint commands that actually work |
| `.github/workflows/ci.yml` | fmt / clippy / test(+doc) / deny jobs, `dtolnay/rust-toolchain` + `Swatinem/rust-cache`, `--locked`, `CARGO_INCREMENTAL: 0` |
| `deny.toml` | from `cargo deny init`; advisories + licenses at minimum |

## Tier 2 — Conditional

Nothing here should be emitted unconditionally — an unused `fuzz/` directory or a `deny.toml`
nobody reads is context pollution, not diligence.

| File / job | Emit when |
|---|---|
| `.cargo/config.toml` | a custom linker (lld/mold), `target-cpu`, per-target rustflags, or cargo aliases are needed — never scaffold empty |
| `clippy.toml` | lint *configuration values* are needed (`msrv`, `disallowed-methods`, `avoid-breaking-exported-api`), not just levels |
| `.config/nextest.toml` | nextest is adopted and profiles, retries, per-test timeouts, or JUnit output are needed |
| MSRV CI job | the package publishes a `rust-version` |
| `cargo-semver-checks` job | the crate is published to a registry |
| `fuzz/` + `cargo-fuzz` job | the crate parses or deserializes untrusted input |
| Miri job | the workspace contains `unsafe` (skip if `unsafe_code = "forbid"`) |
| `cargo-hack` job | the crate has a non-trivial feature matrix, especially if published |
| `cargo-mutants` / `cargo-machete` | scheduled workflow, not the PR path |
| Coverage (`cargo-llvm-cov`) | the number is actually consumed; otherwise it is a job that goes yellow and gets ignored |
| `release-plz.toml` + workflow | the project publishes releases from CI |
| `cargo-vet` (`supply-chain/`) | security-sensitive, with organizational buy-in or an imported audit set |
| `cross`/`cargo-zigbuild` config | binaries ship for other platforms |

Check staging — organizing by *when* a check runs (commit / merge / periodic / release) rather
than a flat tool list — is covered in
[`toolchain-and-workspace.md` § Supply Chain](toolchain-and-workspace.md#supply-chain); this leaf
does not restate that table.

## Workspace Layout — Decide in a Project ADR

The default scaffold is a **single package with modules**, not a multi-crate workspace. A
directory of modules costs nothing to create, has no boundary to maintain, and is the correct
starting shape for the large majority of Rust projects at the point a scaffolder runs.

A **flat `crates/` directory** (each subdirectory a crate, directory name matching crate name, root
as a virtual manifest with no `[package]` table) is a documented alternative *for a workspace you
already have* — it is not, on its own, a reason to create one.

- **Positions:**
  - *For a flat layout, once a workspace exists:* Cargo's own crate namespace is flat, so a nested
    directory tree adds a second organizational scheme with nothing forcing it to stay consistent;
    a flat list stays scannable on one screen; adding or moving a crate needs no parent-directory
    refactor.
  - *Against splitting into a workspace at all:* a crate split buys a compilation boundary, a
    visibility boundary, a dependency boundary, or a publishing boundary — but only if something
    concrete needs one of those. A crate split that buys a boundary nobody enforces has bought a
    rebuild cost (a change low in the dependency graph forces recompilation of everything above it)
    and nothing else.
- **Evidence tier:** the flat-`crates/` recommendation traces to a single tertiary practitioner
  source — a rust-analyzer maintainer's write-up of that project's own workspace, in the
  10K–1M-LOC range. Every stated rationale in it is a property of *large, long-lived,
  multi-contributor* workspaces: at one or two crates there is no tree to deteriorate, nothing to
  scan on one screen, and no parent-directory refactor to avoid. The rationale does not transfer to
  a project at the size a scaffolder actually emits.
- **Precondition before reaching for a workspace at all:** name the concrete reason a second crate
  exists today — a compilation boundary, a visibility boundary that only bites at crate
  granularity, a dependency boundary, or a publishing boundary — not a reason it *might* exist
  later.

Route the actual choice — single package vs. workspace, and if a workspace, flat `crates/` vs. a
nested tree — to a per-project ADR. Nothing shipped by this skill scaffolds a `crates/` directory
by default.

## Binary vs. Library Layout

**Thin `main.rs` over `lib.rs` is a good default**, resting on one mechanism: a binary-only crate
(no library target) cannot be exercised in-process through its own API from `tests/*.rs` — there is
no library target for an integration test to `use`. Moving the real logic into `src/lib.rs` behind
a thin `src/main.rs` restores that testability.

Two further consequences follow, but only **conditionally** — they matter once a specific project
property holds, not as additional unconditional reasons to apply the pattern:

- **If another crate will consume this logic** (a workspace member, a future library extraction), a
  `bin`-only crate cannot be depended on at all; a `lib` target can.
- **If the project uses a compiler-wrapper cache that cannot cache binaries** (bin/dylib/cdylib/
  proc-macro crate types invoke the linker rather than only the compiler), a `lib` target is
  cacheable where a `bin`-only crate is not. This is a real but narrow-configuration benefit — it
  does not hold for a project caching by other means that have no such constraint.

**Both**: `src/lib.rs` + `src/main.rs` in one package is the common and correct shape for a CLI
tool with reusable logic — this is the default this skill scaffolds when a binary's logic is worth
testing in-process.

## Automation

`cargo xtask` — an `xtask` crate invoked as `cargo xtask <task>`, cross-platform by construction —
is **one convention** for project automation once ad-hoc shell/Python scripts stop scaling, not the
only one available. Emit it Tier-2-conditionally: when automation has genuinely outgrown two shell
scripts, not by default.

Its evidence base is a single source, and unlike nearly every other tool recommendation in this
skill, its adoption was never measured — it is a manifest-and-directory convention, not a published
crate with download counts to check. State that plainly rather than treating it as the settled
answer: a survey of task-automation alternatives is a research gap this skill has not closed this
pass, not a decision already made — nothing here names or endorses a specific rival.
