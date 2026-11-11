---
id: dec-draft-9954b327
title: "The first-session completion owns the update path: it refreshes the instructions and the script links, and re-points rule links into an older cached version"
status: proposed
category: architectural
date: 2026-11-10
summary: "After an update, a re-armed hooks/auto_complete_install.py run from a cache version directory re-renders ~/.claude/CLAUDE.md, refreshes ~/.local/bin and re-points rule links that target another cached Praxion version; links outside the cache and regular files are never touched, and a first install or a --plugin-dir run is unchanged."
tags: [installer, hooks, sessionstart, marketplace, auto-complete, symlinks, plugin-update]
made_by: agent
agent_type: systems-architect
branch: feat-install-refresh
pipeline_tier: standard
affected_files:
  - hooks/auto_complete_install.py
  - hooks/_install_refresh.py
  - hooks/_install_update.py
  - hooks/test_auto_complete_install.py
  - hooks/test__install_refresh.py
  - hooks/test_install_update.py
  - lib/install_shared.sh
  - README.md
affected_reqs: [REQ-01, REQ-02, REQ-03, REQ-04, REQ-05, REQ-07, REQ-09, REQ-10, REQ-14, REQ-15, REQ-16, REQ-19, REQ-20, REQ-21, REQ-22, REQ-23, REQ-24, REQ-25]
supersedes_in_part: [dec-491]
dissent: "A version-keyed marker would detect a new version exactly, instead of inferring it from the cache directory's modification time, at the cost of a marker-format change and losing the removal re-arm."
---

## Context

After `claude plugin update praxion@bit-agora`, a marketplace install's next session re-armed the first-session completion. That run only refreshed rule links, and it never re-pointed a live one. `~/.claude/CLAUDE.md` and the `~/.local/bin` script links kept pointing into the previous version's cache directory, so every release needed `bash install.sh --relink`, which a marketplace install cannot run (td-593). dec-491 deferred the instructions and the script links to td-593, and its reversal trigger named re-pointing links into a Praxion cache as the step to take once it could be done without the clone-install risk.

## Decision

The hook owns the update path.

- **When it runs.** A run is the update path when the existing re-arm fires (the completion marker is older than the plugin cache directory), an earlier completion exists (the marker is present), and the plugin root is a version directory of the plugin cache. Every other run keeps today's behaviour exactly: a first install, or a `--plugin-dir` checkout.
- **Instructions.** On the update path the hook classifies `~/.claude/CLAUDE.md` into one of five states: absent, user-owned file, foreign link, live cached render, dangling cached render.
  - A live render of another version is re-rendered from the new template with the values that render carried (dec-draft-1921fe75). The new render is written atomically into the new version's directory, and the link is swapped atomically.
  - An absent or dangling cached render is set up as today's cold path sets it up.
  - A user-owned file or a foreign link is left alone.
- **Rules.** The new library function `repoint_cached_rule_symlinks` re-points each manifest-place link that targets another cached Praxion version, live or dangling. `refresh_rule_symlinks` then sweeps stale links and links missing ones.
- **Scripts.** A planner in the hook, over the hook's own script predicate, re-points cache links under offered names, removes cache links under other names, and links free offered names. It never acts on a regular file or a link outside the cache.
- **Failures.** Any step's failure produces exactly one stderr line naming `/praxion-complete-install`, with the exception type only. Success is silent. The marker is written either way.
- **Unchanged.** The installer, `install.sh --check` and their predicates do not change.

## Considered Options

### Script refresh in `lib/install_shared.sh`, shared with the installer (td-593's 2026-11-08 note)

Rejected. The installer's predicate (dec-042, pinned by `tests/test_install_filter.sh`) and the hook's (pinned by `test_non_operator_facing_files_stay_off_the_path`) differ on `scripts/diagram-regen-hook.sh`. One shared predicate moves either the operator's clone path or every marketplace install's `~/.local/bin`, and the installer's relink is a take-over by design that needs no refresh semantics.

### A Praxion-owned `current` link that every surface points through

Rejected. It removes only the re-pointing, and it adds a persistent artifact every future version must honour. Its link shape is one that `install.sh --check` and `_managed_rule_rel_path` do not recognise, so the check's verdict would move. Values, new names and dropped names would still need the same work.

### A version-keyed completion marker

Runner-up; see Disconfirmation.

### Run today's whole cold path when the instructions link dangles

Rejected. `link_rules` and `_link_scripts` re-point every link, a clone's included.

## Consequences

- A release reaches a marketplace install on its first session after a restart, with no relink. Once that session runs, removing old versions breaks nothing.
- A clone install's links and instructions, live links outside the cache, and regular files are never touched by any new path. A first install and a `--plugin-dir` session behave as before.
- The cache-target rule exists in two languages (bash in the library, Python in the hook), pinned together by a shared example table in their tests.
- A failure line names a hand path that links rules and scripts but renders no instructions. The previous render stays complete, so the session keeps working.
- Removing an old version also re-arms the hook. The re-run is idempotent and silent on success.

## Disconfirmation

- **Falsifier (the responsibility that moved):** refreshing a marketplace install's instructions and script links after an update moves from the user-run `install_claude.sh --relink` to `hooks/auto_complete_install.py`. The decision is wrong if:
  - an updated marketplace install's first session leaves a script or instruction link into the previous version;
  - any new path re-points a live link outside the plugin cache; or
  - a `--plugin-dir` session writes its checkout's `claude/config/CLAUDE.md`.
  The `tests/acceptance/test_plugin_update_*.py` scenarios pin all three.
- **Steelmanned runner-up:** a version-keyed marker (the completed plugin root recorded in the marker, re-arming when the running root differs) answers "first session of this version" exactly. It is immune to unrelated changes of the cache directory's modification time and works when the cache directory is missing. It loses here only because it changes the marker's format for every existing install and drops the removal re-arm that dec-491's dangling-link recovery uses.
- **Reversal trigger:** Claude Code updating a version directory in place, or changing the cache layout, so the cache directory's modification time no longer moves on an update. Also Claude Code deleting old version directories at update time, which makes the dangling case the common path and a prompt on every update unacceptable.

## Prior Decision

dec-491 is narrowed, not replaced.

- **Narrowed clause:** "never re-points a live link, wherever it points" becomes "never re-points a live link outside the plugin cache". A live rule link into another cached Praxion version is now re-pointed to the running version's rule.
- **Settled deferral:** dec-491 deferred "re-render `CLAUDE.md` and re-point script links on every update" to td-593, and this record settles it.
- **Surviving clauses:**
  - installing from the plugin root;
  - linking rules through `lib/install_shared.sh`;
  - never replacing a regular file;
  - sweeping stale links and linking missing ones;
  - a dangling `CLAUDE.md` link counting as not installed.
