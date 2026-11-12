---
id: dec-506
draft_id: dec-draft-5ef88cee
title: "The hand-path skills resolve the plugin root from the substituted token kept inert, with an inline registry fallback; the registry readers stay separate"
status: accepted
category: behavioral
date: 2026-11-11
summary: "Both /praxion-complete-install and /praxion-complete-uninstall read ${CLAUDE_PLUGIN_ROOT} through a quoted heredoc so unsubstituted text never expands from the shell, fall back to an inline registry reader (praxion entries, user scope first, an existing installPath), and never list the cache; the installer's and the hook's registry readers stay as they are because they answer different questions."
tags: [skills, hand-path, plugin-root, claude-code-docs, registry]
made_by: agent
agent_type: systems-architect
branch: fix-hand-path-instructions
pipeline_tier: standard
affected_files:
  - skills/praxion-complete-install/SKILL.md
  - skills/praxion-complete-uninstall/SKILL.md
  - skills/README.md
affected_reqs: [REQ-01, REQ-02, REQ-03]
---

## Context

The Claude Code docs (skills reference, "Available string substitutions"; plugin manifest reference, "Where each variable resolves", read 2026-11-11) say `${CLAUDE_PLUGIN_ROOT}` is substituted into a plugin skill's body as the installed version's path, and is not present in the environment of Bash-tool commands. Both hand-path skills read `${CLAUDE_PLUGIN_ROOT:-$(ls -d ~/.claude/plugins/cache/bit-agora/praxion/*/ | head -1)}`: the `:-` form is not the documented token, so on a stock machine the expression falls through to the lexically first cached version (0.43.0 of 13 at intake), and on a machine whose settings export the variable it names that export (the maintainer's dev checkout).

## Decision

- Each skill has one `bash` block (each block runs in a fresh shell). It reads the substituted token through a quoted heredoc, so text Claude Code did not substitute stays a literal that is not a directory and is never expanded from the shell. When that names an existing directory it is the root; otherwise an inline `python3` reader takes the registry's `praxion@` entries, a user-scope entry first, and the first `installPath` that is an existing directory. The block echoes the root and runs `"$root/install.sh" code --check`, or prints the skill's not-found report; the cache is never listed.
- The two skills' blocks are identical up to the not-found line, held equal by a parity test.
- The installer's `plugin_installed_path` and the hook's `_plugin_root` registry branch stay as they are. They answer different questions: the installer's names the registered version to find its orphan marker in the clone flow, existing or not; the hook's is reached only when Claude Code fails to export the variable to a hook, which the docs say it always exports. Neither can serve the skill, whose fallback runs exactly when no plugin directory is known. Converging the two existing readers on the skill's rule is left to a ledger row.

## Considered Options

### The bare token only
Rejected: REQ-01 keeps the registry fallback for a Claude Code that leaves the text unsubstituted.

### `${CLAUDE_SKILL_DIR}/../..`
Rejected: it names whichever copy loaded the skill, not the registry's installed version, and adds a second substitution the acceptance contract does not model.

### One registry reader inside the plugin, called by every site
Rejected: the skill cannot reach code inside a plugin directory it has not found.

## Consequences

- The handed command names the version Claude Code runs; a stray shell export can never redirect it.
- About ten lines of registry reading live in two shipped skills, held equal by a test; three registry readers exist with three precedence rules until the row lands.
