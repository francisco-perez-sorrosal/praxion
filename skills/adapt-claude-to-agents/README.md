# adapt-claude-to-agents

Generate or refresh a project-local `AGENTS.md.tmpl` from a root `CLAUDE.md`
for Praxion Codex onboarding. Removes Claude-only operational details and
preserves portable project guidance so the result can merge cleanly with
Praxion's shared Codex baseline.

## When to Use

- Onboarding a Praxion-managed project with `install.sh codex`
- A project is missing `AGENTS.md.tmpl` and needs an initial Codex template
- Refreshing a previously generated Codex template after `CLAUDE.md` changes

## Activation

Auto-triggered when the task involves generating or refreshing `AGENTS.md.tmpl`
or when `install.sh codex` needs a Codex source template. Also invoke manually
when adapting a Claude-specific project config for Codex consumption.

## Skill Contents

- `SKILL.md` — workflow, guardrails, and Codex portability contract
- `scripts/claude_to_agents.py` — deterministic generator called by `install.sh codex`

## Related Skills

- [`rule-crafting`](../rule-crafting/SKILL.md) — when authoring rules that need Codex portability annotations
