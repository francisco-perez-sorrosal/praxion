#!/usr/bin/env python3
"""Sync canonical-block files with embedded blocks in command files.

Canonical content blocks live in ``claude/canonical-blocks/<slug>.md`` and
are embedded verbatim into one or more consumer command files.  Each embedded
block is anchored by a ``<!-- canonical-source: ... -->`` comment that names
the canonical file, followed by a fence pair that bounds the embedded body.

Two fence styles are supported, configured per-block in ``BLOCKS`` below:

* **Code-fenced** (``\`\`\`markdown`` / ``\`\`\```) — for blocks that the
  consumer command will *install* into a destination file (e.g., the four
  CLAUDE.md blocks shared between ``onboard-project`` and ``new-project``).
  The fence keeps the content visually grouped and tells readers it is a
  payload to be copied verbatim.
* **HTML-comment-fenced** (``<!-- canonical-content-start -->`` /
  ``<!-- canonical-content-end -->``) — for blocks whose content is the
  command's own prose (e.g., the shared commit workflow embedded in
  ``commands/co.md`` and ``commands/cop.md``). HTML comments are invisible
  in rendered Markdown, so the embedded content reads as a normal part of
  the command prompt rather than as a code block.

Three invocation modes:

    sync_canonical_blocks.py                     # --check (default)
    sync_canonical_blocks.py --check             # exit 0 if in sync, else 1
    sync_canonical_blocks.py --write             # rewrite embedded blocks from canonical
    sync_canonical_blocks.py --dry-run           # print what --write would do; no writes

Exit codes:
    0  -- all blocks in sync (--check / --dry-run) or all rewrites succeeded (--write)
    1  -- drift detected (--check) or would rewrite (--dry-run with drift)
    2  -- script error (missing file, parse failure, unexpected structure)

Usage:
    python3 scripts/sync_canonical_blocks.py [--check | --write | --dry-run]
"""

from __future__ import annotations

import argparse
import difflib
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent

CANONICAL_DIR = REPO_ROOT / "claude" / "canonical-blocks"

# Default fence style: a Markdown code block. Used by blocks that the consumer
# command will install verbatim into a destination file (e.g., CLAUDE.md).
CODE_FENCE_OPENER = "```markdown"
CODE_FENCE_CLOSER = "```"

# Alternative fence style: HTML comments, invisible in rendered Markdown. Used
# by blocks whose content is the command's own prose, so they read inline as
# part of the prompt rather than as a code block.
COMMENT_FENCE_OPENER = "<!-- canonical-content-start -->"
COMMENT_FENCE_CLOSER = "<!-- canonical-content-end -->"


@dataclass(frozen=True)
class BlockSpec:
    """Per-block configuration: which files embed it, and which fence to use."""

    consumers: tuple[Path, ...]
    fence_opener: str = CODE_FENCE_OPENER
    fence_closer: str = CODE_FENCE_CLOSER


_ONBOARDING_PAIR = (
    REPO_ROOT / "commands" / "onboard-project.md",
    REPO_ROOT / "commands" / "new-project.md",
)

_COMMIT_PAIR = (
    REPO_ROOT / "commands" / "co.md",
    REPO_ROOT / "commands" / "cop.md",
)

# Block registry. Order is preserved for deterministic help/error messages.
BLOCKS: dict[str, BlockSpec] = {
    "agent-pipeline": BlockSpec(consumers=_ONBOARDING_PAIR),
    "compaction-guidance": BlockSpec(consumers=_ONBOARDING_PAIR),
    "behavioral-contract": BlockSpec(consumers=_ONBOARDING_PAIR),
    "praxion-process": BlockSpec(consumers=_ONBOARDING_PAIR),
    "hackathon-mode": BlockSpec(consumers=_ONBOARDING_PAIR),
    "project-essentials": BlockSpec(consumers=_ONBOARDING_PAIR),
    "commit-process": BlockSpec(
        consumers=_COMMIT_PAIR,
        fence_opener=COMMENT_FENCE_OPENER,
        fence_closer=COMMENT_FENCE_CLOSER,
    ),
}

# Derived: every consumer file mentioned by any block, sorted for stable iteration.
COMMAND_FILES: tuple[Path, ...] = tuple(
    sorted({path for spec in BLOCKS.values() for path in spec.consumers})
)

# Legacy module-level alias. Tests patch SLUGS to restrict iteration scope; production
# code derives it from BLOCKS at import time. `_slugs_for` honors SLUGS as the iteration
# source so a test override propagates without needing to touch BLOCKS.
SLUGS: tuple[str, ...] = tuple(BLOCKS.keys())


def _slugs_for(cmd_path: Path) -> list[str]:
    """Return the slugs whose consumer list includes cmd_path.

    Iterates the module-level `SLUGS` tuple (which tests can override). For
    paths inside the real repository the consumer-membership filter applies,
    so heterogeneous block ownership (e.g., commit-process not installed in
    onboarding files) is honored. For paths outside REPO_ROOT — i.e., test
    fixtures under pytest's tmp_path — the filter is skipped and the test's
    SLUGS override is trusted as-is. Slugs not in BLOCKS are silently skipped.
    """
    try:
        cmd_path.resolve().relative_to(REPO_ROOT)
        is_repo_path = True
    except ValueError:
        is_repo_path = False

    if not is_repo_path:
        return [slug for slug in SLUGS if slug in BLOCKS]
    return [
        slug for slug in SLUGS if slug in BLOCKS and cmd_path in BLOCKS[slug].consumers
    ]


CANONICAL_SOURCE_PREFIX = "canonical-source: claude/canonical-blocks/"
CANONICAL_SOURCE_SUFFIX = ".md"


def _remediation_hint() -> str:
    """Build a remediation hint listing every consumer file under the registry."""
    parts: list[str] = []
    for path in COMMAND_FILES:
        try:
            parts.append(str(path.relative_to(REPO_ROOT)))
        except ValueError:
            # Test fixtures live outside REPO_ROOT (under pytest's tmp_path); fall
            # back to the absolute path so the hint stays readable in test output.
            parts.append(str(path))
    files_str = " ".join(parts)
    return (
        "  Fix:  python3 scripts/sync_canonical_blocks.py --write\n"
        f"        git add {files_str}"
    )


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


class BlockLocation(NamedTuple):
    """Describes where a fenced block lives within a command file."""

    slug: str
    fence_start: int  # 0-indexed line index of the ``markdown opener
    fence_end: int  # 0-indexed line index of the `` ``` `` closer
    body: str  # extracted fenced content (canonical-file shape)


# ---------------------------------------------------------------------------
# Extraction helpers
# ---------------------------------------------------------------------------


def _find_canonical_source_line(lines: list[str], slug: str) -> int | None:
    """Return the 0-indexed line index of the canonical-source comment for slug."""
    marker = f"{CANONICAL_SOURCE_PREFIX}{slug}{CANONICAL_SOURCE_SUFFIX}"
    for i, line in enumerate(lines):
        if marker in line:
            return i
    return None


def _find_fence_after(lines: list[str], start: int, opener: str) -> int | None:
    """Return the 0-indexed line index of the first opener-matching fence after start."""
    for i in range(start, len(lines)):
        if lines[i].rstrip("\n") == opener:
            return i
    return None


def _find_fence_closer(lines: list[str], start: int, closer: str) -> int | None:
    """Return the 0-indexed line index of the first closer fence after start."""
    for i in range(start, len(lines)):
        if lines[i].rstrip("\n") == closer:
            return i
    return None


def extract_block(lines: list[str], slug: str, file_path: Path) -> BlockLocation:
    """Extract the fenced block for slug from lines using its per-spec fence.

    Raises SystemExit(2) on parse failure.
    """
    spec = BLOCKS[slug]
    marker_idx = _find_canonical_source_line(lines, slug)
    if marker_idx is None:
        _error(f"canonical-source marker for '{slug}' not found in {file_path}")

    fence_start = _find_fence_after(lines, marker_idx + 1, spec.fence_opener)
    if fence_start is None:
        _error(
            f"no '{spec.fence_opener}' fence found after canonical-source marker "
            f"for '{slug}' in {file_path}"
        )

    fence_end = _find_fence_closer(lines, fence_start + 1, spec.fence_closer)
    if fence_end is None:
        _error(
            f"no '{spec.fence_closer}' closing fence found after '{spec.fence_opener}' "
            f"for '{slug}' in {file_path}"
        )

    body = "".join(lines[fence_start + 1 : fence_end])
    return BlockLocation(
        slug=slug,
        fence_start=fence_start,
        fence_end=fence_end,
        body=body,
    )


# ---------------------------------------------------------------------------
# Check / diff helpers
# ---------------------------------------------------------------------------


def _diff_text(slug: str, canonical_body: str, embedded_body: str) -> list[str]:
    """Produce a unified diff between canonical and embedded content."""
    canonical_lines = canonical_body.splitlines(keepends=True)
    embedded_lines = embedded_body.splitlines(keepends=True)
    return list(
        difflib.unified_diff(
            canonical_lines,
            embedded_lines,
            fromfile=f"claude/canonical-blocks/{slug}.md",
            tofile="embedded in command file",
        )
    )


# ---------------------------------------------------------------------------
# Error helper
# ---------------------------------------------------------------------------


def _error(message: str) -> None:
    """Print a script-error message and exit 2."""
    print(f"error: {message}", file=sys.stderr)
    sys.exit(2)


# ---------------------------------------------------------------------------
# Per-file operations
# ---------------------------------------------------------------------------


def check_file(
    cmd_path: Path,
) -> list[tuple[str, list[str]]]:
    """Check one command file for drift across the slugs it owns.

    Returns a list of (slug, diff_lines) for each drifted block.  Empty list
    means the file is fully in sync.  A slug whose canonical-source anchor is
    absent from the consumer is reported as full drift (the entire canonical
    content is missing).  Exits 2 on script errors.
    """
    try:
        content = cmd_path.read_text(encoding="utf-8")
    except OSError as exc:
        _error(f"cannot read {cmd_path}: {exc}")

    lines = content.splitlines(keepends=True)
    drifted: list[tuple[str, list[str]]] = []

    for slug in _slugs_for(cmd_path):
        canonical_path = CANONICAL_DIR / f"{slug}.md"
        try:
            canonical_body = canonical_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            _error(f"canonical file not found: {canonical_path}")
        except OSError as exc:
            _error(f"cannot read {canonical_path}: {exc}")

        # When the canonical-source anchor is absent the block has never been
        # embedded — treat as full drift rather than a parse error.
        if _find_canonical_source_line(lines, slug) is None:
            diff = _diff_text(slug, canonical_body, "")
            drifted.append((slug, diff))
            continue

        loc = extract_block(lines, slug, cmd_path)
        if loc.body != canonical_body:
            diff = _diff_text(slug, canonical_body, loc.body)
            drifted.append((slug, diff))

    return drifted


def write_file(cmd_path: Path, dry_run: bool = False) -> list[str]:
    """Rewrite embedded blocks in one command file from canonical sources.

    Returns the list of slugs that were (or would be) updated.
    Exits 2 on script errors.
    """
    try:
        content = cmd_path.read_text(encoding="utf-8")
    except OSError as exc:
        _error(f"cannot read {cmd_path}: {exc}")

    lines = content.splitlines(keepends=True)
    updated_slugs: list[str] = []

    # Process slugs in reverse order so that line-index replacements do not
    # shift the positions of earlier slugs.
    for slug in reversed(_slugs_for(cmd_path)):
        canonical_path = CANONICAL_DIR / f"{slug}.md"
        try:
            canonical_body = canonical_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            _error(f"canonical file not found: {canonical_path}")
        except OSError as exc:
            _error(f"cannot read {canonical_path}: {exc}")

        # When the canonical-source anchor is absent the block has never been
        # embedded — skip silently (check_file reports this as drift; write_file
        # cannot inject the anchor position, so it skips and lets the user add
        # the anchor manually before re-running --write).
        if _find_canonical_source_line(lines, slug) is None:
            continue

        loc = extract_block(lines, slug, cmd_path)
        if loc.body == canonical_body:
            continue  # already in sync

        updated_slugs.append(slug)

        if dry_run:
            continue  # record the slug but do not mutate lines

        # Replace lines[fence_start+1 : fence_end] with canonical content.
        canonical_lines = canonical_body.splitlines(keepends=True)
        lines[loc.fence_start + 1 : loc.fence_end] = canonical_lines

    if updated_slugs and not dry_run:
        new_content = "".join(lines)
        try:
            cmd_path.write_text(new_content, encoding="utf-8")
        except OSError as exc:
            _error(f"cannot write {cmd_path}: {exc}")

    return list(reversed(updated_slugs))  # restore natural order for reporting


# ---------------------------------------------------------------------------
# Mode implementations
# ---------------------------------------------------------------------------


def run_check() -> int:
    """--check mode: report drift and exit 1 if any found."""
    any_drift = False

    for cmd_path in COMMAND_FILES:
        drifted = check_file(cmd_path)
        if not drifted:
            continue

        any_drift = True
        try:
            display = cmd_path.relative_to(REPO_ROOT)
        except ValueError:
            display = cmd_path

        print(f"\ndrift detected in {display}:")
        for slug, diff_lines in drifted:
            print(f"  block '{slug}':")
            for diff_line in diff_lines:
                print("    " + diff_line, end="")
        print()

    if any_drift:
        print("canonical-block sync check failed.")
        print(_remediation_hint())
        return 1

    file_count = len(COMMAND_FILES)
    block_count = len(BLOCKS)
    print(f"checked {block_count} block(s) across {file_count} file(s); all in sync.")
    return 0


def run_write() -> int:
    """--write mode: rewrite drifted blocks from canonical sources."""
    any_change = False

    for cmd_path in COMMAND_FILES:
        try:
            display = cmd_path.relative_to(REPO_ROOT)
        except ValueError:
            display = cmd_path

        updated = write_file(cmd_path, dry_run=False)
        if updated:
            any_change = True
            print(f"updated {display}: {', '.join(updated)}")

    if not any_change:
        print("all blocks already in sync; no changes written.")

    return 0


def run_dry_run() -> int:
    """--dry-run mode: print what --write would do without writing."""
    any_drift = False

    for cmd_path in COMMAND_FILES:
        try:
            display = cmd_path.relative_to(REPO_ROOT)
        except ValueError:
            display = cmd_path

        would_update = write_file(cmd_path, dry_run=True)
        if would_update:
            any_drift = True
            print(f"would update {display}: {', '.join(would_update)}")

    if not any_drift:
        print("no changes needed; all blocks already in sync.")
        return 0

    print()
    print(
        f"dry-run: {len(COMMAND_FILES)} file(s) checked; re-run with --write to apply."
    )
    return 1


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0] if __doc__ else "",
    )
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--check",
        action="store_true",
        default=False,
        help="Check for drift and exit 1 if any found (default mode).",
    )
    mode_group.add_argument(
        "--write",
        action="store_true",
        default=False,
        help="Rewrite embedded blocks from canonical files.",
    )
    mode_group.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        dest="dry_run",
        help="Print what --write would do without modifying files.",
    )
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    if args.write:
        return run_write()
    if args.dry_run:
        return run_dry_run()
    # Default to --check
    return run_check()


if __name__ == "__main__":
    sys.exit(main())
