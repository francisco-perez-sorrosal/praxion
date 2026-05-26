---
name: adapt-claude-to-agents
description: >
  Generate or refresh a project-local AGENTS.md.tmpl for Praxion Codex onboarding
  from a project's root CLAUDE.md: removes Claude-only operational details, preserves
  portable project guidance. Triggers: install.sh codex needs a Codex
  source template, refreshing a previously generated Codex project template.
allowed-tools: [Read, Write, Edit, Bash]
compatibility: Codex, Claude Code, Cursor, and installer-driven CLI workflows.
---

# Adapt Claude To Agents

Generate a project-local Codex template source from a project's root
`CLAUDE.md`. The output is `AGENTS.md.tmpl`, not the final compiled
`AGENTS.md`.

## Workflow

1. Read the project's root `CLAUDE.md`.
2. Preserve portable project guidance: project description, repository layout,
   build/test commands, verification paths, and cross-project conventions.
3. Remove or rewrite Claude-only operational details that do not belong in a
   Codex project template.
4. Write a reviewable `AGENTS.md.tmpl` that can be merged with Praxion's shared
   Codex baseline.

## Bundled Script

Use `scripts/claude_to_agents.py` for deterministic generation during
`install.sh codex`. The installer may call the script directly; the output still
follows this skill's workflow and contract.

## Guardrails

- Treat `AGENTS.md.tmpl` as project-local source.
- Treat final `AGENTS.md` as compiled output.
- Do not copy Praxion's shared Codex baseline into the generated project
  template.
- Favor conservative removal over speculative rewriting when Claude-only
  details are ambiguous.

## Related Skills

- [`rule-crafting`](../rule-crafting/SKILL.md) — when authoring new rules that need Codex portability annotations.
