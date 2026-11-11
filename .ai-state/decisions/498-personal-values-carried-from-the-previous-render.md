---
id: dec-498
draft_id: dec-draft-1921fe75
title: "An update carries the personal values forward from the previous version's render, aligned with its template, and persists no new copy"
status: accepted
category: implementation
date: 2026-11-10
summary: "On the update path the hook recovers username, email and GitHub URL by aligning the previous version's render with that version's template (render_claude_md.recover_values); a default fills only a placeholder the old render never carried, and an unrecoverable render is kept, never re-rendered with defaults."
tags: [installer, hooks, personal-info, claude-md, plugin-update, marketplace]
made_by: agent
agent_type: systems-architect
branch: feat-install-refresh
pipeline_tier: standard
affected_files:
  - scripts/render_claude_md.py
  - hooks/auto_complete_install.py
affected_reqs: [REQ-06, REQ-08, REQ-15, REQ-18]
---

## Context

Re-rendering `~/.claude/CLAUDE.md` on an update needs the personal values the previous render used (KS3: no prompt, and no default unless the previous version had none). A marketplace install keeps those values nowhere but in that render:

- The hook's cold path renders from `derive_defaults()` and writes no values file.
- `complete_install_from_plugin` (the `/praxion-complete-install` hand path) never renders the instructions.
- `claude/config/.personal_info.env` is written only by a clone's interactive installer.

The brief flagged the choice as a one-way door for every existing install (uncertainty 6/10).

## Decision

`scripts/render_claude_md.py` gains `recover_values(template_text, render_text)`, the pure inverse of `render_claude_md`.

- **The recovery is strict.** Equal line counts; every literal template line equal to its render line; every placeholder line matching its template line with each placeholder as a capture; one value per key.
- **It fails to `None`.** Any doubt returns `None`.
- **What the hook reads.** On the update path, the hook reads the previous version's template and render from that version's `claude/config/`, which is the directory the instructions link names.
- **How the values combine.** A default (`derive_defaults()`, what a fresh install uses) fills only a key the new template has and the old render did not carry.
- **When recovery fails.** No re-render: the old render stays, and the update path's single failure line is printed. A silent fallback to defaults never happens.
- **Nothing new is persisted.**

## Considered Options

### A user-scope values store under `~/.claude`

Runner-up. It is written at every render and survives the old version's removal. It must still be seeded by this same recovery for every existing install, it keeps a second copy of personal values in the home, and once written every future version must read it.

### The previous version's `.personal_info.env`

Rejected. No marketplace install has one.

### Parse `~/.claude/CLAUDE.md` with no template

Rejected. It is a weaker form of the chosen option and guesses where the template knows.

## Consequences

- Every existing marketplace install carries its values on its first update after this change, with no migration.
- The choice stays a two-way door: a store can be added later, seeded by this recovery.
- The template and its render become a cross-version contract. Each placeholder sits on a line whose other text is literal, at most one per line, and a render changes nothing else. A round-trip property test over the shipped template enforces it.
- A hand edit inside a cached render makes the next update keep the old render and print one line. It fails safe.
- The update depends on the previous version's directory surviving until the new version's first session, which is true while Claude Code keeps old versions.

## Disconfirmation

- **Falsifier:** an untouched marketplace install whose render does not round-trip against its own template, either because the shipped-template round-trip test fails or because a real update reports "could not finish" with no hand edit.
- **Steelmanned runner-up:** the user-scope store keeps working when the old version is already gone, and makes values independent of template shape.
- **Reversal trigger:** Claude Code deleting old version directories at update time, or a personal value that the instructions do not show needing to cross versions. Then add the store, seeded by `recover_values`.
