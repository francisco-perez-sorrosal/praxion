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
- Self-documenting code — readable enough that comments are rarely needed
- Comments only to clarify complex algorithms or obscure language idioms to other readers
- Natural line breaks unless the surrounding code is wrapped at a specific column
- Trailing newline in all files

### Formatting and Linting

Every code change must pass the project's formatters and linters before commit. This is non-negotiable — format and lint in fix mode after writing code, before running tests.

**Universal workflow:** format → lint (fix mode) → type check → test. Detect tools from project config files (`pyproject.toml`, `package.json`, `Cargo.toml`, `go.mod`, `.prettierrc`, etc.). Run them on changed files only — not the entire project. Fix any violations that auto-fix cannot resolve.

**When to run:** At minimum before every commit and before each test run. When working interactively outside the agent pipeline (Direct or Spike tiers), run after completing a logical change — not necessarily after every individual edit.

Language-specific tool choices and configuration belong in each language's skill (e.g., `ruff` for Python, Biome or `eslint`/`prettier` for JS/TS). This rule defines the principle; skills define the tools.

### Baseline Configuration

The "must pass the linters/formatters/type-checks" mandate above is vacuous if no config exists. Every Praxion-managed project therefore **must** carry, at the repository root:

- a **linter config** (`[tool.ruff]` for Python; `biome.json` or `eslint.config.*` for JS/TS; the language's equivalent otherwise),
- a **formatter config** (`[tool.ruff.format]`/black; Biome or Prettier; the language's equivalent),
- a universal **`.editorconfig`** (charset, end-of-line, indentation) — stack-agnostic,
- a **type-check config** (`[tool.mypy]`/`[tool.pyright]` for Python; strict `tsconfig.json` for TS),
- a **`.pre-commit-config.yaml`** wiring linter + formatter + a secret scanner (run `pre-commit install` once to activate),
- a **`CONTRIBUTING.md`** documenting branch/commit conventions, the local-check commands, and the PR flow.

Runtime-service signals — a structured-logging dependency, a health check — are **not** in this universal set; they are service-conditional and owned by the `observability` skill (a library or research harness should not be forced to carry them).

These are not authored per-project from scratch. The **canonical baselines are single-sourced** in the language skills and `claude/project-baseline/`, installed idempotently by `/onboard-project` Phase 8e (and `/new-project`): `skills/python-development/assets/{ruff-baseline.toml, mypy-baseline.toml}`, `skills/typescript-development/assets/{biome.json, eslint.config.mjs, prettierrc.json, tsconfig.json}`, and `claude/project-baseline/{editorconfig, pre-commit-config.yaml, CONTRIBUTING.md.tmpl}`. When you find a managed project missing any of these, install from the canonical asset rather than hand-rolling — onboarding never overwrites an existing config. Edit the asset, not the per-project copy, to evolve the baseline.

### Language-Specific Style

Formatting, linting rules, and language idioms belong to each language's toolchain — not here. This rule covers structural and design conventions that transcend any single language.

### Immutability

Create new objects instead of mutating existing ones. When a language provides immutable alternatives, prefer them.

Rationale: immutable data prevents hidden side effects, simplifies debugging, and enables safe concurrency.

Exceptions: performance-critical inner loops where allocation cost is measured and significant, or when the language idiom strongly favors mutation (e.g., builder patterns).

### Code Organization

- Modularize with meaningful, well-scoped package/module names
- Avoid catch-all modules like `utils` — only use when a function is so generic it has no natural home
- When a module grows large, extract its helpers into `<module_name>_utils`, not a shared `utils`
- Break code into multiple files before splitting across directories

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

Always store and transmit in UTC. Convert to local time only at the presentation layer.

### Naming

- Variables and functions: descriptive, intention-revealing names
- Booleans: read as yes/no questions — `is_valid`, `has_permission`, `should_retry`
- Avoid abbreviations unless universally understood (`id`, `url`, `config`)
- Collections: plural nouns (`users`, `pending_tasks`)
- Functions: verb phrases (`fetch_user`, `validate_input`, `calculate_total`)

