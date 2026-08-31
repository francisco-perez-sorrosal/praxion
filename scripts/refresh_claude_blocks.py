#!/usr/bin/env python3
"""Classify a managed project's live CLAUDE.md blocks against the shipped
canonical-block history manifest (run-time consumer half of the refresh
mechanism; ``sync_canonical_blocks.py --write-history`` is the build-time
producer).

For each refresh-eligible slug (``canonical_block_identity.REFRESHABLE_SLUGS``)
present in the manifest, extracts the block's live body from the target
project's ``CLAUDE.md`` and classifies it:

* ``absent``   -- the heading is missing entirely.
* ``current``  -- the live body's hash matches the manifest's current hash.
* ``stale``    -- the live body's hash matches an older (non-current)
  manifest entry -- unmodified boilerplate that can be safely replaced.
* ``modified`` -- the live body's hash matches no manifest entry at all --
  locally customized content that must never be overwritten.

Self-onboard guard: refuses to run against a Claude Code plugin source repo
(``.claude-plugin/plugin.json`` present at the target root) unless
``PRAXION_ALLOW_SELF_ONBOARD=1`` is set -- mirrors the guard already applied
by ``/onboard-project`` and ``/new-project`` (dec-081).

Apply-mode (``--apply``) acts on the classification: an absent block is
appended, a stale block is replaced in place, and a modified block is never
touched -- a unified diff and a pointer to the interactive command are
printed instead.

Three invocation modes:

    refresh_claude_blocks.py --check   # report + exit 1 unless all current
    refresh_claude_blocks.py --json    # machine-readable {slug: classification}
    refresh_claude_blocks.py --apply   # append absent, replace stale, refuse modified

Exit codes:
    0 -- all eligible blocks current (--check); the script ran cleanly
         (--json); or --apply ran cleanly (always 0, barring a script error --
         a refused modified block is normal, expected behavior)
    1 -- one or more eligible blocks are not current (--check only)
    2 -- self-onboard guard refusal, or a script error (missing/unreadable
         file, malformed manifest, not inside a git repository)

Usage:
    python3 scripts/refresh_claude_blocks.py [--check | --json | --apply]
        [--repo-root <path>] [--manifest <path>]
"""

from __future__ import annotations

import argparse
import difflib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import NoReturn

from canonical_block_identity import (
    REFRESHABLE_SLUGS,
    extract_live_body,
    find_heading_span,
    hash_block_body,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
_SHIPPED_REPO_ROOT = SCRIPT_DIR.parent

# Where a slug's current canonical body *text* lives -- the manifest only
# ever stores hashes, so apply-mode's append/replace actions read the body
# from here. Overridable, mirroring sync_canonical_blocks.py's CANONICAL_DIR.
CANONICAL_DIR = _SHIPPED_REPO_ROOT / "claude" / "canonical-blocks"

SELF_ONBOARD_OVERRIDE_ENV = "PRAXION_ALLOW_SELF_ONBOARD"


def _default_manifest_path() -> Path:
    """The shipped history manifest, resolved relative to this script's install location."""
    return _SHIPPED_REPO_ROOT / "claude" / "canonical-blocks" / "block-history.json"


# ---------------------------------------------------------------------------
# Error helper (genuine script errors only -- never used for the self-onboard
# guard, whose refusal is a normal, testable `main()` return value)
# ---------------------------------------------------------------------------


def _error(message: str) -> NoReturn:
    """Print a script-error message and exit 2."""
    print(f"error: {message}", file=sys.stderr)
    sys.exit(2)


# ---------------------------------------------------------------------------
# Self-onboard guard (mirrors dec-081's onboarding-command guard)
# ---------------------------------------------------------------------------


def _is_plugin_source_repo(repo_root: Path) -> bool:
    """True when repo_root carries a Claude Code plugin manifest at its root."""
    return (repo_root / ".claude-plugin" / "plugin.json").is_file()


def _self_onboard_guard_refusal(repo_root: Path) -> str | None:
    """Return a refusal message when the guard should fire, else None.

    Refuses only when repo_root is a plugin source repo AND the override env
    var is not set to "1" -- mirrors dec-081. Returning a message (rather
    than exiting) keeps the guard a plain, testable value the caller reports
    through `main()`'s normal return path.
    """
    if not _is_plugin_source_repo(repo_root):
        return None
    if os.environ.get(SELF_ONBOARD_OVERRIDE_ENV) == "1":
        return None
    return (
        f"refusing to run against {repo_root} -- it looks like a Claude Code "
        "plugin source repo (.claude-plugin/plugin.json present). Set "
        f"{SELF_ONBOARD_OVERRIDE_ENV}=1 to override."
    )


# ---------------------------------------------------------------------------
# Classification core
# ---------------------------------------------------------------------------


def classify_block(live_body: str | None, manifest_entry: dict) -> str:
    """Classify a block's live body against its manifest entry.

    Returns one of "absent" / "current" / "stale" / "modified". The
    current-hash match is checked before history membership: a manifest
    entry's history always contains the current hash as its last element
    (the shipped invariant), so checking membership first would misclassify
    every current block as stale.
    """
    if live_body is None:
        return "absent"

    live_hash = hash_block_body(live_body)
    if live_hash == manifest_entry["current"]:
        return "current"
    if live_hash in manifest_entry["history"]:
        return "stale"
    return "modified"


def _heading_for_slug(slug: str) -> str:
    """Derive a slug's canonical heading line, e.g. 'agent-pipeline' -> '## Agent Pipeline'."""
    return f"## {slug.replace('-', ' ').title()}"


def _read_claude_md(repo_root: Path) -> str:
    """Read the target repo's CLAUDE.md once; "" when absent.

    Read exactly once per invocation and threaded through both
    ``_classify_all`` and ``run_apply`` -- a second independent read would be
    a TOCTOU double-read of the same file within one process, however
    unlikely to observe a change in the single-threaded CLI path.
    """
    claude_md_path = repo_root / "CLAUDE.md"
    return claude_md_path.read_text(encoding="utf-8") if claude_md_path.is_file() else ""


def _classify_all(claude_md_text: str, manifest: dict) -> dict[str, str]:
    """Classify every refresh-eligible slug present in the manifest.

    Scoped to the intersection of the manifest's slugs and REFRESHABLE_SLUGS
    -- a hard membership boundary enforced here regardless of what a
    hand-edited or malformed manifest might otherwise carry.
    """
    eligible_slugs = sorted(set(manifest.get("blocks", {})) & REFRESHABLE_SLUGS)
    classifications: dict[str, str] = {}
    for slug in eligible_slugs:
        live_body = extract_live_body(claude_md_text, _heading_for_slug(slug))
        classifications[slug] = classify_block(live_body, manifest["blocks"][slug])
    return classifications


# ---------------------------------------------------------------------------
# Manifest + repo-root resolution
# ---------------------------------------------------------------------------


def _load_manifest(manifest_path: Path) -> dict:
    """Read and parse the history manifest. Exits 2 on any I/O or parse failure."""
    try:
        text = manifest_path.read_text(encoding="utf-8")
    except OSError as exc:
        _error(f"cannot read manifest {manifest_path}: {exc}")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        _error(f"malformed manifest {manifest_path}: {exc}")


def _resolve_repo_root(repo_root_arg: str | None) -> Path:
    """Resolve the target repo root: explicit --repo-root, else git auto-detect.

    Mirrors upgrade_project_pins.sh's resolution: `git rev-parse
    --show-toplevel` against the *target* project's own repo -- never
    Praxion's own history.
    """
    if repo_root_arg is not None:
        return Path(repo_root_arg).resolve()

    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        _error("not inside a git repository; pass --repo-root to override")
    return Path(result.stdout.strip()).resolve()


# ---------------------------------------------------------------------------
# Mode implementations
# ---------------------------------------------------------------------------


def _report_check(classifications: dict[str, str]) -> int:
    """Print a per-slug classification report; exit 1 unless every slug is current."""
    for slug in sorted(classifications):
        print(f"  {slug}: {classifications[slug]}")

    non_current = sorted(slug for slug, cls in classifications.items() if cls != "current")
    if non_current:
        print(f"\n{len(non_current)} block(s) need attention: {', '.join(non_current)}")
        print("Fix:  /refresh-claude-blocks")
        return 1

    print(f"\nall {len(classifications)} eligible block(s) current.")
    return 0


# ---------------------------------------------------------------------------
# Apply mode: append absent, replace stale in place, refuse modified
# ---------------------------------------------------------------------------


def _load_canonical_body(slug: str) -> str:
    """Read a slug's current canonical body text from CANONICAL_DIR.

    The manifest only ever stores hashes -- append/replace actions need the
    actual body text, which lives only in the canonical file itself.
    """
    canonical_path = CANONICAL_DIR / f"{slug}.md"
    try:
        return canonical_path.read_text(encoding="utf-8")
    except OSError as exc:
        _error(f"cannot read canonical file {canonical_path}: {exc}")


def _trim_trailing_blank_lines(lines: list[str], start: int, end: int) -> int:
    """Shrink `end` past any trailing blank lines in [start, end).

    Those lines are the separator before a following heading -- surrounding
    structure, not part of the block body -- and must survive a stale-body
    replacement untouched rather than being swallowed by a verbatim splice
    of the raw extraction span.
    """
    while end > start and lines[end - 1] == "\n":
        end -= 1
    return end


def _apply_stale_replacements(lines: list[str], stale_slugs: list[str]) -> None:
    """Replace each stale slug's body in place, mutating `lines`.

    Spans are located before any mutation, then applied in descending
    start-index order -- so an earlier splice never shifts the line indices
    already computed for a later one -- mirroring sync_canonical_blocks.py's
    write_file reverse-order-processing technique.
    """
    spans = []
    for slug in stale_slugs:
        span = find_heading_span(lines, _heading_for_slug(slug))
        if span is not None:
            spans.append((slug, span[0], span[1]))

    for slug, start, end in sorted(spans, key=lambda item: item[1], reverse=True):
        core_end = _trim_trailing_blank_lines(lines, start, end)
        lines[start:core_end] = _load_canonical_body(slug).splitlines(keepends=True)


def _append_absent_blocks(text: str, absent_slugs: list[str]) -> str:
    """Append each absent slug's current canonical body at file end.

    Each appended block is separated from the preceding content by exactly
    one blank line.
    """
    for slug in sorted(absent_slugs):
        text += "\n" + _load_canonical_body(slug)
    return text


def _diff_live_against_canonical(slug: str, live_body: str, canonical_body: str) -> list[str]:
    """Produce a unified diff between a modified block's live and canonical
    bodies, mirroring sync_canonical_blocks.py's _diff_text helper."""
    return list(
        difflib.unified_diff(
            canonical_body.splitlines(keepends=True),
            live_body.splitlines(keepends=True),
            fromfile=f"claude/canonical-blocks/{slug}.md",
            tofile="live in target CLAUDE.md",
        )
    )


def _report_modified_block(slug: str, live_body: str) -> None:
    """Print a unified diff and a pointer to the interactive command.

    Apply-mode never touches a modified block's content -- this is the only
    action taken for it.
    """
    canonical_body = _load_canonical_body(slug)
    print(f"'{slug}' is locally modified -- left untouched.")
    for line in _diff_live_against_canonical(slug, live_body, canonical_body):
        print(line, end="")
    print("Resolve interactively:  /refresh-claude-blocks\n")


def run_apply(repo_root: Path, original_text: str, classifications: dict[str, str]) -> int:
    """--apply mode: append absent blocks, replace stale blocks in place,
    refuse to touch modified blocks. Writes the target file at most once,
    only when something actually changed -- never for a purely
    current/modified classification set. Always returns 0: a refused
    modified block is normal, expected behavior, not a run failure.

    ``original_text`` is the CLAUDE.md text ``main()`` already read for
    classification -- passed in rather than re-read here, so this mode never
    performs a second, independent read of the same file.
    """
    claude_md_path = repo_root / "CLAUDE.md"
    lines = original_text.splitlines(keepends=True)

    by_class: dict[str, list[str]] = {"absent": [], "stale": [], "modified": []}
    for slug, classification in classifications.items():
        if classification in by_class:
            by_class[classification].append(slug)

    _apply_stale_replacements(lines, by_class["stale"])
    new_text = _append_absent_blocks("".join(lines), by_class["absent"])

    for slug in sorted(by_class["modified"]):
        live_body = extract_live_body(original_text, _heading_for_slug(slug)) or ""
        _report_modified_block(slug, live_body)

    if new_text != original_text:
        claude_md_path.write_text(new_text, encoding="utf-8")

    return 0


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def _build_arg_parser() -> argparse.ArgumentParser:
    """Build the CLI parser: three mutually exclusive modes plus target overrides."""
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0] if __doc__ else "",
    )
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--check",
        action="store_true",
        default=False,
        help="Report classification; exit 1 unless every eligible block is current (default).",
    )
    mode_group.add_argument(
        "--json",
        action="store_true",
        default=False,
        dest="json_output",
        help="Print a machine-readable {slug: classification} dict; always exits 0.",
    )
    mode_group.add_argument(
        "--apply",
        action="store_true",
        default=False,
        help="Append absent blocks, replace stale blocks in place; refuse to touch "
        "modified blocks (emits a diff + pointer instead). Always exits 0.",
    )
    parser.add_argument(
        "--repo-root",
        dest="repo_root",
        default=None,
        help="Target project root (default: git rev-parse --show-toplevel).",
    )
    parser.add_argument(
        "--manifest",
        dest="manifest_path",
        default=None,
        help="Override path to the history manifest (default: the shipped "
        "claude/canonical-blocks/block-history.json).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv if argv is not None else sys.argv[1:])

    repo_root = _resolve_repo_root(args.repo_root)
    refusal = _self_onboard_guard_refusal(repo_root)
    if refusal is not None:
        print(f"error: {refusal}", file=sys.stderr)
        return 2

    manifest_path = Path(args.manifest_path) if args.manifest_path else _default_manifest_path()
    manifest = _load_manifest(manifest_path)
    claude_md_text = _read_claude_md(repo_root)
    classifications = _classify_all(claude_md_text, manifest)

    if args.json_output:
        print(json.dumps(classifications))
        return 0
    if args.apply:
        return run_apply(repo_root, claude_md_text, classifications)
    return _report_check(classifications)


if __name__ == "__main__":
    sys.exit(main())
