#!/usr/bin/env bash
# diagram-regen-hook.sh — Pre-commit regeneration of LikeC4 → D2 → SVG artifacts.
#
# Called from scripts/git-pre-commit-hook.sh when that script detects that this
# file is executable and present in the same scripts/ directory.
#
# Behavior:
#   1. Detects staged *.c4 files under any diagrams/ subdirectory.
#   2. If none are staged, exits 0 immediately (no-op).
#   3. Gracefully skips (exit 0, stderr warning) when likec4 or d2 are missing.
#   4. For each staged <name>.c4 model:
#        a. Runs `likec4 gen <fmt> <name>.c4 -o <name>/` for each configured format.
#        b. For d2 format: runs `d2 <name>/<view>.d2 <name>/<view>.svg` for each view.
#        c. Stages all generated artifacts with `git add`.
#   5. On render failure: prints failing command + stderr and exits 1.
#   6. Exits 0 on success.
#
# Render-format flexibility:
#   LIKEC4_FORMATS env var is a space-separated list of output formats.
#   Default: "d2". Future additions (mermaid, png) are a config change, not a
#   code rewrite. Only d2 drives a downstream SVG render step.
#
# See: docs/architecture-diagrams.md

set -eo pipefail

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Space-separated list of likec4 output formats to generate.
# Override via LIKEC4_FORMATS env var; default is d2 only.
LIKEC4_FORMATS="${LIKEC4_FORMATS:-d2}"

# ---------------------------------------------------------------------------
# Detect staged .c4 files
# ---------------------------------------------------------------------------

STAGED_C4="$(git diff --cached --name-only --diff-filter=ACMR \
    | grep -E '.*/diagrams/.*\.c4$' \
    || true)"

if [ -z "$STAGED_C4" ]; then
    exit 0
fi

# ---------------------------------------------------------------------------
# Binary availability checks (graceful skip)
# ---------------------------------------------------------------------------

if ! command -v likec4 >/dev/null 2>&1; then
    echo "[diagram-regen] likec4 not installed; skipping diagram regeneration." \
        "See docs/architecture-diagrams.md for install instructions." >&2
    exit 0
fi

if ! command -v d2 >/dev/null 2>&1; then
    echo "[diagram-regen] d2 not installed; skipping diagram regeneration." \
        "See docs/architecture-diagrams.md for install instructions." >&2
    exit 0
fi

# ---------------------------------------------------------------------------
# Regenerate artifacts for each staged .c4 file
# ---------------------------------------------------------------------------

generate_format() {
    local src="$1"   # path to <name>.c4
    local fmt="$2"   # format: d2 | mermaid | png | ...
    local out_dir="${src%.c4}"  # strip .c4 suffix to get the output directory

    echo "[diagram-regen] Generating ${fmt} from ${src} → ${out_dir}/" >&2

    local gen_stderr
    if ! gen_stderr="$(likec4 gen "${fmt}" "${src}" -o "${out_dir}/" 2>&1)"; then
        echo "[diagram-regen] ERROR: likec4 gen ${fmt} failed for ${src}" >&2
        echo "${gen_stderr}" >&2
        return 1
    fi

    # For d2 format, render each generated .d2 file to .svg
    if [ "${fmt}" = "d2" ]; then
        render_d2_views "${out_dir}"
    fi

    git add "${out_dir}/"
}

render_d2_views() {
    local dir="$1"

    # Find all .d2 files produced in the output directory
    local d2_files
    d2_files="$(find "${dir}" -maxdepth 1 -name "*.d2" 2>/dev/null || true)"

    if [ -z "${d2_files}" ]; then
        echo "[diagram-regen] WARNING: no .d2 files found in ${dir}/" >&2
        return 0
    fi

    while IFS= read -r d2_file; do
        local svg_file="${d2_file%.d2}.svg"
        echo "[diagram-regen]   Rendering ${d2_file} → ${svg_file}" >&2

        local render_stderr
        if ! render_stderr="$(d2 "${d2_file}" "${svg_file}" 2>&1)"; then
            echo "[diagram-regen] ERROR: d2 render failed for ${d2_file}" >&2
            echo "${render_stderr}" >&2
            return 1
        fi
    done <<< "${d2_files}"
}

while IFS= read -r c4_file; do
    [ -z "${c4_file}" ] && continue

    for fmt in ${LIKEC4_FORMATS}; do
        generate_format "${c4_file}" "${fmt}"
    done
done <<< "${STAGED_C4}"

echo "[diagram-regen] Diagram regeneration complete." >&2
exit 0
