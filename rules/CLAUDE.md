---
core: true
load: always_on
install: symlink
---

# Rules

Contextual domain knowledge files loaded automatically based on relevance. Rules encode constraints and conventions — they are declarative, not procedural.

## Conventions

- Organized hierarchically by domain: `swe/` for software engineering, `writing/` for documentation, `ml/` for ML/AI training
- Further nesting for related rules (e.g., `swe/vcs/` for version control)
- Each rule is a `.md` file — rules without frontmatter load unconditionally at session start
- Add `paths:` YAML frontmatter to scope a rule to specific file patterns (loaded only when matching files are accessed)
  - Path-scoped rules inject **on Read, not Write/Edit** — an agent creating a new file without first reading a matching sibling misses that file type's conventions. Mitigated by a "read a sibling first" instruction in the `implementer`/`doc-engineer`/`test-engineer` prompts; symptom and full mitigation in `skills/rule-crafting/SKILL.md`.

## Token Budget

IMPORTANT: Rules without `paths:` frontmatter are **always loaded** — each costs tokens every session. The always-loaded budget (CLAUDE.md files + unconditional rules) is **25,000 tokens** — a failure-mode guardrail, not a target. Every always-loaded token must earn its attention share: applied in >30% of sessions, or unconditionally relevant. Scope with `paths:`, or move to a skill, anything not universally needed.

**Measure the always-loaded surface**: `wc -c` over the project + global `CLAUDE.md` files and every `rules/**/*.md` lacking `paths:`; divide bytes by 3.6 for a conservative token estimate (4.0 is more realistic for markdown). Re-measure when touching an always-loaded rule — a cached baseline decays with every commit.

## Installation

`install_claude.sh` symlinks rules to `~/.claude/rules/` for global availability. `install.sh cursor` exports rules to `.cursor/rules/` with frontmatter preserved.

## Modifying Rules

Load the `rule-crafting` skill before creating or modifying rules. It covers the rules-vs-skills-vs-CLAUDE.md decision model, path scoping, and content guidelines.
