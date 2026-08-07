# Arguments and Dynamic Context

Worked examples for wiring arguments (`$ARGUMENTS`, `$1`, `$2`) and dynamic context (bang-prefixed bash, `@` file references) into a slash command. Load when authoring or debugging a command's input handling.

Back to [../SKILL.md](../SKILL.md).

## Argument Handling

### All Arguments (`$ARGUMENTS`)

Captures all arguments as a single string:

```markdown
---
argument-hint: "[issue-details]"
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
argument-hint: "[pr-number] [priority] [assignee]"
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

### Handling Absent Arguments

`$ARGUMENTS` may be empty — the user can always invoke `/command` bare. Test the
no-argument path and either infer a sensible default or decline with a message that names
the missing input. A command that silently proceeds on an empty `$ARGUMENTS` produces the
worst failure mode: plausible output derived from nothing.

## Dynamic Context

### Bash Command Execution

Use `!` prefix to execute bash commands before the command runs. The output is interpolated
into the prompt, so the model sees live repository state rather than a description of it:

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

Every command executed this way must be covered by `allowed-tools`, or the user is prompted
before the command body renders.

### File References

Use `@` prefix to include file contents. This is a command-file feature carried over from the
legacy form; the merged skills docs emphasize bang-prefixed command injection and
`${CLAUDE_SKILL_DIR}` instead — **prefer the bang form for new work**:

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

## Testing Checklist

Exercise each input path before shipping a command:

- No arguments at all (`/command`)
- One argument, and more arguments than the hint declares
- Arguments containing spaces, quotes, and shell metacharacters
- Every bang-prefixed command, run standalone, in a clean checkout
- Every `@` path, confirmed to resolve from the invocation directory
