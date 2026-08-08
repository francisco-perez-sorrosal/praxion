# Command Crafting Skill

Skill for creating and managing slash commands — reusable, user-invoked prompts stored as Markdown files. Compatible with Claude Code and Cursor (see main repo README).

## When to Use

- Creating commands with proper frontmatter, arguments, and tool permissions
- Choosing between slash commands and skills for a given use case
- Debugging command behavior, argument substitution, and discovery issues
- Organizing commands with subdirectories and namespacing

## Activation

The skill activates automatically when the assistant detects tasks related to:

- Creating custom slash commands
- Debugging command behavior or argument handling
- Converting prompts to reusable commands

You can also trigger it explicitly by asking about slash commands or referencing it by name.

## Skill Contents

| File | Purpose |
|------|---------|
| `SKILL.md` | Core: structure, frontmatter (incl. description length and `argument-hint` semantics), substitution mechanisms, best practices |
| `references/arguments-and-context.md` | Worked examples: `$ARGUMENTS`/positional args, bang-prefixed bash, `@` file references, input-testing checklist |
| `references/runtime-and-permissions.md` | Discovery and live-reload timing, `Skill(...)` permission rules, debugging (incl. silent frontmatter parse failures) |
| `REFERENCE.md` | Extended examples: command patterns, real-world recipes, organization strategies |
| `README.md` | This file — overview and testing guide |

## Existing Commands in This Repository

Commands live in `commands/` (this repo) or `.claude/commands/` (consumer projects). Install as a plugin via `claude plugin install praxion@bit-agora`.

| Command | Description |
|---------|-------------|
| `/co` | Create a commit for staged (or all) changes |
| `/cop` | Create a commit and push to remote |
| `/create_worktree` | Create a new git worktree in `.trees/` |
| `/merge_worktree` | Merge a worktree back from `.trees/` |
| `/create-simple-python-prj` | Create a basic Python project with pixi or uv |

## Testing

### In Claude Code (CLI)

**Test command creation guidance:**

```bash
# Start a Claude Code session
claude

# Ask to create a command — the skill should activate automatically
> I want to create a slash command for running my test suite

# Or reference it explicitly
> Using the command-crafting skill, help me build a deploy command
```

**Test an existing command:**

```bash
# Invoke a command directly
/co fix typo in README

# Invoke with arguments
/create_worktree feature-auth
```

**Test command debugging:**

```bash
# Ask about argument issues
> My slash command isn't receiving arguments correctly, can you help?

# Ask about discovery
> Why doesn't my command show up in /help?
```

## Related Skills

- [`skill-crafting`](../skill-crafting/) — the spec for creating skills; commands can graduate to full skills when they outgrow a single file
- [`agent-crafting`](../agent-crafting/) — building custom agents; helps distinguish when to use a command vs an agent

### Validation Checklist

After creating or modifying commands, verify:

- [ ] YAML frontmatter parses under a real loader, not a field-presence grep (no tabs, proper `---` delimiters, quoted values that start with `[`/`{`/`>`/`|` or contain `: `)
- [ ] `description` is specific and action-oriented, and its length matches its consumer (one line when `disable-model-invocation: true`)
- [ ] `allowed-tools` is declared (avoids permission prompts)
- [ ] `argument-hint` lists every accepted argument and flag — or is absent entirely when the command takes none (never `""`)
- [ ] `argument-hint` is **quoted unconditionally** — unquoted `[foo]` loads as a YAML *list*, not a string, and unquoted `[a] [b]` fails to parse at all
- [ ] Command activates when invoked with `/command-name`
- [ ] Arguments substitute correctly (`$ARGUMENTS`, `$1`, `$2`)
- [ ] Bash `!` commands and file `@` references resolve properly
