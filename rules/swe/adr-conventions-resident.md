---
core: true
load: always_on
install: symlink
resident_of: rules/swe/adr-conventions.md
codex:
  load: exclude
---
## ADR Conventions
Architecture Decision Records live in `.ai-state/decisions/` as Markdown files with YAML frontmatter. They persist beyond `.ai-work/` cleanup and are committed to git.
