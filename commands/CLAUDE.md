# Commands

Slash commands invocable during interactive sessions. Each `.md` file becomes a `/command-name` (or `/i-am:command-name` when namespaced by the plugin).

## Conventions

- Each command is a single `.md` file with YAML frontmatter
- Filename (minus `.md`) becomes the command name — choose concise, verb-first names
- `allowed-tools` frontmatter controls which tools the command can use
- Commands are user-invoked prompts, not autonomous agents — they execute in the main conversation context

## Registration

Commands use a directory glob in `.claude-plugin/plugin.json`: `"commands": ["./commands/"]`. New command files are discovered automatically — no manifest update needed.

## Modifying Commands

Load the `command-crafting` skill before creating or modifying commands. It covers frontmatter syntax, argument handling, and tool permissions.
