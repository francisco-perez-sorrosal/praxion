# upstream-stewardship

Methodology for responsibly reporting bugs and contributing fixes to upstream open-source projects. Triggered by the `/report-upstream` command or when agents discover potential upstream bugs during development.

## Files

| File | Purpose |
|------|---------|
| `SKILL.md` | Core methodology: deduplication, sanitization, template compliance, etiquette, responsible disclosure |
| `references/sanitization-patterns.md` | Extended pattern catalog for stripping internal information from issue drafts |
| `references/issue-templates.md` | YAML form template parsing and built-in bug report structure |
| `references/contribution-workflow.md` | Fork-and-PR workflow for contributing fixes upstream |

## Related

- `/report-upstream` command — user-facing trigger for the filing workflow
- `.ai-state/UPSTREAM_ISSUES.md` — persistent tracker of filed upstream issues
- `context-security-review` skill — credential pattern catalog referenced by sanitization pipeline
