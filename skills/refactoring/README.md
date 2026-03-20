# Refactoring Skill

Pragmatic refactoring practices emphasizing modularity, low coupling, high cohesion, and incremental improvement.

## When to Use

- Restructuring code or improving design
- Reducing coupling between modules
- Organizing codebases for better maintainability
- Extracting modules or introducing abstractions
- Eliminating code smells (god objects, feature envy, primitive obsession)
- Deciding whether to extract modules, add abstractions, or split packages

## Activation

The skill activates automatically when the agent detects refactoring tasks: restructuring code, improving design, reducing coupling, extracting modules, or discussing refactoring patterns and code organization.

Trigger explicitly by mentioning "refactoring skill" or referencing it by name.

## Skill Contents

| File | Purpose |
|------|---------|
| `SKILL.md` | Core reference: four pillars, workflow, decision framework, anti-patterns, verification checklist |
| `references/patterns.md` | Detailed refactoring patterns and common scenarios with full code examples |
| `README.md` | This file — overview and usage guide |

## Related Skills

- [`python-development`](../python-development/) — Python-specific patterns used in refactoring (Protocols, dataclasses, type hints)
- [`software-planning`](../software-planning/) — embedding refactoring phases within structured plans
- [`code-review`](../code-review/) — structured post-refactoring review with finding classification and report templates
