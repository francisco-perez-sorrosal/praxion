---
id: dec-101
title: Architectural fitness functions infrastructure — fitness/ at project root, import-linter + pytest, citation contract, waiver mechanism
status: accepted
category: architectural
date: 2026-04-30
summary: 'Introduce a fitness/ directory at project root holding import-linter contracts and pytest fitness rules; every rule cites an ADR id or CLAUDE.md principle in module docstring (pytest) or description= field (import-linter); a meta-fitness rule self-polices the citation contract; waivers carry the same anchor+reason discipline.'
tags: [aac, fitness-functions, architecture, import-linter, pytest, citation-contract, waivers]
made_by: agent
agent_type: systems-architect
pipeline_tier: standard
affected_files:
  - fitness/
  - fitness/import-linter.cfg
  - fitness/tests/__init__.py
  - fitness/tests/conftest.py
  - fitness/tests/test_starter_rule.py
  - fitness/tests/test_meta_citation.py
  - fitness/README.md
  - skills/architectural-fitness-functions/SKILL.md
  - skills/architectural-fitness-functions/references/import-linter-recipes.md
re_affirmed_by:
  - dec-104
---

## Context

Praxion has zero fitness functions. ArchUnit-style invariants ("no skill imports an agent module", "every Built component appears in the LikeC4 DSL", "every public API has at least one ADR carrier") have no test home. Without them, model→code drift accumulates silently between sentinel runs.

The promethean's Idea 5 named `import-linter` + `pytest` as the Python ArchUnit-equivalent. The seed brief asked the architect to resolve four sub-decisions:

1. Directory placement (project root vs `tests/fitness/`).
2. Citation contract (frontmatter vs docstring vs decorator).
3. Waiver mechanism shape.
4. CI integration scope.

## Decision

**Directory placement: `fitness/` at project root.** Reasons: (a) `import-linter` configs are conventionally `.cfg`/`.toml` files at project root, so co-locating pytest fitness rules with them avoids splitting the suite; (b) `fitness/` is its own test category — visually distinct from `tests/` (unit/integration) signals "these test architecture, not behavior"; (c) keeps `tests/` semantically clean.

**Internal layout:**

```
fitness/
  README.md                    # one-paragraph: purpose, citation contract, waiver mechanism
  import-linter.cfg            # import-graph contracts
  tests/
    __init__.py
    conftest.py                # shared fixtures
    test_starter_rule.py       # at least one starter rule citing an ADR or CLAUDE.md principle
    test_meta_citation.py      # meta-fitness: every rule has a citation; every waiver has anchor+reason
```

**Citation contract: module docstring (pytest) + `description=` field (import-linter).** Every rule MUST include one of:

- An ADR id matching `dec-\d{3,}`
- A CLAUDE.md principle reference matching `CLAUDE\.md§[A-Z][A-Za-z ]+`

The meta-fitness rule (`test_meta_citation.py`) scans every sibling rule and FAILs the suite when any rule lacks a citation OR any waiver lacks both anchor and reason.

**Waiver mechanism:** `# fitness-waiver: <ADR-id-or-principle> <reason>` comment on the offending line/block. The meta-fitness rule scans waivers and validates each carries a citation-regex-matching anchor AND a non-empty reason (≥1 word).

**CI integration: deferred to Idea 7 / v1.1.** v1 ships `fitness/` runnable locally (`pixi run fitness` or project-defined equivalent — the implementation-planner picks the wrapper task name based on project conventions). The `cicd-engineer` authors `.github/workflows/architecture.yml` in v1.1.

A new skill `skills/architectural-fitness-functions/SKILL.md` provides the decision rubric (import-graph invariants → import-linter; everything else → pytest), the citation contract, the waiver pattern, and `references/import-linter-recipes.md` for common contract patterns.

## Considered Options

### Sub-decision A — Directory placement

#### Option A1 — `tests/fitness/`

**Pros:** Keeps all test-runnable code under one root; existing test discovery (`pytest tests/`) finds it automatically.

**Cons:** Mixes architecture-tests with behavior-tests in one directory tree. `import-linter` configs conventionally live at project root, so this option splits the suite (config at root, tests under `tests/`). Failures in fitness tests would compete with behavior-test failures in the same report — different remediation paths, same surface.

#### Option A2 — `fitness/` at project root (chosen)

**Pros:** Visual + structural separation between behavior and architecture tests. Consolidates `import-linter.cfg` and pytest fitness rules in one place. Different report (`pixi run fitness`) signals different category. `tests/` stays semantically clean.

**Cons:** Contributors must learn one new directory location.

#### Option A3 — `.ai-state/fitness/`

**Pros:** Co-located with other persistent state.

**Cons:** `.ai-state/` is for state, not code. Fitness rules ARE code (executable). Misclassification.

### Sub-decision B — Citation contract location

#### Option B1 — YAML frontmatter at top of file

**Pros:** Machine-parseable; tooling-friendly.

**Cons:** Pytest tests don't conventionally have frontmatter (the docstring is the documentation surface). `import-linter.cfg` is INI — no frontmatter concept. Inconsistent across rule types.

#### Option B2 — Module docstring (pytest) + `description=` field (import-linter) (chosen)

**Pros:** Each rule type uses its native documentation surface. Both surfaces are inspected by `inspect.getdoc()` (pytest) or `configparser` (import-linter). Citation-regex scan over both is straightforward.

**Cons:** Two locations means the meta-fitness rule must scan two formats. Mitigated by a single regex applied to the extracted text from each.

#### Option B3 — Decorator (`@cite("dec-NNN")`)

**Pros:** Explicit at the call site.

**Cons:** Pytest-only — alien for `import-linter`. Adds a third surface (test code beyond docstring/contract description).

### Sub-decision C — Waiver mechanism

#### Option C1 — Standalone `fitness/waivers.toml` file

**Pros:** Centralized; auditable in one place.

**Cons:** Waivers are local exceptions; centralizing them creates a metadata surface that drifts from the code being waived. Audit by review of one file is harder than audit by review of the diff that introduces the waiver.

#### Option C2 — `# fitness-waiver: <anchor> <reason>` inline comment (chosen)

**Pros:** Waivers live where they apply. The diff that introduces a waiver reviews simultaneously with the code it waives. Meta-fitness rule scans for the comment pattern and validates anchor + reason.

**Cons:** Distributed; an audit must scan the codebase for the marker.

#### Option C3 — Decorator + reason (`@waive("dec-NNN", "reason")`)

**Pros:** Explicit; programmatic.

**Cons:** Pytest-only. Doesn't apply to import statements (where most waivers will land).

### Sub-decision D — CI integration scope in v1

#### Option D1 — Ship CI workflow in v1

**Pros:** Fitness suite enforced from day one in CI.

**Cons:** Couples Idea 5 to Idea 7 (v1.1). Bundling them ships more files in v1; rolling back v1 means rolling back CI too. Idea 7 is `cicd-engineer`'s domain — handing it to the architect agent in v1 is a boundary creep.

#### Option D2 — Defer CI to v1.1 (chosen)

**Pros:** v1 scope stays surgical (Ideas 1, 2, 4, 5 only). Each idea is independently revertible. `cicd-engineer` authors the CI workflow in v1.1 with the right specialist context.

**Cons:** v1 fitness rules run only locally; contributors who don't run them locally will not see failures until v1.1's CI lands. Mitigated by the architect-validator's path-scope check including `fitness/` so changes there trigger validator runs in v1.

## Consequences

**Positive:**

- Architectural invariants become enforced, not aspirational.
- Fitness directory is itself a living catalog of architectural rules — readable by humans, executable by machines.
- Citation contract makes every rule traceable to its source of authority (ADR or CLAUDE.md principle).
- Waiver mechanism prevents ossification (no "permanent waivers without explanation"; meta-fitness FAILs uncited waivers).
- Self-policing: meta-fitness rule guarantees citation discipline, no external auditing required.

**Negative:**

- Authoring overhead: every fitness rule needs a citation. Mitigated because uncited rules indicate fuzzy thinking — the friction is the feature.
- Suite grows over time; CI runtime cost rises. Mitigated by the citation requirement (each rule must justify itself), `import-linter` being fast (millisecond-scale) and pytest fitness rules being typically AST-based (also fast).
- Two test surfaces (`tests/` and `fitness/`) require two pytest invocations. Mitigated by a `pixi run fitness` wrapper task.
- Rules without citations would create a "looks fine" surface area; mitigated by the meta-fitness self-policing rule.

**Operational:**

- v1 ships only starter rules — one `import-linter` contract and one pytest fitness test, both citing an existing ADR or CLAUDE.md principle.
- The implementer schedules version verification of `import-linter` and `pytest` via the `python-prj-mgmt` skill before pinning versions.
- `pixi run fitness` (or project-defined equivalent) wraps both `import-linter --config fitness/import-linter.cfg` and `pytest fitness/tests/` invocations.
- The architect-validator agent's Phase 4 (Model→Code drift) consumes the import-linter resolved graph; `fitness/import-linter.cfg` therefore serves both as the project's invariant declaration and as a dependency-graph input source for the validator.
