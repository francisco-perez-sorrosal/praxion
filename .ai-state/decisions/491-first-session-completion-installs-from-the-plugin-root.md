---
id: dec-491
draft_id: dec-draft-7d28458a
title: The first-session completion installs from the plugin root and links rules through the installer's library, never re-pointing a live link
status: accepted
category: architectural
date: 2026-11-06
summary: "hooks/auto_complete_install.py resolves the plugin it installs from (CLAUDE_PLUGIN_ROOT, else the install path in installed_plugins.json) instead of the unversioned cache parent, and links rules through lib/install_shared.sh; after an update it runs refresh_rule_symlinks, which sweeps stale links and links missing ones but never re-points a live link or replaces a regular file."
tags: [installer, hooks, sessionstart, rules, marketplace, auto-complete, symlinks]
made_by: agent
agent_type: orchestrator
branch: main
pipeline_tier: lightweight
supersedes_in_part: [dec-170]
superseded_in_part_by: [dec-draft-9954b327]
affected_files:
  - hooks/auto_complete_install.py
  - hooks/test_auto_complete_install.py
  - lib/install_shared.sh
  - install_claude.sh
  - tests/acceptance/drivers/model_routing_move.py
affected_reqs: []
---

## Context

The SessionStart completion hook exists so a marketplace install needs no manual step: the README says setup completes on the first session. It looked for the plugin's files in `~/.claude/plugins/cache/bit-agora/praxion/`, but Claude Code installs a plugin into a version directory under it (`.../praxion/<version>/`), so on every real install the hook linked no rule, rendered no `CLAUDE.md`, wrote its completion marker and printed "Auto-install complete." A marketplace-only install therefore ran its main session without the behavioural contract and without the user instructions, which carry the two constitutional sentences. Its tests built the same unversioned layout, and so did one acceptance driver, which is how it passed. The hook also kept its own rule-linking code: a PyYAML manifest reader that fell back to linking every rule when PyYAML was missing from the ambient `python3`, and a skip list that still linked `rules/CLAUDE.md`. And after an update it exited as soon as the links existed, so it never swept a link to a rule that had become hook-delivered; project gating's plan (dec-490) had named this re-arm as its double-delivery mitigation.

## Decision

The hook installs from the plugin it runs from: `CLAUDE_PLUGIN_ROOT` when set, else the install path the plugin registry (`installed_plugins.json`) records for the praxion plugin; with neither, it does nothing and writes no marker. Rule linking goes through `lib/install_shared.sh`, the library the installer and `install.sh --check` use, so all three read the manifest and judge a stale link the same way (dec-170's per-file linker inside the hook is replaced). A cold install runs the installer's `link_rules`. After an update, when the surfaces are already present, it runs the new `refresh_rule_symlinks`: it sweeps stale Praxion links (into the plugin's rules or any cached version's) and links each manifest rule that has no working link, but never re-points a live link, wherever it points, and never replaces a regular file. A `CLAUDE.md` link that no longer resolves counts as not installed. A failed install reports itself, with the command that completes it.

## Considered Options

- **Re-point every rule link to the new version on re-arm** (the installer's `link_rules`): rejected. A clone install's links point into the user's checkout, and re-pointing them at the plugin cache would silently move a developer off their own tree.
- **Keep the hook's own Python linker and only fix the path**: rejected. Two readers of one manifest had already diverged twice (the PyYAML fallback, the directory guide), and the installer's library is shipped in every plugin version.
- **Re-render `CLAUDE.md` and re-point script links on every update**: deferred to td-593. A re-render needs the personal values, which live in each version's own directory, so it needs a decision on carrying them across versions.

## Consequences

- A fresh marketplace install gets the manifest's symlink rules and a rendered `CLAUDE.md` on its first session, through the same linking code `install.sh` uses.
- After an update, the next session sweeps links to rules the new version no longer links and links the ones it adds; links that still resolve keep their target. A link left dangling by a removed version is relinked.
- `CLAUDE.md` and script links still point into the previous version's directory after an update until `/praxion-complete-install` runs or that directory is removed (td-593).
- The hook needs `bash` to link rules; without it the link step fails, the failure is reported, and the session is never blocked.

## Disconfirmation

- **Falsifier (the responsibility that moved):** choosing which rules a user rules directory links moves from `hooks/auto_complete_install.py` to `lib/install_shared.sh`. The decision is wrong if a fresh marketplace install's first session leaves `~/.claude/rules/swe/agent-behavioral-contract.md` unlinked, or an update after which a live link into a checkout points into the plugin cache. Both are pinned by tests in `hooks/test_auto_complete_install.py`.
- **Steelmanned runner-up:** re-pointing every link to the new version keeps a marketplace install exactly current and needs no dangling-link path; it loses only for installs that mix a clone checkout with the plugin, which is the developer setup this project itself runs on.
- **Reversal trigger:** if Claude Code removes old version directories at update time (so live links into an old version never exist), the refresh can re-point links into a Praxion cache without the clone-install risk, and this record should be revisited.

## Prior Decision

dec-170 made the hook link rules file by file, with its own reading of the manifest, so it could leave hook-delivered rules unlinked "matching the behavior of lib/install_shared.sh link_rules()". That intent stands; the mechanism is replaced. The hook no longer keeps a second reader of the manifest: it calls the installer's library, which is what dec-170 meant to match, so the two cannot drift again.
