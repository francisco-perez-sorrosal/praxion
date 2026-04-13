---
id: dec-042
title: Scripts install filter uses a combined predicate (executable + not-internal-helper) plus stale-symlink sweep
status: accepted
category: implementation
date: 2026-04-13
summary: install_claude.sh links only scripts that are executable AND not internal git helpers; clean_stale_symlinks sweeps ~/.local/bin/ on upgrade
tags: [install, scripts, symlinks, filter, correctness]
made_by: agent
agent_type: systems-architect
pipeline_tier: standard
affected_files:
  - install_claude.sh
  - scripts/regenerate_adr_index.py
affected_reqs:
  - REQ-SL-01
  - REQ-SL-02
  - REQ-SL-04
  - REQ-SL-05
---

## Context

The installer currently links every regular file under `scripts/` into `~/.local/bin/`, including `CLAUDE.md` (documentation, not a script) and test files (`test_reconcile_ai_state.py`). The ROADMAP 3.6 item proposes a simple `[ -f && -x ]` filter to exclude non-executables.

User constraint (verbatim from the task prompt):

> "Works at the user level for all the projects and preserves the isolation of each project."

Initial design was a simple `-x` filter. Context-engineer review surfaced two additional concerns:

1. **Correctness risk — internal helpers**: `merge_driver_memory.py`, `merge_driver_observations.py`, and `git-post-merge-hook.sh` are all executable (they need to be — git invokes them). But they are installed via `install_git_merge_infra()` into per-repo git config, not into `$PATH`. Linking them to `~/.local/bin/` lets a user accidentally invoke `merge_driver_memory.py` as a shell command, which operates on `%O %A %B` git-merge arguments — running it manually would corrupt arbitrary files. A plain `-x` filter does not catch this.

2. **Regression risk — advertised script with wrong permissions**: `regenerate_adr_index.py` is documented as a user-facing tool in `scripts/CLAUDE.md:11` but its source file has `-rw-r--r--` (no executable bit). Under the new filter it would be silently dropped from the install — a regression for any user who had it linked before.

3. **Upgrade path — stale symlinks**: A user who installed under the old buggy filter has symlinks for `CLAUDE.md`, merge drivers, etc. in `~/.local/bin/`. The new filter does not re-link those, but also does not remove them — the stale symlinks persist. `clean_stale_symlinks()` currently only sweeps `$HOME/.claude/`, not `~/.local/bin/`.

## Decision

The scripts install filter is a **combined predicate**:

```sh
for script in "$scripts_src"/*; do
    [ -f "$script" ] && [ -x "$script" ] || continue
    name="$(basename "$script")"
    case "$name" in
        merge_driver_*|git-*-hook.sh) continue ;;
    esac
    ln -sf "$script" "${bin_dir}/${name}"
done
```

Three supporting changes land in the same PR:

1. `chmod +x scripts/regenerate_adr_index.py` — source-file permission fix so the advertised tool is included.
2. `clean_stale_symlinks()` extended to sweep `~/.local/bin/` for symlinks pointing into `$SCRIPT_DIR/scripts/` that no longer pass the filter, removing them.
3. The `uninstall_claude_code()` and `check_claude_code()` loops apply the same combined filter for symmetry.

The user constraint is preserved: installing is user-level (one-time, `~/.local/bin/`); every linked script resolves its project scope via `$PWD` or `git rev-parse` at invocation, so per-project isolation is maintained by design — no script reads a global state path that would leak between projects.

## Considered Options

### Option 1 — Simple `-f && -x` filter only

Ship exactly what the ROADMAP Action line proposes.

- Pros: Minimal diff.
- Cons: Silently drops `regenerate_adr_index.py` (advertised tool with wrong permissions); leaves merge drivers linked into `$PATH` where a user could invoke them destructively; leaves stale symlinks on upgrade.

### Option 2 — Explicit allow-list manifest

Introduce `scripts/linked_scripts.txt` (mirroring `config_items.txt`) listing the exact scripts to link.

- Pros: Explicit inventory.
- Cons: New artifact to maintain; duplicates filesystem metadata (the `-x` bit is the natural signal for "user-facing"); drifts when new scripts are added; not consistent with `commit_gate.sh`-style convention.

### Option 3 — Combined predicate (chosen)

`-f && -x` plus a `case` block excluding internal-helper filename patterns, plus a stale-symlink sweep.

- Pros: No new artifact; filesystem metadata remains the signal; internal helpers are excluded by filename convention (which is already how they are differentiated — `merge_driver_*` prefix, `-hook.sh` suffix); stale symlinks are cleaned up on re-install; advertised tools keep working via the `chmod +x` source fix.
- Cons: The filter is three lines, not one. Acceptable — correctness matters more than terseness.

## Consequences

**Positive**:
- `CLAUDE.md` and test files are excluded (as the ROADMAP intended).
- `regenerate_adr_index.py` stays in `$PATH` (not a silent regression).
- Merge drivers and git hooks are excluded from `$PATH` (correctness — they should never be user-invocable).
- Upgrading users get their stale symlinks swept on the next install.
- The filesystem metadata remains the canonical "is this user-facing?" signal.

**Negative**:
- Three-line filter instead of one.
- A future contributor adding a new internal helper must remember to follow the `merge_driver_*` or `*-hook.sh` naming convention, or the helper ends up in `$PATH`.
- Non-executable scripts that are genuinely meant as user-facing must get `+x` in source control (which is the right convention anyway).

**Precedent**: The executable bit is the canonical signal for "user-facing CLI tool" in `scripts/`. Internal helpers follow one of two naming patterns (`merge_driver_*` or `*-hook.sh`). Anyone adding a new script should adopt these conventions.
