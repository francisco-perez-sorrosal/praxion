# Error and Panic Handling

Rust's error-handling doctrine and the panic-vs-`Result` contract. Reference material for the
[Rust Development](../SKILL.md) skill.

## The Library/Application Fork

Nearly every error-handling decision in Rust forks on the crate's role. Determine the role first
— a single ruleset is wrong half the time.

| | Library | Application |
|---|---|---|
| Error type | Concrete: `#[non_exhaustive]` enum or struct per fallible operation | Opaque, context-carrying (`anyhow::Error`) |
| Boilerplate tool | `thiserror` (derive only, no runtime type) | `anyhow` (`Result`, `Context`, `bail!`) |
| Rationale | Callers must be able to *match* on failure modes; avoid leaking dependency types into the public API | Caller is `main`; what matters is a legible chain and a backtrace |

An **internal workspace crate** (never published, consumed only by siblings) is the third case:
either doctrine is defensible. Default to the library doctrine unless the crate is pure glue for
one binary — see Contested C3 below for the fuller argument.

## C-GOOD-ERR: Error Type Requirements

A well-formed error type (whether hand-written or `thiserror`-derived) satisfies all of the
following:

- Implements `std::error::Error` (requires `Debug + Display`).
- Is `Send + Sync + 'static`, so it can cross threads and become `Box<dyn Error + Send + Sync>`.
- `Display` messages are **lowercase, no trailing punctuation**, concise (e.g. `"invalid digit
  found in string"`).
- Implements `source()` to expose the underlying error — and then **does not also render it in
  `Display`**. Return the cause via `source()` *or* render it in `Display`, never both, or chains
  print duplicated text.
- Never uses `()` as an error type; never implements the deprecated `description()`.
- Follows verb-object-error naming (`ParseIntError`, `RecvTimeoutError`, `StripPrefixError`).

## `?` Propagation

`?` is the default propagation mechanism. An explicit `match` on a `Result` where a combinator or
`?` would do is a smell. In rustdoc examples, `?` is *mandated* over `unwrap` (C-QUESTION-MARK)
because users copy examples verbatim — hide setup with `#`-prefixed lines and a hidden `# fn
main() -> Result<...>` wrapper rather than reaching for `unwrap`.

## Panic-vs-`Result` Contract

- Return `Result` when failure is **expected**: malformed input, a rate-limited response, anything
  the caller can reasonably handle. Default to `Result`.
- `panic!` when the code reaches a **bad state** — a broken assumption, invariant, or contract —
  *and* the state is unexpected, *and* later code depends on it not happening, *and* it cannot be
  encoded in the types.
- A **contract violation by the caller** should panic: it is a caller-side bug, not a runtime
  condition, and must be documented in a `# Panics` section (see below).

## Legitimate `unwrap`/`expect`

`unwrap`/`expect` are acceptable in:

- Tests (a failed call *should* fail the test).
- Examples and prototypes (as a visible placeholder).
- Cases where the programmer holds information the compiler lacks — e.g. parsing a hard-coded
  `"127.0.0.1"`.

**Proof-in-message convention**: in that last case, the `expect` message must record *why* the
call cannot fail, not merely restate that it might — e.g. `.expect("hardcoded IP address should be
valid")`, not `.expect("parse failed")`. A bare `.unwrap()` in library code with no such proof
alongside it is the flagged form.

## Doc-Comment Error Contract: `# Errors` / `# Panics` / `# Safety`

Three standard rustdoc sections, referenced by name, make failure modes part of the executable
documentation contract rather than prose:

| Section | Required when | States |
|---|---|---|
| `# Errors` | Function returns `Result` | What error conditions the function returns |
| `# Panics` | Function contains `panic!`/`unwrap`/indexing/other panicking paths | When it panics (speculative caller-supplied-impl panics excluded) |
| `# Safety` | Function or trait is `unsafe` | The invariants the caller must uphold |

A public fallible function lacking `# Errors`, or a panicking function lacking `# Panics`, is an
incomplete contract — the same way a missing test is an incomplete verification.

## Contested: Error Granularity and `anyhow` in Libraries

These two questions are presented as positions with their evidence tiers — **not resolved here**.
Route the decision to a per-project ADR; do not let a shipped skill enforce a contested default.

### C2 — Crate-Wide Enum vs. Per-Operation Errors

`[certainty: med — one well-argued dissent (tier 3) against a widely practiced default; the
dissent is not refuted, merely less adopted]`

- **Mainstream default** (Effective Rust Item 4, `thiserror`'s typical use): a per-crate or
  per-module error enum.
- **Dissenting position** (Sabrina Jewson, [Modular Errors in
  Rust](https://sabrinajewson.org/blog/errors), tertiary): "kitchen-sink" enums produce five
  concrete defects — vague context, inextensible variants, imprecise matching, dependency types
  leaking into public error enums (forcing unrelated major bumps), and non-modularity that blocks
  extracting components into separate crates. The prescription: an error type per *unit of
  fallibility*, colocated with the operation, `#[non_exhaustive]` struct + `*Kind` enum, semantic
  variant names (`ReadFile`, not `Io`), proper `source()` chains — accepting more boilerplate in
  exchange.
- Both positions are compatible with C-GOOD-ERR and `#[non_exhaustive]`; the disagreement is
  granularity, not mechanism.

### C3 — `anyhow` in Libraries

- **Doctrine**: no — libraries expose matchable, concrete error types (see the fork table above).
- **Practical dissent**: exists for leaf binaries in disguise, internal-only crates, and build/CLI
  helper crates where no external caller matches on the error.
- **Fair statement**: the rule is about *public, external* APIs; an internal workspace crate that
  only `main` consumes is not the case the rule was written for. `[certainty: med — the exception
  is inferred from the rule's own stated rationale rather than stated by a source]`

Both C2 and C3 belong in a per-project ADR, not in this skill's enforced defaults — see the
[Mechanical vs. Judgment](../SKILL.md#mechanical-vs-judgment) table in the parent skill.
