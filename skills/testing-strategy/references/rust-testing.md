# Rust Testing

Rust testing patterns, tools, and best practices using the built-in test framework and popular crates. Back to [SKILL.md](../SKILL.md).

## Built-in Test Framework

### Test Organization

Rust has two test categories with distinct conventions:

| Category | Location | Purpose | Runs With |
|----------|----------|---------|-----------|
| **Unit tests** | Inline `#[cfg(test)] mod tests` | Test private functions, isolated logic | `cargo test` |
| **Integration tests** | `tests/` directory | Test public API, cross-module behavior | `cargo test` |
| **Doc tests** | `///` doc comments | Verify documentation examples compile and run | `cargo test --doc` |

### The Three Compilation Situations

Rust's built-in test locations are not really a pyramid — they are three different compilation situations, each with a different cost:

| Location | Sees private items? | Compiles as | Cost |
|---|---|---|---|
| `#[cfg(test)] mod tests` in `src/` | **yes** | part of the crate under test | cheapest |
| `tests/*.rs` | no — public API only | **one separate binary per file** | linking cost per file |
| `///` doc examples | no — public API only | one binary each, run by `cargo test --doc` | slowest; **nextest cannot run these** |

Two consequences follow from the "one binary per file" row: (1) a `tests/` directory with many files pays a linking cost per file that inline `#[cfg(test)]` units never see — matklad's ["Delete Cargo Integration Tests"](https://matklad.github.io/2021/02/27/delete-cargo-integration-tests.html) argues for consolidating `tests/` into one binary with submodules once this cost is material on a large workspace; (2) doc-tests are the only kind that verifies your documentation still compiles, which makes them valuable on public-API library crates and near-worthless on internal binaries with no public API to document.

### Unit Test Pattern

```rust
// src/parser.rs
pub fn parse_config(input: &str) -> Result<Config, ParseError> {
    // implementation
}

// Private helper -- testable via unit tests
fn normalize_key(key: &str) -> String {
    key.trim().to_lowercase()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parse_config_valid_input() {
        let input = "key = value";
        let config = parse_config(input).unwrap();
        assert_eq!(config.get("key"), Some("value"));
    }

    #[test]
    fn parse_config_empty_input_returns_error() {
        let result = parse_config("");
        assert!(result.is_err());
    }

    #[test]
    fn normalize_key_trims_and_lowercases() {
        assert_eq!(normalize_key("  MyKey  "), "mykey");
    }
}
```

The `#[cfg(test)]` attribute ensures test code is excluded from release builds. `use super::*` imports all items from the parent module, including private functions.

### Integration Test Pattern

```rust
// tests/api_integration.rs
use my_crate::Client;

#[test]
fn client_fetches_user_by_id() {
    let client = Client::new("http://localhost:8080");
    let user = client.get_user(42).unwrap();
    assert_eq!(user.name, "Alice");
}
```

Each file in `tests/` is compiled as a separate crate. It can only access the public API of your library.

### Shared Test Helpers

```rust
// tests/common/mod.rs
pub fn setup_test_db() -> TestDb {
    // shared setup logic
}

// tests/api_integration.rs
mod common;

#[test]
fn test_with_db() {
    let db = common::setup_test_db();
    // ...
}
```

Use `tests/common/mod.rs` (not `tests/common.rs`) to prevent Cargo from treating the helper as an integration test binary.

## Key Cargo Test Flags

| Flag | Purpose |
|------|---------|
| `cargo test` | Run all tests (unit + integration + doc) |
| `cargo test -- --nocapture` | Show stdout/stderr output from tests |
| `cargo test test_name` | Run tests matching a name pattern |
| `cargo test -- --ignored` | Run only `#[ignore]`-marked tests |
| `cargo test --lib` | Unit tests only |
| `cargo test --test integration` | Specific integration test file |
| `cargo test --doc` | Doc tests only |
| `cargo test -- --test-threads=1` | Run tests sequentially |

## Test Runners: `cargo test` vs `cargo-nextest`

`cargo-nextest` runs each test as its own process instead of all tests inside one shared binary process. Measured speedups range roughly 1.37x-3.38x across real projects (most in the 2-2.5x band on developer machines; a more modest ~40% wall-clock improvement has been independently reported in CI), but the isolation guarantee is arguably the bigger win: a test that panics or corrupts global state cannot take down its neighbors, and per-test timeouts, retries, and leak detection become tractable.

**Doc-test gotcha (do not skip this): `cargo-nextest` does not run doc-tests.** This is a stable-Rust limitation, not an oversight — any pipeline that adopts nextest must pair it with `cargo test --doc` or it silently loses doc-test coverage.

```bash
cargo nextest run              # unit + integration tests, in parallel, one process per test
cargo test --doc               # doc-tests -- ALWAYS run separately alongside nextest
```

Verdict: use `cargo-nextest` in CI and for large local suites, always paired with `cargo test --doc`; plain `cargo test` remains fine for a small crate where nextest's per-test-process overhead outweighs its isolation benefit.

## Assertions

### Standard Assertions

```rust
assert!(condition);                              // Boolean check
assert_eq!(left, right);                         // Equality (both must impl Debug)
assert_ne!(left, right);                         // Inequality
assert!(result.is_ok());                         // Result is Ok
assert!(result.is_err());                        // Result is Err
assert_eq!(result.unwrap_err().to_string(), "expected error message");
```

### Custom Error Messages

```rust
assert_eq!(
    actual, expected,
    "Expected {expected} but got {actual} for input '{input}'"
);
```

### Testing Panics

```rust
#[test]
#[should_panic(expected = "index out of bounds")]
fn panics_on_invalid_index() {
    let v = vec![1, 2, 3];
    let _ = v[99];
}
```

### Testing Results

```rust
#[test]
fn returns_error_for_invalid_input() -> Result<(), Box<dyn std::error::Error>> {
    let result = parse("invalid");
    assert!(result.is_err());
    Ok(())
}
```

## Property-Based Testing with proptest

```toml
# Cargo.toml
[dev-dependencies]
proptest = "1"
```

```rust
use proptest::prelude::*;

proptest! {
    #[test]
    fn roundtrip_encode_decode(input in ".*") {
        let encoded = encode(&input);
        let decoded = decode(&encoded).unwrap();
        assert_eq!(decoded, input);
    }

    #[test]
    fn sort_is_idempotent(mut vec in prop::collection::vec(any::<i32>(), 0..100)) {
        vec.sort();
        let sorted_once = vec.clone();
        vec.sort();
        assert_eq!(vec, sorted_once);
    }
}
```

### Custom Strategies

```rust
use proptest::prelude::*;

#[derive(Debug, Clone)]
struct Config {
    port: u16,
    host: String,
}

fn config_strategy() -> impl Strategy<Value = Config> {
    (1024..65535u16, "[a-z]{3,10}")
        .prop_map(|(port, host)| Config { port, host })
}

proptest! {
    #[test]
    fn config_serialization_roundtrip(config in config_strategy()) {
        let json = serde_json::to_string(&config).unwrap();
        let parsed: Config = serde_json::from_str(&json).unwrap();
        assert_eq!(parsed.port, config.port);
    }
}
```

## Mocking — a Genuinely Contested Practice

Whether to mock, and what, is one of the few areas where Rust practitioner opinion is split rather than converged. Present both positions — do not encode "always mockall."

**Position A — mockall as the default.** [`mockall`](https://docs.rs/mockall) derives mock implementations of traits, with expectation setting on arguments, call counts, ordering, and return values:

```toml
[dev-dependencies]
mockall = "0.13"
```

```rust
use mockall::automock;

#[automock]
trait UserRepository {
    fn find_by_id(&self, id: u64) -> Option<User>;
    fn save(&self, user: &User) -> Result<(), DbError>;
}

#[test]
fn service_returns_none_for_missing_user() {
    let mut mock_repo = MockUserRepository::new();
    mock_repo
        .expect_find_by_id()
        .with(eq(42))
        .returning(|_| None);

    let service = UserService::new(Box::new(mock_repo));
    assert!(service.get_user(42).is_none());
}
```

Every listicle-tier source (blog posts, SEO content) names mockall as the thing to learn first — but that popularity is not itself an argument about test design.

**Position B — don't mock your own code.** The strongest practitioner counter-argument (matklad, in ["Unit and Integration Tests"](https://matklad.github.io/2022/07/04/unit-and-integration-tests.html)) argues against mocking *your own code* — as opposed to mocking impure I/O. Mocking between your own pure modules encodes the current internal structure into the test, so refactoring the mocked module breaks tests that were never exercising the behavior actually being changed.

**The synthesis both positions support:** mock at the impure boundary — network, clock, filesystem, database, external process — expressed as a trait implemented by a real adapter and a test double; do not mock between your own pure modules. `mockall` is a perfectly good way to generate the test double for that boundary trait; the disagreement is about *where the seam is drawn*, not the tool's quality.

- **Mock traits at boundaries**: external services, databases, file systems.
- **Do not mock concrete types or your own pure logic**: prefer exercising the real code — a mock there tests the mock, not the behavior.
- **Prefer fakes for simple cases**: a `HashMap`-backed in-memory repository is often clearer than a mock's `expect_*` chain.

## Async Testing

### tokio

```toml
[dev-dependencies]
tokio = { version = "1", features = ["macros", "rt-multi-thread"] }
```

```rust
#[tokio::test]
async fn async_fetch_returns_data() {
    let client = Client::new();
    let result = client.fetch("https://example.com").await;
    assert!(result.is_ok());
}

// With custom runtime configuration
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn concurrent_operations() {
    // ...
}
```

### Timeout Pattern

```rust
use tokio::time::{timeout, Duration};

#[tokio::test]
async fn operation_completes_within_deadline() {
    let result = timeout(Duration::from_secs(5), async_operation()).await;
    assert!(result.is_ok(), "Operation timed out");
}
```

## Snapshot Testing with insta

```toml
[dev-dependencies]
insta = { version = "1", features = ["yaml"] }
```

```rust
use insta::assert_yaml_snapshot;

#[test]
fn api_response_format() {
    let response = build_response(test_data());
    assert_yaml_snapshot!(response);
}
```

```bash
# Review and accept snapshots
cargo insta review

# Update all snapshots
cargo insta accept
```

Snapshot files are stored in `src/snapshots/` (or `tests/snapshots/` for integration tests). Commit them to version control.

## Test Fixtures with rstest

```toml
[dev-dependencies]
rstest = "0.23"
```

### Parameterized Tests

```rust
use rstest::rstest;

#[rstest]
#[case("hello", 5)]
#[case("", 0)]
#[case("rust", 4)]
fn string_length(#[case] input: &str, #[case] expected: usize) {
    assert_eq!(input.len(), expected);
}
```

### Fixtures

```rust
use rstest::*;

#[fixture]
fn test_config() -> Config {
    Config::builder()
        .port(8080)
        .host("localhost")
        .build()
}

#[rstest]
fn server_starts_with_config(test_config: Config) {
    let server = Server::new(test_config);
    assert!(server.start().is_ok());
}
```

## Compile-Time API Guarantees: rustdoc `compile_fail` vs `trybuild`

Two mechanisms exist for asserting "this misuse must not compile," and they carry different maintenance costs.

**rustdoc `compile_fail` is the low-maintenance default.** A doc-test annotated `compile_fail` asserts only that the example fails to compile — not the exact compiler diagnostic:

```rust
/// ```compile_fail
/// let s: SealedState = SealedState::new(); // constructor is private outside the crate
/// ```
```

Because it checks compilation failure only (not stderr text), it stays stable across Rust releases in the common case.

**`trybuild` is conditioned on proc-macro and diagnostic-UX crates.** [`trybuild`](https://docs.rs/trybuild) asserts a program fails to compile *with a specific error message*, snapshotting the compiler's stderr. This earns its cost where the diagnostic **is** the product — proc-macro crates, and type-level API guarantees whose value is the quality of the error message a caller sees. Its **operative caveat**: stderr snapshots are compiler-version-sensitive, so an unpinned `trybuild` job has a scheduled failure on the next stable release — pin the toolchain for the `trybuild` job specifically, or expect churn on every Rust release.

```toml
[dev-dependencies]
trybuild = "1"
```

```rust
#[test]
fn ui_tests() {
    let t = trybuild::TestCases::new();
    t.compile_fail("tests/ui/must_not_compile.rs");
}
```

**Default to rustdoc `compile_fail` for "this must not compile" guarantees. Reach for `trybuild` only when the diagnostic text itself is the contract** (proc-macro crates, diagnostic-UX libraries) — and pin the toolchain for that job when you do.

## Fuzzing with `cargo-fuzz`

[`cargo-fuzz`](https://rust-fuzz.github.io/book/cargo-fuzz.html) is "not itself a fuzzer, but a tool to invoke a fuzzer" (currently libFuzzer via `libfuzzer-sys`). Requires a nightly toolchain.

```bash
cargo install cargo-fuzz
cargo fuzz init
cargo fuzz add parse_target
cargo fuzz run parse_target
```

```rust
// fuzz/fuzz_targets/parse_target.rs
#![no_main]
use libfuzzer_sys::fuzz_target;

fuzz_target!(|data: &[u8]| {
    let _ = my_crate::parse(data);
});
```

Structure-aware fuzzing uses the `arbitrary` crate's `Arbitrary` derive — a project that adopts both property testing (`proptest`) and fuzzing usually implements `Arbitrary` once and reuses it for both.

**Scope honestly**: fuzzing pays off for parsers, decoders, deserializers, and anything consuming untrusted bytes. Scaffolding a `fuzz/` directory into a CRUD service with no untrusted-input boundary is cargo-culting.

## Concurrency Testing: `loom` vs `shuttle`

Both `loom` and `shuttle` (awslabs) test hand-rolled synchronization code by shadowing `std::sync`/`std::thread` with instrumented equivalents. **Both are only relevant to lock-free or hand-rolled synchronization code** — a project whose concurrency is "spawn tokio tasks and pass channels" needs neither.

| | `loom` | `shuttle` |
|---|---|---|
| Strategy | **Exhaustive** exploration of interleavings | **Randomized** scheduling |
| Guarantee | A passing run explores the modelled state space | **Not sound** — a passing run does not prove correctness by itself |
| Scale | Small state spaces only | Scales to much larger tests |

```rust
// loom -- exhaustive, small state space
#[test]
fn loom_concurrent_increment() {
    loom::model(|| {
        let counter = std::sync::Arc::new(loom::sync::atomic::AtomicUsize::new(0));
        let handles: Vec<_> = (0..2)
            .map(|_| {
                let counter = counter.clone();
                loom::thread::spawn(move || {
                    counter.fetch_add(1, std::sync::atomic::Ordering::SeqCst);
                })
            })
            .collect();
        for h in handles {
            h.join().unwrap();
        }
        assert_eq!(counter.load(std::sync::atomic::Ordering::SeqCst), 2);
    });
}
```

**Use `loom`** for a small, hand-rolled data structure or lock-free algorithm where exhaustive coverage of interleavings is tractable. **Use `shuttle`** when the state space is too large for `loom` to exhaust and randomized scheduling with a high detection probability is an acceptable trade — its own documentation states the trade-off explicitly: it is not sound, but it scales to much larger test cases than `loom`.

## Mutation Testing with `cargo-mutants`

[`cargo-mutants`](https://mutants.rs) mutates the source, re-runs the suite, and reports mutants that **survived** — behavior changes your tests did not notice. This answers the honest question behind "we have 90% line coverage": coverage says the line ran; mutation testing says the line's behavior was actually asserted on.

```bash
cargo install cargo-mutants
cargo mutants                        # full run
cargo mutants --file src/parser.rs   # scoped run
```

Runtime is roughly (number of mutants) x (suite duration) — for any non-trivial repo this belongs on a **scheduled job or a manual audit, never on the PR path**. A mutation run gating every PR trains people to disable the gate.

## Benchmarking: `criterion` vs `divan` vs `gungraun`

Three harnesses, three different measurement approaches — the cadence and release facts below, not a single verdict:

| | `criterion` | `divan` | `gungraun` |
|---|---|---|---|
| Measures | Wall-clock, statistical (bootstrap confidence intervals, regression detection vs. previous run) | Wall-clock + allocation profiling | Instruction counts via Valgrind/callgrind |
| Release cadence | Active | No release in well over a year as of this writing — verify current status before adopting | Active |
| Notable trade-off | Highest adoption; statistical rigor | Simpler macros, allocation counts out of the box | Instruction counts are far more stable on noisy shared CI runners than wall-clock time, at the cost of requiring Valgrind and being a proxy for (not a measurement of) real-world time |

```rust
// criterion
use criterion::{black_box, criterion_group, criterion_main, Criterion};

fn bench_parse(c: &mut Criterion) {
    c.bench_function("parse_config", |b| {
        b.iter(|| my_crate::parse_config(black_box("key = value")))
    });
}

criterion_group!(benches, bench_parse);
criterion_main!(benches);
```

`gungraun` is the renamed successor to `iai-callgrind` — verify the current package name against crates.io before pinning, since the ecosystem has moved once already. Whichever harness a project chooses, tracking benchmark results over time (via a continuous-benchmarking service, or a checked-in history) matters more than which harness produced the number.

## Code Coverage

### cargo-llvm-cov (Recommended)

```bash
cargo install cargo-llvm-cov

cargo llvm-cov                 # Run tests with coverage
cargo llvm-cov --html          # Generate HTML report
cargo llvm-cov --lcov > lcov.info  # LCOV format for CI
```

### cargo-tarpaulin (Alternative)

```bash
cargo install cargo-tarpaulin

cargo tarpaulin --out html     # HTML report
cargo tarpaulin --out xml      # Cobertura XML for CI
```

## Gotchas

- **Tests run in parallel by default**: Use `-- --test-threads=1` or synchronization primitives when tests share resources (files, ports, global state).
- **`#[should_panic]` tests cannot return `Result`**: Choose one or the other. For error assertions, prefer `Result`-returning tests with explicit `is_err()` checks.
- **Doc tests are slow**: Each doc test is compiled as a separate binary. Use `#[cfg(doctest)]` attributes to control compilation. For large crates, run `--doc` separately from `--lib`.
- **Integration tests see only `pub` items**: If you need to test internal behavior, use unit tests in `#[cfg(test)] mod tests`.
- **`cargo test` compiles tests as debug**: Tests may pass in debug but fail in release due to integer overflow checks. Periodically run `cargo test --release`.
- **Temporary directories**: Use `tempfile::tempdir()` instead of hardcoded paths. The directory is automatically cleaned up when the `TempDir` guard is dropped.

---

## Test Topology — Rust Leaf

This section is the Rust leaf for the language-agnostic test topology protocol defined in [`references/test-topology.md`](test-topology.md). The trunk defines the group schema, tier vocabulary, identifier registries, and closure semantics. This leaf provides the concrete Cargo/nextest wiring: selector strategy identifiers, parallel runner identifiers, and the `shared_fixture_scope` mapping.

**Read the trunk first** if you are unfamiliar with the protocol. This section does not repeat trunk definitions — it only extends them.

### Defaults

- **Registered selector strategies** (Registry 1): `cargo-test-filters` (plain `cargo test`), `nextest-filters` (`cargo-nextest`, once adopted).
- **Registered parallel runners** (Registry 2): `cargo-test-jobs` (`cargo test -- --test-threads=N`), `nextest-threads` (`cargo nextest run --test-threads=N`).
- **Recommended default**: `nextest-filters` + `nextest-threads` for any workspace with `cargo-nextest` on the toolchain — nextest's process-per-test isolation (see "Test Runners: `cargo test` vs `cargo-nextest`" above) makes it the safer parallel default, mirroring the Python leaf's `pytest-xdist-loadfile` recommendation. Projects that have not adopted `cargo-nextest` fall back to `cargo-test-filters` + `cargo-test-jobs` (plain `cargo test`).
- **In both cases, `cargo test --doc` must run as a separate invocation** — nextest cannot execute doc-tests (see the doc-test gotcha above). This is not optional: a group's runner invocation is incomplete without it whenever the group covers a library with a documented public API.
- **`shared_fixture_scope` mapping**: see table below. Rust's built-in test framework (`libtest`) has no fixture-scope system comparable to pytest's; scopes are approximated via `OnceLock`/`static` initialization patterns, documented per-value below.

### Registry 1 — Selector Strategy Identifiers (Rust)

These two identifiers are **registered** by this leaf in the trunk's Selector Strategy Registry (Registry 1) — they are live, not indicative, and may be used in populated `TEST_TOPOLOGY.md` files.

| Identifier | Cargo invocation | Argument shape |
|-----------|------------------|----------------|
| `cargo-test-filters` | `cargo test <args>` | List of 1+ filter strings; each is passed positionally and matched by substring against the fully-qualified test name (`module::tests::test_name`). Multiple entries are unioned (a test matching any filter runs). |
| `nextest-filters` | `cargo nextest run <args>` | List of 1+ filter strings, same substring-match semantics as `cargo-test-filters` for parity. For expression-based selection (by binary, package, or attribute) nextest also has its own `-E '<filterset-expr>'` DSL — verify the current filterset syntax against `cargo nextest run --help` for the installed version before relying on it in CI, since nextest is under active development. |

### Registry 2 — Parallel Runner Identifiers (Rust)

These two identifiers are **registered** by this leaf in the trunk's Parallel Runner Registry (Registry 2) — they are live, not indicative.

| Identifier | Concrete invocation | When to use |
|-----------|--------------------|-----------|
| `cargo-test-jobs` | `cargo test -- --test-threads=N` (omit `N` for the libtest default, the host's CPU count) | Small crates, or projects that have not adopted `cargo-nextest`. libtest still runs every test inside one shared process — this flag only changes thread count, not isolation. |
| `nextest-threads` | `cargo nextest run --test-threads=N` | **Recommended default** wherever `cargo-nextest` is on the toolchain. Each test runs in its own process, so a panicking or leaking test cannot corrupt another's state — a stronger isolation guarantee than `cargo-test-jobs`'s thread-level parallelism alone. Verify the current flag name against `cargo nextest run --help` for the installed nextest version before relying on it in CI. |

### shared_fixture_scope — Mapping to Rust Idioms

| Trunk value | Rust idiom | Notes |
|------------|-----------|-------|
| `none` | No shared state; each `#[test]` builds and tears down everything itself | Simplest, always safe under any parallel runner |
| `per-test` | A local `setup()` helper function called at the top of each `#[test]` | Default; conceptually similar to pytest's `function` scope, but `libtest` has no fixture-injection mechanism — the call is explicit in the test body |
| `per-file` | `#[cfg(test)] mod tests { static SHARED: std::sync::OnceLock<T> = std::sync::OnceLock::new(); }`, initialized once per test binary | For `tests/*.rs` integration tests, each file already compiles to its own binary (see "The Three Compilation Situations" above), so `per-file` and `per-process` collapse to the same mechanism there |
| `per-process` | A crate-level `static` guarded by `OnceLock`/`Mutex`, initialized once per test binary process | Distinguishes from `per-file` mainly for inline `#[cfg(test)] mod tests` within one library's test binary, where multiple modules share the same process |
| `per-suite` | A cross-binary lock (e.g., the `fd-lock` crate, or a lock file under a shared temp path) guarding a marker file | Required because `tests/*.rs` files and doc-tests are **separate OS processes** — an in-process `OnceLock` cannot coordinate across them. Mirrors the Python leaf's filelock-based session-fixture recipe. Groups with `parallel_safe: false` do not need this; they run sequentially with exclusive access. |
