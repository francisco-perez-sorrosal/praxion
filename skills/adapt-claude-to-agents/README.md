# adapt-claude-to-agents

Generate or refresh a project-local `AGENTS.md.tmpl` from a root `CLAUDE.md`
for Praxion Codex onboarding.

## When to Use

Use this skill when:

- onboarding a Praxion-managed project with `install.sh codex`
- a project is missing `AGENTS.md.tmpl` and needs an initial Codex template
- refreshing a previously generated Codex project template from updated
  `CLAUDE.md` guidance

## Skill Contents

- `SKILL.md` -- workflow and guardrails for Claude-to-Agents adaptation
- `scripts/claude_to_agents.py` -- deterministic generator used by
  `install_codex.sh`
