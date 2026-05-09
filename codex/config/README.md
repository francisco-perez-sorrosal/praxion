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
  canonical Praxion agent file before acting

It intentionally does not translate Claude-specific tool, hook, permission,
memory, or model frontmatter yet. Those fields have different Codex semantics
and need explicit design instead of lossy copying.

## Skill Export

`export-codex-skills.py` converts `skills/*/SKILL.md` into Codex skill wrappers
under a target `.agents/skills/` directory.

The exporter preserves:

- the canonical skill name
- the full canonical description
- a thin wrapper body that points back to the canonical Praxion skill file

It intentionally does not copy canonical skill bodies into the wrapper. Codex
loads the wrapper at startup and can read the canonical skill on activation.

## Rules Bridge

`export-codex-rules-bridge.py` generates the Praxion-managed Codex rules bridge
under a target project's `.codex/` directory.

Generated surfaces:

- `.codex/praxion/rules_manifest.json` -- canonical rule index derived from
  `rules/**/*.md`
- `.codex/praxion/rules_lookup.py` -- helper for matching always-on,
  prompt-scoped, and path-scoped Praxion rules
- `.codex/hooks/praxion-session-start.py` -- injects always-on Praxion rule
  context at session start
- `.codex/hooks/praxion-user-prompt-submit.py` -- routes prompt-matched rules
- `.codex/hooks/praxion-pre-tool-use.py` -- routes file-scoped rules before
  read/edit/write-style tool activity
- `.codex/praxion/hook_registrations.json` -- expected Praxion hook
  registrations for merge/check logic

This bridge intentionally does **not** export semantic Praxion Markdown rules
into `.codex/rules/`. Native Codex `.rules` remain reserved for command
approval / sandbox policy semantics.

Rule pickup is dynamic: every exporter run rescans `rules/**/*.md`. The bridge
does not depend on a hardcoded Python allowlist for new rules. Automatic Codex
classification is derived from the canonical rule source, with optional
rule-local `codex:` frontmatter for exceptions:

```yaml
---
codex:
  portability: portable
  load: always_on
---
```

## Config and Hook Registration

`manage-codex-rules-bridge.py` installs, checks, and uninstalls the
Praxion-managed Codex rule bridge state in a target project:

- ensures `.codex/config.toml` has `hooks = true` and removes deprecated
  `codex_hooks` entries during install
- merges Praxion-managed hook registrations into `.codex/hooks.json`
- preserves non-Praxion Codex config and hook entries
- removes only Praxion-managed entries during uninstall

All Praxion-managed rule-bridge assets are prefixed `praxion-` or live under
`.codex/praxion/` so ownership remains explicit and uninstall stays surgical.
