---
id: dec-502
draft_id: dec-draft-66aba0de
title: No hook script reaches the PATH, by one installer predicate held equal to the first-session hook's
status: accepted
category: behavioral
date: 2026-11-11
summary: "install_claude.sh's script_is_user_facing now excludes every *-hook.sh script, not only git-*-hook.sh, matching the first-session hook's offered_scripts; every installer site (relink, the plugin hand path, --check) calls that one function, uninstall removes every link into scripts/ whatever today's filter says, and a parity test holds the bash and Python predicates equal over scripts/. scripts/diagram-regen-hook.sh, which only pre-commit runs and only by path, leaves ~/.local/bin on the next relink."
tags: [install, scripts, symlinks, filter, path, first-session, td-613]
made_by: agent
agent_type: orchestrator
branch: main
pipeline_tier: lightweight
affected_files:
  - install_claude.sh
  - hooks/_install_update.py
  - hooks/test_install_script_predicate.py
  - tests/test_install_filter.sh
  - scripts/CLAUDE.md
affected_reqs: []
supersedes_in_part: dec-042
---

## Context

dec-042 links into `~/.local/bin` only scripts that are executable and are not internal helpers, naming the helpers `merge_driver_*` and `git-*-hook.sh`. The first-session hook (dec-491, dec-499) decides the same question for a marketplace install with `offered_scripts`, which excludes every `*-hook.sh`. The two disagreed on `scripts/diagram-regen-hook.sh`. A marketplace install completed by the installer's hand path (`/praxion-complete-install`) had that link added by the installer and removed by the next update refresh (td-613). dec-499 rejected sharing one predicate between the two, because doing so moves either the clone path's `~/.local/bin` or every marketplace install's. The predicate also lived in five copies inside `install_claude.sh`.

`diagram-regen-hook.sh` is run only by Praxion's own `.pre-commit-config.yaml`, by path (`entry: scripts/diagram-regen-hook.sh`). No onboarding template, skill or script invokes it by name from the PATH.

## Decision

- A script whose name ends in `-hook.sh` is a hook, run by git or pre-commit by path, and never reaches the PATH. A merge driver stays excluded too.
- `script_is_user_facing` is the installer's one predicate. Relink, the plugin hand path and `--check` call it instead of their inline copies.
- Uninstall removes every link in `~/.local/bin` that points into `scripts/`, whatever the filter says today, so a link an older filter made is never stranded.
- The first-session hook's `offered_scripts` is the predicate's twin in Python. `hooks/test_install_script_predicate.py` runs both over the repository's `scripts/` and fails when their answers differ.

## Considered Options

- **The hook's rule, `*-hook.sh`.** Chosen. It is true to purpose: a hook script is never a command a person types. The only link it moves is a clone install's `diagram-regen-hook.sh`, which nothing runs from the PATH; the next relink's stale-link sweep removes it.
- **The installer's rule, `git-*-hook.sh`.** Rejected. Every marketplace install would gain a PATH entry for a pre-commit hook it never runs.
- **One shared implementation.** Rejected again, as in dec-499. Bash and Python cannot share code, so the parity test is what keeps the two equal.

## Consequences

- A clone install's next `install.sh` relink removes `~/.local/bin/diagram-regen-hook.sh`. Pre-commit keeps running the hook by path.
- The installer's hand path and the hook's update refresh no longer undo each other's links.
- A new `*-hook.sh` script needs no change to either predicate. A new kind of internal helper must be added in both places, or the parity test fails.
