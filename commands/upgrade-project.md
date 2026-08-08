---
description: Re-point this project's version-pinned Praxion surfaces (git hooks, merge driver) to the live plugin install after a praxion plugin upgrade
argument-hint: "[--check | --dry-run]"
allowed-tools: [Bash(scripts/upgrade_project_pins.sh:*), Bash(bash:*), Bash(git:*), Bash(gh:*), Bash(jq:*), Bash(ls:*), Bash(readlink:*), Bash(python3:*), Read]
disable-model-invocation: true
---

# Upgrade Praxion pins for this project

Reconcile the **version-pinned** surfaces that `/onboard-project` installed
into this project so they point at the **currently installed** praxion plugin
version. Run this once after upgrading the praxion plugin (e.g. `0.8.0 → 0.9.0`):
the per-project git-hook symlinks and merge-driver registration encode the old
plugin-cache path, which is garbage-collected on upgrade, leaving them dangling.

This is the focused, gate-free counterpart to re-running the full
`/onboard-project` — it touches only what a version bump invalidates:

1. The three finalize-hook symlinks (`post-merge`, `post-commit`, `post-checkout`)
2. The `merge.observations-jsonl.driver` git config
3. Any retired merge driver + its `.gitattributes` line (cross-version cleanup)
4. The `.ai-state/.praxion-onboard.json` version stamp
5. The `ci-autofix.yml` caller's pinned hub commit reference (re-pointed to the
   current tip), the `cross-model-review.yml` caller (added when absent and
   `autofix-policy.yml`'s gate allows it), and the `labels-reconcile.yml`
   caller's pinned hub commit reference (re-pointed the same way as the
   `ci-autofix.yml` caller) — reconciled only when `gh` can resolve the
   current hub commit for this run; skipped with an advisory otherwise (see
   Process, below). Never overwrites an existing `cross-model-review.yml`,
   and never touches a foreign / hand-edited / non-SHA-pinned `ci-autofix.yml`
   or `labels-reconcile.yml` caller.
6. When `.github/labels.yml` exists, its `baseline:` block is refreshed from
   `claude/project-baseline/labels/labels.yml.tmpl` (resolved from the live
   plugin install) via `scripts/refresh_labels_baseline.py`, preserving the
   project's `additional:` block — and any comments around either key —
   untouched. This runs whenever the manifest is present — it needs no
   cross-repo commit pin, only the shipped template.

The pre-commit hook resolves the plugin path at run time, so it is never stale
and is left untouched.

## What this command does

The reconciliation logic lives in the deterministic, idempotent script
`scripts/upgrade_project_pins.sh` (resolved from the live praxion plugin install).
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

1. **Resolve the script.** Get the live praxion install path from
   `~/.claude/plugins/installed_plugins.json`:
   ```bash
   PLUGIN_ROOT="$(jq -r '.plugins["praxion@bit-agora"][0].installPath' "$HOME/.claude/plugins/installed_plugins.json")"
   ```
   If that is null/empty, tell the user the praxion plugin is not installed and stop
   — there is nothing to re-point *to*. (Install via
   `claude plugin install praxion@bit-agora` or `./install.sh code` from a Praxion
   checkout.)

2. **Resolve the current hub SHA**, so surface 5 (the ci-autofix caller
   re-point + cross-model-review add + labels-reconcile caller re-point)
   always uses a real, current commit — never a placeholder, and never a
   mutable tag or branch ref:
   ```bash
   NEW_SHA="$(gh api repos/francisco-perez-sorrosal/praxion/commits/main --jq .sha 2>/dev/null)" || NEW_SHA=""
   ```
   Validate the result matches **40 hex characters** before forwarding it —
   this is the same `gh api` + `--jq .sha` resolution call and 40-hex
   validation onboard sub-step 8e.8 uses to resolve `{{HUB_SHA}}`:
   ```bash
   printf '%s' "$NEW_SHA" | grep -Eq '^[0-9a-f]{40}$' || NEW_SHA=""
   ```
   If `gh` is unavailable, unauthenticated, or the call above produced
   anything other than a 40-hex SHA, print an advisory to the user and skip
   surface 5 entirely for this run — proceed without `--hub-sha`; the four
   pre-existing surfaces still reconcile normally:
   ```
   Advisory: gh is unavailable or unauthenticated — the ci-autofix SHA
   re-point and cross-model-review add are skipped this run. The four
   pre-existing surfaces still reconcile below.
   ```

3. **Run the reconciler**, forwarding `$ARGUMENTS` (`--check` / `--dry-run` or
   nothing). The script auto-detects the repo root via `git rev-parse`. When
   `NEW_SHA` resolved successfully, forward it:
   ```bash
   bash "$PLUGIN_ROOT/scripts/upgrade_project_pins.sh" --hub-sha "$NEW_SHA" $ARGUMENTS
   ```
   Otherwise, run without `--hub-sha` — the script skips surface 5 and
   reconciles the four pre-existing surfaces exactly as before:
   ```bash
   bash "$PLUGIN_ROOT/scripts/upgrade_project_pins.sh" $ARGUMENTS
   ```

4. **Refresh the labels-taxonomy baseline**, independent of whether `NEW_SHA`
   resolved (this surface needs no hub SHA — only the shipped template). If
   `.github/labels.yml` exists at the repo root, run
   `scripts/refresh_labels_baseline.py`:
   ```bash
   python3 "$PLUGIN_ROOT/scripts/refresh_labels_baseline.py" \
     "$PLUGIN_ROOT/claude/project-baseline/labels/labels.yml.tmpl" .github/labels.yml
   ```
   This replaces the manifest's Praxion-owned `baseline:` block with the
   currently-shipped template's, preserving the project's `additional:` block
   — and any comments around either key — untouched. `git add .github/labels.yml`
   if it changed. Skip entirely (no print needed) when `.github/labels.yml`
   is absent.

5. **Report the outcome** verbatim from the script — which surfaces were
   stale, what was re-pointed, and what was staged. If the script's
   `[caller]` section reports the `cross-model-review.yml` caller was
   installed this run, print the one-time operator step (never auto-run it —
   the same print-not-inject convention onboard 8e.8 uses for this secret):
   ```
   gh secret set CURSOR_API_KEY
   ```
   Without it, the review gate's reviewer step no-ops.

6. **If changes were applied** (not `--check`/`--dry-run`), remind the user that
   the staged changes are ready and propose a commit message — do **not** commit
   for them:
   ```
   chore: re-point Praxion pins to <version>
   ```
   Note that the hook symlink and git-config changes are **not** tracked files
   (they live in `.git/`), so the staged diff covers `.gitattributes`, the
   onboard manifest, and — when surface 5 reconciled — the caller workflow
   file(s) under `.github/workflows/`. The hook/driver re-points take effect
   immediately.

## Notes

- **Idempotent.** Re-running on an already-current project is a no-op.
- **Safe on dev/self-host installs.** A finalize-hook symlink that already
  resolves to a real file outside the `/praxion/<version>/` cache (a `--plugin-dir`
  dev install, or Praxion's own self-hosted tree) is recognized and left alone.
- **Never overwrites a non-Praxion hook or merge driver** — a foreign value in
  the `merge.observations-jsonl.driver` slot is reported and left as-is; a
  non-Praxion hook is backed up to `<name>.pre-praxion` before installing.
- **Surface 5 is gh-gated, not a hard dependency.** A missing or unauthenticated
  `gh` never fails the whole upgrade — it only skips the ci-autofix SHA
  re-point, the cross-model-review add, and the labels-reconcile caller
  re-point; the four pre-existing surfaces reconcile regardless.
- **The labels-taxonomy baseline refresh (surface 6) needs no `gh` and no hub
  SHA** — it runs whenever `.github/labels.yml` is present, independent of
  whether surface 5 resolved this run.
- This command is the maintenance path; the full `/onboard-project` re-run still
  works and reconciles the same surfaces as part of its broader flow.
- **Known gap — the plugin namespace rename (`i-am` → `praxion`) is not
  reconciled here.** Two shipped templates embed the plugin namespace in text
  this command does not re-render: `.github/workflows/architecture.yml` (a
  `Load the <ns>:architect-validator agent` prompt) and the Block D pre-commit
  fragment. Both **fail open** — the workflow reports green while the
  architecture sweep never runs, and the golden-rule gate stops enforcing
  behind a single `info:` line — so nothing surfaces the breakage on its own.
  A project onboarded before the rename must update both by hand until
  `td-145` closes. Check with
  `grep -rn 'i-am:' .github/ .pre-commit-config.yaml` in the managed project.
