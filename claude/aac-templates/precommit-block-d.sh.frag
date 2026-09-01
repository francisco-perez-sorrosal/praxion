# ---------------------------------------------------------------------------
# Block D: AaC golden-rule gate
#
# HOW TO USE: Append this fragment to your existing .git/hooks/pre-commit
# AFTER any prior blocks (Blocks A, B, C if present). Do not replace existing
# blocks. Installed by /onboard-project Phase 8b.
#
# Trigger: staged paths touch architectural surfaces (docs/diagrams/, *.c4,
# ARCHITECTURE.md, docs/architecture.md).
#
# Blocks the commit if a generated artifact was edited without staging the
# corresponding source change and without an adjacent override comment.
#
# Script resolution: ${PLUGIN_ROOT} is derived at hook-run time from
# ~/.claude/plugins/installed_plugins.json via the same jq key loop as the
# id-citation block installed in Phase 4. If the plugin is not installed,
# Block D exits cleanly (skip-gracefully guard below).
# ---------------------------------------------------------------------------

STAGED_AAC="$(git diff --cached --name-only --diff-filter=ACMR \
    | grep -E '^(docs/diagrams/|.*\.c4$|.*ARCHITECTURE\.md$|docs/architecture\.md$)' \
    || true)"

if [ -n "$STAGED_AAC" ]; then
    # Resolve plugin install path from installed_plugins.json — the registry is
    # {"version": N, "plugins": {"<name>@<marketplace>": [{"installPath": ...}]}},
    # so the lookup must go through .plugins[$k][0].installPath (the flat
    # top-level walk a previous version of this block used never resolved).
    PLUGIN_ROOT=""
    PLUGINS_JSON="$HOME/.claude/plugins/installed_plugins.json"
    if [ -f "$PLUGINS_JSON" ] && command -v jq >/dev/null 2>&1; then
        for AAC_KEY in "praxion@bit-agora" "i-am@bit-agora"; do
            AAC_CANDIDATE="$(jq -r --arg k "$AAC_KEY" \
                '.plugins[$k][0].installPath // empty' "$PLUGINS_JSON" 2>/dev/null)"
            if [ -n "$AAC_CANDIDATE" ] && [ -d "$AAC_CANDIDATE" ]; then
                PLUGIN_ROOT="$AAC_CANDIDATE"
                break
            fi
        done
    fi

    # Skip-gracefully guard: if plugin root not found, exit 0 (non-blocking)
    if [ -z "$PLUGIN_ROOT" ]; then
        echo "info: praxion plugin not found in installed_plugins.json — skipping Block D golden-rule gate"
    else
        AAC_SCRIPT="${PLUGIN_ROOT}/scripts/check_aac_golden_rule.py"
        if [ ! -f "$AAC_SCRIPT" ]; then
            echo "info: check_aac_golden_rule.py not found in plugin — skipping Block D golden-rule gate"
        else
            AAC_EXIT=0
            python3 "$AAC_SCRIPT" --mode=gate || AAC_EXIT=$?
            if [ "$AAC_EXIT" -ne 0 ]; then
                cat >&2 <<'BLOCK_D_EOF'

error: AaC golden-rule violation(s) detected in staged files.

  A generated artifact (docs/diagrams/<name>/<view>.{d2,svg} or content
  inside an aac:generated fence) was edited without a co-staged source
  change. Either:

  1. Stage the corresponding source file (.c4 or the fence's source= path)
     so the generated artifact is regenerated from the model, OR

  2. Add a line-adjacent override comment to justify the hand-edit:
       # aac-override: <reason>               (code/d2/yaml/sh)
       <!-- aac-override: <reason> -->        (SVG/HTML/Markdown)

  Convention: rules/writing/aac-dac-conventions.md (Override Syntax)
  Bypass (risky): git commit --no-verify
BLOCK_D_EOF
                exit 1
            fi
        fi
    fi
fi
