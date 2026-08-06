---
id: dec-054
title: Separate new_cc_project.sh from install.sh
status: accepted
category: architectural
date: 2026-04-18
summary: The new-project entry point ships as a standalone repo-root script symlinked into PATH as new-cc-project, sibling to install.sh rather than as an install.sh subcommand, because configuring the host and creating a project are different verbs with different UX surfaces.
tags:
  - onboarding
  - cli
  - install
  - boundaries
made_by: user
agent_type: systems-architect
pipeline_tier: standard
affected_files:
  - new_project.sh
  - install_claude.sh
---

## Context

The greenfield onboarding feature needs a user-facing CLI entry point. Two reasonable shapes exist in this codebase:

1. Extend `install.sh` with a new subcommand: `install.sh new <name>`. This reuses the existing dispatcher, the existing `--check` / `--dry-run` / `--uninstall` action flags, and the install banner. It is one more case in the existing dispatch.
2. Ship a separate top-level script `new_cc_project.sh`, sibling to `install.sh` / `install_claude.sh` / `install_cursor.sh`. It is its own entry, has its own argument shape, and has its own help text.

The user's brief explicitly asked for the second shape. This ADR records the rationale so the decision is not silently revisited.

The deeper distinction: `install.sh` and its delegates *configure the host* — they put symlinks under `~/.claude/`, register the plugin, set up MCP servers, install the Phoenix daemon. These are idempotent host-mutations with `--check`, `--uninstall`, `--relink` modes. The new-project entry, by contrast, *creates a new artifact* in the world (a directory, a git repo) and hands off to an interactive Claude session. The verbs are different (configure vs create), the destinations are different (`~/.claude/` vs a new project directory), and the lifecycle is different (rerunnable mutation vs one-shot bootstrap).

There is also a question of where the script's PATH name comes from. Three choices: (a) parked at repo root, user runs `./new_cc_project.sh` from the checkout; (b) parked under `scripts/` and auto-linked by `install_claude.sh::relink_all()` into `~/.local/bin/new_cc_project.sh`; (c) parked at repo root with an explicit symlink step in `install_claude.sh` publishing it as `~/.local/bin/new-cc-project` (kebab-case canonical).

## Decision

The new-project entry ships as `new_cc_project.sh` at the **Praxion repo root** (sibling to `install.sh`, `install_claude.sh`, `install_cursor.sh`), and `install_claude.sh` gains a one-time symlink step that publishes it on PATH as `new-cc-project`.

Concretely:

- The file lives at `<praxion>/new_cc_project.sh`, executable, ~40 lines of bash.
- `install_claude.sh::relink_all()` adds a step (after the existing `scripts/` linking pass) that creates `~/.local/bin/new-cc-project` → `<praxion>/new_cc_project.sh` using the existing `link_item()` helper.
- `install_claude.sh::clean_stale_symlinks` and the uninstall path remove the symlink on cleanup.
- `install.sh` is not modified — no new subcommand, no new dispatch case.

## Considered Options

### Option A — `install.sh new <name>` subcommand

**Pros:**
- Single dispatcher; users learn one command surface.
- Reuses `--check`, `--dry-run`, etc.

**Cons:**
- Conflates two verbs (configure vs create) in one tool. `install.sh new --uninstall <name>` becomes meaningful but is not what we want.
- The `install.sh` banner advertises "Praxion installer" — running it to *create* a project is jarring.
- Requires changes to `install.sh`'s dispatch (~30 lines) plus the new logic, instead of a clean greenfield script.
- Worse `--help` surface: the same help page must explain both verbs.

### Option B — `scripts/new_cc_project.sh` auto-linked via `relink_all()`

**Pros:**
- Zero changes to `install_claude.sh` (the scripts loop already does the work).
- Discovery via `ls scripts/` is straightforward.

**Cons:**
- `scripts/` is semantically "internal dev helpers + small CLI tools." A new-project entry is a **product entry point**, not a helper.
- The PATH name becomes `new_cc_project.sh` (snake-case with `.sh`), which clashes with the canonical Claude Code binary naming (`claude`, `ccwt`).
- A user who `ls`'s the repo root sees `install*.sh` but no `new_cc_project.sh`, hiding the entry from the most natural discovery surface.

### Option C — Repo-root file + explicit kebab-case symlink (chosen)

**Pros:**
- Repo-root placement preserves the sibling relationship with the install scripts.
- Kebab-case PATH name (`new-cc-project`) matches Claude Code conventions.
- One small block in `install_claude.sh` (~5 lines using the existing `link_item()` helper) is easily reviewable and reversible.
- Stale-symlink sweep already exists; one entry to add.

**Cons:**
- Two locations to remember (the file and the install step); if the file is ever moved, the install step must move too. Mitigated by pinning the path via a constant at the top of `install_claude.sh`.
- Symlink collision possible if another tool already owns `~/.local/bin/new-cc-project`. Mitigated by `link_item()`'s collision prompt.

## Consequences

**Positive:**
- `install.sh` stays semantically pure (configure the host).
- `new_cc_project.sh` is discoverable from the repo root and from PATH under a canonical name.
- The install-step change is small, surgical, reuses existing helpers, and is reversible.
- Future variants (e.g., `new-cursor-project.sh`) follow the same pattern without conflating into install.sh.

**Negative:**
- One extra bullet in the installer's symlink list.
- A user who has not run `./install.sh code` cannot use the kebab-case PATH name; they fall back to `./new_cc_project.sh` from the checkout. Acceptable — they have not yet onboarded their host to Praxion.
