---
name: praxion-command-co
description: 'Create a commit for staged (or all) changes'
---

# /co

This is a Codex command-skill wrapper for a Praxion slash command.

Before running this workflow, read the canonical command definition at `/opt/praxion/commands/co.md` and follow it as the authoritative source.
Do not treat this wrapper as a fork; it exists only to expose Praxion commands through Codex's documented skill activation surface.

Preserve the original slash-command semantics:

- Invoke this workflow when the user asks for `/co` or names `praxion-command-co`.
- Treat any user text after the command name as `$ARGUMENTS`.
- Derive `$1`, `$2`, and later positional arguments by splitting `$ARGUMENTS` on shell-style whitespace.
- Treat Claude `allowed-tools` frontmatter as the command's intended tool boundary; in Codex, use available equivalent tools and respect the active sandbox and approval policy.
- Interpret command-body `!` shell snippets and `@` file references as instructions to gather that context with Codex tools before executing the workflow.
- Keep all substantive behavior in the canonical command file; update `commands/*.md` in Praxion when command behavior changes.

Argument hint: `[message]`
