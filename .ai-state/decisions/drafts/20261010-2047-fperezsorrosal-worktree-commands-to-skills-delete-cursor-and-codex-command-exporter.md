---
id: dec-draft-d99bfb15
title: Delete the Cursor and Codex command exporters; both assistants reach workflows as native skills
status: proposed
category: architectural
date: 2026-10-10
summary: "cursor/config/export-cursor-commands.py and codex/config/export-codex-command-skills.py are deleted with their tests; install_cursor.sh sweeps stem-matched stale .cursor/commands exports once, install_codex.sh keeps its legacy-marker prune, and the generic Codex skill wrapper carries the argument hint."
tags: [cursor, codex, installers, adapters, skills, commands]
made_by: agent
agent_type: systems-architect
branch: worktree-commands-to-skills
pipeline_tier: full
affected_files:
  - install_cursor.sh
  - install_codex.sh
  - codex/config/export-codex-skills.py
  - codex/config/README.md
  - cursor/config/README.md
  - docs/cursor-compat.md
dissent: "Cursor's handling of text typed after a skill name is undocumented, so a Cursor user may lose argument passing that a per-workflow command export could have spelled out."
---

## Context

Two adapters projected `commands/*.md` into assistant-specific shapes: Cursor command files under `.cursor/commands/` and Codex `praxion-command-<name>` wrapper skills. Both fail outright once `commands/` is gone. Meanwhile Cursor already receives every skill through the `.cursor/skills/` symlink and Codex through `export-codex-skills.py`, so after the move each workflow would appear twice in each assistant. The user decided at intake to delete both exporters.

**Activation:** no — user-decided; the open questions were only the sweep shape and the Codex argument hint.

## Decision

1. Delete both exporters and their tests; drop the count, verify and export steps from both installers.
2. `install_cursor.sh` removes a `.cursor/commands/<stem>.md` only when `skills/<stem>/SKILL.md` exists in the Praxion source, never the directory wholesale (users keep their own commands), removes the directory only when left empty, prints a path-free count, and writes nothing on `--dry-run`. The block is marked as a legacy shim with its removal condition.
3. `install_codex.sh` keeps the legacy wrapper-marker grep so the existing prune removes every `praxion-command-*` wrapper; marked the same way.
4. `export-codex-skills.py` adds one line to a wrapper whose source declares `argument-hint`, telling Codex to treat the text after `$<name>` as the arguments — carrying over the argument semantics the command wrappers gave Codex users.

## Considered Options

### Option 1 — Delete and sweep (chosen)

Each workflow appears once per assistant; stale projections are cleaned on the next install.

### Option 2 — Re-point the exporters at `skills/`

Keeps per-workflow command entries. Rejected: duplicates every workflow in Cursor's picker and Codex's skill list, and keeps the command concept alive in the adapters.

### Option 3 — Delete without sweeps

Smallest change. Rejected: existing users keep stale duplicates that never update.

## Consequences

**Positive:** two scripts and their tests removed; one projection path per assistant; installers stop failing on a missing directory.

**Negative:** existing users must reinstall once; the sweep and prune shims stay until no supported release produced those projections; Cursor argument passing remains undocumented (unchanged from before: the old export performed no substitution either).

## Disconfirmation

- **Falsifier:** after a reinstall, a Cursor or Codex user cannot invoke a workflow by name, or sees it twice.
- **Steelmanned runner-up:** keep a re-pointed Cursor export, because a Cursor command file attaches the workflow body to the user's message verbatim and so passes typed arguments by construction, whereas skill invocation's argument handling is undocumented; parity with today's behaviour would then be guaranteed rather than assumed.
- **Reversal trigger:** Cursor documents that skill invocation drops trailing text, or users report workflows losing their arguments in Cursor.
