#!/usr/bin/env python3
"""DL06: cross-reference pointers between ADRs are reciprocal (both directions set).

DL04 checks that a supersession/re-affirmation/retirement pointer's *target
exists*. This checks the different, easier-to-miss half: when the target
exists, does it carry the matching back-link? A decision that replaces three
predecessors owes three back-links; a check that verifies the first pointer
and stops reports a reciprocal graph that is two edges short of the truth.

Six frontmatter fields form three field pairs, two checked in *both*
directions and one checked in only one:

    supersedes            <-> superseded_by            (bidirectional)
    supersedes_in_part     <-> superseded_in_part_by     (bidirectional)
    re_affirms              -> re_affirmed_by            (one-directional)

The bidirectional pairs are checked from both sides because either field can
be set without its reciprocal -- an ADR claiming `supersedes: [X]` with no
`superseded_by` on X is one gap; an ADR claiming `superseded_by: X` with no
`supersedes` entry on X pointing back is a different gap that a forward-only
scan cannot see. `re_affirms` is one-directional because the Re-affirmation
Protocol writes both sides in the same edit -- the re-affirming decision
appends its own id to the target's `re_affirmed_by` at authoring time, so
there is no protocol step that would produce `re_affirmed_by` set ahead of
the matching `re_affirms`.

`retired_by` is exempt and never flagged here, by design: it is
one-directional -- a removing decision made no claim about what its removal
stranded, and writing a back-link would assert a deliberation that never
happened. Its own existence is still checked, by DL04.

`supersedes` is typed `string | list` (`adr-conventions.md`); every element
is iterated, never just the first -- the golden bad-case is an ADR carrying
`supersedes: [dec-A, dec-B, dec-C]` where only `dec-A` sets `superseded_by`,
which must WARN on `dec-B` and `dec-C` by name. Reading the list as one
opaque value is the exact defect this fixture exists to catch.

Draft-stage `dec-draft-<hash>` pointers are checked the same way as finalized
ones, within the combined finalized+draft id space `query_adrs.discover_adr_files`
already builds -- a dangling cross-stage pointer (the target file itself
absent) is DL04's mixed-pointer WARN, not this check's; a target that exists,
in either stage, is simply checked for its back-link like any other.

A target this check cannot resolve (the id is unknown, or its frontmatter
would not parse) is silently skipped rather than flagged -- that is DL04's
job (a dangling pointer) or a `withheld` entry (unreadable frontmatter), and
double-reporting the same gap under two checks would make the two dimensions'
findings drift only through this list ever changing width.

Reuses `query_adrs.py`'s frontmatter-loading primitives (`_FRONTMATTER_RE`,
`_try_import_yaml`, `_parse_frontmatter_fallback`) and its scalar-or-list
normalizer `_as_list`, rather than forking either -- `adr_health.py::_parse_edge_ids`
is the alternative source for the same normalization and is not used here on
purpose, to keep one shared normalizer rather than two that could drift.

Invoked by the sentinel's DL dimension (`--json`); also runnable standalone.
Advisory by construction: default exit 0 even with findings; `--check` opts
into exit 1 for a deliberate CI gate.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import dataclass
from pathlib import Path

from _repo_root import is_plugin_cache_path, resolve_repo_root
from _script_cli import configure_logging
from query_adrs import (
    _FRONTMATTER_RE,
    _as_list,
    _parse_frontmatter_fallback,
    _try_import_yaml,
    discover_adr_files,
)

SCRIPT_DIR = Path(__file__).resolve().parent
CHECK_ID = "DL06"
SEVERITY = "warn"

logger = logging.getLogger("check_adr_reciprocity")

# The six frontmatter fields this check reads, normalized via `_as_list`
# regardless of whether a given field is documented scalar or list --
# uniform handling is simpler than branching per field, and the normalizer
# is safe either way.
_EDGE_FIELDS = (
    "supersedes",
    "superseded_by",
    "re_affirms",
    "re_affirmed_by",
    "supersedes_in_part",
    "superseded_in_part_by",
)

# (forward, backward) pairs to check. The two symmetric relations are listed
# in both directions -- either field can be set without its reciprocal, and
# checking only the forward direction would miss the case where the *target*
# claims the edge but the *source* does not. `re_affirms` is listed once: the
# authoring protocol writes both sides together, so there is no legitimate
# state where only `re_affirmed_by` is set first.
_CHECKED_PAIRS = (
    ("supersedes", "superseded_by"),
    ("superseded_by", "supersedes"),
    ("supersedes_in_part", "superseded_in_part_by"),
    ("superseded_in_part_by", "supersedes_in_part"),
    ("re_affirms", "re_affirmed_by"),
)


@dataclass(frozen=True)
class _AdrEdges:
    """One ADR's id and its normalized edge fields."""

    id: str
    file: str
    fields: dict[str, list[str]]


def _load_edges(path: Path, yaml_module) -> _AdrEdges | None:
    """Parse one ADR's frontmatter into `_AdrEdges`, or None if unreadable.

    Mirrors `query_adrs.load_adr`'s parse dispatch, but returns the edge
    fields `AdrRecord` does not carry (only `superseded_in_part_by` is on
    that dataclass) -- built directly from the shared primitives rather than
    calling `load_adr` and re-parsing the same frontmatter a second time.
    """
    text = path.read_text(encoding="utf-8")
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return None
    raw = match.group(1)
    if yaml_module is not None:
        try:
            data = yaml_module.safe_load(raw)
        except yaml_module.YAMLError:
            data = None
    else:
        data = _parse_frontmatter_fallback(raw, path)
    if not isinstance(data, dict):
        return None
    adr_id = str(data.get("id", "")).strip()
    if not adr_id:
        return None
    fields = {field: _as_list(data.get(field)) for field in _EDGE_FIELDS}
    return _AdrEdges(id=adr_id, file=path.name, fields=fields)


def _finding(source: _AdrEdges, target_id: str, forward: str, backward: str) -> dict:
    return {
        "check": CHECK_ID,
        "severity": SEVERITY,
        "entity": source.id,
        "message": (
            f"{source.id} ({source.file}) names {target_id} in `{forward}`, but "
            f"{target_id}'s `{backward}` does not list {source.id} back"
        ),
    }


def find_missing_reciprocals(records: list[_AdrEdges]) -> list[dict]:
    """One WARN per relation field whose reciprocal back-link is missing.

    A target this check cannot resolve (unknown id) is skipped, not flagged --
    a dangling pointer is DL04's finding, not a missing back-link.
    """
    by_id = {r.id: r for r in records}
    findings: list[dict] = []
    for source in records:
        for forward, backward in _CHECKED_PAIRS:
            for target_id in source.fields[forward]:
                target = by_id.get(target_id)
                if target is None:
                    continue
                if source.id not in target.fields[backward]:
                    findings.append(_finding(source, target_id, forward, backward))
    return findings


def classify(repo_root: Path) -> dict:
    """Build the canonical envelope: reciprocity findings over the full ADR corpus."""
    decisions_dir = repo_root / ".ai-state" / "decisions"
    if not decisions_dir.is_dir():
        return _skipped_report("substrate-absent", str(decisions_dir))

    paths = discover_adr_files(repo_root)
    if not paths:
        return _skipped_report("substrate-absent", str(decisions_dir))

    yaml_module = _try_import_yaml()
    records: list[_AdrEdges] = []
    withheld: list[str] = []
    for path in paths:
        edges = _load_edges(path, yaml_module)
        if edges is None:
            withheld.append(
                f"{path.name}: frontmatter unreadable, excluded from reciprocity checks"
            )
            continue
        records.append(edges)

    findings = find_missing_reciprocals(records)
    return {
        "check": CHECK_ID,
        "skipped": None,
        "examined": {"records": len(records)},
        "findings": findings,
        "info": {},
        "withheld": withheld,
        "bound": (
            "DL06 clean means every reciprocal-relation field that was set carries its "
            "back-link; it does not mean every relation that should exist does -- a "
            "missing pointer entirely, or one pointing at a nonexistent id, is DL04's "
            "finding, not this one's."
        ),
    }


def _skipped_report(reason: str, path: str) -> dict:
    return {
        "check": CHECK_ID,
        "skipped": {"reason": reason, "path": path},
        "examined": None,
        "findings": [],
        "info": {},
        "withheld": [],
        "bound": "DL06 did not run; no reciprocity conclusion can be drawn.",
    }


# -- CLI ----------------------------------------------------------------------


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="check_adr_reciprocity",
        description=(
            "Advisory: flag ADR supersedes/superseded_by, supersedes_in_part/"
            "superseded_in_part_by, and re_affirms/re_affirmed_by pairs missing their "
            "reciprocal back-link. Called by sentinel DL06."
        ),
    )
    parser.add_argument(
        "--repo-root",
        default=None,
        metavar="DIR",
        help="Repository to operate on (default: discovered via git rev-parse).",
    )
    parser.add_argument("--json", action="store_true", help="Machine-readable JSON output.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit 1 when any DL06 finding is present (opt-in CI gate).",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable DEBUG logging.")
    return parser.parse_args(argv)


def _format_human(report: dict) -> str:
    if report["skipped"] is not None:
        return f"check_adr_reciprocity: skipped ({report['skipped']['reason']})"
    findings = report["findings"]
    if not findings:
        return f"check_adr_reciprocity: no DL06 violations across {report['examined']['records']} ADRs."
    lines = [f"DL06 WARN ({len(findings)} missing back-link(s)):"]
    lines.extend(f"  - {f['message']}" for f in findings)
    return "\n".join(lines)


def _run(args: argparse.Namespace) -> int:
    repo_root = resolve_repo_root(args.repo_root, script_dir=SCRIPT_DIR)
    if is_plugin_cache_path(repo_root):
        logger.error("Refusing to operate on plugin-cache path: %s", repo_root)
        return 2

    report = classify(repo_root)

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        text = _format_human(report)
        print(text, file=sys.stderr if report["findings"] else sys.stdout)

    return 1 if (args.check and report["findings"]) else 0


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    configure_logging(args.verbose)
    try:
        code = _run(args)
    except OSError as exc:
        logger.error("check_adr_reciprocity: %s", exc)
        sys.exit(0)
    sys.exit(code)


if __name__ == "__main__":
    main()
