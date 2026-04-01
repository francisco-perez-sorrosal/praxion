# Skills

Reusable skill modules following the Agent Skills standard. Each skill is a self-contained directory with progressive disclosure: metadata at startup, full content on activation, reference files on demand.

## Conventions

- Each skill is a subdirectory containing at minimum a `SKILL.md` with YAML frontmatter
- Optional subdirectories: `references/` (detailed docs), `scripts/` (tooling), `contexts/` (context-specific content)
- Most skills also have a `README.md` for human-facing quick reference
- `SKILL.md` target: under 500 lines. Move procedural depth to `references/` files
- Reference file header: `# Title` + one-line description + recommended back-link to `../SKILL.md` (not yet universal — ~40% of existing references include it)

## Progressive Disclosure Model

1. **Startup**: Only frontmatter `name` + `description` loaded (~1 line per skill, ~450 tokens total)
2. **Activation**: Full `SKILL.md` body loaded when the skill is triggered or contextually relevant
3. **On demand**: Reference files loaded only when Claude reads them explicitly

## Registration

Skills use a directory glob in `.claude-plugin/plugin.json`: `"skills": ["./skills/"]`. New skill directories are discovered automatically — no manifest update needed.

## Validation

Run `skills/skill-crafting/scripts/validate.py` after modifying any skill to check frontmatter correctness and structural integrity.

## Modifying Skills

Load the `skill-crafting` skill before creating or modifying skills. It covers activation triggers, content structure, and the init/validate/package workflow.
