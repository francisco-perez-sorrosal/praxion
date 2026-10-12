# Rules

Contextual domain knowledge files loaded automatically based on relevance. Rules encode constraints and conventions — they are declarative, not procedural.

This file is the rules tree's directory guide, not a rule: the installer does not link it into `~/.claude/rules/`, and Claude Code loads it on demand (as a nested `CLAUDE.md`) when a session touches a file under `rules/`.

## Conventions

- Organized hierarchically by domain: `swe/` for software engineering, `writing/` for documentation, `ml/` for ML/AI training
- Further nesting for related rules (e.g., `swe/vcs/` for version control)
- Each rule is a `.md` file — `paths:` YAML frontmatter scopes it to specific file patterns (loaded when a matching file is read, written or edited); without `paths:` it always loads at session start
  - Claude Code (2.1.288 and later) loads path-scoped rules on Read, Write and Edit, and on single-file Bash reads. A brand-new file is still composed inside its first Write, before the rule arrives, so the "read a sibling first" instruction in the `implementer`/`doc-engineer`/`test-engineer` prompts stays; it also covers Cursor, which ignores rule globs, and Codex, which routes path rules through its own bridge. Detail in `skills/rule-crafting/SKILL.md`.

## Token Budget

IMPORTANT: Rules without `paths:` frontmatter are **always loaded** — each costs tokens every session. The always-loaded budget (CLAUDE.md files + unconditional rules) is **25,000 tokens** — a failure-mode guardrail, not a target. Every always-loaded token must earn its attention share: applied in >30% of sessions, or unconditionally relevant. Scope with `paths:`, or move to a skill, anything not universally needed.

**Measure with `scripts/measure_token_budget.py`, never by hand.** The file set, the ceiling and the fallback all live there, and it counts real tokens when `ANTHROPIC_API_KEY` is set. That script is the authoritative basis — any site restating a divisor is a copy that will drift. Re-measure when touching an always-loaded rule. Every reading names its tokenizer (`ruler`); the gate keeps the ruler its baseline was recorded on, and `--model <id>` gives a report-only reading on a current model's tokenizer, which counts the same text higher. Measurement history (why the file set excludes catalog `README.md`s, why a divisor is not a measurement): `skills/rule-crafting/SKILL.md § Token budget measurement history`.

## Installation

`install_claude.sh` symlinks rules to `~/.claude/rules/` for global availability, driven by `rules/_manifest.yaml` (directory guides such as this file are not rules and are not linked). `install.sh cursor` exports rules to `.cursor/rules/`, replacing each rule's frontmatter with Cursor's `description` and `alwaysApply: false`; `paths:` globs are not carried over.

## Modifying Rules

Load the `rule-crafting` skill before creating or modifying rules. It covers the rules-vs-skills-vs-CLAUDE.md decision model, path scoping, and content guidelines.
