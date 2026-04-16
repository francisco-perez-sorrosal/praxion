# Skill Crafting Skill

Meta-skill for creating and optimizing Agent Skills — the open format for extending AI agents with specialized knowledge and workflows. Compatible with Claude Code, Cursor, and other Agent Skills–compatible tools.

## When to Use

- Creating a new skill from scratch
- Converting memory files or repeated prompts into reusable skills
- Debugging why a skill isn't activating or loading correctly
- Reviewing skill structure, naming, or description quality
- Understanding progressive disclosure, frontmatter fields, or the spec

For the official specification, see [agentskills.io](https://agentskills.io).

## Activation

The skill activates automatically when the agent detects tasks related to:

- Creating, authoring, or structuring skills
- Skill activation or discovery issues
- Questions about `SKILL.md` format, frontmatter, or best practices

Trigger explicitly by asking about "agent skills," "creating a skill," or referencing this skill by name.

## Skill Contents

| File | Purpose |
|------|---------|
| `SKILL.md` | Core reference: creation process, anatomy, progressive disclosure, principles, portability, checklist |
| `README.md` | This file — overview and usage guide |
| `references/cross-agent-portability.md` | Adopter list, discovery paths, portable vs. tool-specific |
| `references/artifact-naming.md` | Naming conventions for skills, agents, commands, rules |
| `references/content-and-development.md` | Content type selection, feedback loops, evaluation-driven development |
| `references/output-patterns.md` | Template and examples patterns for skill output |
| `references/workflows.md` | Sequential and conditional workflow patterns |
| `references/skill-categories.md` | Nine skill archetype categories from Anthropic's internal practice |
| `references/plugin-and-troubleshooting.md` | Plugin mechanics, anti-patterns, recommended hooks, persistent state, troubleshooting |
| `scripts/init_skill.py` | Scaffold a new skill directory from template |
| `scripts/package_skill.py` | Create a distributable .skill archive (validates first) |
| `scripts/validate.py` | Quick validation of skill structure and frontmatter |
| `scripts/validate_references.py` | Validate intra-repo Markdown cross-references (paths, anchors) across skills/agents/rules/commands/docs. Stdlib-only. `--file` / `--all` modes; exit 0 clean, 1 FAIL, 2 error. Per-class severity: FAIL/WARN/OK. Ignore via inline `<!-- validate-references:ignore -->` or frontmatter `validate-references: off` |

## Quick Start

1. **Load the skill**: reference `skill-crafting` when starting skill authoring work
2. **Understand the domain**: describe the skill's use cases with concrete examples
3. **Plan contents**: identify what scripts, references, and assets to include
4. **Create the skill**: `skill-name/SKILL.md` with `name` and `description` frontmatter
5. **Write content**: instructions, then bundle resources as needed
6. **Validate**: run `scripts/validate.py` and the deployment checklist
7. **Iterate**: test with real tasks using the author-tester workflow

## Related Skills

- [`agent-crafting`](../agent-crafting/) — building custom agents that consume skills via the `skills` frontmatter field
- [`command-crafting`](../command-crafting/) — creating slash commands; understanding the distinction between commands and skills

## Testing

**Test skill creation guidance:**

```
# Ask about creating a skill — the skill should activate automatically
> I want to create a skill for reviewing pull requests

# Or reference it explicitly
> Using the skill-crafting skill, help me structure a new data-analysis skill
```

**Test troubleshooting:**

```
> My custom skill isn't activating when I mention PDF processing
> What's wrong with this SKILL.md frontmatter?
```

**Validate a skill you've built:**

```bash
# Run the validation script on a skill directory
python skills/skill-crafting/scripts/validate.py ./my-skill

# Or manually check against the checklist in SKILL.md
```
