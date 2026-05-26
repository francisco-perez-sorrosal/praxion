# Documentation Management

Writing, maintaining, and validating project-facing documentation. Covers README authoring, cross-reference integrity, catalog maintenance, staleness detection, Mermaid diagrams, and the Diátaxis mode framework for architecture documents.

## When to Use

- Creating or refining README.md files (project, catalog, component)
- Maintaining catalog READMEs that list skills, agents, commands, or rules
- Validating cross-references in documentation (paths, links, counts, names)
- Detecting stale documentation after codebase changes
- Auditing documentation quality or freshness across a project
- Authoring Mermaid diagrams in project documentation
- Applying Diátaxis modes to architecture documentation

## Activation

Activates automatically when the task context matches documentation tasks: README writing, documentation review, catalog maintenance, cross-reference validation, or freshness assessment. Reference explicitly with "doc-management skill" or "documentation management skill."

## Skill Contents

| File | Purpose |
|------|---------|
| `SKILL.md` | Core principles, README authoring workflow, cross-reference validation, catalog maintenance, freshness indicators, checklist |
| `references/cross-reference-patterns.md` | Detailed cross-reference validation procedures, catalog sync patterns, common drift scenarios, automated checking |
| `references/documentation-types.md` | Per-type guidelines for README, architecture, changelog, contributing, and API documentation |
| `references/diagram-conventions.md` | Mermaid diagram creation, decomposition methodology, type recipes, styling guide |
| `references/advanced-markdown-patterns.md` | `<details>`/`<summary>`, GitHub Alerts, footnotes, anchor links — decision rules, syntax, and scope constraints |
| `references/diataxis-modes.md` | Diátaxis mode rationale (Tutorial, How-to, Reference, Explanation), common pitfalls, and worked examples |
| `references/doc-manifest-schema.md` | `doc_manifest.yaml` schema for the dashboard's documentation discovery spine |
| `assets/ARCHITECTURE_GUIDE_TEMPLATE.md` | 8-section template for developer-facing `docs/architecture.md` navigation guide |

## Related Skills

- [`readme-style` rule](../../rules/writing/readme-style.md) — documentation conventions (what to follow: writing style, structural integrity, naming)
- [`code-review`](../code-review/SKILL.md) — after a code review identifies added, removed, or renamed files, use this skill to update affected documentation
- [`web-ui-design`](../web-ui-design/SKILL.md) — visual design canon for HTML share-out artifacts and diagram-heavy docs
