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
7. Two AaC-tier surfaces instantiated by `/onboard-project` Phase 8b —
   `.github/workflows/architecture.yml`'s `architect-validator` agent-load
   prompt and the installed Block D pre-commit fragment's skip-gracefully
   notice — each re-pointed in place, line-for-line, when the namespace
   token they were rendered with has fallen behind the live template's
   (td-145). Neither needs `gh` or any commit resolution; both are
   independent of surfaces 5-6.

The pre-commit hook's `${PLUGIN_ROOT}` resolution runs at run time, so it is
never stale and is left untouched — only the literal Block D notice text
(surface 7) can drift.

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

5. **Reconcile the AaC namespace surfaces** (surface 7, td-145) —
   independent of whether `NEW_SHA` resolved, and independent of the
   labels-taxonomy refresh above. `/onboard-project` Phase 8b instantiates
   two templates into the project tree — `.github/workflows/architecture.yml`
   and a Block D fragment appended to `.git/hooks/pre-commit` — each
   embedding the plugin namespace in one line of static text. Neither is
   re-rendered by a later `/onboard-project` re-run (both sub-step
   predicates are file-existence guards that skip once the file exists) nor
   by the script-driven surfaces above, so a project onboarded before a
   plugin namespace change carries a permanently stale copy of both: the
   workflow's `claude-code-action` prompt asks for an agent name that will
   never resolve — nothing rejects an unresolvable agent name, so the job
   still reports **green** while the architecture sweep silently never runs
   — and the Block D skip-gracefully guard's `info:` notice misnames the
   plugin.

   Detect drift by comparing each installed file's namespace token against
   the **live template's** current token — never a hardcoded name, so this
   keeps working across future renames — and fix only that one line,
   in place, never a full re-render (which would clobber the project's
   `{{PROJECT_PATHS_DIAGRAMS}}` / `{{PROJECT_PYTHON_VERSION}}` /
   `{{PROJECT_PLUGIN_DIR}}` substitutions or any hand edits made since
   Phase 8b):
   ```bash
   case "$ARGUMENTS" in
     --check)   MODE="check" ;;
     --dry-run) MODE="dry-run" ;;
     *)         MODE="apply" ;;
   esac

   python3 - "$PLUGIN_ROOT" "$MODE" <<'PYEOF'
   import re
   import subprocess
   import sys
   from pathlib import Path

   plugin_root, mode = Path(sys.argv[1]), sys.argv[2]
   repo_root = Path(subprocess.run(
       ["git", "rev-parse", "--show-toplevel"],
       capture_output=True, text=True, check=True,
   ).stdout.strip()).resolve()

   # (label, template, installed, anchor pattern, line format, tracked-by-git)
   SURFACES = [
       (
           "architecture.yml",
           plugin_root / "claude/aac-templates/architecture.yml.tmpl",
           repo_root / ".github/workflows/architecture.yml",
           re.compile(r"Load the (\S+):architect-validator agent"),
           "Load the {}:architect-validator agent",
           True,
       ),
       (
           "pre-commit Block D",
           plugin_root / "claude/aac-templates/precommit-block-d.sh.frag",
           repo_root / ".git/hooks/pre-commit",
           re.compile(r"info: (\S+) plugin not found in installed_plugins\.json"),
           "info: {} plugin not found in installed_plugins.json",
           False,
       ),
   ]

   drift = False
   for label, template_path, installed_path, anchor, line_fmt, tracked in SURFACES:
       if not installed_path.exists():
           print(f"{label}: not installed — nothing to reconcile")
           continue
       current = anchor.search(template_path.read_text())
       installed_text = installed_path.read_text()
       installed = anchor.search(installed_text)
       if not current or not installed:
           print(f"{label}: anchor line not found — skipping (manual review)")
           continue
       if current.group(1) == installed.group(1):
           print(f"{label}: current (namespace={current.group(1)})")
           continue
       drift = True
       old_line = line_fmt.format(installed.group(1))
       new_line = line_fmt.format(current.group(1))
       if mode == "check":
           print(f"{label}: STALE — names '{installed.group(1)}', template now says '{current.group(1)}'")
       elif mode == "dry-run":
           print(f"{label}: would replace:\n  - {old_line}\n  + {new_line}")
       else:
           installed_path.write_text(installed_text.replace(old_line, new_line))
           print(f"{label}: fixed — re-pointed to '{current.group(1)}'")
           if tracked:
               subprocess.run(["git", "add", str(installed_path)], cwd=repo_root, check=True)

   if mode == "check" and drift:
       sys.exit(1)
   PYEOF
   ```
   A second run after applying finds both surfaces `current` and prints
   nothing further to fix — idempotent by construction, since the check is a
   direct string comparison against the live template rather than an
   unconditional overwrite.

6. **Report the outcome** verbatim from the script and from Step 5 — which
   surfaces were stale, what was re-pointed, and what was staged. If the
   script's `[caller]` section reports the `cross-model-review.yml` caller
   was installed this run, print the one-time operator step (never auto-run
   it — the same print-not-inject convention onboard 8e.8 uses for this
   secret):
   ```
   gh secret set CURSOR_API_KEY
   ```
   Without it, the review gate's reviewer step no-ops.

7. **If changes were applied** (not `--check`/`--dry-run`), remind the user that
   the staged changes are ready and propose a commit message — do **not** commit
   for them:
   ```
   chore: re-point Praxion pins to <version>
   ```
   Note that the hook symlink, git-config, and Block D fragment changes are
   **not** tracked files (they live in `.git/`), so the staged diff covers
   `.gitattributes`, the onboard manifest, and — when surface 5 or surface 7
   reconciled — the caller workflow file(s) and/or `.github/workflows/architecture.yml`.
   The hook/driver re-points take effect immediately.

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
- **Surface 7 needs no `gh` and no hub SHA either** — like surface 6, it
  diffs the live template against the installed file directly, so it
  reconciles regardless of whether surface 5 resolved this run. Unlike
  surface 6, it patches only the one line that changed per file — never a
  full re-render — so project-specific template substitutions and any hand
  edits survive untouched.
- This command is the maintenance path; the full `/onboard-project` re-run still
  works and reconciles the same surfaces as part of its broader flow.
- **Historical note (td-145).** Before surface 7 shipped, a plugin namespace
  rename (e.g. `i-am` → `praxion`) left `.github/workflows/architecture.yml`
  and the installed Block D fragment silently stale in any project onboarded
  before the rename — both fail open (green CI with no sweep ever running; a
  skip notice naming the wrong plugin). Step 5 above now detects and fixes
  both. Confirm a pre-surface-7 project needed it with
  `grep -rn 'i-am:' .github/workflows/architecture.yml .git/hooks/pre-commit`.
