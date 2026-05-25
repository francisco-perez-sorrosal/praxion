---
name: command-crafting
description: >
  Creating and managing slash commands (/commands, Claude Code commands): reusable
  user-invoked prompts with arguments, tool permissions, dynamic context (!, @,
  argument-hint). Triggers: creating custom slash commands, debugging command
  behavior, fixing argument substitution, converting prompts to commands,
  organizing commands with namespacing.
allowed-tools: [Read, Write, Edit, Glob, Grep, Bash]
compatibility: Claude Code
staleness_sensitive_sections:
  - "Command Files vs Skill Directories"
  - "Discovery and Live Reload"
  - "Permission Management"
---

# Slash Commands

Guide for creating effective, reusable slash commands.

> **Commands are skills now (Claude Code).** A file at `.claude/commands/deploy.md` and a skill at `.claude/skills/deploy/SKILL.md` both create `/deploy` and behave identically; on a name clash the skill wins. Legacy `commands/*.md` files keep working and accept the **same frontmatter** as skills — they are the simpler, single-file layout. Anthropic recommends the skill-directory form for *new* work that needs supporting files or auto-invocation. **Praxion deliberately keeps its slash commands as `commands/*.md`** — that directory is the assistant-agnostic source `install.sh` exports to Cursor and Codex, which do not share Claude Code's merge. See [Command Files vs Skill Directories](#command-files-vs-skill-directories).

**Satellite files** (loaded on-demand):
- [../skill-crafting/references/context-engineering-foundations.md](../skill-crafting/references/context-engineering-foundations.md) -- the shared "why" (a command/skill description costs listing budget every session)
- [../skill-crafting/SKILL.md](../skill-crafting/SKILL.md) -- since commands are skills, skill-crafting holds the shared mechanics (full frontmatter superset, progressive disclosure, lifecycle)
- [REFERENCE.md](REFERENCE.md) -- command patterns, full examples, organization strategies
- [../skill-crafting/references/artifact-naming.md](../skill-crafting/references/artifact-naming.md) -- naming conventions for all artifact types

## What Are Slash Commands

**Slash commands** are user-invoked prompts stored as Markdown files that you trigger with `/` prefix during interactive sessions.

- User-initiated (explicitly type `/command`)
- Single `.md` file per command
- Support arguments (`$ARGUMENTS`, `$1`, `$2`) and dynamic substitution
- Can execute bash commands (`!`) and reference files (`@`)
- Project or personal scope

**Invocation**: `/<command-name> [arguments]`

## File Locations

**Project commands** (shared with team):
```
.claude/commands/<command-name>.md
```

**Personal commands** (across all projects):
```
~/.claude/commands/<command-name>.md
```

**Namespacing with subdirectories**:
```
.claude/commands/
├── git/
│   ├── commit.md      → /commit (shows "project:git")
│   └── merge.md       → /merge (shows "project:git")
└── docs/
    └── generate.md    → /generate (shows "project:docs")
```

## Naming Convention

- Default to **kebab-case**: `create-worktree.md`, `add-rules.md`
- **Abbreviations** acceptable for high-frequency commands: `co.md`, `cop.md`
- The filename (minus `.md`) becomes the slash command name: `create-worktree.md` → `/create-worktree`

## Command Structure

```markdown
---
description: Brief description shown in /help
argument-hint: [expected] [arguments]
allowed-tools: [Bash(git:*), Read, Grep]
model: haiku
---

Your command content here
```

## Frontmatter Fields

All frontmatter is optional. Because command files are skills, they accept the **full Claude Code skill frontmatter superset** — the common fields are below; see [skill-crafting/references/schema.md](../skill-crafting/references/schema.md#claude-code-frontmatter-superset) for the complete set.

| Field | Purpose | Example |
|-------|---------|---------|
| `description` | Shown in `/help`; used by Claude to decide auto-invocation | "Create a git commit" |
| `allowed-tools` | Pre-approve tools (no permission prompt while active) | `Bash(git:*), Read, Grep` |
| `argument-hint` | Show expected arguments in autocomplete | `[message]` or `[pr-number] [priority]` |
| `model` | Model while active (`haiku`/`sonnet`/`opus`/`inherit`) | `haiku` |
| `disable-model-invocation` | `true` = only the user can invoke; keeps the description out of model context | `true` |
| `user-invocable` | `false` = hide from the `/` menu (background knowledge only) | `false` |

> `allowed-tools` **does not restrict** — it pre-approves. Every tool stays callable, governed by your permission settings. Use deny rules in `/permissions` to actually block a tool.

## Argument Handling

### All Arguments (`$ARGUMENTS`)

Captures all arguments as a single string:

```markdown
---
argument-hint: [issue-details]
description: Fix issue with provided details
---

Fix issue: $ARGUMENTS

Follow our coding standards and write tests.
```

**Usage**: `/fix-issue 123 high-priority database`
**Result**: `$ARGUMENTS` = `"123 high-priority database"`

### Positional Arguments (`$1`, `$2`, etc.)

Access specific arguments by position:

```markdown
---
argument-hint: [pr-number] [priority] [assignee]
description: Review pull request
---

Review PR #$1 with priority $2 and assign to $3.

Focus on:
- Security vulnerabilities
- Performance issues
- Code style violations
```

**Usage**: `/review-pr 456 high alice`
**Result**: `$1="456"`, `$2="high"`, `$3="alice"`

## Advanced Features

### Bash Command Execution

Use `!` prefix to execute bash commands before the command runs:

```markdown
---
allowed-tools: Bash(git:*), Bash(find:*)
---

## Current Status

!`git status`

## Recent Changes

!`git log --oneline -5`

## Modified Files

!`git diff --name-only`

Review the above changes and create a commit message.
```

### File References

Use `@` prefix to include file contents (a command-file feature carried over from the legacy form; the merged skills docs emphasize `` !`cmd` `` injection and `${CLAUDE_SKILL_DIR}` instead — prefer `!` for new work):

```markdown
---
allowed-tools: Read
---

Review @src/components/Button.tsx for accessibility issues.

Compare:
- Old: @src/old-version.js
- New: @src/new-version.js

Provide a summary of changes.
```

## Command Files vs Skill Directories
<!-- last-verified: 2026-05-25 -->

Since the merge, this is **not** "commands vs skills" (one system) but a choice of *layout* for the same thing. Both produce `/name`; both load the rendered body into the conversation.

| | Command file (`commands/<name>.md`) | Skill directory (`skills/<name>/SKILL.md`) |
|---|---|---|
| **Layout** | Single `.md` file | Directory + optional `scripts/`, `references/`, `assets/` |
| **Supporting files** | No | Yes (progressive disclosure) |
| **Cross-tool portability** | Read by Claude Code; exported to Cursor + Codex by `install.sh` | Read by Claude Code; the Agent Skills standard is increasingly cross-tool |
| **Best for** | A focused, single-file, user-invoked workflow | A workflow needing bundled scripts/templates, or knowledge that should auto-load |

**Choosing:** reach for a **command file** when the workflow is one self-contained prompt and must stay portable across assistants (Praxion's default — see the merged-model note at the top). Reach for a **skill directory** when you need supporting files, want Claude to auto-load it by relevance, or it is reference knowledge rather than a user action. When a command file outgrows a single file, promote it to a skill directory.

## Best Practices

- **Clear descriptions**: Be specific -- "Review code for security vulnerabilities" not "Helps with code"
- **Always declare `allowed-tools`**: Without it, Claude prompts for permission every time
- **Use `argument-hint`**: Show users what arguments are expected
- **Provide context via `!` commands**: Include git status, project structure, recent changes
- **Test with various inputs**: no arguments, one argument, multiple, special characters
- **Don't duplicate rule content**: Commands define *process* (what to do); rules provide *knowledge* (conventions, constraints). If a relevant rule exists, Claude loads it automatically when the command runs — don't inline that knowledge in the command body
- **Guard side-effecting commands with `disable-model-invocation: true`**: a command that commits, pushes, releases, deploys, or posts externally should not be auto-invokable by Claude. Setting it also drops the description from the always-loaded listing budget (see [context-engineering foundations](../skill-crafting/references/context-engineering-foundations.md))

## Common Mistakes

- **Missing descriptions** -- commands without `description` are invisible in `/help`
- **No tool restrictions** -- without `allowed-tools`, Claude prompts every time
- **Name conflicts** -- project commands override personal ones with the same name; use subdirectories
- **Overloaded commands** -- slash commands work best for focused tasks; use Skills for complex workflows
- **Untested arguments** -- `$ARGUMENTS` might be empty; test and handle missing values gracefully
- **Inlining rule knowledge** -- if conventions or constraints already exist in a rule file, don't copy them into the command; rules load automatically by semantic relevance when the command executes
- **Discovery timing differs by location** — see [Discovery and Live Reload](#discovery-and-live-reload).

## Discovery and Live Reload
<!-- last-verified: 2026-05-25 -->

Discovery timing depends on *where* the command/skill lives:

- **Project / personal locations** (`.claude/skills/`, `~/.claude/skills/`, and `.claude/commands/` files) have **live change detection** — edits, adds, and removals take effect within the session, no restart. Creating a *new top-level* skills directory that did not exist at session start still requires a restart (so it can be watched).
- **Plugin components** (Praxion's `commands/`, `agents/`) are scanned once at session start and cached for the session. A command added mid-session — or installed via `bash install.sh` against a running session — is invisible until a fresh session. Symptom: `/my-new-command` reports "unknown command" despite a valid file at the right path. There is no plugin hot-reload — restart the session.

(Subagents always require a restart on disk edits; the `/agents` interface takes effect immediately.)

## Permission Management
<!-- last-verified: 2026-05-25 -->

Since commands are skills, Claude's invocation access is governed by `Skill(...)` permission rules (the older `SlashCommand:/name:*` form predates the merge):

```text
# In /permissions
Skill(co)          # allow exactly /co
Skill(review-pr *) # allow /review-pr with any arguments
Skill(deploy *)    # (as a deny rule) block /deploy
Skill              # (as a deny rule) Claude can invoke no skills/commands
```

To stop Claude from auto-invoking a *specific* command (e.g. a side-effecting one), set its frontmatter instead — this also removes its description from model context:

```markdown
---
disable-model-invocation: true
---
```

## Debugging

```bash
# List all commands
ls -R .claude/commands/
ls -R ~/.claude/commands/

# View command content
cat .claude/commands/my-command.md
```

Within Claude Code, the `Read` and `Glob` tools can also inspect command files directly.

Verify: proper `---` delimiters, valid YAML, correct field names, expected argument substitution.

## Creation Workflow

1. **Define** -- identify the repeated prompt or workflow to automate
2. **Create** -- write the `.md` file with frontmatter and content
3. **Test** -- invoke with `/command` and verify behavior with various inputs
4. **Iterate** -- refine based on output; adjust tools, arguments, context
5. **Share** -- commit to `.claude/commands/` for team use

## Resources

- [Official Documentation](https://code.claude.com/docs/en/skills) (the `/slash-commands` page now redirects here — commands are documented as skills)
- Extended examples: See [REFERENCE.md](REFERENCE.md) for command patterns and organization strategies
