---
description: Create a commit for staged (or all) changes
argument-hint: [message]
allowed-tools: [Bash(git:*), Read, Grep]
---

Create a commit for the current staged changes (or all changes if nothing is staged). If changes clearly mix more than one target (e.g. fix + feature, docs + refactor), perform multiple commits—one per logical task—instead of a single mixed commit.

## Process

1. Run `git status` and `git diff --staged` (or `git diff` if nothing staged)
2. Analyze the changes to understand their purpose and scope
3. **Single vs multiple commits**: If the diff clearly mixes distinct targets (e.g. `feat` + `fix`, `docs` + `refactor`, `test` + `chore`), treat as multiple logical tasks. Otherwise, proceed with one commit.
4. **When splitting**:
   - Group changes by logical task (by file and/or by diff hunks). Prefer grouping by file when files have a single clear purpose; use partial staging (`git add -p` or file subsets) when one file contains unrelated edits.
   - For each group in a sensible order (e.g. fix before feat, code before docs): stage only that group, craft a conventional commit message for that type, create the commit. Repeat until all changes are committed.
5. **When not splitting**: Stage files if needed (prefer specific files over `git add -A`), craft the commit message following our commit conventions, create the commit.
6. If `.ai-work/` exists, ask the user whether to clean it up (`rm -rf .ai-work/`). Before deleting, check for `LEARNINGS.md` and remind the user to merge any valuable content into permanent locations first
