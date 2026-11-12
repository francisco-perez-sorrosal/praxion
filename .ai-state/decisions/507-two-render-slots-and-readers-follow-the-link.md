---
id: dec-507
draft_id: dec-draft-249348a7
title: "A version directory has two render slots: a write never replaces the file the instructions link resolves to, and every reader follows the link"
status: accepted
category: implementation
date: 2026-11-11
summary: "claude/config/CLAUDE.md stays the primary render and claude/config/CLAUDE.alternate.md is written only when the link resolves to the installed version's own primary render; carry-forward, read-back and the current check read the render the link names (CachedRender gains render), so an in-place hand edit is never overwritten and the next update carries forward from the live render."
tags: [instructions, render, carry-forward, hand-path]
made_by: agent
agent_type: systems-architect
branch: fix-hand-path-instructions
pipeline_tier: standard
affected_files:
  - hooks/_install_refresh.py
  - hooks/_install_update.py
  - hooks/test__install_refresh.py
  - hooks/test_install_carry_forward.py
affected_reqs: [REQ-05, REQ-07, REQ-08, REQ-13]
---

## Context

REQ-08 promises that the render `~/.claude/CLAUDE.md` pointed to is never modified when the hand path replaces an unreadable one. The commonest unreadable render is one edited in place through the link, and when that render is the installed version's own `claude/config/CLAUDE.md`, writing the new render there destroys the edit. The frozen acceptance guard snapshots that file's inode. Every reader today assumes the render is `version_dir/claude/config/CLAUDE.md`.

## Decision

- `claude/config/CLAUDE.md` stays the primary render. `claude/config/CLAUDE.alternate.md` is written only when the link currently resolves to the installed version's own primary render (`render_slot`, pure). A write never replaces the file the link resolves to.
- `CachedRender` gains `render`, the normalised path the link names, set by the classifier. Carry-forward, read-back and the current check read that file against its version's template. For every link Praxion writes it is the primary path, so the update path's behaviour does not move.
- A cold first install still writes the primary render as today.

## Considered Options

### One slot, moving the hand-edited render aside to a kept copy
Rejected: it modifies, by moving, the file REQ-08 protects, and breaks the frozen guard; the kept copy is just as invisible inside the cache.

### Leave an in-place-edited installed render alone as the person's own
Rejected: REQ-08's scenarios expect the instructions to read as the installed template filled with the person's answers.

### Two slots, but readers keep assuming the primary render
Rejected: the next update would carry forward from the hand-edited primary file, fail, and ask again at every release.

## Consequences

- An in-place hand edit is never overwritten; the next update carries the person's answers forward.
- One more legal file per version directory, unknown to `--check` (td-626).
- A hand-made link to some other file in a cache version directory now fails the carry-forward where it once carried from the primary render; the failure line names the hand path, which asks.
- The update refresh's failure line now names `UnrecoverableRenderError` where it named the raw exception type (`PermissionError`, `IsADirectoryError`, `FileNotFoundError`, or `UnicodeDecodeError` for a render that does not decode) when the earlier render or its template cannot be read. This is deliberate: the line says the earlier render could not be read back and names the hand path, which then asks. A permission fault on those files is labelled the same way. It is the one change to the hook's observable output.
