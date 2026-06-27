#!/usr/bin/env python3
"""Detect spec-archival gaps: recent ADR clusters without a paired archived spec.

A *gap* exists when the newest archived SPEC is more than N_DAYS older than a
cluster of ≥K_ADRS finalized ADRs sharing a common tag. This signals that a
feature shipped (ADRs landed) without archiving its behavioral spec.

Skip conditions (exit 0, no gap finding):
  - .ai-state/specs/ is absent or contains no SPEC_*.md files

Logic:
  1. Find the newest SPEC by date extracted from the filename
     (pattern: SPEC_<slug>_<YYYY-MM-DD>.md).
  2. Scan finalized ADRs in .ai-state/decisions/*.md (not drafts/).
  3. An ADR is *qualifying* when its date is more than N_DAYS days after the
     newest SPEC date — it belongs to a feature cluster that may have skipped
     spec archival.
  4. Group qualifying ADRs by tag. If any tag accumulates ≥K_ADRS qualifying
     ADRs, a gap is reported.

Invocation:

    check_spec_archival_gap.py                    # human-readable summary
    check_spec_archival_gap.py --json             # machine-readable JSON
    check_spec_archival_gap.py --check            # exit 1 on gap, else 0
    check_spec_archival_gap.py --repo-root PATH   # target repo (tests/worktrees)

Exit code: 0 by default (informational). With --check, 1 when a gap is
detected; 0 otherwise. Always 0 when .ai-state/specs/ is absent.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

from _repo_root import is_plugin_cache_path, resolve_repo_root

# -- Constants ----------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent

# Gap thresholds — exposed as module-level constants so callers and tests can
# reference them without re-importing or hard-coding.
N_DAYS: int = 90  # days the newest SPEC must trail the ADR cluster to flag a gap
K_ADRS: int = 3  # minimum cluster size (ADRs sharing a tag) to constitute a signal

# Regex to extract the ISO date from a SPEC filename.
# Pattern: SPEC_<slug>_<YYYY-MM-DD>.md  (slug may contain hyphens)
_SPEC_DATE_RE = re.compile(r"^SPEC_.+_(\d{4}-\d{2}-\d{2})\.md$")

# Frontmatter field regexes — applied to the raw text between the --- delimiters.
_FM_DATE_RE = re.compile(r"^date:\s*(\d{4}-\d{2}-\d{2})", re.MULTILINE)
_FM_TAGS_BLOCK_RE = re.compile(r"^tags:\s*\n((?:[ \t]+-[ \t]+\S+\n?)+)", re.MULTILINE)
_TAG_ITEM_RE = re.compile(r"^[ \t]+-[ \t]+(\S+)", re.MULTILINE)

logger = logging.getLogger("check_spec_archival_gap")


# -- Helpers ------------------------------------------------------------------


def _parse_iso_date(date_str: str) -> datetime | None:
    """Return an aware UTC datetime for an ISO-8601 date string, or None."""
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=UTC)
    except ValueError:
        return None


def _extract_frontmatter(text: str) -> str | None:
    """Return the YAML block between the first pair of --- delimiters, or None."""
    if not text.startswith("---"):
        return None
    parts = text.split("---", 2)
    return parts[1] if len(parts) >= 3 else None


def _newest_spec(specs_dir: Path) -> tuple[str | None, datetime | None]:
    """Return (filename, date) for the newest SPEC_*.md by date in filename."""
    best_name: str | None = None
    best_date: datetime | None = None
    for path in specs_dir.glob("SPEC_*.md"):
        m = _SPEC_DATE_RE.match(path.name)
        if not m:
            continue
        dt = _parse_iso_date(m.group(1))
        if dt is None:
            continue
        if best_date is None or dt > best_date:
            best_date = dt
            best_name = path.name
    return best_name, best_date


def _adr_meta(path: Path) -> tuple[datetime | None, list[str]]:
    """Parse (date, tags) from a finalized ADR's YAML frontmatter.

    Returns (None, []) on read errors or missing/unparseable frontmatter.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None, []

    fm = _extract_frontmatter(text)
    if fm is None:
        return None, []

    date_m = _FM_DATE_RE.search(fm)
    adr_date = _parse_iso_date(date_m.group(1)) if date_m else None

    tags: list[str] = []
    tags_m = _FM_TAGS_BLOCK_RE.search(fm)
    if tags_m:
        tags = _TAG_ITEM_RE.findall(tags_m.group(1))

    return adr_date, tags


# -- Core detection -----------------------------------------------------------


def detect_gap(repo_root: Path, now: datetime | None = None) -> dict:
    """Detect whether a spec-archival gap exists in *repo_root*.

    Parameters
    ----------
    repo_root:
        Repository root (contains ``.ai-state/``).
    now:
        Reference datetime for age calculations.  Defaults to the current UTC
        time.  Inject a fixed value in tests for determinism.

    Returns
    -------
    dict with keys:

    - ``gap`` (bool): True when a gap is detected.
    - ``newest_spec`` (str | None): filename of the newest archived SPEC.
    - ``spec_age_days`` (int | None): age in days of the newest SPEC relative
      to *now*.
    - ``recent_adr_count`` (int): size of the largest qualifying ADR cluster.
    - ``details`` (str): human-readable summary.
    """
    if now is None:
        now = datetime.now(UTC)

    specs_dir = repo_root / ".ai-state" / "specs"

    # Skip condition: absent or empty specs directory.
    if not specs_dir.exists() or not any(specs_dir.glob("SPEC_*.md")):
        logger.info(
            "No .ai-state/specs/ directory or no SPEC_*.md files found — "
            "spec-archival gap check skipped."
        )
        return {
            "gap": False,
            "newest_spec": None,
            "spec_age_days": None,
            "recent_adr_count": 0,
            "details": "No spec files found; check skipped (INFO — not a finding).",
        }

    newest_spec_name, newest_spec_date = _newest_spec(specs_dir)
    if newest_spec_date is None:
        return {
            "gap": False,
            "newest_spec": newest_spec_name,
            "spec_age_days": None,
            "recent_adr_count": 0,
            "details": "Could not parse a date from any SPEC filename; check skipped.",
        }

    spec_age_days = (now - newest_spec_date).days

    # Count qualifying ADRs per tag.  An ADR qualifies when its date is more
    # than N_DAYS after the newest SPEC date — signalling it belongs to a
    # feature that landed after the last spec archival.
    decisions_dir = repo_root / ".ai-state" / "decisions"
    tag_counts: dict[str, int] = {}

    if decisions_dir.exists():
        for adr_path in sorted(decisions_dir.glob("*.md")):
            adr_date, adr_tags = _adr_meta(adr_path)
            if adr_date is None:
                continue
            if (adr_date - newest_spec_date).days <= N_DAYS:
                continue
            for tag in adr_tags:
                tag_counts[tag] = tag_counts.get(tag, 0) + 1

    # Find the largest cluster.
    best_tag: str | None = None
    max_count: int = 0
    for tag, count in tag_counts.items():
        if count > max_count:
            max_count = count
            best_tag = tag

    gap = max_count >= K_ADRS

    if gap:
        details = (
            f"Gap detected: newest spec '{newest_spec_name}' is {spec_age_days} days old; "
            f"{max_count} ADRs share tag '{best_tag}' and are >{N_DAYS} days newer "
            f"(threshold: ≥{K_ADRS} ADRs)."
        )
    else:
        details = (
            f"No gap: newest spec '{newest_spec_name}' is {spec_age_days} days old; "
            f"no qualifying ADR cluster of ≥{K_ADRS} found (gap threshold: >{N_DAYS} days)."
        )

    return {
        "gap": gap,
        "newest_spec": newest_spec_name,
        "spec_age_days": spec_age_days,
        "recent_adr_count": max_count,
        "details": details,
    }


# -- CLI ----------------------------------------------------------------------


def main(argv: list[str] | None = None) -> None:
    """Entry point for CLI invocation.

    Parameters
    ----------
    argv:
        Argument list (``sys.argv[1:]`` when None).  Tests pass an explicit
        list to avoid touching the real process environment.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Detect spec-archival gaps: features that shipped ADRs without "
            "archiving a behavioral spec."
        ),
    )
    parser.add_argument(
        "--repo-root",
        metavar="PATH",
        help="Repository root (default: auto-detect via git rev-parse).",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit 1 when a gap is detected (for CI / pre-merge gates).",
    )
    parser.add_argument(
        "--json",
        dest="json_output",
        action="store_true",
        help="Emit machine-readable JSON instead of a human-readable summary.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s: %(message)s",
        stream=sys.stderr,
    )

    repo_root = resolve_repo_root(
        args.repo_root,
        script_dir=SCRIPT_DIR,
        on_fallback=lambda p: logger.warning(
            "git root not detected; falling back to script-relative path %s", p
        ),
    )

    if is_plugin_cache_path(repo_root):
        logger.error("Refusing to operate on plugin-cache path: %s", repo_root)
        sys.exit(2)

    result = detect_gap(repo_root=repo_root)

    if args.json_output:
        print(json.dumps(result, indent=2))
    else:
        print(result["details"])

    if args.check:
        sys.exit(1 if result["gap"] else 0)


if __name__ == "__main__":
    main()
