---
paths:
- '**/*.py'
- '**/*.pyi'
- '**/*.ts'
- '**/*.tsx'
- '**/*.js'
- '**/*.jsx'
- '**/*.mjs'
- '**/*.cjs'
- '**/*.go'
- '**/*.rs'
- '**/*.java'
- '**/*.kt'
- '**/*.kts'
- '**/*.rb'
- '**/*.swift'
- '**/*.c'
- '**/*.h'
- '**/*.cpp'
- '**/*.hpp'
- '**/*.cc'
- '**/*.m'
- '**/*.sh'
- '**/*.bash'
- '**/*.zsh'
core: false
---

## Coding Style

Language-independent structural and design conventions for writing and reviewing code.

### Core Principles

- Object and functional programming with immutable data when possible
- Self-documenting code — naming and structure carry the *what*, so restatement comments are never needed
- Comments carry what code cannot: rationale and invariants (*why*), complex-algorithm explanation, skimmable structure in long files, cross-file obligations — per `### Reading Order and Narrative` below; never a restatement of the next line
- Natural line breaks unless the surrounding code is wrapped at a specific column
- Trailing newline in all files

### Formatting and Linting

Every code change must pass the project's formatters and linters before commit. This is non-negotiable — format and lint in fix mode after writing code, before running tests.

**Universal workflow:** format → lint (fix mode) → type check → test. Detect tools from project config files (`pyproject.toml`, `package.json`, `Cargo.toml`, `go.mod`, `.prettierrc`, etc.). Run them on changed files only — not the entire project. Fix any violations that auto-fix cannot resolve.

**When to run:** At minimum before every commit and before each test run. When working interactively outside the agent pipeline (Direct or Spike tiers), run after completing a logical change — not necessarily after every individual edit.

Language-specific tool choices and configuration belong in each language's skill (e.g., `ruff` for Python, Biome or `eslint`/`prettier` for JS/TS). This rule defines the principle; skills define the tools.

### Baseline Configuration

The "must pass the linters/formatters/type-checks" mandate above is vacuous if no config exists. Every Praxion-managed project therefore **must** carry, at the repository root:

- a **linter config** (`[tool.ruff]` for Python; `biome.json` or `eslint.config.*` for JS/TS; `[lints]` in `Cargo.toml` for Rust; the language's equivalent otherwise),
- a **formatter config** (`[tool.ruff.format]`/black; Biome or Prettier; `rustfmt.toml` for Rust; the language's equivalent),
- a universal **`.editorconfig`** (charset, end-of-line, indentation) — stack-agnostic,
- a **type-check config** (`[tool.mypy]`/`[tool.pyright]` for Python; strict `tsconfig.json` for TS; for Rust, **the compiler is the type checker** — `[lints]` in `Cargo.toml` carries the policy and no separate config file exists, so this bullet is satisfied by the linter config above, not by an additional file),
- a **`.pre-commit-config.yaml`** wiring linter + formatter + a secret scanner (run `pre-commit install` once to activate),
- a **`CONTRIBUTING.md`** documenting branch/commit conventions, the local-check commands, and the PR flow.

Runtime-service signals — a structured-logging dependency, a health check — are **not** in this universal set; they are service-conditional and owned by the `observability` skill (a library or research harness should not be forced to carry them).

These are not authored per-project from scratch. The **canonical baselines are single-sourced** in the language skills and `claude/project-baseline/`, installed idempotently by `/onboard-project` Phase 8e (and `/new-project`): `skills/python-development/assets/{ruff-baseline.toml, mypy-baseline.toml}`, `skills/typescript-development/assets/{biome.json, eslint.config.mjs, prettierrc.json, tsconfig.json}`, `skills/rust-development/assets/{rustfmt.toml, cargo-lints.toml, rust-toolchain.toml}`, and `claude/project-baseline/{editorconfig, pre-commit-config.yaml, CONTRIBUTING.md.tmpl}`. When you find a managed project missing any of these, install from the canonical asset rather than hand-rolling — onboarding never overwrites an existing config. Edit the asset, not the per-project copy, to evolve the baseline.

### Language-Specific Style

Formatting, linting rules, and language idioms belong to each language's toolchain — not here. This rule covers structural and design conventions that transcend any single language.

### Expressive Constructs

Choose the construct that states the intent most directly for the file's actual readers:

- Prefer declarative forms (comprehension, pattern match, pipeline) when they remove accumulator boilerplate the reader would otherwise simulate mentally; keep the explicit loop when ordering, effects, or error flow genuinely need to be visible
- Write idiomatically for the language — an idiom imported from another paradigm forces a context switch and needs justification
- Density has a ceiling: code a reader must *decode* rather than *read* has left expressiveness for cleverness. Expressiveness serves clarity, never terseness for its own sake
- Calibrate surprise to the actual reading audience, not the author's habits

Type-level expressiveness (sum types, newtypes, exhaustiveness): `### Data Structures and Invariants` below and `skills/data-structure-design/SKILL.md`. Judgment layer: `skills/beautiful-code/SKILL.md`.

### Immutability

Create new objects instead of mutating existing ones. When a language provides immutable alternatives, prefer them.

Rationale: immutable data prevents hidden side effects, simplifies debugging, and enables safe concurrency.

Exceptions: performance-critical inner loops where allocation cost is measured and significant, or when the language idiom strongly favors mutation (e.g., builder patterns).

### Side-Effect Discipline

Isolate computation from effect — functional core, imperative shell:

- Structure impure procedures as gather → compute → use: collect inputs at the edge, pass them through pure logic, apply effects (I/O, logging, mutation) at the end — never buried mid-call-stack inside "business logic"
- A function's parameter list accounts for every value affecting its output — no hidden reads of globals, singletons, ambient config, or the wall clock behind a pure-looking signature
- Core logic is unit-testable without mocks; needing a mock to test a function signals effect entanglement — extract the pure part
- Purity is a continuum, not a gate: grade by impurity count (reads global / writes global / does I/O / mutates parameters) and move code toward zero; do not wrap trivial IO-glue in ceremony

Complements `### Immutability` (data discipline) with effect placement (control discipline).

### Data Structures and Invariants

Choose a structure's representation before writing the behavior that consumes it. For types that cross a component boundary, carry invariants, or have a lifecycle:

- **Make illegal states unrepresentable** where the language allows it cheaply — mutually exclusive shapes are a sum type / discriminated union, not correlated nullable fields or boolean pairs whose combinations include impossible states
- **Every invariant has a named enforcement point** — type system, validating constructor, or runtime check. An invariant stated only in a comment or docstring is not enforced
- **Closed option sets are enums or literal unions**, never raw strings; matches over them are exhaustive (compiler flag, linter, or `assert_never`)
- **Constrained domain values get a domain type** (newtype/branded type + validating constructor), not a bare primitive re-validated at every call site
- **Parse, don't validate, at boundaries** — external input becomes a precisely typed internal value once, at the edge; the interior never re-checks and never handles the raw shape (extends `### Input Validation` below: validation *produces the validated type*, it doesn't just gate)

Exceptions: throwaway/glue shapes that never cross a boundary; exploratory spikes where the domain model is still moving. Methodology, techniques, and the review checklist: `skills/data-structure-design/SKILL.md`.

### Code Organization

- Modularize with meaningful, well-scoped package/module names
- Avoid catch-all modules like `utils` — only use when a function is so generic it has no natural home
- When a module grows large, extract its helpers into `<module_name>_utils`, not a shared `utils`
- Break code into multiple files before splitting across directories

### Reading Order and Narrative

A file tells its story top-down:

- Order file contents by decreasing abstraction — entry point or top-level function first, helpers after — so a top-to-bottom read follows the call structure (the newspaper/stepdown reading). Language-forced declaration orders are acceptable when applied consistently
- Comments carry what code cannot: *why* comments (rationale, invariants, units), *guide* comments (skimmable section structure in long files), and *checklist* comments ("if you change X, also update Y") at cross-file obligation sites. Comments that restate the code and commented-out code are removed on sight
- A change lands as named, revertible, commit-sized steps — the commit sequence is part of the narrative, never "WIP / fix / more fixes"

Extends `### Code Organization` from placement to reading order. Module-tree narrative (the directory as table of contents) is owned by the implementation-planner's structure discipline.

### Code Reuse and DRY

- Before writing new logic, check if equivalent functionality exists in the current file, module, or sibling modules
- Extract shared logic into a single source of truth — never copy-paste with minor variations
- When the same pattern appears three times, refactor immediately into a shared abstraction
- When modifying a file, scan related files in the same directory for similar functions or patterns
- Prefer extending an existing function with a parameter over duplicating it with small differences

### File Size

- Target: 200–400 lines
- Hard ceiling: 800 lines — beyond this, split by cohesion
- Extract when a file covers two or more unrelated concerns, regardless of line count

### Function Size

- Target: under 30 lines of logic (excluding docstrings, blank lines, and signatures)
- Hard ceiling: 50 lines — beyond this, extract a helper
- A function should do one thing and be nameable without conjunctions ("and", "or", "then")

### Nesting Depth

- Maximum 4 levels of indentation in any function
- Use early returns, guard clauses, and extraction to flatten logic

```
// Wrong — deep nesting
function process(items):
    if items is not empty:
        for item in items:
            if item.isValid():
                if item.needsUpdate():
                    update(item)

// Right — early return + guard clause
function process(items):
    if items is empty:
        return
    for item in items:
        if not item.isValid():
            continue
        if item.needsUpdate():
            update(item)
```

### Error Handling

- Handle errors explicitly at every level — never silently swallow exceptions
- UI-facing code: user-friendly messages with actionable guidance
- Internal/server code: log full context (stack trace, input values, operation attempted)
- Distinguish recoverable errors (retry, fallback) from fatal ones (fail fast)

### Ordered Operations

When operations have an inherent required order — shutdown sequences, initialization protocols, middleware chains, resource cleanup, migration steps — the code must make that order explicit and resistant to accidental reordering.

- Define the sequence in a single authoritative place (a list, an enum, a pipeline definition) — never scatter ordered steps across unrelated functions where a reader cannot see the full sequence
- Release resources in reverse acquisition order: what was acquired last is released first
- Add a comment at the sequence definition explaining *why* the order matters when the reason is not obvious from the operations themselves
- When steps are added or removed, verify the ordering invariant still holds — especially for cleanup and teardown paths where a misordered step can leak resources or corrupt state

### Input Validation

Validate at system boundaries only — not between trusted internal modules.

System boundaries:
- User input (CLI args, form data, API request bodies)
- External API responses
- File content and environment variables
- Database query results when schema is not enforced

Use schema-based validation where available. Fail fast with clear error messages that identify what was wrong and what was expected.

### Compatibility and Deprecation

Observable behavior of a consumed surface is a contract — with enough users, everything observable (error text, ordering, defaults, timing) is depended on by somebody (Hyrum's Law):

- A change that breaks observable public behavior is a defect by default; shipping one deliberately requires an explicit deprecation or versioning path stated with the change
- Minimize unintended observability on public surfaces; document what cannot be hidden as explicit contract
- At boundaries, reject malformed input with a contractual error rather than silently tolerating or coercing it — silent tolerance calcifies divergent behavior (the modern supersession of "be liberal in what you accept"; same stance as `### Input Validation`'s fail-fast)
- Compatibility rigor is proportional to blast radius: the ratchet binds public, consumed surfaces; internals behind a stable contract stay free to improve

Evolution and versioning mechanics for data shapes: `### Data Structures and Invariants` and `skills/data-structure-design/SKILL.md`.

### Constants Over Magic Values

- No hardcoded literals in logic — extract to named constants or configuration
- Exception: trivially obvious values (`0`, `1`, `""`, `true/false`) where meaning is self-evident in context

### Timestamp Formatting

Use the appropriate format for the context:

- **Data interchange** (JSON, APIs, logs): ISO 8601 — `2026-02-08T14:30:00Z`
- **Filenames**: `YYYY-MM-DD_HH-MM-SS` — no colons, which are invalid or problematic on macOS/Windows
- **User-facing display**: locale-aware formatting

Language-specific:
- Python: `datetime.isoformat()`
- Java/Kotlin: `Instant.toString()`
- JS/TS: `toISOString()`
- Rust: format via `time`/`chrono`/`jiff` `Display`/`to_rfc3339`, not manual string-building — crate choice: `skills/rust-development/references/essential-crates.md`

Always store and transmit in UTC. Convert to local time only at the presentation layer.

### Naming

- Variables and functions: descriptive, intention-revealing names
- Booleans: read as yes/no questions — `is_valid`, `has_permission`, `should_retry`
- Avoid abbreviations unless universally understood (`id`, `url`, `config`)
- Collections: plural nouns (`users`, `pending_tasks`)
- Functions: verb phrases (`fetch_user`, `validate_input`, `calculate_total`)
