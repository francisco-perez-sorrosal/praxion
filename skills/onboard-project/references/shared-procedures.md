# Praxion Onboarding — Shared Procedures

Procedures cited by more than one phase body, extracted once here so `phases-core.md` and `phases-optional.md` do not restate the same rule twice. See [../SKILL.md](../SKILL.md) for §Pre-flight, §Flow, §Phase Gates, and §Idempotency Predicates.

## § Stack command resolution

Used by: §Phase 6 (Project Essentials Block placeholders, `phases-core.md`) and §Phase 8e sub-step 8e.6 (CONTRIBUTING.md, `phases-optional.md`). Resolve once per run; reuse the same values in both places rather than re-deriving them.

**General rule.** Inspect the project's config (`pyproject.toml`, `package.json`, `Cargo.toml`, `go.mod`, `Makefile`, CI workflows, the README) and fill `<build command>` / `<test command>` / `<lint command>` / `<typecheck command>` with the project's actual commands. Omit a line (and renumber) when the project has no such command; never invent one. If a value is genuinely undeterminable, leave the placeholder with an inline `# TODO:` note so the user fills it.

**Rust command resolution.** When `Cargo.toml` is detected:

- `<build command>` → `cargo build`
- `<test command>` → `cargo test` (or `cargo nextest run` once the project has adopted `cargo-nextest`), **plus** `cargo test --doc` on its own line — nextest does not run doc-tests, and plain `cargo test` running them is not a substitute for calling this out explicitly
- `<lint command>` → `cargo clippy --all-targets -- -D warnings`
- `<typecheck command>` → omit entirely (renumber) — the compiler performs type checking as part of `cargo build`/`cargo test`, so there is no separate Rust typecheck step to name
- Also add a formatting-check line alongside the numbered list — `cargo fmt --all -- --check` — since Rust's format gate is a distinct command from its lint gate (unlike some stacks where one tool does both)

## § Hub SHA resolution and template self-check

Used by: §Phase 8e sub-step 8e.8 (ci-autofix caller + policy + cross-model review gate) and sub-step 8e.9 (label taxonomy manifest + reconciler caller), both in `phases-optional.md`.

**Resolution.** `{{HUB_SHA}}` → the hub's **real, current 40-hex commit SHA**, resolved at install time — e.g. `gh api repos/francisco-perez-sorrosal/praxion/commits/main --jq .sha` (the tip of the hub's default branch), or the SHA behind a pinned hub release tag. Resolve it to an actual SHA: **never** a placeholder, and never a mutable tag or branch ref — a dangling `uses:` ref makes the installed caller fail to load. **Reuse across sub-steps within one run**: if an earlier sub-step in this same onboarding run already resolved the SHA (e.g. 8e.8 ran before 8e.9), reuse that value rather than re-resolving.

**`{{`-survivor self-check.** After writing any file rendered from a template containing `{{PLACEHOLDER}}` tokens, grep the installed file for any surviving `{{` and abort loudly if one remains — no unresolved placeholder may survive into the installed file.

## § Version-aware staleness comparison rationale

Used by: §Phase 3 (merge driver registration) and §Phase 4 (git hooks), both in `phases-core.md`; cross-referenced by §Phase 6's stale-block self-heal note.

**The rule.** When a predicate checks whether a Praxion-managed artifact (a `git config` value, a symlink target) is "already installed," compare the **full resolved path** against the **live** `${PLUGIN_INSTALL_PATH}` captured at pre-flight — never a version-agnostic substring check like "already contains `/praxion/`".

**Why.** A version-agnostic substring check treats any prior-version pin as "already done." That is the bug that stranded upgraded consumers: a plugin upgrade moves the install path (`/praxion/<old-version>/` → `/praxion/<new-version>/`), and a substring-only check can no longer distinguish a current pin from a stale one — so the artifact quietly keeps pointing at a path that may no longer exist (old version caches get garbage-collected) or no longer receives updates. Comparing the full path makes drift detectable: a match confirms currency, a `/praxion/` substring hit with a path mismatch flags the artifact as **stale** and triggers re-registration/re-pointing, not a skip.
