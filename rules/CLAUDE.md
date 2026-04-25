# Rules

Contextual domain knowledge files loaded automatically based on relevance. Rules encode constraints and conventions — they are declarative, not procedural.

## Conventions

- Organized hierarchically by domain: `swe/` for software engineering, `writing/` for documentation
- Further nesting for related rules (e.g., `swe/vcs/` for version control)
- Each rule is a `.md` file — rules without frontmatter load unconditionally at session start
- Add `paths:` YAML frontmatter to scope a rule to specific file patterns (loaded only when matching files are accessed)

## Token Budget

IMPORTANT: Rules without `paths:` frontmatter are **always loaded** — every new unconditional rule costs tokens on every session. The project budget for always-loaded content (CLAUDE.md files + rules) is **25,000 tokens** — a failure-mode guardrail, not a target. The principle is that every always-loaded token must earn its attention share (applied in >30% of sessions, or unconditionally relevant). Prefer `paths:` scoping or skills for content that isn't universally needed.

**Measure current always-loaded surface**: `wc -c` over the project + global `CLAUDE.md` files plus every rule under `rules/**/*.md` whose frontmatter lacks `paths:`; divide bytes by 3.6 for a conservative token estimate (1/4.0 is a more realistic Claude-tokenizer estimate for markdown). Anyone touching an always-loaded rule should re-measure rather than rely on a baseline number that decays with every commit.

## Installation

`install_claude.sh` symlinks rules to `~/.claude/rules/` for global availability. `install.sh cursor` exports rules to `.cursor/rules/` with frontmatter preserved.

## Modifying Rules

Load the `rule-crafting` skill before creating or modifying rules. It covers the rules-vs-skills-vs-CLAUDE.md decision model, path scoping, and content guidelines.
