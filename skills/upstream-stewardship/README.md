# Upstream Stewardship

Methodology for responsibly reporting bugs and contributing fixes to upstream open-source projects. Covers issue deduplication, sensitive information sanitization, issue template compliance, contribution etiquette, and responsible disclosure.

## When to Use

- Filing an issue against an upstream dependency
- Reviewing a bug report draft before sending to an external project
- Discovering a potential upstream bug during development
- Contributing a fix to an open-source dependency
- Performing responsible disclosure for a security vulnerability in a dependency

## Activation

Activates automatically when the task context matches upstream contribution patterns: filing upstream issues, reporting third-party bugs, contributing to OSS dependencies, or reviewing issue drafts for external projects. Reference explicitly with "upstream-stewardship skill" or "report upstream."

## Skill Contents

| File | Purpose |
|------|---------|
| `SKILL.md` | Core methodology: deduplication, sanitization pipeline, template compliance, issue draft structure, responsible disclosure, contribution etiquette |
| `references/sanitization-patterns.md` | Extended pattern catalog for stripping internal information from issue drafts |
| `references/issue-templates.md` | YAML form template parsing and built-in bug report structure for repos without templates |
| `references/contribution-workflow.md` | Fork-and-PR workflow for contributing fixes upstream |
| `references/secret-patterns.md` | Secret and credential pattern catalog for upstream bug report sanitization |

## Related Skills

- [`context-security-review`](../context-security-review/SKILL.md) -- credential pattern catalog for secret detection
