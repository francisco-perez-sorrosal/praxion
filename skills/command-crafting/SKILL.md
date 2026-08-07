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
- [references/arguments-and-context.md](references/arguments-and-context.md) -- worked examples for `$ARGUMENTS`/positional args, bang-prefixed bash, `@` file references, input testing
- [references/runtime-and-permissions.md](references/runtime-and-permissions.md) -- discovery/live-reload timing, `Skill(...)` permission rules, debugging a command that does not appear or does not parse
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
argument-hint: "[expected] [arguments]"
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
| `argument-hint` | Show expected arguments in autocomplete; **always quote** (see [below](#argument-hint-and-the-no-argument-case)) | `"[message]"` or `"[pr-number] [priority]"` |
| `model` | Model while active (`haiku`/`sonnet`/`opus`/`inherit`) | `haiku` |
| `disable-model-invocation` | `true` = only the user can invoke; keeps the description out of model context | `true` |
| `user-invocable` | `false` = hide from the `/` menu (background knowledge only) | `false` |

> `allowed-tools` **does not restrict** — it pre-approves. Every tool stays callable, governed by your permission settings. Use deny rules in `/permissions` to actually block a tool.

### Description Length and Its Consumer

**Who reads a command's `description` depends entirely on `disable-model-invocation`** — and the two cases want opposite lengths.

| | `disable-model-invocation` absent / `false` | `disable-model-invocation: true` |
|---|---|---|
| **Consumers** | The model (always-loaded listing) **+** `/help` **+** autocomplete | `/help` **+** autocomplete only — the description *leaves model context* |
| **Trigger terms** | Load-bearing — the description is the sole auto-invocation mechanism | Inert — no model will ever match against them |
| **Cost** | Charged to the always-loaded listing budget every session | None |
| **Target length** | As long as it needs to be to carry the trigger vocabulary, up to the 1,536-char `description` + `when_to_use` listing cap | **One line** |

Two consequences worth internalizing:

- **Do not truncate a model-invocable command's description** to satisfy a style guideline. Its trigger terms are the only thing that makes the command discoverable; shortening it degrades activation silently and you will not see the regression. "The body carries the detail" is false here — the body is read *after* invocation, and the description is what decides whether invocation happens.
- **Do not write a long description on a `disable-model-invocation: true` command.** Every consumer is a single-line UI surface, so the overflow is displayed to nobody and read by nobody. Writing an explicit `Activation terms: …` list into such a description is the sharpest version of this mistake: it addresses a reader that the same frontmatter has just disconnected. Put the detail in the body, where the user who typed `/name` will actually see it.

**A long `description` is also a parse hazard.** A folded block scalar (`description: >`) that runs 10+ lines pushes every later key below the eye-line, which is where malformed values survive review. Frontmatter that fails to parse registers *no* `description` and *no* `allowed-tools`, and nothing announces it — grepping for field presence succeeds on a file the YAML loader rejects. If a description must be long, keep it a quoted single-line string, and validate with a real parser (see [Debugging](references/runtime-and-permissions.md#debugging)).

### `argument-hint` and the No-Argument Case

`argument-hint` exists for exactly one purpose: telling a user what to type after `/name`. It has no model-facing role.

- **A command that takes no arguments must omit the key entirely.** Neither `argument-hint: ""` nor a bare `argument-hint:` (which YAML reads as null) is acceptable — both occupy the field while conveying nothing, and they are not even consistent with each other, so no convention can be inferred from them. Absence is the correct signal for "takes no arguments."
- **A command that takes arguments must list all of them**, including flags. If the body documents `--dry-run`, the hint says `--dry-run`. A hint that omits half the accepted flags is worse than none, because it reads as exhaustive.
- **Always quote the value — it is a string, never a list.** Write `argument-hint: "[message]"`, not `argument-hint: [message]`. This is a type rule, not a style preference: `[...]` is conventional CLI usage notation meaning *optional*, but YAML reads a leading `[` as a **flow sequence**, so the unquoted form silently loads as the list `['message']` while the quoted form loads as the string `[message]`. A corpus mixing the two hands its readers two different types for one field. The divergence is invisible until it bites, because the two reader classes disagree: a line-regex frontmatter reader (the kind used by exporters that strip frontmatter for another assistant) coerces every value to a string and shows `[message]` either way, while a real YAML parser returns a list for one and a string for the other. Same file, same field, two types.

  Quote **unconditionally**, not just when the value starts with `[`. A hint like `<skill-name>` or `<discipline> [--on <artifact>]` happens to parse as a string only because it does not *begin* with a bracket — reorder it and it becomes a list, or worse. The worse case is the real one: a multi-group hint such as `argument-hint: [<run_tag>] [--task-slug <slug>]` is *two* flow sequences on one line, which no YAML parser accepts. The whole frontmatter block then fails to load, taking `description` and `allowed-tools` with it, and a command whose frontmatter does not load cannot register the description that is its only model-invocation mechanism. Quoting is the single habit that forecloses the entire class.

## Arguments and Dynamic Context

Four substitution mechanisms are available in a command body:

| Mechanism | Syntax | Yields |
|---|---|---|
| All arguments | `$ARGUMENTS` | Everything the user typed after `/name`, as one string |
| Positional | `$1`, `$2`, … | Individual whitespace-separated arguments |
| Bash execution | ``!`git status` `` | Live command output, interpolated before the body renders |
| File reference | `@path/to/file` | That file's contents (legacy form — prefer the bang form for new work) |

Every bang-prefixed command needs matching `allowed-tools` coverage, or the user is prompted
before the body renders. `$ARGUMENTS` may be empty — handle the bare `/command` invocation
explicitly rather than proceeding on nothing.

--> Worked examples for each mechanism, plus the input-testing checklist: [references/arguments-and-context.md](references/arguments-and-context.md).

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

- **Clear descriptions**: Be specific -- "Review code for security vulnerabilities" not "Helps with code". Length is not a style choice; it follows from who consumes the description (see [Description Length and Its Consumer](#description-length-and-its-consumer))
- **Always declare `allowed-tools`**: Without it, Claude prompts for permission every time
- **Use `argument-hint` when there are arguments, omit it when there are none**: never leave it empty (see [`argument-hint` and the No-Argument Case](#argument-hint-and-the-no-argument-case))
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
- **Empty `argument-hint`** -- a hint of `""` or a bare `argument-hint:` (YAML null) occupies the field while telling the user nothing; omit the key entirely for a no-argument command
- **A long `description` on a command the model cannot invoke** -- see [Description Length and Its Consumer](#description-length-and-its-consumer)
- **Inlining rule knowledge** -- if conventions or constraints already exist in a rule file, don't copy them into the command; rules load automatically by semantic relevance when the command executes
- **Discovery timing differs by location** — see [Discovery and Live Reload](references/runtime-and-permissions.md#discovery-and-live-reload).

## Runtime and Debugging

Three runtime concerns live in [references/runtime-and-permissions.md](references/runtime-and-permissions.md) — consult it when a command misbehaves rather than when authoring one:

- [Discovery and Live Reload](references/runtime-and-permissions.md#discovery-and-live-reload) — project/personal files hot-reload; **plugin commands are cached at session start**, so a newly installed command is invisible until a restart.
- [Permission Management](references/runtime-and-permissions.md#permission-management) — invocation is governed by `Skill(...)` rules since the merge, not the legacy `SlashCommand:/name:*` form.
- [Debugging](references/runtime-and-permissions.md#debugging) — inspecting command files, and why unparseable frontmatter fails silently.

## Creation Workflow

1. **Define** -- identify the repeated prompt or workflow to automate
2. **Create** -- write the `.md` file with frontmatter and content
3. **Test** -- invoke with `/command` and verify behavior with various inputs
4. **Iterate** -- refine based on output; adjust tools, arguments, context
5. **Share** -- commit to `.claude/commands/` for team use

## Resources

- [Official Documentation](https://code.claude.com/docs/en/skills) (the `/slash-commands` page now redirects here — commands are documented as skills)
- Extended examples: See [REFERENCE.md](REFERENCE.md) for command patterns and organization strategies
