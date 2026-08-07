#!/usr/bin/env python3
"""Flag finalized ADRs that never completed promotion.

A finalized ADR at ``.ai-state/decisions/<NNN>-<slug>.md`` must self-identify
as ``dec-<NNN>`` in its frontmatter ``id`` and must have left the ``proposed``
lifecycle state. ``scripts/finalize_adrs.py`` is responsible for both, but a
staging defect in its ``git mv`` sequence let a promoted draft ship with its
draft frontmatter still intact -- a finalized ADR reading
``id: dec-draft-<hash>``, ``status: proposed``. See
``rules/swe/gate-liveness.md`` clause 5 and td-103 in
``.ai-state/TECH_DEBT_LEDGER.md``.

This is a STATE gate -- its input is the current bytes of tracked files, not
repository history -- so it lives in ``scripts/`` rather than
``fitness/tests/``. See the gate-placement-and-history-baseline ADR
(``.ai-state/decisions/drafts/``). It reaches CI through ``test.yml``'s
``test-root`` job, which has no ``paths:`` filter and therefore fires even on
a pull request touching only ``scripts/finalize_adrs.py`` -- the exact PR
shape that could reintroduce this defect.

Two read modes:

  default   reads the working tree (what is currently on disk).
  --staged  reads git index blobs via ``git show :<path>`` -- the mode wired
            into the pre-commit hook, and the one that actually catches the
            shipped defect: ``git mv`` stages the destination against the
            *pre-rewrite* blob, so the working tree can be correct while the
            index (what the commit will actually contain) is not.

A ``.md`` file directly under ``.ai-state/decisions/`` that matches neither
the finalized-ADR filename shape (``<NNN>-<slug>.md``) nor a known exemption
(``DECISIONS_INDEX.md``, ``CLAUDE.md``) is reported unclassified rather than
silently skipped -- the gate's computed scope must not drift below its
documented scope. Files under ``.ai-state/decisions/drafts/`` are out of
scope entirely; drafts are governed by the ADR-drafts lifecycle, not this
gate.

Exit codes: 0 clean, 1 violations found, 2 script error.

Usage:
    python3 scripts/check_adr_frontmatter_promotion.py
    python3 scripts/check_adr_frontmatter_promotion.py --staged
    python3 scripts/check_adr_frontmatter_promotion.py --repo-root PATH
    python3 scripts/check_adr_frontmatter_promotion.py --json
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

from _git_runner import run_git
from _repo_root import resolve_repo_root as _resolve_repo_root

SCRIPT_DIR = Path(__file__).resolve().parent

DECISIONS_SUBDIR = ".ai-state/decisions"
FRONTMATTER_DELIMITER = "---"
FINALIZED_ADR_FILENAME_RE = re.compile(r"^(\d+)-.+\.md$")
EXEMPT_FILENAMES = frozenset({"DECISIONS_INDEX.md", "CLAUDE.md"})


# -- Frontmatter extraction ----------------------------------------------------


def _frontmatter_id_and_status(content: str) -> tuple[str | None, str | None]:
    """Return the frontmatter ``id`` and ``status`` scalar values, if present.

    Deliberately minimal: this gate only ever needs two scalar fields, so it
    does not pull in a full YAML parser or the block-list handling that
    ``regenerate_adr_index.py`` needs for ``tags``/``affected_files``.
    """
    lines = content.splitlines()
    if not lines or lines[0].strip() != FRONTMATTER_DELIMITER:
        return None, None

    found_id: str | None = None
    found_status: str | None = None
    for line in lines[1:]:
        stripped = line.strip()
        if stripped == FRONTMATTER_DELIMITER:
            break
        if found_id is None and stripped.startswith("id:"):
            found_id = stripped[len("id:") :].strip()
        elif found_status is None and stripped.startswith("status:"):
            found_status = stripped[len("status:") :].strip()
    return found_id, found_status


# -- Entry collection (default vs. staged) -------------------------------------


def _default_mode_entries(repo_root: Path) -> list[tuple[str, str]]:
    """(relative path, content) for every ``.md`` file on disk in the dir."""
    decisions_dir = repo_root / ".ai-state" / "decisions"
    if not decisions_dir.is_dir():
        return []
    entries: list[tuple[str, str]] = []
    for path in sorted(decisions_dir.glob("*.md")):
        content = path.read_text(encoding="utf-8", errors="replace")
        entries.append((f"{DECISIONS_SUBDIR}/{path.name}", content))
    return entries


def _git(repo_root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run `git <args>`, returning the `CompletedProcess` whatever the exit code.

    Deliberately *not* the swallowing `git_output` variant: this is a gate, and
    collapsing "git could not run" into the same `None` as "git exited
    non-zero" would let an unavailable git report a false all-clear. The
    `GitUnavailableError` this may raise is an `OSError`, so it lands in
    ``main``'s existing handler and exits 2 (script error) -- which is what a
    missing binary already did, and is now also what a hang does.
    """
    return run_git(repo_root, *args)


def _staged_mode_entries(repo_root: Path) -> list[tuple[str, str]]:
    """(relative path, content) for every staged ``.md`` blob in the dir.

    ``git ls-files`` reports the index, not the working tree, so a rename
    that ``git mv`` staged shows up here even when nothing was ``git add``-ed
    afterward. ``git show :<path>`` reads the staged blob for that path.
    """
    listing = _git(repo_root, "ls-files", "--", DECISIONS_SUBDIR)
    if listing.returncode != 0:
        return []

    entries: list[tuple[str, str]] = []
    prefix = f"{DECISIONS_SUBDIR}/"
    for raw_line in listing.stdout.splitlines():
        rel = raw_line.strip()
        if not rel.startswith(prefix):
            continue
        remainder = rel[len(prefix) :]
        if "/" in remainder or not remainder.endswith(".md"):
            continue  # skip drafts/ and any other nested path
        blob = _git(repo_root, "show", f":{rel}")
        if blob.returncode != 0:
            continue
        entries.append((rel, blob.stdout))
    return entries


# -- Classification -------------------------------------------------------------


def _classify(rel_path: str, content: str) -> list[str]:
    name = Path(rel_path).name
    if name in EXEMPT_FILENAMES:
        return []

    match = FINALIZED_ADR_FILENAME_RE.match(name)
    if match is None:
        return [
            f"{rel_path}: unclassified file under .ai-state/decisions/ -- matches "
            "neither the finalized ADR filename shape <NNN>-<slug>.md nor a known "
            "exemption (DECISIONS_INDEX.md, CLAUDE.md)"
        ]

    expected_id = f"dec-{match.group(1)}"
    found_id, status = _frontmatter_id_and_status(content)
    violations: list[str] = []
    if found_id != expected_id:
        violations.append(
            f"{rel_path}: frontmatter id is {found_id!r}, expected {expected_id!r} "
            "-- this ADR was never promoted (or its id was rewritten to the wrong "
            "value)"
        )
    if status == "proposed":
        violations.append(
            f"{rel_path}: frontmatter status is still 'proposed' -- a finalized "
            "ADR must have left the draft lifecycle state"
        )
    return violations


def find_violations(repo_root: Path, *, staged: bool = False) -> list[str]:
    """Every promotion defect found under ``.ai-state/decisions/``."""
    entries = _staged_mode_entries(repo_root) if staged else _default_mode_entries(repo_root)
    violations: list[str] = []
    for rel_path, content in entries:
        violations.extend(_classify(rel_path, content))
    return violations


# -- CLI ------------------------------------------------------------------------


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="check_adr_frontmatter_promotion",
        description=(
            "Flag finalized ADRs whose frontmatter id/status was never "
            "promoted out of its draft state."
        ),
    )
    parser.add_argument(
        "--repo-root",
        default=None,
        metavar="DIR",
        help="Repository to operate on (default: git-root of the cwd).",
    )
    parser.add_argument(
        "--staged",
        action="store_true",
        help="Read git index blobs instead of the working tree.",
    )
    parser.add_argument("--json", action="store_true", help="Machine-readable output.")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = _parse_args(argv)
    repo_root = _resolve_repo_root(args.repo_root, script_dir=SCRIPT_DIR)

    try:
        violations = find_violations(repo_root, staged=args.staged)
    except OSError as exc:
        print(f"check_adr_frontmatter_promotion: error: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps({"violations": violations, "count": len(violations)}, indent=2))
        return 1 if violations else 0

    if not violations:
        mode = "staged" if args.staged else "working-tree"
        print(f"check_adr_frontmatter_promotion: {mode} scan clean -- all finalized ADRs conform.")
        return 0

    print(
        f"check_adr_frontmatter_promotion: {len(violations)} violation(s) in .ai-state/decisions/:",
        file=sys.stderr,
    )
    for violation in violations:
        print(f"  - {violation}", file=sys.stderr)
    print("", file=sys.stderr)
    print("Rule: rules/swe/adr-conventions.md (Finalize Protocol)", file=sys.stderr)
    print(
        "Fix:  re-run scripts/finalize_adrs.py, or hand-correct the frontmatter.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
