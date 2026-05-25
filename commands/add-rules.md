---
description: Copy rules into the current project for customization
argument-hint: "[rule-names... | all]"
allowed-tools: [Bash(mkdir:*), Bash(cp:*), Bash(ls:*), Bash(find:*), Read, Glob, Grep]
disable-model-invocation: true
---

Copy rules from the personal library (`~/.claude/rules/`) into this project's `.claude/rules/` directory so they can be customized with project-specific content.

**Why**: Personal rules already load for every project. Copying a rule to `.claude/rules/` creates an independent project copy where you can fill in `[CUSTOMIZE]` sections. The project copy takes precedence over the personal one.

## Arguments

- `$ARGUMENTS` — Space-separated rule names (filename stem without `.md`) or `all`
- Examples: `/add-rules coding-style git-conventions`, `/add-rules all`

## Process

1. Verify `~/.claude/rules/` exists and contains rule files
2. Scan `~/.claude/rules/` recursively for `.md` files — build a map of filename stem → relative path (e.g., `coding-style` → `swe/coding-style.md`)
3. If no arguments provided, list available rules (stem and relative path) and ask the user which ones to add
4. If `$ARGUMENTS` is `all`, select every available rule. Otherwise, match each argument against the filename stem map
5. For each selected rule:
   a. If the rule already exists at the target path under `.claude/rules/`, skip it and report "already exists"
   b. Create the target subdirectory under `.claude/rules/` if needed (preserve source directory structure)
   c. Copy the rule file to the target location
6. Report summary: rules added, rules skipped, rules not found
7. Remind the user to fill in `[CUSTOMIZE]` sections in the copied rules

## Important

- **Copy, do not symlink** — project rules must be independent, customizable, and committable to git
- **Preserve subdirectory structure** — `swe/coding-style.md` → `.claude/rules/swe/coding-style.md`
- **Never overwrite** — if a rule already exists in the project, skip it and inform the user
- **Ignore README.md files** — only copy rule content files, not directory documentation
