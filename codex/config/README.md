# Codex Config

Codex-specific adapter sources live here. Shared Praxion artifacts remain
canonical at the repository root; files in this directory generate or install
Codex-native surfaces from those sources.

## Agent Export

`export-codex-agents.py` converts `agents/*.md` into Codex custom-agent TOML
files under a target `.codex/agents/` directory.

The exporter preserves:

- `name`
- `description`
- a thin `developer_instructions` wrapper that tells Codex to read the
  canonical `agents/<name>.md` file before acting

It intentionally does not translate Claude-specific tool, hook, permission,
memory, or model frontmatter yet. Those fields have different Codex semantics
and need explicit design instead of lossy copying.

## Skill Export

`export-codex-skills.py` converts `skills/*/SKILL.md` into Codex skill wrappers
under a target `.agents/skills/` directory.

The exporter preserves:

- the canonical skill name
- a compact description that fits Codex startup limits
- a thin wrapper body that points back to `skills/<name>/SKILL.md`

It intentionally does not copy canonical skill bodies into the wrapper. Codex
loads the wrapper at startup and can read the canonical skill on activation.
