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
- Each rule is a `.md` file — `paths:` YAML frontmatter scopes it to specific file patterns (loaded only when a matching file is read); without `paths:` it always loads at session start
  - Path-scoped rules inject **on Read, not Write/Edit** — an agent creating a new file without first reading a matching sibling misses that file type's conventions. Mitigated by a "read a sibling first" instruction in the `implementer`/`doc-engineer`/`test-engineer` prompts; symptom and full mitigation in `skills/rule-crafting/SKILL.md`.

## Token Budget

IMPORTANT: Rules without `paths:` frontmatter are **always loaded** — each costs tokens every session. The always-loaded budget (CLAUDE.md files + unconditional rules) is **25,000 tokens** — a failure-mode guardrail, not a target. Every always-loaded token must earn its attention share: applied in >30% of sessions, or unconditionally relevant. Scope with `paths:`, or move to a skill, anything not universally needed.

**Measure with `scripts/measure_token_budget.py`, never by hand.** The file set, the ceiling and the fallback all live there, and it counts real tokens when `ANTHROPIC_API_KEY` is set. That script is the authoritative basis — any site restating a divisor is a copy that will drift. Re-measure when touching an always-loaded rule. Measurement history (why the file set excludes catalog `README.md`s, why a divisor is not a measurement): `skills/rule-crafting/SKILL.md § Token budget measurement history`.

## Installation

`install_claude.sh` symlinks rules to `~/.claude/rules/` for global availability. `install.sh cursor` exports rules to `.cursor/rules/` with frontmatter preserved.

## Modifying Rules

Load the `rule-crafting` skill before creating or modifying rules. It covers the rules-vs-skills-vs-CLAUDE.md decision model, path scoping, and content guidelines.
