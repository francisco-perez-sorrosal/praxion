# Project Principles Authoring Reference

Per-project standards artifact (`.ai-state/principles.yaml`): schema, authoring boundary, advisory/blocking guidance, absent-behavior contract, and migration path. Back to [SKILL.md](../SKILL.md).

---

## What This Artifact Is For

`.ai-state/principles.yaml` is a declarative, user-authored file that records the specific standards a particular codebase has committed to. When it exists, the implementation-planner threads applicable principles into step acceptance criteria, and the verifier gates against them per severity.

The artifact is entirely optional. Absent, empty, or malformed → silent no-op in both consumers (see [Absent / Empty / Malformed Behavior](#absent--empty--malformed-behavior)).

---

## Schema

```yaml
# .ai-state/principles.yaml — per-project standards (user-authored, optional, committed to git)
# version is reserved for forward-compatible schema evolution; absent → treated as 1
version: 1
principles:
  - id: no-raw-sql                        # required; kebab-case, stable, unique within this file
    statement: >                          # required; one declarative standard, behavior-phrased
      Database access goes through the repository layer; no raw SQL in handlers.
    severity: blocking                    # required; advisory | blocking
    scope: "src/api/**"                   # optional; glob or list of globs; absent → "*" (project-wide)
    rationale: >                          # optional; why this standard exists
      Centralizes query auditing and prevents injection surface.

  - id: public-fn-docstrings
    statement: Every exported function carries a docstring with a usage example.
    severity: advisory
    # scope omitted → applies project-wide ("*")
    # rationale omitted → fine
```

### Field Reference

| Field | Required | Type | Default | Meaning |
|---|---|---|---|---|
| `id` | yes | string (kebab-case) | — | Stable, unique-within-file identifier. Cited in findings as `[Principle: <id>]`. Use a descriptive slug that survives refactors. |
| `statement` | yes | string | — | One declarative project standard, behavior-phrased. This is what the verifier assesses code against. Write it as a constraint, not a goal: "X goes through Y" not "we try to use Y". |
| `severity` | yes | `advisory` \| `blocking` | — | Routes the gate: `blocking` → FAIL on violation (gates like an unmet acceptance criterion); `advisory` → WARN (surfaced, never fails the gate). Unknown value → coerced to `advisory` + one WARN noting the coercion (fail-safe, never fail-closed on a typo). |
| `scope` | no | string (glob) or list of globs | `"*"` | Applicability filter against the set of changed files. A principle whose scope matches none of the changed files is skipped silently — no finding emitted (avoids PASS noise). `"*"` matches everything. |
| `rationale` | no | string | absent | Why the standard exists. Surfaced in the finding body to help the user act on a violation. Optional but strongly recommended for `blocking` principles. |

**Top-level `version:`** is reserved for forward-compatible schema evolution. Absent → treated as `1`. Do not use it for anything else.

---

## Advisory vs Blocking — Guidance

Choose severity by asking: "What should happen if this standard is violated in a real PR?"

| Severity | Gate effect | When to use |
|---|---|---|
| `blocking` | FAIL — same as an unmet acceptance criterion. Feeds the rework loop. User can override via the standard FAIL-override path (tech-debt promotion). | Standards where a violation would cause real harm if merged: security boundaries, data-integrity invariants, mandatory audit trails. |
| `advisory` | WARN — surfaced in the report, never fails the gate. | Standards where a violation is worth noting but does not block delivery: style preferences, documentation completeness, test coverage aspirations. |

**When in doubt, start with `advisory`.** You can tighten to `blocking` once the team has had time to comply. The opposite direction (loosening a `blocking` that turns out to be too strict) is disruptive mid-pipeline.

---

## Principles-vs-Rules Boundary

### What belongs here vs in `rules/**`

**Project-principles** (`.ai-state/principles.yaml`) are *project-specific standards* — decisions a particular codebase has made about how *it* is built. Examples: "all DB access goes through the repository layer," "public functions need usage-example docstrings," "no third-party HTTP clients other than `httpx`."

They are user-authored, per-project, and gate only this project's pipeline.

**Framework rules** (`rules/**`) are *Praxion conventions* — cross-project engineering discipline shipped with the plugin (coordination protocol, behavioral contract, coding style). They are framework-authored, global, and apply to every managed project.

See `rules/CLAUDE.md` for the full catalog of existing framework rules before authoring a new principle.

### Decision test

> **"Would this standard make sense in a different, unrelated project?"**
>
> - **Yes** → it is probably a framework rule. Check `rules/` first — it may already exist there. Do not reinvent it as a project-principle.
> - **No / "only for this codebase"** → it is a project-principle and belongs in `principles.yaml`.

Examples applying the test:

| Candidate standard | Test result | Where it belongs |
|---|---|---|
| "No raw SQL in handlers" | No (specific to this repo's layering) | `principles.yaml` |
| "Functions under 50 lines" | Yes (universal coding style) | Already in `rules/swe/coding-style.md` |
| "All auth goes through our `auth_service` module" | No (specific module name) | `principles.yaml` |
| "Explicit error handling, no silent swallowing" | Yes (universal discipline) | Already in `rules/swe/coding-style.md` |
| "Use `AsyncSession` not `Session` for all DB calls" | No (specific to this project's async choice) | `principles.yaml` |

---

## Absent / Empty / Malformed Behavior

All three cases → **silent no-op** in both the implementation-planner and the verifier.

| Case | Behavior |
|---|---|
| File does not exist | Skip silently. No finding, no WARN, no error. |
| File exists but `principles:` list is empty (`[]` or absent key) | Skip silently. Same as absent. |
| File exists but YAML is unparseable | Skip principles check; emit one note (not a FAIL/WARN finding) in `LEARNINGS.md` (planner) or the report preamble (verifier) that the file could not be parsed. Proceed as if absent. Never block a pipeline run on a user typo in a YAML comment. |

This mirrors the SH07 absent-specs skip and the "advisory doc absent → no gate" precedent used for deployment-doc staleness and architecture-doc staleness.

---

## Migration Path → `project_profile.yaml`

`project_profile.yaml` has no active producer today. `principles.yaml` ships ahead of it and is designed for non-breaking migration:

1. **Schema is location-agnostic.** The `principles:` list shape in `principles.yaml` is byte-identical to the eventual `project_profile.yaml.principles:` block. No field renames at migration.

2. **Single resolver seam.** Both consumers (planner and verifier) read through one conceptual lookup — "get this project's principles list." When `project_profile.yaml` gains a producer, the resolver gains one branch with a defined precedence:

   > **`project_profile.yaml.principles:` (if present and non-empty) wins; otherwise fall back to `.ai-state/principles.yaml`.**

   This is a one-line resolver edit per consumer, not a re-plumb.

3. **Deprecation, not deletion.** When the profile producer lands, `principles.yaml` becomes the fallback/override (soft-deprecation). Existing projects keep working; new projects get principles via the profile automatically.

4. **Zero always-loaded cost to migrate.** The inventory lives in this on-demand reference (not an always-loaded rule), so migrating the documentation is a reference edit with zero budget impact.

---

## Scope Matching

The `scope` field is a glob (or list of globs) matched against the set of files changed in the pipeline run (already computed by the verifier's `git diff` phase and by the planner's `Files` field per step).

- `"*"` (or absent) → matches everything → principle applies project-wide.
- `"src/api/**"` → matches only files under `src/api/`.
- `["src/api/**", "src/auth/**"]` → matches files under either directory.
- A principle whose scope matches **none** of the changed files is **omitted silently** — no PASS, no WARN, no noise.

Matching uses Python's `fnmatch` semantics (standard glob: `*` matches within a path segment; `**` is treated as a greedy wildcard across segments by the resolver).

---

## Worked Example

```yaml
# .ai-state/principles.yaml — Example for a FastAPI + SQLAlchemy project
version: 1
principles:

  # Architectural boundary — hard blocking standard
  - id: repo-layer-only
    statement: >
      All database queries go through repository classes in `src/repositories/`;
      no SQLAlchemy Session usage directly in route handlers or service functions.
    severity: blocking
    scope: "src/**"
    rationale: >
      Keeps the test double surface small (mock the repo, not the Session),
      and centralizes query-level caching logic.

  # Documentation standard — advisory: surfaces violations without blocking delivery
  - id: route-docstrings
    statement: >
      Every FastAPI route function has a docstring describing its purpose,
      expected inputs, and the shape of its response.
    severity: advisory
    scope: "src/routes/**"

  # Security boundary — blocking with narrow scope
  - id: no-user-input-in-log-messages
    statement: >
      Log messages must not interpolate unvalidated user input directly;
      use structured log fields instead.
    severity: blocking
    # scope absent → applies project-wide
    rationale: Log injection attack surface; structured fields are queryable and safe.
```
