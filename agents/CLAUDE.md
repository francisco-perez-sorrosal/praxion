# Agents

Agent definitions for the software development pipeline. Each agent runs in its own context window as an autonomous subprocess.

## Conventions

- Each agent is a single `.md` file with YAML frontmatter (`description`, `tools`, `skills`, optional `model`, `color`)
- Flat structure — no subdirectories; one file per agent
- `description` drives delegation — Claude decides when to spawn based on this field, so it must be precise and differentiated
- Agents cannot spawn other agents; they can only recommend spawning in their output
- Skills listed in the `skills:` frontmatter are injected into the agent's context — agents do not inherit skills from the parent

## Registration

After adding or removing an agent, update `.claude-plugin/plugin.json` under the `agents` array. Agents require **explicit file paths** — directory globs are not supported.

## Modifying Agents

Load the `agent-crafting` skill before creating or modifying agent definitions. It covers prompt structure, tool selection, and frontmatter conventions.

## Pipeline Context

Agents communicate through shared documents in `.ai-work/` (ephemeral) and `.ai-state/` (persistent). See the `swe-agent-coordination-protocol` rule for pipeline ordering and boundary discipline.
