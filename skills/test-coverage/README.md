# Test Coverage

Language-agnostic dispatcher for locating, invoking, and rendering project test coverage. Reads the project's own coverage tooling and produces consistent output across terminal, Markdown, and report surfaces. This skill is the **canonical polyglot template** for cross-language skills in the Praxion ecosystem.

## When to Use

- Reporting coverage percentages for a project
- Running the canonical coverage target without installing new tooling
- Rendering coverage tables for reports or pipeline artifacts
- Comparing coverage against a prior run (delta tracking)
- Wiring coverage into commands, agents, or metrics pipelines

## Activation

Activates automatically when the agent needs to measure or report test coverage: "run coverage", "coverage report", "coverage percentage", "compare coverage", "coverage delta".

Trigger explicitly by mentioning "test-coverage skill" or referencing it by name.

## Skill Contents

| File | Purpose |
|------|---------|
| `SKILL.md` | Core dispatcher: locate/invoke/render responsibilities, presentation conventions, gotchas |
| `references/python.md` | Python-specific: probe order, pytest-cov invocation, config block, presentation notes |
| `references/typescript.md` | TypeScript-specific: Vitest + @vitest/coverage-v8, Istanbul reporter, Next.js notes |
| `README.md` | This file -- overview and usage guide |

## Related Skills

- [`testing-strategy`](../testing-strategy/SKILL.md) -- coverage philosophy (discovery tool vs target); this skill provides the mechanics
- [`testing-conventions` rule](../../rules/swe/testing-conventions.md) -- declarative constraints for test code
- [`test-engineer` agent](../../agents/test-engineer.md) -- pipeline agent for test authoring and execution
- [`verifier` agent](../../agents/verifier.md) -- loads this skill at its discretion for coverage assessment
