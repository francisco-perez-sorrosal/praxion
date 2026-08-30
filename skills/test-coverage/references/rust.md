# Rust Reference

Rust-specific mechanics for the [`test-coverage`](../SKILL.md) skill. Loaded on demand when the active project is detected as Rust.

This reference does **not** install `cargo-llvm-cov`, `cargo-tarpaulin`, or any other tool. The project owns its coverage tooling. Unlike the Python and TypeScript references, Rust coverage tools are driven entirely by CLI flags — there is no persistent `[coverage]` block in `Cargo.toml` analogous to `pyproject.toml`'s `[tool.coverage.*]` or `vitest.config.ts`'s `coverage` object. The "config block" below is a `Makefile`/`justfile` recipe, not a manifest section.

## Default: `cargo-llvm-cov`

`cargo-llvm-cov` is the default coverage tool for Rust projects. The recommendation rests on **mechanism, not popularity**: it drives `-C instrument-coverage`, which is the Rust compiler's own source-based coverage instrumentation facility. Because the instrumentation lives in `rustc` itself, coverage accuracy tracks the compiler directly rather than depending on an external tracer reverse-engineering process behavior. This is the same reasoning that should govern the choice going forward — re-verify it against whichever tool is closer to the compiler at the time, not against download counts alone.

**Alternative: `cargo-tarpaulin`.** Tarpaulin instruments via `ptrace` (and other backends), historically a Linux-centric approach. It remains a reasonable choice when a project already has `tarpaulin.toml` or a `[package.metadata.tarpaulin]` block from before `cargo-llvm-cov` became the ecosystem default — continuity with an existing CI pipeline can outweigh a mechanism argument alone. Absent that prior investment, there is no independent technical edge for tarpaulin found in the source material; prefer `cargo-llvm-cov` for new adoption.

**Gotcha — branch and doctest coverage both require nightly.** The stable-toolchain default invocation (`cargo llvm-cov`) reports line and region coverage only. Branch coverage and doctest coverage are both gated behind a nightly toolchain. State this limitation plainly to callers rather than silently reporting incomplete coverage as if it were the full picture — a stable-only run is not missing data by omission, it is a documented ceiling of the mechanism.

## `cargo llvm-cov nextest` and the Doctest Gap

Projects using `cargo-nextest` as their test runner (see the [`testing-strategy`](../../testing-strategy/SKILL.md) Rust leaf) compose it with coverage via `cargo llvm-cov nextest`, which runs the workspace's tests through nextest under instrumentation. This inherits nextest's own limitation: **nextest cannot run doctests**, so `cargo llvm-cov nextest` alone never measures doc-example coverage, no matter which toolchain is active. A pipeline that wants doctest coverage in the same numbers needs a second, nightly-gated invocation (`cargo llvm-cov --doctests` or equivalent) — or an explicit, disclosed decision to exclude doctests from the coverage figure, mirroring the same disclosure obligation `cargo test --doc` carries as a required second CI step when nextest is the primary runner.

## Target-Discovery Probe Order

Probe these sources in order and stop at the first hit. Each check is a simple filesystem or file-content test — the skill does not execute anything during probing.

1. **`Makefile`/`justfile` target** — look for a coverage-oriented recipe (commonly `coverage`, `test-coverage`, or `cov`). If present, invoke via `make <target>` or `just <target>`. A project that has already wired a recipe has almost always pinned the correct tool, flags, and output path there.
2. **`.config/nextest.toml` present** — if nextest is the project's test runner (detectable by this file, or a `cargo-nextest` mention in CI config) and `cargo-llvm-cov` is resolvable on PATH, invoke `cargo llvm-cov nextest`. Remember the doctest gap above — surface it in the result rather than silently omitting doc-example coverage.
3. **`cargo-llvm-cov` on PATH, no nextest config** — fall back to `cargo llvm-cov` (drives `cargo test` internally). This is a best-effort branch — emit a clear message that no project-level recipe was found.
4. **`tarpaulin.toml` or `[package.metadata.tarpaulin]` in `Cargo.toml`** — signals prior tarpaulin adoption. Invoke `cargo tarpaulin` using the project's own config rather than pushing the project toward `cargo-llvm-cov` unasked.

If all four probes fail, return a structured "no target found" result. The appropriate remediation is to add `cargo-llvm-cov` as a real tool (`cargo install cargo-llvm-cov --locked`, plus the `llvm-tools` rustup component) and adopt a recipe like the one below — not to bootstrap anything from inside the skill.

## Invocation Conventions

- **Invoke through the project's task runner when one is detected.** `make coverage` / `just coverage` over a bare `cargo llvm-cov` invocation — the recipe almost always pins the correct output path and flag set.
- **Compose with nextest deliberately, not by default.** Only route through `cargo llvm-cov nextest` when the project has already adopted nextest as its primary runner; otherwise `cargo llvm-cov` (plain `cargo test` underneath) is the simpler default.
- **Stream output to stderr, not stdout.** The calling surface (command, metrics pipeline, verifier) may want stdout reserved for a clean result; `cargo-llvm-cov`/`cargo-tarpaulin` chatter belongs on stderr.
- **Propagate non-zero exits.** If the coverage invocation exits non-zero (test failure, missing `llvm-tools` component, missing tool), surface the exit code. Callers that want to downgrade failure to a warning wrap the invocation — the skill itself does not swallow failures.
- **Do not mutate project config.** The skill reads `Cargo.toml`, `.config/nextest.toml`, and `tarpaulin.toml` during probing but never writes to them.
- **Doctest coverage is opt-in and nightly-gated.** Do not silently run a nightly-only invocation on a project pinned to stable via `rust-toolchain.toml` — surface that doctest/branch coverage requires an explicit toolchain override.

## Presentation Notes

The skill's rendering invariants are language-independent and defined in the main `SKILL.md`. Rust-specific notes:

- **Repo-relative paths for the `path` column.** Prefer paths like `src/foo/bar.rs` over absolute paths. `cargo-llvm-cov`'s lcov and JSON output already emit repo-relative paths — use them as-is.
- **Exclude generated and test-only code from the per-file breakdown by default.** `build.rs` output and `#[cfg(test)] mod tests` blocks measuring themselves inflate the table without insight; `cargo-llvm-cov`'s `--ignore-filename-regex` flag is the mechanical lever for this.
- **`covered/total` uses line counts, not branch counts,** to keep the visual consistent across languages — the same convention the Python and TypeScript references follow. Branch coverage, when a nightly run has produced it, belongs in an optional separate row or surface, never folded silently into the default per-file line-count column.

## Output Formats

`cargo-llvm-cov` supports lcov, Cobertura XML, JSON, text, and HTML output. For this skill:

- **`--lcov --output-path lcov.info`** — the interchange format most CI coverage dashboards (Codecov, Coveralls) consume directly.
- **`--html`** — human-browsable per-file HTML report, written under `target/llvm-cov/html/`.
- **`--json --output-path coverage.json`** — machine-readable, the shape this skill's renderer should parse for the per-file breakdown table.

Pick the format the calling surface needs; `cargo-llvm-cov` can emit more than one in the same invocation.

## Example Recipe (Makefile)

Copy a recipe like this into the project's `Makefile` or `justfile` so probe step 1 finds a canonical target. There is no manifest-level config block to ship — this recipe *is* the project's coverage configuration.

```makefile
# --- test-coverage skill: default Rust coverage recipe ----------------------
# Requires: cargo install cargo-llvm-cov --locked; rustup component add llvm-tools
# Produces lcov.info (CI dashboards) and an HTML report (target/llvm-cov/html/)
# at the project root. Swap `cargo llvm-cov` for `cargo llvm-cov nextest` if the
# project has adopted nextest as its primary runner — remember nextest cannot
# run doctests, so that substitution silently drops doc-example coverage
# unless a second `--doctests` (nightly) pass is added explicitly.
coverage:
	cargo llvm-cov --lcov --output-path lcov.info
	cargo llvm-cov --html
# --- end test-coverage skill defaults ---------------------------------------
```

**Tool ownership.** The project still needs `cargo-llvm-cov` installed as a real tool, not a `Cargo.toml` dependency:

```bash
cargo install cargo-llvm-cov --locked
rustup component add llvm-tools
```

The skill does not manage this installation — the project does.

**Branch and doctest coverage (nightly).** These require an explicit nightly override and are not part of the default recipe above:

```bash
cargo +nightly llvm-cov --branch --lcov --output-path lcov.info
cargo +nightly llvm-cov --doctests
```

**Adjusting the per-project floor.** `cargo-llvm-cov` supports `--fail-under-lines <float>` for a hard floor. The skill does not set this by default — a hard floor is a policy decision, not a mechanical default, matching the Python and TypeScript references.

**Overriding threshold bands.** The rendering bands (red `<60`, yellow `<80`, green `≥80`) live in the skill's render functions, not in the recipe above. Projects that need different bands override them via the render API.

## Related Artifacts

- [`test-coverage`](../SKILL.md) skill — dispatcher and renderer (language-agnostic entry point)
- [`rust-development`](../../rust-development/SKILL.md) skill — Rust conventions and toolchain baseline
- [`testing-strategy`](../../testing-strategy/SKILL.md) skill — coverage philosophy (coverage as discovery tool, not target); its Rust leaf covers `cargo-nextest` selector/runner mechanics in depth
