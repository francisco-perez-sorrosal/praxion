---
name: architectural-fitness-functions
description: >
  Architectural fitness functions: ArchUnit-style invariants via import-graph
  tooling and assertion-based tests, decision rubric (graph-rule vs assertion),
  citation contract (ADR/CLAUDE.md), waiver pattern. Triggers: authoring fitness
  rules, deciding between graph-rule and assertion-based invariants, authoring a
  fitness waiver. Language modules available for Python, TypeScript.
allowed-tools: [Read, Grep, Bash, Write, Edit]
compatibility: Claude Code
---

# Architectural Fitness Functions

Fitness functions make architectural invariants executable. Each rule is a
runnable check that fails loudly when a structural constraint is violated.

**Satellite files** (loaded on-demand):

- [contexts/python.md](contexts/python.md) -- import-linter quickstart, pytest fitness tests, meta-citation rule, authoring workflow for Python
- [contexts/typescript.md](contexts/typescript.md) -- dependency-cruiser quickstart, ESLint no-restricted-imports, ArchUnitTS alternative, authoring workflow for TypeScript
- [references/import-linter-recipes.md](references/import-linter-recipes.md) -- common import-linter contract recipes with INI stanzas and citation examples

## Decision Rubric

```
Is the invariant about which module imports which?
├── YES → graph-rule tool (see language context for the tool name)
└── NO  → assertion-based test (see language context for the test runner)
```

Common cases:

| Invariant | Tool |
|-----------|------|
| "Layer X must not import from layer Y" | graph-rule tool (`layers` / forbidden rule) |
| "Module X must never import from module Y" | graph-rule tool (`forbidden` / no-restricted-imports) |
| "Modules A and B must not import each other" | graph-rule tool (`independence` / symmetric forbidden rules) |
| "All public functions in module X have docstrings" | assertion-based test (AST-based) |
| "All YAML frontmatter has required field Z" | assertion-based test (file-parsing) |
| "No file in directory D has more than N lines" | assertion-based test (filesystem) |
| "Every fitness rule has a citation" | assertion-based test (the meta-citation rule) |

See the language context for your project's toolchain for the specific tool invocations.

## Citation Contract

Every fitness rule — whether a graph-rule contract or an assertion-based test — **must**
cite its architectural justification. This makes each rule self-documenting and
enables the meta-citation rule to enforce coverage automatically.

**Accepted citation forms:**

- An ADR id matching the pattern `dec-\d{3,}` (preferred when the invariant has a specific decision record)
- A CLAUDE.md principle matching `CLAUDE\.md§[A-Z][A-Za-z ]+` (preferred when the invariant follows from a foundational principle rather than a specific decision)

**Where the citation lives:**

| Rule type | Citation location |
|-----------|-------------------|
| pytest test module | Module docstring (first line is sufficient) |
| Graph-rule contract (Python) | `description=` field of the contract stanza |
| Graph-rule contract (TypeScript) | `comment` field of the rule object |
| ESLint per-file restriction | `message` field of the pattern |

**The meta-citation rule** (`fitness/tests/test_meta_citation.py`) scans both
Python surfaces with the regex `dec-\d{3,}|CLAUDE\.md§[A-Z][A-Za-z ]+`. Any uncited
rule causes the suite to FAIL.

Write the citation **before** the rule logic — it forces upfront justification and
prevents the meta-citation rule from catching you by surprise.

## Waiver Pattern

When an invariant must be temporarily violated (e.g., during a migration), annotate
the offending line with a waiver comment:

```python
import some_forbidden_module  # fitness-waiver: dec-NNN migration in progress
```

A valid waiver requires **both**:
1. A citation anchor matching the citation regex (`dec-\d{3,}` or `CLAUDE\.md§...`)
2. A non-empty reason following the anchor

The meta-citation rule scans waivers and FAILs uncited or reason-less ones.

Waivers are intentionally **distributed** — they live at the point of violation,
not in a centralized `waivers.toml`. This ensures each waiver is reviewed alongside
the code it waives, and waivers surface immediately in code review diffs.

## Language Contexts

| Language | Context File | Tooling |
|----------|--------------|---------|
| Python | [contexts/python.md](contexts/python.md) | graph-rule tool + pytest |
| TypeScript | [contexts/typescript.md](contexts/typescript.md) | dependency-cruiser + ESLint |

## Related Skills

- **[testing-strategy](../testing-strategy/SKILL.md)** -- test strategy and isolation principles that fitness tests follow
- **[code-review](../code-review/SKILL.md)** -- structured review methodology; fitness violations surface as FAIL findings in review reports
- **[refactoring](../refactoring/SKILL.md)** -- remediation path when fitness violations indicate structural issues
