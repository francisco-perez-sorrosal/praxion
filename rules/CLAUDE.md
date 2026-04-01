# Rules

Contextual domain knowledge files loaded automatically based on relevance. Rules encode constraints and conventions — they are declarative, not procedural.

## Conventions

- Organized hierarchically by domain: `swe/` for software engineering, `writing/` for documentation
- Further nesting for related rules (e.g., `swe/vcs/` for version control)
- Each rule is a `.md` file — rules without frontmatter load unconditionally at session start
- Add `paths:` YAML frontmatter to scope a rule to specific file patterns (loaded only when matching files are accessed)

## Token Budget

IMPORTANT: Rules without `paths:` frontmatter are **always loaded** — every new unconditional rule costs tokens on every session. The project budget for always-loaded content (CLAUDE.md files + rules) is 8,500 tokens. Prefer `paths:` scoping or skills for content that isn't universally needed.

## Installation

`install_claude.sh` symlinks rules to `~/.claude/rules/` for global availability. `install.sh cursor` exports rules to `.cursor/rules/` with frontmatter preserved.

## Modifying Rules

Load the `rule-crafting` skill before creating or modifying rules. It covers the rules-vs-skills-vs-CLAUDE.md decision model, path scoping, and content guidelines.
