# Architectural Fitness Functions

Skill for making architectural invariants executable. Provides the decision rubric (graph-rule tool vs assertion-based test), citation contract, and waiver pattern for authoring runnable architectural checks that fail loudly when structural constraints are violated. Language modules available for Python and TypeScript.

## When to Use

- Authoring a new architectural invariant (import boundary, layer rule, or convention check)
- Choosing between a graph-rule tool and an assertion-based test for a given invariant
- Debugging the meta-citation rule (`fitness/tests/test_meta_citation.py`)
- Authoring or reviewing a fitness waiver

## Activation

Activates automatically when the agent encounters fitness function tasks: "architectural invariant", "import boundary rule", "fitness function", "ArchUnit", "dependency-cruiser", "import-linter", "fitness waiver".

Trigger explicitly by mentioning "architectural-fitness-functions skill" or referencing it by name.

## Skill Contents

| File | Purpose |
|------|---------|
| `SKILL.md` | Core reference: decision rubric, citation contract, waiver pattern, language contexts table |
| `contexts/python.md` | Python-specific: import-linter quickstart, pytest fitness tests, meta-citation rule |
| `contexts/typescript.md` | TypeScript-specific: dependency-cruiser quickstart, ESLint no-restricted-imports, ArchUnitTS |
| `references/import-linter-recipes.md` | Common import-linter contract recipes with INI stanzas and citation examples |
| `README.md` | This file -- overview and usage guide |

## Related Skills

- [`testing-strategy`](../testing-strategy/SKILL.md) -- test strategy principles that fitness tests follow
- [`code-review`](../code-review/SKILL.md) -- fitness violations surface as FAIL findings in review reports
- [`refactoring`](../refactoring/SKILL.md) -- remediation when fitness violations indicate structural issues
