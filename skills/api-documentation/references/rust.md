# Documenting a Rust API Surface

How to document a Rust crate's **library** surface — rustdoc, the named-heading
contract, and doc-tests as executed contracts. Back to [SKILL.md](../SKILL.md).

Rust's library surface is the strongest contract-test-as-doc story of any
surface this skill covers: every `# Examples` block is compiled and run by
`cargo test --doc`, so a broken example fails CI, not a reader's copy-paste.
A Rust *service's* wire contract (REST/gRPC) is a separate artifact — document
it via [`rest-openapi.md`](rest-openapi.md) or the gRPC/protobuf section of
[`extending.md`](extending.md) and cross-link back to the crate docs for the
shared model types, same as the Go and Rust stub pattern in that file.

Versions below are **defaults at time of writing, not pins** — verify the
current toolchain/crate release before adopting (`rustc --version`, `cargo
--version`, or the crate's own changelog).

## Toolchain

**rustdoc** (`cargo doc`) is built into the toolchain — no separate install,
no version to pin. `cargo doc --open` builds and opens the local site;
crates.io publication auto-builds and hosts on docs.rs. There is no tool
decision to make the way Python/TypeScript have one: rustdoc is the only
generator in the ecosystem, and it is not competing with anything.

## Doc-comment convention

`///` (outer) documents the item immediately below it; `//!` (inner)
documents the enclosing module or crate and belongs at the top of `lib.rs` or
`mod.rs` (**C-CRATE-DOC**). Both are Markdown. Cross-reference other items with
intra-doc links (**C-LINK**) — `` [`OtherType`] `` resolves to the actual item
and breaks the build if the target is renamed or removed, unlike a bare
Markdown link:

```rust
//! # my_crate
//!
//! A minimal example crate demonstrating documentation conventions.

/// Parses a duration from a human-readable string.
///
/// # Examples
///
/// ```
/// use my_crate::parse_duration;
///
/// let d = parse_duration("30s")?;
/// assert_eq!(d.as_secs(), 30);
/// # Ok::<(), my_crate::ParseError>(())
/// ```
///
/// # Errors
///
/// Returns [`ParseError::InvalidFormat`] if `input` does not match
/// `<number><unit>` (units: `s`, `m`, `h`).
pub fn parse_duration(input: &str) -> Result<Duration, ParseError> {
    /* ... */
}
```

Keep implementation detail out of the rendered surface with `pub(crate)` /
`#[doc(hidden)]` (**C-HIDDEN**) — rustdoc renders everything `pub`, so
anything not meant for callers needs a narrower visibility, not a comment
telling readers to ignore it.

## The named-heading contract (C-FAILURE)

Three headings are load-bearing, not stylistic — rustdoc and the ecosystem's
linked-to-from-everywhere [Rust API Guidelines](https://rust-lang.github.io/api-guidelines/documentation.html)
treat them as the canonical place a caller looks for failure behavior:

| Heading | On what | States |
|---|---|---|
| `# Errors` | any function returning `Result` | which conditions produce which error variant |
| `# Panics` | any function that can panic | when — not *whether* a caller's own bad callback panics, only panics the function itself introduces |
| `# Safety` | `unsafe fn` / `unsafe trait` only | the invariants the caller must uphold for the call to be sound |

`# Examples` is the conventional heading for the example block itself
(**C-EXAMPLE**) — every public module, trait, struct, enum, function, method,
macro, and type definition should carry one, and it should show *why* you'd
reach for the item, not merely how to spell the call.

A public function that can fail or panic with no matching heading is an
incomplete doc, exactly as much as a REST operation with no documented error
response.

## Doc-tests are executed contracts

`cargo test` (and `cargo test --doc` specifically) compiles **and runs** every
`# Examples` code block. rustdoc auto-wraps each block in `fn main()` and
inserts `extern crate` for you, so a bare code fence is already a full test —
this is what makes Rust's docs uniquely resistant to going stale: an example
that stops compiling fails the build, not a reader.

The attribute set on the code-fence line changes what's asserted:

| Attribute | Asserts | Use when |
|---|---|---|
| *(none)* | compiles **and** runs successfully | the default — most examples |
| `should_panic` | compiles, runs, and **panics** | documenting the `# Panics` contract with a live demonstration |
| `no_run` | compiles but is **not executed** | network calls, file I/O, anything with an external side effect the test suite shouldn't trigger |
| `compile_fail` | the code **must not compile** | the canonical way to test that an API rejects misuse — e.g. a type-state transition that should be a compile error |
| `ignore` | skipped entirely | a smell — it means the example is untested; prefer one of the above so the example still proves *something* |

Hide setup that would clutter the example but is needed for it to compile —
imports, a wrapping `fn main`, a struct definition — with a `#`-prefixed line;
the line still compiles and runs, it's just not rendered:

```rust
/// ```
/// # use my_crate::Config;
/// let cfg = Config::default();
/// assert_eq!(cfg.timeout_secs, 30);
/// ```
```

## C-QUESTION-MARK: `?`, never `unwrap`, in examples

Rustdoc examples use `?` to propagate errors — never `.unwrap()` or the
deprecated `try!`. The rationale is specifically about documentation, not a
restatement of the library error-handling doctrine: **examples get copied
verbatim into production code.** A reader who copies a `.unwrap()`-laced
example into their own service has just shipped a panic-on-error path they
never intended; a reader who copies a `?`-based example inherits a `Result`
they still have to handle, which is the correct default.

Because `?` needs a function that returns `Result`, and the example is
implicitly wrapped in `fn main()`, add a hidden line that gives `main` a
`Result` return type:

```rust
/// ```
/// # fn main() -> Result<(), my_crate::ParseError> {
/// use my_crate::parse_duration;
///
/// let d = parse_duration("30s")?;
/// assert_eq!(d.as_secs(), 30);
/// # Ok(())
/// # }
/// ```
```

`.unwrap()`/`.expect()` remain legitimate in tests (a failing call *should*
fail the test) and in genuine prototype code — but a doc example is neither;
it is the one artifact explicitly designed to be copied.

## `#[deprecated]`

Rust's deprecation mechanism is a first-class attribute, not a doc-comment
convention — rustdoc renders it as a strikethrough plus the note automatically:

```rust
#[deprecated(since = "2.1.0", note = "use `parse_duration_checked` instead")]
pub fn parse_duration(input: &str) -> Result<Duration, ParseError> {
    /* ... */
}
```

Always give `since` (the version the deprecation landed) and `note` (the
replacement — name it explicitly, ideally with an intra-doc link). A
deprecation with no replacement named is a documentation bug, same as the
cross-surface rule in [`extending.md`](extending.md).

## `cargo test --doc` as the CI gate — and the nextest interaction

Doc-tests are part of the ordinary `cargo test` run, so a project using plain
`cargo test` already gets this gate for free.

**Projects that have adopted `cargo-nextest`** (a process-per-test runner
commonly chosen for its parallel execution speedup on larger suites) need to
know one hard limitation: **nextest cannot run doctests** — it is a
stable-Rust constraint, not a bug nextest could fix. A CI pipeline that swaps
`cargo test` for `cargo nextest run` and stops there silently drops all
doctest coverage; the examples keep compiling into the binary artifact, but
nothing ever checks that they still run.

The fix is a required second step, not a replacement:

```
cargo nextest run --workspace --locked
cargo test --doc
```

Treat `cargo test --doc` as unconditional on any crate with a public API
worth documenting — it is the only test kind that verifies your documentation
still compiles, which makes it near-worthless on internal-only binaries and
uniquely valuable everywhere else.

## Sources

- [rustdoc book — Documentation tests](https://doc.rust-lang.org/rustdoc/write-documentation/documentation-tests.html) — doctest execution model, `#` hiding, the full attribute set
- [Rust API Guidelines — Documentation](https://rust-lang.github.io/api-guidelines/documentation.html) — C-EXAMPLE, C-FAILURE, C-QUESTION-MARK, C-CRATE-DOC, C-LINK, C-HIDDEN
- [The Rust Reference — Doc comments](https://doc.rust-lang.org/reference/comments.html#doc-comments) — `///` vs `//!` syntax
- [`#[deprecated]` attribute reference](https://doc.rust-lang.org/reference/attributes/diagnostics.html#the-deprecated-attribute)
- [cargo-nextest — doctests](https://nexte.st/docs/design/why-process-per-test/) — the stable-Rust limitation and the required `cargo test --doc` companion step
- [`rest-openapi.md`](rest-openapi.md) — the shared spec layer for a Rust service's wire contract
- [`extending.md`](extending.md) — the gRPC/protobuf seed section and the surface-agnostic pattern this reference instantiates
