# Essential Crates

Curated third-party crates by project archetype. Reference material for the
[Rust Development](../SKILL.md) skill — the Rust peer of
[`python-development/references/essential-libraries.md`](../../python-development/references/essential-libraries.md).

## Purpose

This catalog exists so a Rust project doesn't reinvent functionality that a well-known,
actively-maintained crate already solves well. It is a **shortlist**, not a mandate:

- Pick from here before naming a candidate crate for a new capability.
- Still verify the current version before pinning: `cargo search <crate>` prints the latest
  published version, or check `https://crates.io/crates/<crate>` directly. This catalog says
  *what* tends to be the right default; that check confirms the *current* version and
  capability fit before it's pinned (REQ-11).
- If a project already has an established stack, prefer consistency with what's already there
  over introducing a second crate for the same job, even if this catalog lists a newer
  alternative.
- Where there's a clear current consensus pick, the table says so directly. Where there's a
  genuine ongoing debate between two solid options — or a maintenance-status question no source
  resolves — both are presented with an honest annotation instead of a forced verdict. Three
  categories below are explicitly **contested, not resolved**: date/time, benchmarking cadence,
  and mocking doctrine.

## Essential Crates
<!-- last-verified: 2026-08-30 -->

All defaults and download figures below were retrieved from the crates.io API on **2026-08-30**
(90-day download counts). `recent_downloads` conflates direct and transitive use, so it ranks
*ecosystem centrality*, not "number of teams who chose it" — and for **binary tools**
(`cargo-*` subcommands) it under-counts badly, since most installs arrive via
`cargo-binstall`, GitHub Releases, or a pinned GitHub Action rather than a `crates.io` install.
Weight release cadence more heavily than volume for those.

### Crate Catalog by Archetype

| Archetype | 2026 default | Main alternative | When the alternative wins |
|---|---|---|---|
| Serialization | `serde` (+ `serde_json`) | `rkyv`, `postcard`, `prost`, `facet` | rkyv: zero-copy deser; postcard: `no_std`/embedded; prost: protobuf/gRPC; facet: reflection + lighter derive (early, single-source — see below) |
| Async runtime | `tokio` | `smol`, `embassy`, `glommio` | smol: small/single-threaded, avoids `Send + 'static`; embassy: embedded (essential there); glommio: io_uring thread-per-core |
| Web framework | `axum` | `actix-web`, `salvo`, `rocket` | actix-web: peak throughput, actor model, mature; salvo: built-in OpenAPI/TLS |
| HTTP client | `reqwest` | `ureq` | ureq: sync-only, no tokio in the dependency graph, far smaller build |
| CLI | `clap` (derive) | `bpaf`, `lexopt`, `pico-args` | all three: much faster compile / smaller binary; lexopt: minimal runtime |
| Error (libraries) | `thiserror` | `snafu` | snafu: context selectors, richer per-site context |
| Error (applications) | `anyhow` | `color-eyre`, `miette` | color-eyre: better terminal reports; miette: diagnostic spans/source snippets (compiler/linter/config-validator UX) |
| Logging | `tracing` (+ `tracing-subscriber`) | `log` | log: sync, non-async, minimal |
| Observability | `opentelemetry` + `tracing-opentelemetry` | vendor SDKs | vendor-locked stacks |
| DB — SQL-first | `sqlx` | `diesel`, `sea-orm` | contested three-way trade-off — see [Database](#database-sqlx-vs-diesel-vs-sea-orm) below |
| Parallelism | `rayon` | manual threads / `std` scoped threads | non-data-parallel workloads |
| Date/time | `jiff` | `chrono`, `time` | contested — see [Date and Time](#date-and-time-the-jiff-question) below |
| Python interop | `pyo3` + `maturin` | `setuptools-rust` | more build flexibility, more config |
| Node interop | `napi-rs` (`napi`) | `neon`, wasm | wasm: portability over performance |
| Browser/WASM | `wasm-bindgen` | — | — |
| Multi-language bindings | `uniffi` | hand-written FFI + `cbindgen` | need a C ABI specifically |
| C/C++ interop | `bindgen` / `cbindgen` / `cxx` | — | cxx for safe C++; bindgen for C→Rust; cbindgen for Rust→C |

Verify any entry's current version before pinning: `cargo search <crate>` or
`https://crates.io/crates/<crate>` (REQ-11). Version-specific claims below are stated only where
the version itself is load-bearing to the recommendation.

### Serialization

`serde`'s dominance is not seriously contested (285.9M/90d as of 2026-08-30). Two 2026-relevant
developments worth knowing:

- **`serde_core`.** serde split its trait definitions into a `serde_core` crate. Downstream crates
  that need only the traits (not `#[derive]`) can depend on `serde_core`, which compiles in
  parallel with `serde_derive` instead of serializing behind it — a real build-time win in wide
  dependency graphs. Visible in the wild (e.g. `jiff`'s feature table references it).
- **`facet`** (fasterthanlime) offers reflection-based derive as a lighter, faster alternative, and
  is claimed to be better at binary formats. `[certainty: low — single-source (author's own
  announcement), no independent corroboration gathered]`. Early and nowhere near serde's ecosystem
  position — worth watching, not worth defaulting to.

### Async Runtime

**`async-std` is discontinued.** RUSTSEC-2025-0052 records the discontinuation at version 1.13.1;
an independent practitioner source corroborates the same, dating the official announcement to
2025-03-01. Two independent sources converge on this — the one genuinely unambiguous negative
verdict in this catalog. `[certainty: high]`. The maintainers direct users to `smol` (which shares
building blocks); the wider ecosystem's practical default is `tokio`.

`tokio` is described by an independent practitioner source as *"Rust's canonical async
runtime"* and *"a vast majority of libraries are tailored specifically for it"* — while its
multithreaded-by-default design imposes `Send + 'static` and pushes toward `Arc<Mutex<_>>`, which
the same source calls *"accidental complexity completely unrelated to the task of writing async
code."* Practical guidance carried from that source: **default tokio, and do not abstract over the
runtime** — the abstraction almost never pays for itself, and libraries are written against
individual runtimes, so an abstraction layer just relocates the `cfg` gymnastics rather than
removing them.

`smol`'s last release predates most of this catalog's other entries, which looks alarming but
reflects its architecture: it is a thin facade over `async-executor`, `async-io`, `async-task`,
`futures-lite`, etc., which version independently. `[certainty: med — the component architecture
is documented; individual component release dates were not independently verified]`. Do not read
the facade's own release date as project inactivity.

### Web Framework: axum vs actix-web

The download gap is stark — roughly 11:1 in favor of axum — but both are actively released. The
gap partly reflects axum being a transitive dependency of many other crates rather than a straight
count of adopting teams.

- **axum** is a Tokio-team project built directly on `tower`/`tower-http`, so its middleware is the
  generic tower ecosystem rather than a bespoke one. Its extractor model is plain functions with
  typed arguments. A curated ecosystem list (blessed.rs) describes it as *"minimal and
  ergonomic."*
- **actix-web** has an actor heritage, is consistently at or near the top of throughput
  benchmarks, and is more mature in absolute age.

Verdict: **axum by default** — tower interop and Tokio-team stewardship are strategic advantages
that compound. **actix-web wins** when the project is throughput-bound at the framework layer, or
the team already knows it. `[certainty: high on the download numbers; med on the "strategic
advantage" framing, which is judgment]`. Defensible either way, not a correctness question.

### HTTP Client: reqwest vs ureq

`reqwest` is the default — async, connection pooling, HTTP/2, cookies, redirects, multipart,
JSON, optional blocking mode. `ureq` is a serious alternative for one specific reason: it is
**synchronous and does not drag in tokio**. For a CLI tool or a build script making a handful of
requests, ureq removes an entire async runtime from the dependency graph and the compile time —
a bigger deal than it sounds.

### CLI: clap and the Compile-Time Objection

`clap` is not seriously challenged on capability — derive API, subcommands, validation, shell
completions, `--help` generation. The real caveat, per a curated ecosystem list (blessed.rs): **it
compiles slower than the alternatives.** `bpaf`, `lexopt`, and `pico-args` all exist primarily to
be cheaper. For a tool whose whole point is fast iteration, or a binary with a hard size budget,
the alternatives are rational. For everything else, clap.

### Errors

The settled split is **`thiserror` in libraries** (derive a concrete error enum; callers can match
on variants) and **`anyhow` in applications** (type-erased, `?`-friendly, attach context with
`.context()`). Both crates share the same maintainer (dtolnay), which is one reason this is the
most consensus-y verdict in this catalog.

Alternatives are about **presentation and context**, not correctness: `snafu` provides context
selectors and is preferred by developers who find thiserror's context story thin; `color-eyre` is
an `anyhow` fork with much better terminal reports; `miette` renders diagnostics with source spans
and snippets, which is the right choice when the binary is a compiler, linter, or config validator
whose error messages *are* the product. Note: `miette`'s last release lagged roughly 16 months as
of this catalog's measurement date — a cadence flag on an otherwise excellent crate, verify its
current release status (`cargo search miette`) before adopting it for a long-lived project.
`[certainty: high on the thiserror/anyhow split; med on miette's maintenance status — same
abandonment-vs-stability ambiguity noted for `divan` below]`.

### Logging and Observability

`tracing` has replaced `log` as the default for anything async, per a curated ecosystem list
(blessed.rs), which states so directly. Worth knowing for planning purposes: `tracing`'s core crate
was still pre-1.0 (`0.1.x`) as of this catalog's measurement date, with no `0.2` release landed
despite long-discussed plans. Practically this reads as **API stability** (the 0.1 surface has
held for years) rather than stalled development — but a project planning a multi-year lifetime
should know a breaking release is nominally pending. `[certainty: med — version and cadence are
direct measurements; the "stable not stalled" reading is interpretation]`. Verify current version:
`cargo search tracing`.

**OpenTelemetry Rust: all three signals (traces, metrics, logs) were Beta** per the official OTel
site as of this catalog's measurement date. The standard wiring is `tracing` for instrumentation →
`tracing-opentelemetry` as the bridge layer → `opentelemetry-otlp` as the exporter — this specific
wiring is ecosystem convention, not documented on the OTel Rust page itself. Two consequences worth
flagging: **Beta means breaking changes across 0.x bumps**, and the `opentelemetry` /
`tracing-opentelemetry` version pair must be upgraded in lockstep — a recurring source of
dependency-resolution pain. `[certainty: high on Beta status (official source); med on the
lockstep-upgrade pain, which is practitioner-reported rather than documented]`.

### Database: sqlx vs diesel vs sea-orm

This is a real three-way trade-off, not a ranking — do not encode a single winner.

| | `sqlx` | `diesel` | `sea-orm` |
|---|---|---|---|
| Model | SQL-first, async, **compile-time-checked raw queries** | Query-builder DSL / ORM, sync-first | Full async ORM, built on sqlx |
| Type checking | queries verified against a live DB at compile time (or offline via prepared metadata) | types enforced by the DSL and schema codegen | runtime, entity-model driven |
| You write | SQL | Rust DSL | Rust entities + relations |
| Operational cost | needs `DATABASE_URL` or checked-in offline query metadata (`cargo sqlx prepare`) for CI | DSL learning curve; async story less natural | another layer over sqlx |

- **`sqlx` by default** — highest adoption, async-native, and its compile-time query checking
  gives most of an ORM's safety while still writing SQL directly. The operational cost is real and
  must be scaffolded: CI needs either a live database or committed offline query metadata.
- **`diesel` wins** when the schema and query correctness should be enforced by Rust's type system
  rather than by a build-time database connection, or when the project is sync. A curated
  ecosystem list (blessed.rs) calls it high-performance with strict guarantees.
- **`sea-orm` wins** when the project genuinely wants entity-relationship modelling and
  active-record ergonomics. It reached its `2.0` major version recently as of this catalog's
  measurement date, so an "immature" objection against it is dated.
- For SQLite specifically, `rusqlite` is the direct, sync, full-featured choice; for Postgres-only
  work with maximum control, `tokio-postgres`.

### Date and Time: the jiff Question

| | `jiff` | `chrono` | `time` |
|---|---|---|---|
| Maturity | **pre-1.0** (`0.2.x` as of this catalog's measurement date — verify: `cargo search jiff`) | past 1.0 | past 1.0 |
| Design basis | JS **Temporal** proposal | traditional | focused/minimal |
| Time zones | bundled/system tzdb, first-class | via `chrono-tz` | limited |
| 90-day downloads (2026-08-30) | 58.7M | 165.4M | 165.5M |

**`jiff` (BurntSushi) is the technically strongest choice for new code.** It is modelled on the
Temporal proposal, treats time zones and DST arithmetic as first-class rather than bolted on, and
a curated ecosystem list (blessed.rs) describes `chrono` as **"soft-deprecated"** for new
projects. Its adoption curve since a first publish in Feb 2024 is remarkable.

**But two things must be stated honestly, not smoothed over:**

1. **`jiff` is still pre-1.0.** A pre-1.0 crate in a public API signals breaking changes ahead —
   a genuine consideration for a library, less so for an application. This is the single most
   important correction against a blanket "just use jiff" recommendation circulating in
   secondary sources.
2. **`chrono` and `time` each carry roughly 3× `jiff`'s download volume.** Whatever
   "soft-deprecated" means, `chrono` is not going anywhere, and any non-trivial dependency graph
   will pull it in transitively regardless of what a project chooses directly.

Verdict: **jiff for new application code; chrono if maximum ecosystem interop or a 1.0 guarantee
is needed; `time` for a minimal, focused API.** The "soft-deprecated" label on chrono is **one
curated source's judgment, not consensus** — it must not be relayed as settled fact.
`[certainty: med — versions/downloads are direct measurements; "soft-deprecated" is one source's
characterization, and no second independent source was found echoing it]`.

### Parallelism

`rayon` is the default for data-parallel workloads (map/reduce over a collection) — no serious
contest for that use case. Manual `std::thread` (scoped threads) or `std` channels remain the
right tool when the workload is not data-parallel (task orchestration, pipelines, producer/
consumer) — reaching for `rayon` there is a shape mismatch, not a maintenance concern.

### FFI and Interop (Rust Beside Python/TS/Native)

- **Python: `pyo3` + `maturin`.** The pyo3 guide names `maturin` as the primary recommendation
  (*"the easiest way to try this out"*) and `setuptools-rust` as the more flexible/more
  configuration alternative. Supports CPython, PyPy, and GraalPy across a documented version
  range — verify the exact supported range against the pyo3 guide before committing, since it
  changes across pyo3 releases. **Two gaps are flagged as unresolved, not answered**: the pyo3
  guide's landing page does not cover **abi3/stable-ABI** guidance or **free-threaded Python
  (PEP 703)** support status; both matter for a project targeting Python 3.13+ and must be checked
  against the pyo3 guide's dedicated chapters before committing. `[certainty: high on
  versions/tooling existing; the abi3 and free-threading gaps are explicitly unresolved]`.
- **Node: `napi-rs`** (`napi`) — N-API-based native addons, prebuilt-binary distribution, stable
  ABI across Node versions.
- **Browser/WASM: `wasm-bindgen`** — no alternative worth naming; the de facto standard.
- **Multi-language: `uniffi`** (Mozilla) — generates Kotlin/Swift/Python/Ruby bindings from one
  Rust definition. Niche but real (single-digit-million 90-day downloads vs. pyo3/napi-rs's
  tens-of-millions). Wins when several language targets are needed from one core; loses to
  pyo3/napi-rs when one target done idiomatically is the goal.
- **C/C++:** `bindgen` (C→Rust), `cbindgen` (Rust→C header), `cxx` (safe bidirectional C++).

### Testing Crates

The [`testing-strategy` skill's `references/rust-testing.md`](../../testing-strategy/references/rust-testing.md)
leaf owns the Defaults section (registered selector strategies, parallel runners) and the deeper
methodology; this catalog names the crates by capability for quick reference.

| Capability | 2026 default | Alternative | Note |
|---|---|---|---|
| Property-based testing | `proptest` | `quickcheck` | proptest: explicit `Strategy` objects, stateful shrinking, ~4.5x quickcheck's download share; quickcheck: type-directed `Arbitrary`, stateless shrinking is up to an order of magnitude faster when generation cost dominates. Both are actively maintained — "quickcheck is abandoned" is a false claim found in secondary sources. |
| Snapshot testing | `insta` | — | `assert_snapshot!` writes a `.snap` file on first run; `cargo insta review` gives an interactive accept/reject diff. **Failure mode**: `cargo insta accept` on a red suite converts a real regression into a green build — review snapshot diffs as code, in the PR. |
| Compile-fail / API-surface testing | `trybuild` | — | Asserts a program fails to compile with a specific error message. Essential for proc-macro crates (the diagnostics *are* the UX). **Conditioned, not unconditional**: its stderr snapshots are compiler-version-sensitive, so pin the toolchain for the trybuild job or expect churn on every Rust release. |
| Concurrency testing | `loom` | `shuttle` (awslabs) | loom: **exhaustive** exploration of interleavings, small state spaces only; shuttle: **randomized** scheduling, not sound but scales further, stated explicitly as a soundness-scalability trade-off by its own README. Both are relevant only to lock-free / hand-rolled synchronization — a project whose concurrency is "spawn tokio tasks and pass channels" needs neither. |
| Fuzzing | `cargo-fuzz` | — | Not itself a fuzzer — invokes libFuzzer via `libfuzzer-sys`. Requires nightly. Pays off for parsers, decoders, deserializers, and anything consuming untrusted bytes; scaffolding it into a CRUD service is cargo-culting. |
| Mutation testing | `cargo-mutants` | — | Mutates the source, re-runs the suite, reports mutants that **survived** (behavior changes the tests did not notice) — a test-suite *quality* measure, distinct from coverage. Runtime scales with (mutant count) × (suite duration): belongs on a scheduled job or manual audit, never the PR path for a non-trivial repo. |
| Benchmarking | `criterion` | `divan`, `gungraun` | See below — contested cadence question on `divan`. |
| Mocking | — (contested) | `mockall` | See below — contested doctrine, no single verdict. |
| Parameterized tests / fixtures | `rstest` | — | `#[case]` parameterization, `#[fixture]`, value-matrix expansion. Ergonomics, not a capability gap — removes the main reason people hand-roll table-driven test loops in Rust. |

**Benchmarking — `criterion` vs `divan` vs `gungraun` (contested cadence, `divan`)**: `criterion`
is the default on release cadence and roughly 20x `divan`'s usage; its statistical rigor
(bootstrap confidence intervals, regression detection vs. the previous run) is the reason it has
persisted. `divan` is genuinely nicer to write (simpler macros, allocation counts out of the box)
and a curated ecosystem list (blessed.rs) still lists it — but as of this catalog's measurement
date it had had **no release in roughly 16 months**, with **no archival notice, no deprecation
banner, and no announced fork** on its repository, and open issues/PRs still present. This is
*stalled cadence*, not *declared dead* — report the date, don't attach a verdict.
`[certainty: med — release dates and absence-of-notice are directly observed; whether that
constitutes abandonment is an inference with no maintainer statement either way]`. `gungraun` is
the renamed successor to `iai-callgrind`; it counts CPU **instructions** via Valgrind/callgrind
rather than wall-clock time, which makes it dramatically more stable on noisy shared CI runners —
the standard answer to "our benchmark job flaps on GitHub-hosted runners." Cost: requires Valgrind,
and instruction count is a proxy for, not a measurement of, real-world time. Verify current
versions before pinning any of the three: `cargo search criterion` / `cargo search divan` /
`cargo search gungraun`.

**Mocking doctrine (contested, no single verdict)**: Position A — every 2026-era listicle-tier
secondary source found names `mockall` the default and "the thing to learn first," with no
argument beyond popularity; `mockall` itself has a large download share supporting the popularity
claim. Position B — a widely-cited practitioner source (rust-analyzer's lead, matklad) argues
against *"mocking your own code (as opposed to mocking impure IO)"* on the grounds that it reduces
fidelity and makes the suite brittle under refactoring: the mock encodes the current internal
structure, so restructuring breaks tests that were never testing the restructured behavior. These
positions are not actually contradictory once the target of mocking is separated: **mock at the
impure boundary (network, clock, filesystem, database, external process); do not mock between your
own pure modules.** In Rust that boundary is naturally expressed as a trait implemented by a real
adapter and a test double — and `mockall` is a perfectly good way to generate the test double *for
that trait*. The disagreement is about **where the seam is drawn**, not about whether the tool is
good. Source-quality asymmetry is worth stating plainly: Position A's support is entirely
secondary-tier content with no argument beyond popularity; Position B comes from a named,
high-authority practitioner with a stated mechanism. `[certainty: med — the reconciliation above
is a synthesis; each position is individually well-attested but no source states the reconciliation
explicitly]`. **Never encode "always reach for mockall" as doctrine.** Adjacent tools frequently
better than a mock: `wiremock` (HTTP server stub), `testcontainers` (real DB in a container), and a
plain hand-written fake struct implementing the trait — often the smallest thing that works, with
no macro budget at all.

## Not a Package-Manager Guide

This catalog says *which* crate; it does not cover *how* to add it to a project. For Cargo
workspace dependency declarations, `[workspace.dependencies]` inheritance, and version pinning,
see [`references/toolchain-and-workspace.md`](toolchain-and-workspace.md).
