---
description: Clean the .ai-work/ directory after pipeline completion
allowed-tools: [Bash(rm:*), Bash(ls:*), Bash(cat:*), Read, AskUserQuestion]
---

Remove task-scoped subdirectories from `.ai-work/` containing ephemeral pipeline intermediates.

## Process

1. Check if `.ai-work/` exists and has task-scoped subdirectories. If not, report that there is nothing to clean and stop
2. List the task-scoped subdirectories and their contents so the user can see what will be removed
3. For each subdirectory, check if `LEARNINGS.md` exists. If so, display its contents and warn: "LEARNINGS.md exists in `.ai-work/<task-slug>/` and may contain insights worth preserving. Merge valuable content into permanent locations (e.g., project CLAUDE.md, rules, skills, or .ai-state/) before deleting." Ask the user whether to proceed or abort
4. If the user confirms (or no LEARNINGS.md exists), remove each task-scoped subdirectory (`rm -rf .ai-work/<task-slug>/`). Remove `.ai-work/` itself only when empty
5. Confirm deletion
