#!/usr/bin/env bash
# Git pre-commit hook: Praxion-internal shipped-artifact checks.
#
# Runs two independent checks. Both must pass for the commit to proceed.
#
# Block A — Shipped-artifact isolation. Blocks the commit if any staged
# Markdown file under a shipped surface (rules/, skills/, agents/, commands/,
# claude/config/, claude/canonical-blocks/) references a specific .ai-state/
# or .ai-work/ entry. Test fixtures under **/tests/fixtures/** are excluded.
# Intentional exceptions: add  <!-- shipped-artifact-isolation:ignore -->  on
# the same line.  See rules/swe/shipped-artifact-isolation.md.
#
# Block B — Canonical-block sync. Blocks the commit if any staged
# claude/canonical-blocks/*.md file or either onboarding command file is out
# of sync per scripts/sync_canonical_blocks.py --check. Fix by editing the
# canonical file and running scripts/sync_canonical_blocks.py --write.
#
# This hook is Praxion-author-only -- user projects get a tailored inline
# pre-commit hook from /onboard-project Phase 4 that runs only the inbound
# id-citation check.
#
# Installed by install_claude.sh into .git/hooks/pre-commit.

set -eo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"
if [ -z "$REPO_ROOT" ]; then
    exit 0
fi

# ---------------------------------------------------------------------------
# Block A: Shipped-artifact isolation
# ---------------------------------------------------------------------------

ISO_SCRIPT="$REPO_ROOT/scripts/check_shipped_artifact_isolation.py"
if [ -f "$ISO_SCRIPT" ]; then
    # Collect staged .md files under shipped surfaces (Added, Copied, Modified,
    # Renamed; ignores deletions).
    STAGED_ISO="$(git diff --cached --name-only --diff-filter=ACMR \
        | grep -E '^(rules|skills|agents|commands|claude/config|claude/canonical-blocks)/.*\.md$' \
        || true)"

    if [ -n "$STAGED_ISO" ]; then
        # shellcheck disable=SC2086
        if ! python3 "$ISO_SCRIPT" --repo-root "$REPO_ROOT" --files $STAGED_ISO; then
            cat >&2 <<'EOF'

error: shipped-artifact isolation violation(s) detected in staged files.

  Shipped surfaces (rules/, skills/, agents/, commands/, claude/config/,
  claude/canonical-blocks/) must not reference specific .ai-state/ or
  .ai-work/ entries -- those are per-project meta-state and would dangle
  when the plugin installs elsewhere.

  Fix the flagged lines, or -- if the reference is genuinely intentional --
  append this marker to the same line:

      <!-- shipped-artifact-isolation:ignore -->

  Rule:           rules/swe/shipped-artifact-isolation.md
  Bypass (risky): git commit --no-verify
EOF
            exit 1
        fi
    fi
fi

# ---------------------------------------------------------------------------
# Block B: Canonical-block sync
# ---------------------------------------------------------------------------

SYNC_SCRIPT="$REPO_ROOT/scripts/sync_canonical_blocks.py"
if [ -f "$SYNC_SCRIPT" ]; then
    # Trigger only when staged paths include canonical-block files or either
    # of the two consumer command files. This keeps the check fast for the
    # common case (commit that does not touch the canonical-block surface).
    STAGED_SYNC="$(git diff --cached --name-only --diff-filter=ACMR \
        | grep -E '^(claude/canonical-blocks/.*\.md|commands/(onboard-project|new-project)\.md)$' \
        || true)"

    if [ -n "$STAGED_SYNC" ]; then
        if ! python3 "$SYNC_SCRIPT" --check; then
            cat >&2 <<'EOF'

error: canonical-block drift detected.

  The four canonical CLAUDE.md blocks (Agent Pipeline, Compaction Guidance,
  Behavioral Contract, Praxion Process) live at claude/canonical-blocks/<slug>.md
  and are embedded byte-identically in commands/onboard-project.md and
  commands/new-project.md.

  To fix:
    1. Edit the canonical file at claude/canonical-blocks/<slug>.md
    2. Run: python3 scripts/sync_canonical_blocks.py --write
    3. Re-stage the updated command files and re-commit

  Bypass (risky): git commit --no-verify
EOF
            exit 1
        fi
    fi
fi

# ---------------------------------------------------------------------------
# Block C: Diagram regeneration
# ---------------------------------------------------------------------------

# Run the diagram-regen-hook if it exists alongside this script and is
# executable. Produces .d2 and .svg artifacts from staged .c4 sources.
# Gracefully skips when likec4 or d2 binaries are absent.
DIAGRAM_HOOK="$(dirname "$0")/diagram-regen-hook.sh"
if [ -f "$DIAGRAM_HOOK" ] && [ -x "$DIAGRAM_HOOK" ]; then
    if ! "$DIAGRAM_HOOK"; then
        exit 1
    fi
fi

exit 0
