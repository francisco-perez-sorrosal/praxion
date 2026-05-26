# Testing Strategy

Language-agnostic testing methodology for strategic testing decisions: what to test, at which level, with what isolation and coverage approach.

## When to Use

- Choosing between unit, integration, and end-to-end tests
- Designing mocking boundaries and test double strategies
- Architecting fixture and test data patterns
- Evaluating property-based testing applicability
- Planning coverage philosophy (coverage as discovery tool, not target)
- Assessing test isolation and determinism requirements

## Activation

Activates automatically on testing strategy tasks: test pyramid decisions, mocking philosophy, fixture architecture, coverage approach, or property-based testing questions.

Trigger explicitly by mentioning "testing-strategy skill" or referencing it by name.

## Skill Contents

| File | Purpose |
|------|---------|
| `SKILL.md` | Core reference: strategy selection, isolation, mocking, fixtures, coverage, property-based testing, naming |
| `references/python-testing.md` | Advanced pytest patterns: conftest architecture, hypothesis, fixture composition, markers, coverage |
| `references/typescript-testing.md` | TypeScript testing patterns with Vitest and Jest, type-safe mocking, integration testing |
| `references/rust-testing.md` | Rust testing with the built-in test framework, proptest, and integration patterns |
| `references/test-topology.md` | Language-agnostic test topology schema: group schema, tier vocabulary, identifier registries |
| `references/gate-canaries.md` | How to author canary tests that prove a CODE gate bites (negative-case contract) |
| `README.md` | This file -- overview and usage guide |

## Related Skills

- [`testing-conventions` rule](../../rules/swe/testing-conventions.md) -- Declarative constraints for test code (what must be true)
- [`test-engineer` agent](../../agents/test-engineer.md) -- Pipeline agent for test execution workflow
- [`/test` command](../../commands/test.md) -- Auto-detect test framework and run tests
- [`python-development` skill](../python-development/) -- Python language patterns (cross-references this skill for advanced pytest)
