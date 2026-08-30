# Toolchain and Workspace

Cargo workspace manifests, toolchain pinning, lint/format configuration, MSRV policy, supply-chain
and release tooling. Reference material for the [Rust Development](../SKILL.md) skill.

## Toolchain and Workspace

### Workspace Manifests

Multi-crate projects use a **virtual manifest** at the root: a `Cargo.toml` with a `[workspace]`
table and no `[package]` table. A virtual manifest has no `package.edition` to infer a resolver
from, so it **must set `resolver` explicitly** — use `resolver = "3"` (the MSRV-aware resolver;
see [MSRV](#msrv) below).

```toml
# root Cargo.toml (virtual manifest)
[workspace]
resolver = "3"
members = ["crates/*"]

[workspace.package]
edition = "2024"
license = "MIT OR Apache-2.0"
rust-version = "1.85"

[workspace.dependencies]
serde = { version = "1", features = ["derive"] }
```

```toml
# each member Cargo.toml
[package]
name = "my-crate"
edition.workspace = true
license.workspace = true

[dependencies]
serde = { workspace = true }
```

- **`[workspace.dependencies]`** declares each external dependency once; members opt in with
  `dep = { workspace = true, features = [...] }`. A member may *add* features but cannot mark an
  inherited dependency `optional` in the workspace table.
- **`[workspace.package]`** carries `version`, `edition`, `license`, `repository`, `rust-version`,
  `authors`, `publish`, etc. — members inherit with `field.workspace = true`. Requires a cargo
  new enough to support workspace-level package inheritance; verify with `cargo --version`.
- **`[patch]`, `[replace]`, and `[profile.*]` are honoured only in the root manifest** — a copy in
  a workspace member's `Cargo.toml` compiles without error and does nothing. This is a quiet
  footgun for anyone used to per-crate configuration; put these three tables in the root only.
- One shared `target/` and one `Cargo.lock` for the whole workspace. `default-members` narrows
  what a bare `cargo build` operates on in a large workspace.

### `rust-toolchain.toml`

```toml
[toolchain]
channel = "stable"                     # or a pinned release, e.g. "1.85.0"
components = ["rustfmt", "clippy"]
targets = []                            # host is always included; these are additive
profile = "minimal"                     # minimal | default | complete
```

Discovered by walking up the directory tree from the invocation point. Precedence, highest first:
`cargo +toolchain` shorthand → `RUSTUP_TOOLCHAIN` env var → `rustup override` (directory-scoped) →
`rust-toolchain.toml` → the rustup default. A `path` key is mutually exclusive with `channel` and
nullifies `components`/`targets`/`profile`.

**Pin-vs-float, routed to a per-project ADR.** Pinning `channel` to an exact release gives
byte-reproducible formatting and lint behavior across every contributor and CI runner, but it
silently ages the compiler and misses new Clippy lints (which land on nightly first, then stable).
Floating `channel = "stable"` inverts both trade-offs. Libraries more often float and test a
version matrix; applications more often pin for reproducibility — but this is a tendency, not a
rule, and the shipped [`assets/rust-toolchain.toml`](../assets/rust-toolchain.toml) floats on
`stable` as the more conservative unopinionated default. Do not let a shipped artifact pick the
pin for a project; record the choice as a per-project ADR.

### Lint Configuration: `[lints]`, `clippy.toml`, and `-D warnings`

Three mechanisms, three different jobs — conflating any two of them is the most common
misconfiguration:

| Mechanism | Sets | Scope |
|---|---|---|
| `[lints]` table (`Cargo.toml`) | **levels** (`forbid`/`deny`/`warn`/`allow`) for lints you opt into | Table names map to tools: `lints.rust`, `lints.clippy`, `lints.rustdoc` |
| `clippy.toml` / `.clippy.toml` | **configuration values** for lints already active: `disallowed-names`, `disallowed-methods`, `msrv`, cognitive-complexity thresholds | Lookup order: `CLIPPY_CONF_DIR` → `CARGO_MANIFEST_DIR` → cwd → walk up. Use `".."` inside a list to extend rather than replace the default |
| `-D warnings` (CI flag) | **enforcement** — promotes every remaining warning, including rustc defaults and lints added by a future toolchain, to an error | `cargo clippy -- -D warnings`, or `RUSTFLAGS="-D warnings"` to apply across all cargo subcommands |

```toml
# workspace root Cargo.toml
[workspace.lints.rust]
unsafe_code = "forbid"          # or "deny" with documented exceptions — see the shipped baseline

[workspace.lints.clippy]
all = { level = "warn", priority = -1 }        # group first, negative priority
pedantic = { level = "warn", priority = -1 }    # contested — see SKILL.md Mechanical vs. Judgment
enum_glob_use = "deny"
```

```toml
# each member Cargo.toml
[lints]
workspace = true
```

**The negative-priority rule.** `priority` is a signed integer; *lower priority is emitted first*.
When a lint group (`clippy::all`, `clippy::pedantic`) is set alongside an individual lint that
should override it, the group needs a **negative priority** — otherwise the individual override is
emitted after the group and silently loses. `all = { level = "warn", priority = -1 }` before
`enum_glob_use = "deny"` is the correct order; omitting `priority = -1` on the group is the single
most common `[lints]` mistake.

**`[lints]` and `-D warnings` are complementary, not alternatives.** The table sets policy for
lints you have explicitly opted into; `-D warnings` promotes *every other* remaining warning to an
error at the CI boundary — including defaults and lints a future toolchain adds that you never
declared. Run both. `[certainty: med on "run both" as a joint prescription — the Clippy book
recommends `[lints.clippy]` on one page and `-D warnings` on another, and the two pages never
cross-reference each other; the combination is a reading of both primary sources, not a stated
joint recommendation]`

**Scope is local-package-only.** Cargo caps lints on non-path dependencies via `--cap-lints`, so a
workspace's `[lints]` table never leaks into the dependency tree.

The shipped baseline lives at [`assets/cargo-lints.toml`](../assets/cargo-lints.toml), in both
package form (`[lints.*]`) and workspace form (`[workspace.lints.*]` + member
`lints.workspace = true`).

### Contested: Source-Level `#![deny(warnings)]` (`C5`)

Presented as positions, not resolved here — route the choice to a per-project ADR.

- **Canonical position** (Rust Design Patterns, secondary): a crate-level `#![deny(warnings)]` is
  an anti-pattern. New compiler lints and deprecations land as warnings first; a source-level
  blanket `deny` turns a future toolchain upgrade into a broken build, for both the crate's own CI
  and every downstream consumer who builds it from source. The recommended form is CI-level
  `RUSTFLAGS="-D warnings"` (already covered above) plus, where a specific lint truly must be
  hard-enforced, an explicit `#![deny(that_lint)]` naming it.
- **Common habit**: the source-level blanket form remains widespread in the wild despite the
  documented anti-pattern status.
- **Evidence tier**: this is not a disagreement between two sources — it is canon against habit.
  `[certainty: high on the anti-pattern mechanism (a future toolchain adding a warning is
  observable, not speculative); the routing to ADR follows Decision 4's rule that even a
  one-sided disagreement between documented guidance and common practice is not enforced as a
  shipped default]`.

### `rustfmt.toml`: the Stable/Nightly Split

**Stable-usable keys** (a checked-in `rustfmt.toml` enforced by a stable `cargo fmt`): `edition`,
`style_edition`, `max_width`, `tab_spaces`, `hard_tabs`, `newline_style`, `use_small_heuristics`,
`use_field_init_shorthand`, `use_try_shorthand`, `reorder_imports`, `reorder_modules`,
`merge_derives`, `match_block_trailing_comma`, `match_arm_leading_pipes`, `force_explicit_abi`,
`hex_literal_case`, `remove_nested_parens`, `empty_item_single_line`, `disable_all_formatting`,
`fn_params_layout`, and the width family (`array_width`, `chain_width`, `fn_call_width`,
`struct_lit_width`, `struct_variant_width`, `attr_fn_like_width`,
`single_line_if_else_max_width`, `single_line_let_else_max_width`,
`short_array_element_width_threshold`).

**Nightly-only, despite being the most requested**: `group_imports`, `imports_granularity`,
`wrap_comments`, `comment_width`, `format_code_in_doc_comments`, `normalize_comments`,
`format_strings`, `reorder_impl_items`. A `rustfmt.toml` populated with these keys produces a
config that stable `cargo fmt` warns about and silently ignores — it *looks* configured but
enforces nothing. A project that genuinely wants import grouping or granularity must run
`cargo +nightly fmt` as a dedicated (typically non-blocking) CI job, or accept the keys as
unenforced.

A defensible stable-only default — what [`assets/rustfmt.toml`](../assets/rustfmt.toml) ships —
is `edition` + `style_edition` and nothing else. Every additional key is a divergence from what
every other Rust reader expects from `cargo fmt` defaults.

### Edition and Style Edition

`edition` selects the language edition (`2015`/`2018`/`2021`/`2024`) a crate compiles under —
editions are opt-in, migrated with `cargo fix --edition`, and are not a version bump: crates on
different editions still link together. `style_edition` is a separate, narrower knob inside
`rustfmt.toml` that controls *formatting* rule changes bundled with an edition (defaults to
`edition` when unset). Set both explicitly to the same value rather than relying on the implicit
fallback, so the formatting contract is legible without cross-referencing `Cargo.toml`.

### MSRV

**The four expectations** a declared `rust-version` (MSRV) carries, per the Cargo book:

1. **Complete** — all functionality is available on every supported version, under every feature
   combination.
2. **Verified** — the claim is actually tested in CI, not merely asserted.
3. **Patchable** — the whole workspace loads (not necessarily builds a specific feature set, but
   resolves) on the oldest supported version.
4. **Dependency support** — every dependency requirement admits at least one MSRV-compatible
   version.

**Mechanics**: `resolver = "3"` enables MSRV-aware dependency resolution — `cargo add` picks the
newest version compatible with the declared `rust-version` and reports when that is not the
overall newest; `resolver.incompatible-rust-versions = "fallback"` controls the exact resolution
behavior. Clippy's `incompatible_msrv` lint catches MSRV violations directly in source.
`cargo-msrv` discovers the true minimum by bisection. `cargo-hack --rust-version` (see
[Feature Additivity](#feature-additivity-and-cargo-hack) below) verifies the declared MSRV across
the feature matrix. Note also that **changing `rust-version` is itself a semver-minor
incompatibility** by the Cargo book's own convention — an MSRV bump is not free even when no code
changed.

### Contested: MSRV Policy (`C1`)

`[certainty: high on the mechanics above; the choice of policy itself is not something either
primary source resolves]`

The Cargo book names four MSRV policies in use across the ecosystem without endorsing one:
*latest stable only*, *N − 2 stable releases*, *even releases plus a two-release grace period*,
and *calendar year plus one year*. Its own guidance is less about *which* policy to adopt and more
about **declaring one and not drifting from it** — the friction the book warns against is an
unpredictable MSRV bump, not a strict one. This is presented as positions, not resolved here:
route the choice to a per-project ADR (see the parent skill's
[Mechanical vs. Judgment](../SKILL.md#mechanical-vs-judgment) table). No shipped Rust artifact in
this skill enforces a specific MSRV policy.

### Feature Additivity and `cargo-hack`

Cargo unifies features across the entire dependency graph: if any consumer anywhere enables a
feature, every crate in the build sees it enabled. This makes features **additive-only by
contract** — enabling a feature must never remove or change an API, or the build becomes
consumer-order-dependent ("it compiles for me" bugs trace back to this almost every time).

`cargo-hack` is the tool that verifies additivity mechanically:

- `--each-feature` — builds/tests each feature in isolation, plus the default set and
  `--no-default-features`.
- `--feature-powerset` — every feature combination, deduplicated; `--depth N` bounds the
  combinatorial explosion.
- `--no-dev-deps` — excludes dev-dependencies from the build, avoiding a documented Cargo behavior
  where dev-dependencies can leak into a normal build's dependency resolution.
- `--rust-version` / `--version-range` — verifies the declared MSRV, tied to `Cargo.toml`'s
  `rust-version` field.

`cargo-hack` temporarily rewrites manifests and processes workspace members sequentially, which
makes it slow on a large feature matrix. It belongs on a **scheduled or pre-release job**, not
every PR, once the matrix is non-trivial — see the staging model below.

### Supply Chain

| Tool | Role |
|---|---|
| `cargo-deny` | advisories + **bans** + **licenses** + **sources**, config-driven; bootstrap with `cargo deny init` |
| `cargo-audit` | RustSec advisory scan of `Cargo.lock` only |
| `cargo-vet` | records *human audits* of dependencies, shareable across organizations |
| `cargo-machete` | unused-dependency detection; fast and imprecise; runs on stable |
| `cargo-udeps` | unused-dependency detection; more precise; **requires nightly** |

`cargo-deny`'s `advisories` check consumes the same RustSec database `cargo-audit` does, while
additionally enforcing license policy and banned/duplicate crates — for most repos it supersedes
`cargo-audit` as the single tool to run. `cargo-vet` is a different category: it only pays off with
organizational buy-in or an imported shared audit set, and belongs on security-sensitive work
specifically, not as a default. Prefer `cargo-machete` over `cargo-udeps` for routine scaffolding
purely because it runs on stable; suppress its false positives via
`[package.metadata.cargo-machete] ignored = [...]` and run it periodically, not as a merge gate —
an imprecise tool blocking merges trains contributors to disable it.

**Staging model.** Not every check belongs at every point in the pipeline. A commit/merge/periodic
/release classification, organized by *when* a check runs rather than a flat tool list, makes the
cost/benefit explicit:

| Stage | Checks |
|---|---|
| Commit (fast, local/pre-commit) | `rustfmt`, TOML formatting, spell check |
| Merge (CI gate) | `clippy`, `cargo-deny` (medium cost); `cargo-vet`, `cargo-hack` (high cost) |
| Periodic (scheduled, non-blocking) | `cargo-machete`, dependency-upgrade checks |
| Release only | `cargo-semver-checks`, minimal-version verification, `cargo-msrv` |

`[certainty: med — this four-stage classification comes from a single source (the Rust Project
Primer); no second source was found corroborating the specific stage assignments, though each
tool's own cost profile independently supports the stage it lands in]` Not every check is relevant
to every project — a binary that never publishes gains nothing from `cargo-semver-checks`, and only
security-sensitive work justifies `cargo-vet`'s organizational cost.

### Miri

Detects out-of-bounds access, use-after-free, uninitialized reads, misalignment, type-invariant
violations, data races and weak-memory effects, aliasing violations, and leaks — by interpreting
the MIR rather than compiling to native code.

```yaml
miri:
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
    - run: rustup toolchain install nightly --component miri
    - run: rustup override set nightly
    - run: cargo miri setup
    - run: cargo miri test
```

Limits that determine whether a project needs it: **nightly-only**, an interpreter (so slow),
explores only the executions the test suite actually takes (evidence, not a proof of soundness),
and has almost no FFI/platform-API support. **Gate a Miri job on the presence of `unsafe`** — for
a workspace declaring `unsafe_code = "forbid"`, a Miri job is close to pure cost; for any crate with
hand-written `unsafe`, it is close to mandatory.

### Caching

Two tools, easily confused because both claim "cache my Rust build":

- **`Swatinem/rust-cache`** (GitHub Actions) caches `~/.cargo` and `./target` *dependency*
  artifacts. It deliberately excludes workspace crates themselves,
  `~/.cargo/registry/src` (re-extracting is faster than a cache restore), incremental artifacts,
  and anything older than a week. Key inputs: `shared-key` (a stable key shared across jobs),
  `key` (extra differentiation), `save-if` (e.g. only write from the default branch),
  `cache-on-failure`, `workspaces`, `cache-all-crates`. Caveat: GitHub caps caches at 10 GB total
  with LRU eviction, and a nightly toolchain invalidates the cache daily unless pinned.
- **`sccache`** is a compiler-wrapper cache with shared backends (S3, R2, GCS, Redis, Memcached,
  WebDAV, GHA). Its Rust-specific caveats are sharp: **incrementally compiled crates cannot be
  cached** (and Cargo enables incremental compilation for workspace members in the debug profile
  by default), and **`bin`, `dylib`, `cdylib`, and `proc-macro` crates cannot be cached** because
  they invoke the system linker rather than only the compiler. The suggested workaround — moving
  logic into a `lib` crate with a thin `bin` wrapper — is the same layout the
  [Binary vs Library Layout](#binary-vs-library-layout) guidance below recommends independently.

Pair either with CI-level settings: `CARGO_INCREMENTAL=0` (incremental compilation *hurts* in CI,
where there is no warm local cache to benefit from), `CARGO_PROFILE_TEST_DEBUG=0` (shrinks
`target/`, which matters against the 10 GB cache cap), and `--locked` on every `cargo` invocation
for reproducibility.

### Binary vs Library Layout

- **Library**: `src/lib.rs`; public API documented with `///` so doc-tests verify the
  documentation; `tests/` for public-API integration tests; `rust-version` set;
  `cargo-semver-checks` run before publish.
- **Binary**: `src/main.rs` as a thin shell over `src/lib.rs`, resting on one mechanism: a
  bin-only crate (no library target) cannot be exercised in-process through its own API from
  `tests/*.rs` — there is no library target for an integration test to `use`. Two further
  consequences follow only **conditionally**, not as additional unconditional reasons: if another
  crate will consume this logic, a `bin`-only crate cannot be depended on at all; if the project
  uses a compiler-wrapper cache that cannot cache binaries (bin/dylib/cdylib/proc-macro crate
  types invoke the linker rather than only the compiler — see [Caching](#caching) above), a `lib`
  target is cacheable where a `bin`-only crate is not, a narrow-configuration benefit that does
  not hold for a project caching by other means.
- **Both**: `src/lib.rs` + `src/main.rs` in one package is the common shape for a CLI tool with
  reusable internal logic.

### Cross-Compilation

| | `cross` | `cargo-zigbuild` |
|---|---|---|
| Mechanism | Containerized (Docker/Podman), one image per target | Zig as the linker, no container runtime |
| Target breadth | 60+ targets: ARM variants, MIPS, PowerPC, RISC-V, s390x, SPARC, Android, FreeBSD, Solaris, illumos | Linux and macOS targets only |
| Distinctive capability | Cross-*testing* via QEMU (slow, sequential — QEMU does not tolerate multiple threads well; requires `binfmt_misc`) | Targeting a specific minimum glibc via a suffixed triple (e.g. `aarch64-unknown-linux-gnu.2.17`); `universal2-apple-darwin` fat binaries |
| Cost | QEMU emulation bugs can produce failures unrelated to the crate under test | With newer Zig releases, `bindgen`-dependent crates may need a correspondingly newer clang |

They are complementary rather than competing: reach for `cross` when targeting an exotic
architecture or when cross-*testing* matters; reach for `cargo-zigbuild` for glibc-version
portability or macOS universal binaries without a container runtime.

### Release Automation: `release-plz` vs `cargo-release`

Neither tool's own documentation compares itself to the other; the framing below is assembled from
each tool's independent feature description, not a head-to-head either project publishes.

| | `release-plz` | `cargo-release` |
|---|---|---|
| Model | CI-driven **release PR** — on each push it opens or updates a PR showing what would be released and at what version; merging triggers publish, tag, and release creation | Imperative local command — a human decides when and what to release from a terminal |
| Versioning | Derived from conventional commits | Operator specifies the bump |
| Changelog | `git-cliff`, keep-a-changelog format | Configurable |
| Semver check | `cargo-semver-checks` invoked automatically | External — run it yourself |
| Workspace support | Yes | Yes |

`release-plz` fits a project that wants releases to fall out of merging PRs, uses conventional
commits, and is comfortable with a bot holding publish credentials. `cargo-release` fits a project
where a human decides release timing explicitly, that does not use conventional commits, or that
declines to grant publish credentials to automation. This is a project-level choice, not a
correctness question — present both rather than defaulting one into a shipped workflow.

### Publish Hygiene

- Set `rust-version` and hold to it — see [MSRV](#msrv) above for the four expectations.
- Run `cargo publish --dry-run`, and set `include`/`exclude` in `[package]` so fixtures and CI
  configuration are not shipped in the published crate.
- Run `cargo-semver-checks` before publishing (it compares rustdoc JSON between versions to detect
  breaking API changes) — but hold its **documented blind spots** in mind, so a green run is never
  mistaken for a proof of API stability. It does not detect:
  - breaking changes to the type of a field or function parameter;
  - breaking changes in generics or lifetimes;
  - breaking changes that exist only when a subset of the crate's features is activated.
  Treat it as a high-value net with known holes, not a gate — run it via its own CI action, or let
  `release-plz` invoke it automatically.
- `cargo-minimal-versions` (unstable, `-Z minimal-versions`) verifies that the lower bounds
  declared in `Cargo.toml` are actually buildable — a check almost nobody runs, and one that
  catches real, silent breakage for downstream consumers who pin to the declared minimum.
