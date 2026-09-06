---
description: Re-point this project's version-pinned Praxion surfaces (git hooks, merge driver, CI callers, labels baseline, AaC surfaces) to the live plugin install after a praxion plugin upgrade
argument-hint: "[--check | --dry-run]"
allowed-tools: [Bash(bash:*), Bash(git:*), Bash(gh:*), Bash(jq:*), Read]
disable-model-invocation: true
---

# Upgrade Praxion pins for this project

Reconcile the surfaces that `/onboard-project` installed into this **managed
project** so they point at the **currently installed** praxion plugin version.
Run this once after upgrading the praxion plugin (e.g. `0.25.0 → 0.26.0`): the
per-project git-hook symlinks and merge-driver registration encode the old
plugin-cache path, which is garbage-collected on upgrade, leaving them
dangling. (On Praxion's own self-hosted checkout every surface is recognized
as a dev install and the run is a no-op — the command targets onboarded
projects, not this repo.)

This is the focused, gate-free counterpart to re-running the full
`/onboard-project`. All reconciliation logic lives in the deterministic,
idempotent, tested script `scripts/upgrade_project_pins.sh` (resolved from the
live plugin install); this command is a thin wrapper that resolves the two
inputs the script must not fetch itself (the live plugin path and the current
hub SHA), runs it, and surfaces the result. The script reconciles:

1. The three finalize-hook symlinks (`post-merge`, `post-commit`, `post-checkout`)
2. The `merge.observations-jsonl.driver` git config
3. Any retired merge driver + its `.gitattributes` line (cross-version cleanup)
4. The `.ai-state/.praxion-onboard.json` version stamp
5. The hub-SHA-pinned workflow callers — `ci-autofix.yml` and
   `labels-reconcile.yml` re-pointed to the current hub commit, and
   `cross-model-review.yml` added when absent and the `autofix-policy.yml`
   gate allows it. Reconciled only when `gh` resolved a current hub SHA for
   this run (see Process step 2); a foreign, hand-edited, or non-SHA-pinned
   caller is always left untouched.
6. The `.github/labels.yml` `baseline:` block (delegated to
   `scripts/refresh_labels_baseline.py`), refreshed from the shipped
   template — the project's `additional:` block and surrounding comments are
   preserved. Mode-aware: `--check`/`--dry-run` report the verdict without
   touching the manifest.
7. The two AaC surfaces instantiated by onboarding's AaC tier (delegated to
   `scripts/reconcile_aac_surfaces.py`): the `architecture.yml` agent-load
   prompt and the pre-commit Block D fragment get their embedded plugin
   namespace re-pointed line-in-place, and a Block D carrying the broken
   pre-fix `PLUGIN_ROOT` resolution (which made the AaC gate silently skip on
   every commit) is structurally repaired from the shipped template. A
   hand-edited Block D is reported and left untouched.

The Phase-4 pre-commit hook body resolves the plugin path at run time, so it
never goes stale and is left alone — only its appended Block D fragment
(surface 7) can drift.

## Arguments

- (none) — apply the reconciliation and `git add` the touched tracked files.
  **Never commits** — you review and commit.
- `--check` — report drift only; exit non-zero if any pin is stale. Mutates
  nothing. Use in CI or before deciding to upgrade.
- `--dry-run` — print what would change; mutate nothing.

## Process

1. **Resolve the live plugin install path** from
   `~/.claude/plugins/installed_plugins.json`, preferring a project-scoped
   entry for this repo over user scope (the same precedence the script itself
   uses):
   ```bash
   PLUGIN_ROOT="$(jq -r --arg root "$(git rev-parse --show-toplevel)" '
     (.plugins["praxion@bit-agora"] // [])
     | (map(select(.scope=="project" and .projectPath==$root)) + map(select(.scope=="user")) + .)
     | (.[0].installPath // empty)' "$HOME/.claude/plugins/installed_plugins.json")"
   ```
   If that is empty, tell the user the praxion plugin is not installed and stop
   — there is nothing to re-point *to*. (Install via
   `claude plugin install praxion@bit-agora` or `./install.sh code` from a
   Praxion checkout.)

2. **Resolve the current hub SHA**, so surface 5 always uses a real, current
   commit — never a placeholder, and never a mutable tag or branch ref:
   ```bash
   NEW_SHA="$(gh api repos/francisco-perez-sorrosal/praxion/commits/main --jq .sha 2>/dev/null)" || NEW_SHA=""
   printf '%s' "$NEW_SHA" | grep -Eq '^[0-9a-f]{40}$' || NEW_SHA=""
   ```
   This is the same resolution call and 40-hex validation the onboarding CI
   sub-step uses for `{{HUB_SHA}}`. If `gh` is unavailable, unauthenticated,
   or anything other than a 40-hex SHA came back, print an advisory and
   proceed without `--hub-sha`:
   ```
   Advisory: gh is unavailable or unauthenticated — surface 5 (the hub-SHA
   caller re-points and the cross-model-review add) is skipped this run;
   the pre-existing surfaces 1–4 plus surfaces 6–7 still reconcile below.
   ```

3. **Run the reconciler**, forwarding `$ARGUMENTS` (`--check` / `--dry-run` or
   nothing) and, when it resolved, the hub SHA:
   ```bash
   bash "$PLUGIN_ROOT/scripts/upgrade_project_pins.sh" ${NEW_SHA:+--hub-sha "$NEW_SHA"} $ARGUMENTS
   ```

4. **Report the outcome** verbatim from the script — which surfaces were
   stale, what was re-pointed or repaired, and what was staged. If the
   `[caller]` section reports the `cross-model-review.yml` caller was
   installed this run, print the one-time operator step (never auto-run it —
   the same print-not-inject convention onboarding uses for this secret):
   ```
   gh secret set CURSOR_API_KEY
   ```
   Without it, the review gate's reviewer step no-ops.

5. **If changes were applied** (not `--check`/`--dry-run`), remind the user
   that the staged changes are ready and propose a commit message — do **not**
   commit for them:
   ```
   chore: re-point Praxion pins to <version>
   ```
   Note that the hook symlink, git-config, and Block D changes are **not**
   tracked files (they live in `.git/`), so the staged diff covers
   `.gitattributes`, the onboard manifest, and — when surfaces 5–7 reconciled
   — the touched `.github/` files. The hook/driver re-points take effect
   immediately.

6. **Point at the companion steps.** This command covers path/SHA/namespace
   pins; two sibling maintenance surfaces are intentionally out of its scope:
   - `/refresh-claude-blocks` — reconciles the four canonical `CLAUDE.md`
     blocks against the newly installed plugin (content-versioned, with an
     interactive disposition loop for locally customized blocks). Suggest
     running it after any plugin upgrade.
   - If the plugin itself hasn't been refreshed yet, that comes first:
     `claude plugin marketplace update` then `claude plugin update praxion`,
     and re-run this command afterwards.

## Notes

- **Idempotent.** Re-running on an already-current project is a no-op.
- **Safe on dev/self-host installs.** A finalize-hook symlink that already
  resolves to a real file outside the `/praxion/<version>/` cache (a
  `--plugin-dir` dev install, or Praxion's own self-hosted tree) is recognized
  and left alone.
- **Never overwrites a non-Praxion hook or merge driver** — a foreign value in
  the `merge.observations-jsonl.driver` slot is reported and left as-is; a
  non-Praxion hook is backed up to `<name>.pre-praxion` before installing.
- **Surface 5 is gh-gated, not a hard dependency.** A missing or
  unauthenticated `gh` never fails the whole upgrade — it only skips the
  hub-SHA caller surfaces; everything else reconciles regardless.
- **Relationship to `/onboard-project`.** A full onboarding re-run reconciles
  the version-aware core surfaces (hooks, merge driver, manifest) but **not**
  surfaces 5–7 — its idempotency predicates are file-existence guards that
  deliberately skip files that already exist, so the SHA-pinned callers, the
  labels baseline, and the instantiated AaC surfaces refresh **only** through
  this command. The two paths are complements, not alternatives.
- **Block D repair history.** Every Block D installed from the pre-fix
  template resolves `PLUGIN_ROOT` by walking the top level of
  `installed_plugins.json` (whose real shape nests installs under `.plugins`),
  so the AaC golden-rule gate silently skipped on every commit while printing
  a green result. Surface 7 detects that shape and replaces the block with the
  fixed shipped template. Confirm a project needed it with
  `grep -n 'data.items()' .git/hooks/pre-commit`. This particular repair also
  self-delivers: the finalize hook chain carries it as a backstop, so once the
  plugin is updated, the next merge/commit/checkout in a project heals its
  hook even if this command is never run. The earlier namespace-rename
  staleness (a project onboarded under the old plugin name carrying
  `i-am:architect-validator` in `architecture.yml`) is handled by the same
  surface's token re-point.
