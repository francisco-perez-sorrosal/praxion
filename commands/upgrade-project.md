---
description: Re-point this project's version-pinned Praxion surfaces (git hooks, merge driver) to the live plugin install after an i-am plugin upgrade
argument-hint: "[--check | --dry-run]"
allowed-tools: [Bash(scripts/upgrade_project_pins.sh:*), Bash(bash:*), Bash(git:*), Bash(jq:*), Bash(ls:*), Bash(readlink:*), Read]
disable-model-invocation: true
---

# Upgrade Praxion pins for this project

Reconcile the four **version-pinned** surfaces that `/onboard-project` installed
into this project so they point at the **currently installed** i-am plugin
version. Run this once after upgrading the i-am plugin (e.g. `0.8.0 → 0.9.0`):
the per-project git-hook symlinks and merge-driver registration encode the old
plugin-cache path, which is garbage-collected on upgrade, leaving them dangling.

This is the focused, gate-free counterpart to re-running the full
`/onboard-project` — it touches only what a version bump invalidates:

1. The three finalize-hook symlinks (`post-merge`, `post-commit`, `post-checkout`)
2. The `merge.observations-jsonl.driver` git config
3. Any retired merge driver + its `.gitattributes` line (cross-version cleanup)
4. The `.ai-state/.praxion-onboard.json` version stamp

The pre-commit hook resolves the plugin path at run time, so it is never stale
and is left untouched.

## What this command does

The reconciliation logic lives in the deterministic, idempotent script
`scripts/upgrade_project_pins.sh` (resolved from the live i-am plugin install).
This command is a thin wrapper that runs it against the current project,
surfaces the result, and reminds you to commit.

### Arguments

- (none) — apply the reconciliation and `git add` the touched tracked files
  (`.gitattributes`, `.ai-state/.praxion-onboard.json`). **Never commits** — you
  review and commit.
- `--check` — report drift only; exit non-zero if any pin is stale. Mutates
  nothing. Use in CI or before deciding to upgrade.
- `--dry-run` — print what would change; mutate nothing.

## Process

1. **Resolve the script.** Get the live i-am install path from
   `~/.claude/plugins/installed_plugins.json`:
   ```bash
   PLUGIN_ROOT="$(jq -r '.plugins["i-am@bit-agora"][0].installPath' "$HOME/.claude/plugins/installed_plugins.json")"
   ```
   If that is null/empty, tell the user the i-am plugin is not installed and stop
   — there is nothing to re-point *to*. (Install via
   `claude plugin install i-am@bit-agora` or `./install.sh code` from a Praxion
   checkout.)

2. **Run the reconciler**, forwarding `$ARGUMENTS` (`--check` / `--dry-run` or
   nothing). The script auto-detects the repo root via `git rev-parse`:
   ```bash
   bash "$PLUGIN_ROOT/scripts/upgrade_project_pins.sh" $ARGUMENTS
   ```

3. **Report the outcome** verbatim from the script — which surfaces were stale,
   what was re-pointed, and what was staged.

4. **If changes were applied** (not `--check`/`--dry-run`), remind the user that
   the staged changes are ready and propose a commit message — do **not** commit
   for them:
   ```
   chore: re-point Praxion pins to <version>
   ```
   Note that the hook symlink and git-config changes are **not** tracked files
   (they live in `.git/`), so the staged diff only covers `.gitattributes` and
   the onboard manifest. The hook/driver re-points take effect immediately.

## Notes

- **Idempotent.** Re-running on an already-current project is a no-op.
- **Safe on dev/self-host installs.** A finalize-hook symlink that already
  resolves to a real file outside the `/i-am/<version>/` cache (a `--plugin-dir`
  dev install, or Praxion's own self-hosted tree) is recognized and left alone.
- **Never overwrites a non-Praxion hook or merge driver** — a foreign value in
  the `merge.observations-jsonl.driver` slot is reported and left as-is; a
  non-Praxion hook is backed up to `<name>.pre-praxion` before installing.
- This command is the maintenance path; the full `/onboard-project` re-run still
  works and reconciles the same surfaces as part of its broader flow.
