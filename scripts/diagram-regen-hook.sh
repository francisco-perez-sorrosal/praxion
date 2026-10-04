#!/usr/bin/env bash
# diagram-regen-hook.sh — pre-commit entry for the `diagram-regen` hook.
#
# A thin wrapper: every regeneration rule (pinned versions, the four regeneration
# failures, which renders to write and stage) lives in the regeneration command,
# scripts/regenerate_diagrams.py, run here in `--staged` mode. pre-commit fires the
# hook only when a staged path matches `\.c4$` (.pre-commit-config.yaml).
#
# The toolchain check runs before any `python3` call, so a commit made without
# likec4 or d2 proceeds with a warning even when the system Python shim is broken.
# Past that check the command decides; this script never calls likec4 or d2 itself.
#
# Exit status: the command's (0 renders written and staged, 1 a regeneration
# failure that aborts the commit, 2 a usage error), or 0 after the skip warning.
#
# See: docs/architecture-diagrams.md

set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REGENERATE="${SCRIPT_DIR}/regenerate_diagrams.py"

for tool in likec4 d2; do
    if ! command -v "${tool}" >/dev/null 2>&1; then
        echo "[diagram-regen] WARN ${tool} not installed; skipping diagram regeneration." \
            "See docs/architecture-diagrams.md for install instructions." >&2
        exit 0
    fi
done

exec python3 "${REGENERATE}" --staged
