#!/usr/bin/env python3
"""ADR reference-decay classifier.

An `affected_files` entry that no longer resolves on disk is a *reference-decay*
signal, not a retirement signal. Measured on a 316-ADR corpus, 125 of 1,432
references were orphaned -- and classifying them by cause shows the default
disposition is **repair**, not retirement:

    placeholder-shape   a path *shape*, never a real path        -> fix the entry
    out-of-repo         `~/...` -- outside the repository        -> fix the entry
    lazy-artifact       absence is declared expected             -> nothing
    renamed             the subject moved                        -> update the path
    removed-by-self     this decision deleted it                 -> nothing; it worked
    removed-by-later    another decision deleted it              -> link the supersession
    vanished            no successor found                       -> retirement candidate

Only `vanished` means retire. A naive "does the path exist" rule would flag every
"remove X" decision as stale -- inverting the truth on some of the most
load-bearing records in a corpus.

`removed-by-later` is the highest-value output. It reconstructs decision-graph
edges that exist in reality but were never recorded, which is the honest
explanation for a supersession rate near 4%: the corpus is under-linked, not
bloated with dead decisions.

Advisory by construction: emits candidates, never edits an ADR, never changes a
`status`, and exits 0 even with findings. A decision can be correct and silent
forever; automatic demotion would destroy exactly the constraints that work
without being spoken. Humans and agents dispose.

Both oracles can fail silently and would then mislabel everything as `vanished`
-- the worst possible failure for this feature. Each is checked, and when
unavailable its dependent classes are **withheld with a named reason** rather
than defaulted (`--json` reports them under `withheld`).

Invoked by the sentinel's DH dimension (`--json`); also runnable standalone.
Exit code is always 0 -- this reports, it does not gate.

Cites: rules/swe/gate-liveness.md (a named consumer for every gate output);
CLAUDE.md§Root Causes Over Workarounds.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

from _repo_root import resolve_repo_root
from validate_adr_references import parse_affected_files

SCRIPT_DIR = Path(__file__).resolve().parent

# -- Constants ----------------------------------------------------------------

# A path *shape* teaching a convention, never a concrete file.
_SHAPE = re.compile(r"<[^>]*>|\*|\{\{|\bNNN\b|\bYYYY\b")

# Titles/summaries whose decision is itself a removal. Deliberately broad: a
# false positive here only downgrades a finding to "the decision worked", which
# is far cheaper than falsely proposing a load-bearing record for retirement.
_REMOVAL_INTENT = re.compile(
    r"\b(remove|retire|delete|drop|replac|supersed|consolidat|migrat|rename|unif|retir)",
    re.IGNORECASE,
)

# Absence is only evidence of decay when presence was expected. The inventory
# declares, per artifact, what absence *means*.
_EXPECTED_ABSENT_STATES = frozenset({"optional-lazy", "threshold-lazy", "future-designed"})
_INVENTORY = Path("skills/software-planning/references/artifact-inventory.md")
_INVENTORY_ROW = re.compile(r"^\|\s*`([^`]+)`[^|]*\|\s*([a-z-]+)\s*\|")
# Below this, the table format has changed and the parse is not trustworthy.
_MIN_INVENTORY_ROWS = 8

_GIT_TIMEOUT = 30


# -- Git history indexes ------------------------------------------------------


def _git(repo_root: Path, *args: str) -> str | None:
    """Run git; return stdout, or None when the command is unusable."""
    try:
        result = subprocess.run(  # noqa: S603
            ["git", "-C", str(repo_root), *args],
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout if result.returncode == 0 else None


def history_available(repo_root: Path) -> bool:
    """True when the clone carries enough history to classify deletions.

    A shallow clone can still answer `git log`, but only over a truncated
    window, so a deletion outside that window looks like it never happened --
    which would silently promote repairable findings to retirement candidates.
    """
    if _git(repo_root, "rev-parse", "--git-dir") is None:
        return False
    return (_git(repo_root, "rev-parse", "--is-shallow-repository") or "").strip() != "true"


def build_deletion_index(repo_root: Path) -> dict[str, str]:
    """Map deleted path -> ISO date of the commit that deleted it (most recent).

    One git call for the whole repository. Per-path `git log` would be ~1,400
    subprocesses on a corpus this size.
    """
    out = _git(repo_root, "log", "--diff-filter=D", "--name-only", "--format=%cI", "--no-renames")
    index: dict[str, str] = {}
    date = ""
    for line in (out or "").splitlines():
        line = line.strip()
        if not line:
            continue
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}T.*", line):
            date = line[:10]
        elif line not in index:  # log is newest-first; keep the most recent
            index[line] = date
    return index


def build_rename_index(repo_root: Path) -> dict[str, str]:
    """Map old path -> newest known new path, following rename chains."""
    out = _git(repo_root, "log", "--diff-filter=R", "-M", "--name-status", "--format=")
    direct: dict[str, str] = {}
    for line in (out or "").splitlines():
        parts = line.split("\t")
        if len(parts) == 3 and parts[0].startswith("R") and parts[1] not in direct:
            direct[parts[1]] = parts[2]
    resolved: dict[str, str] = {}
    for old in direct:
        seen, cur = {old}, direct[old]
        while cur in direct and direct[cur] not in seen:
            seen.add(cur)
            cur = direct[cur]
        resolved[old] = cur
    return resolved


# -- Lifecycle oracle ---------------------------------------------------------


def load_expected_absent_shapes(repo_root: Path) -> list[str] | None:
    """Artifact shapes whose absence the inventory declares expected.

    Returns None when the table cannot be parsed -- the caller then withholds
    the `lazy-artifact` class rather than misreporting those artifacts as
    vanished.
    """
    path = repo_root / _INVENTORY
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    rows = [m.groups() for line in text.splitlines() if (m := _INVENTORY_ROW.match(line))]
    if len(rows) < _MIN_INVENTORY_ROWS:
        return None
    return [shape for shape, state in rows if state in _EXPECTED_ABSENT_STATES]


def _matches_shape(path: str, shape: str) -> bool:
    """Match a concrete path against an inventory shape like `foo/BAR_*.md`."""
    stem = shape.split("*")[0].rstrip("/")
    return bool(stem) and (stem in path or path in stem)


# -- Classification -----------------------------------------------------------


def classify(repo_root: Path) -> dict:
    """Classify every unresolved `affected_files` reference in the corpus."""
    decisions_dir = repo_root / ".ai-state" / "decisions"
    adrs = sorted(decisions_dir.glob("[0-9]*.md"))

    have_history = history_available(repo_root)
    deletions = build_deletion_index(repo_root) if have_history else {}
    renames = build_rename_index(repo_root) if have_history else {}
    lazy_shapes = load_expected_absent_shapes(repo_root)

    withheld = []
    if not have_history:
        withheld.append(
            "renamed/removed-by-self/removed-by-later: git history unavailable "
            "(shallow clone or not a repository) -- these findings are withheld, "
            "not defaulted to `vanished`"
        )
    if lazy_shapes is None:
        withheld.append(
            f"lazy-artifact: could not parse {_INVENTORY} (fewer than "
            f"{_MIN_INVENTORY_ROWS} lifecycle rows) -- withheld, not defaulted"
        )

    # Removal-intent ADRs, so a deletion can be attributed to the decision that
    # caused it rather than to whichever decision merely mentioned the path.
    removers = []
    for adr in adrs:
        text = adr.read_text(encoding="utf-8")
        date = (re.search(r"^date:\s*(\S+)", text, re.MULTILINE) or [None, ""])[1]
        title = (re.search(r"^title:\s*(.+)$", text, re.MULTILINE) or [None, ""])[1]
        summary = (re.search(r"^summary:\s*(.+)$", text, re.MULTILINE) or [None, ""])[1]
        if _REMOVAL_INTENT.search(f"{title} {summary}"):
            removers.append((adr.name, date, set(parse_affected_files(text))))

    findings, scanned = [], 0
    for adr in adrs:
        text = adr.read_text(encoding="utf-8")
        for ref in parse_affected_files(text):
            scanned += 1
            if (repo_root / ref).exists():
                continue
            cls, disp, detail = _classify_one(
                adr.name, ref, deletions, renames, lazy_shapes, removers, have_history
            )
            findings.append(
                {
                    "adr": adr.name,
                    "path": ref,
                    "decay_class": cls,
                    "disposition": disp,
                    "detail": detail,
                }
            )

    return {
        "scanned_references": scanned,
        "adrs": len(adrs),
        "findings": findings,
        "withheld": withheld,
        "summary": _summarize(findings),
    }


def _classify_one(adr_name, ref, deletions, renames, lazy_shapes, removers, have_history):
    """Return (decay_class, disposition, detail) for one unresolved reference."""
    if _SHAPE.search(ref):
        return "placeholder-shape", "fix-entry", "a path shape, not a concrete path"
    if ref.startswith(("~", "/")):
        return "out-of-repo", "fix-entry", "resolves outside the repository"
    if lazy_shapes is not None and any(_matches_shape(ref, s) for s in lazy_shapes):
        return "lazy-artifact", "none", "artifact-inventory declares absence expected"
    if not have_history:
        return "unclassified", "none", "history unavailable; cause not determined"
    if ref in renames:
        return "renamed", "update-path", f"renamed to {renames[ref]}"

    deleted_on = deletions.get(ref)
    if deleted_on:
        owners = [(n, d) for n, d, paths in removers if ref in paths]
        if any(n == adr_name for n, _ in owners):
            return "removed-by-self", "none", f"this decision removed it ({deleted_on})"
        if owners:
            # Removal intent is matched broadly, so several decisions can claim the
            # same path. Rank by date proximity to the deletion: the decision that
            # actually caused it is the one closest in time. Naming all of them
            # would make the disposition ("record the supersession link") require
            # the reader to re-do this attribution by hand.
            ranked = [n for n, _ in sorted(owners, key=lambda o: _date_distance(o[1], deleted_on))]
            # Ordering is a hint, not a verdict. Date proximity is a weak proxy
            # for causation -- an unrelated decision landing near the deletion can
            # outrank the real remover -- so candidates are offered for the human
            # disposition step rather than asserted. The CLASS is the reliable
            # part: some decision removed this, and no link records it.
            detail = (
                f"removed {deleted_on}; candidate removers, nearest-dated first: "
                f"{', '.join(ranked)} -- confirm which, then record the link"
            )
            return "removed-by-later", "link-supersession", detail
        return "vanished", "retire-candidate", f"deleted {deleted_on}, no owning decision found"
    return "vanished", "retire-candidate", "absent, with no deletion recorded"


def _date_distance(a: str, b: str) -> int:
    """Absolute day distance between two ISO dates; large when either is absent."""
    try:
        from datetime import date

        d1 = date.fromisoformat(a[:10])
        d2 = date.fromisoformat(b[:10])
    except (ValueError, TypeError):
        return 10**6
    return abs((d1 - d2).days)


def _summarize(findings: list[dict]) -> dict[str, int]:
    out: dict[str, int] = {}
    for f in findings:
        out[f["decay_class"]] = out.get(f["decay_class"], 0) + 1
    return dict(sorted(out.items()))


# -- CLI ----------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ADR reference-decay classifier (advisory).")
    parser.add_argument("--json", action="store_true", help="emit findings as JSON")
    parser.add_argument("--repo-root", help="repository root (defaults to git discovery)")
    parser.add_argument(
        "--class",
        dest="only",
        help="report only this decay class (e.g. removed-by-later)",
    )
    args = parser.parse_args(argv)

    report = classify(resolve_repo_root(args.repo_root, script_dir=SCRIPT_DIR))
    if args.only:
        report["findings"] = [f for f in report["findings"] if f["decay_class"] == args.only]

    if args.json:
        print(json.dumps(report, indent=2))
        return 0

    print(f"scanned {report['scanned_references']} references across {report['adrs']} ADRs")
    for reason in report["withheld"]:
        print(f"  WITHHELD -- {reason}")
    for cls, n in report["summary"].items():
        print(f"  {cls:20} {n:4}")
    for f in report["findings"]:
        if f["disposition"] != "none":
            print(
                f"\n  {f['adr']}: {f['path']}\n    {f['decay_class']} -> "
                f"{f['disposition']} ({f['detail']})"
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
