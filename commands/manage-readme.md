---
description: Create or refine README.md files with precision-first technical writing style
argument-hint: "[file-paths...]"
allowed-tools: [Read, Write, Edit, Glob, Grep, Bash(find:*)]
---

Create or refine README.md documentation following our technical writing conventions.

## Requirements

- **Target files**: $ARGUMENTS (optional — if omitted, discover and act on all README.md files in the project)

## Process

1. If `$ARGUMENTS` is provided, treat each argument as a path to a specific README.md to create or refine
2. If no arguments, run `find . -name 'README.md' -not -path '*/node_modules/*' -not -path '*/.git/*'` to discover all README.md files in the project
3. For each target file:
  - If the file **does not exist**: examine the surrounding code, config, and directory purpose, then create a README.md that explains what it is, how to use it, and any prerequisites
  - If the file **exists**: read it, evaluate against our writing conventions, and refine it in place
4. When refining an existing README, preserve the author's intent and structure. Fix precision, remove filler, and fill gaps — do not rewrite from scratch unless the document is fundamentally disorganized
5. Present a summary of changes made (or files created) when done and validate their acceptance with the user
