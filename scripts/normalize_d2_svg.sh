#!/usr/bin/env bash
# normalize_d2_svg.sh — Scrub the volatile d2 version stamp from rendered SVGs.
#
# WHY: d2 stamps `data-d2-version="<ver>"` into every SVG it renders. That string
# varies by *build provenance*, not just by version number — a Homebrew d2 0.7.1
# emits `0.7.1`, while the standalone release tarball emits `v0.7.1`. CI renders
# with the pinned standalone build; a contributor regenerating a diagram locally
# with a Homebrew d2 flips the stamp and fails the architecture.yml drift diff
# even though the diagram is byte-identical. Normalizing the attribute to a fixed
# constant on BOTH render paths — the local pre-commit regen
# (diagram-regen-hook.sh) and the CI render (.github/workflows/architecture.yml) —
# makes the stamp non-load-bearing and kills the whole drift class. This is the
# single source of truth for that normalization rule; both callers invoke it so
# they cannot drift apart (the drift between the two was the original bug).
#
# Idempotent. Operates in place via a temp-file swap so it is portable across
# BSD (macOS) and GNU (Linux/CI) sed without relying on `sed -i` flag differences.
# Files lacking the attribute (e.g. likec4-native SVGs) pass through untouched.
#
# Usage: normalize_d2_svg.sh <svg-file>...
set -euo pipefail

# Synthetic, build-independent placeholder. Any constant works; this one reads as
# deliberately scrubbed. The real pinned version lives in architecture.yml's d2
# install step, not in the committed artifact.
NORMALIZED_VERSION="pinned"

for svg in "$@"; do
    [ -f "${svg}" ] || continue
    tmp="${svg}.normtmp"
    sed -E "s/data-d2-version=\"[^\"]*\"/data-d2-version=\"${NORMALIZED_VERSION}\"/g" \
        "${svg}" > "${tmp}"
    mv "${tmp}" "${svg}"
done
