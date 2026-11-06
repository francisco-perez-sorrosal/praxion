#!/usr/bin/env python3
"""Report DESIGN.md's architecture checkpoint and its un-folded ADR suffix.

`.ai-state/DESIGN.md` section 1 carries a `Current as of` row naming a
`dec-NNN` high-water mark: the decision-log id up to which every
architecture-bearing ADR has been considered, whether folded into the doc or
judged not applicable. This script derives the **un-folded suffix** -- ADRs
sorting after that mark that satisfy the architecture-bearing predicate
(`status in {accepted,re-affirmation} AND category==architectural AND >=1
live affected_files`) -- so the mark's claim is checkable rather than an
assertion nobody can audit.

Read-only and advisory: it never edits the mark, never fails the build on a
non-empty suffix (a red gate on merge day, when a pipeline's own drafts
finalize above the checkpoint it just advanced, would teach consumers to
ignore it), and never generates an artifact. Reuses `query_adrs.py`'s ADR
loader rather than forking it.

The checkpoint cell is parsed at the boundary into a four-state sum type
(`DesignCheckpoint.state`: present/draft/absent/malformed) -- never coerced
to a default. Collapsing "the mark could not be read" or "the mark names an
in-flight draft, not yet comparable" into the same empty-list shape as "the
mark is clean" is the one failure mode that would make the whole mechanism a
lie (SYSTEMS_PLAN.md Data Structures #1).

Usage:
    python3 scripts/check_design_checkpoint.py --json

Exit codes: 0 (design doc read -- present, absent, or malformed checkpoint),
2 (`.ai-state/DESIGN.md` missing or unreadable).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import query_adrs
from _repo_root import resolve_repo_root as _resolve_repo_root

SCRIPT_DIR = Path(__file__).resolve().parent

_DESIGN_DOC = Path(".ai-state") / "DESIGN.md"
_GUIDE_DOC = Path("docs") / "architecture.md"

_CURRENT_AS_OF_ROW = re.compile(
    r"^\|\s*\*\*Current as of\*\*\s*\|\s*(?P<cell>.*?)\s*\|\s*$", re.MULTILINE
)
# Matches only the leading `` `dec-NNN` (asserted YYYY-MM-DD `` prefix -- the
# rest of the cell (attribution, task, trailing prose) is free text this
# script does not need to parse.
_PRESENT_CELL_PREFIX = re.compile(
    r"^`(?P<id>dec-[A-Za-z0-9_-]+)`\s*\(asserted\s+(?P<date>\d{4}-\d{2}-\d{2})"
)
_NUMERIC_ID = re.compile(r"^dec-(\d+)$")
# A checkpoint pinned to an in-flight ADR fragment -- legal (the
# normal state while a pipeline is running) but not yet a resolvable corpus
# position: finalize renumbers it to `dec-NNN` and only then can the un-folded
# suffix be computed. Distinguished from `_NUMERIC_ID` at parse time so this
# case never falls through to the `[]` branch a comparable checkpoint uses.
_DRAFT_ID = re.compile(r"^dec-draft-[0-9a-f]+$")

_STREAMLINE_STATUSES = frozenset({"accepted", "re-affirmation"})
_ARCHITECTURAL_CATEGORY = "architectural"
_PREDICATE_DESCRIPTION = (
    "status in {accepted,re-affirmation} AND category==architectural AND >=1 live affected_files"
)

# The check id this script's row surface declares -- read via AST by the row/registry/
# script Triangle in `tests/test_sentinel_check_triangle.py`, mirroring the flat
# CHECK_ID shape (this script owns exactly one sentinel row, not a keyed family).
CHECK_ID = "AC14"
_AC14_BOUND = (
    "AC14 clean means DESIGN.md's checkpoint is present and well-formed and no "
    "architecture-bearing ADR sorts after it unfolded; a malformed or absent "
    "checkpoint is a FAIL, a non-empty un-folded suffix is advisory (WARN, never "
    "a FAIL) -- the un-folded count itself must never read as a gate."
)


@dataclass(frozen=True)
class DesignCheckpoint:
    """The `Current as of` mark, parsed once at the boundary -- a sum type.

    `state` discriminates which of `checkpoint_id` / `asserted` / `raw` is
    meaningful. Callers must switch on `state` first; there is no default
    value to fall back on for the other fields when `state == "absent"`.

    `"draft"` is a fourth, deliberate state distinct from `"present"`: the
    cell is well-formed and both `checkpoint_id`/`asserted` are populated,
    but the id is a `dec-draft-<hash>` fragment with no numeric position to
    compare against the corpus -- resolvable only after finalize. Folding it
    into `"present"` would let `_id_number()`'s `None` return silently
    collapse "un-resolvable" into the same `unfolded: []` shape a genuinely
    clean checkpoint produces -- exactly the ambiguity this type exists to
    prevent.
    """

    state: str  # "present" | "draft" | "absent" | "malformed"
    checkpoint_id: str | None
    asserted: str | None
    raw: str | None


def resolve_repo_root(cli_repo_root: str | None) -> Path:
    """Resolve the repo root via the shared resolver (never `__file__`-relative)."""
    return _resolve_repo_root(cli_repo_root, script_dir=SCRIPT_DIR)


# -- Checkpoint parsing ---------------------------------------------------


def parse_design_checkpoint(design_text: str) -> DesignCheckpoint:
    """Parse the `Current as of` row out of DESIGN.md §1 text.

    No row at all is `absent` (the contract has not been adopted yet); a row
    whose cell does not start with a backtick-wrapped id and an asserted date
    is `malformed` (a fact to report, never a default to discard).
    """
    row = _CURRENT_AS_OF_ROW.search(design_text)
    if row is None:
        return DesignCheckpoint(state="absent", checkpoint_id=None, asserted=None, raw=None)

    cell = row.group("cell")
    present = _PRESENT_CELL_PREFIX.match(cell)
    if present is None:
        return DesignCheckpoint(state="malformed", checkpoint_id=None, asserted=None, raw=cell)

    checkpoint_id = present.group("id")
    state = "draft" if _DRAFT_ID.match(checkpoint_id) else "present"
    return DesignCheckpoint(
        state=state,
        checkpoint_id=checkpoint_id,
        asserted=present.group("date"),
        raw=cell,
    )


def _id_number(adr_id: str) -> int | None:
    """The numeric suffix of a finalized `dec-NNN` id, or None (drafts, non-numeric ids)."""
    match = _NUMERIC_ID.match(adr_id)
    return int(match.group(1)) if match else None


# -- Architecture-bearing predicate ----------------------------------------


def _has_live_affected_file(record: query_adrs.AdrRecord, repo_root: Path) -> bool:
    return any((repo_root / path).exists() for path in record.affected_files)


def _is_architecture_bearing(
    record: query_adrs.AdrRecord, repo_root: Path, checkpoint_number: int
) -> bool:
    record_number = _id_number(record.id)
    if record_number is None or record_number <= checkpoint_number:
        return False
    if record.status.lower() not in _STREAMLINE_STATUSES:
        return False
    if record.category.lower() != _ARCHITECTURAL_CATEGORY:
        return False
    return _has_live_affected_file(record, repo_root)


def _unfolded_entry(
    record: query_adrs.AdrRecord, design_text: str, guide_text: str
) -> dict[str, object]:
    return {
        "id": record.id,
        "title": record.title,
        "status": record.status,
        "category": record.category,
        # Proxies, not ground truth -- a substring hit correlates with "this
        # decision was folded in", it does not prove it.
        "cited_in_design": record.id in design_text,
        "cited_in_guide": record.id in guide_text,
    }


def _corpus_tip(records: list[query_adrs.AdrRecord]) -> query_adrs.AdrRecord | None:
    numbered = [
        (number, record) for record in records if (number := _id_number(record.id)) is not None
    ]
    if not numbered:
        return None
    return max(numbered, key=lambda pair: pair[0])[1]


# -- Report -----------------------------------------------------------------


def _compute_design_checkpoint_payload(repo_root: Path) -> tuple[int, dict[str, object]]:
    """Compute the checkpoint report. Returns `(exit_code, json_payload)`."""
    design_path = repo_root / _DESIGN_DOC
    if not design_path.is_file():
        return 2, {
            "checkpoint_state": "unreadable",
            "checkpoint": None,
            "message": f"{_DESIGN_DOC} is missing or unreadable",
        }

    design_text = design_path.read_text(encoding="utf-8")
    checkpoint = parse_design_checkpoint(design_text)

    yaml_module = query_adrs._try_import_yaml()
    adr_paths = query_adrs.discover_adr_files(repo_root)
    records = [
        record
        for path in adr_paths
        if (record := query_adrs.load_adr(path, repo_root, yaml_module)) is not None
    ]
    # `load_adr` returning `None` for a file the loader could not parse must
    # never disappear silently into the un-folded computation -- a record
    # this validator cannot see is a record it cannot certify as folded in.
    unparseable = len(adr_paths) - len(records)
    corpus_tip_record = _corpus_tip(records)
    corpus_tip = corpus_tip_record.id if corpus_tip_record is not None else None

    payload: dict[str, object] = {
        "checkpoint_state": checkpoint.state,
        "checkpoint": checkpoint.checkpoint_id,
        "corpus_tip": corpus_tip,
        "predicate": _PREDICATE_DESCRIPTION,
        "unparseable": unparseable,
    }

    if checkpoint.state != "present":
        # `None`, never `[]` -- an empty list would be indistinguishable from
        # a genuinely clean present checkpoint (the invariant this type exists
        # to protect).
        payload["unfolded"] = None
        payload["count"] = None
        if checkpoint.state == "malformed":
            payload["raw"] = checkpoint.raw
        elif checkpoint.state == "draft":
            payload["asserted"] = checkpoint.asserted
            payload["message"] = (
                f"checkpoint {checkpoint.checkpoint_id} is a draft ADR id -- "
                "un-resolvable to a corpus position until finalize; the "
                "un-folded suffix is UNCOMPUTABLE, not empty"
            )
        return 0, payload

    payload["asserted"] = checkpoint.asserted
    checkpoint_number = _id_number(checkpoint.checkpoint_id)

    guide_path = repo_root / _GUIDE_DOC
    guide_text = guide_path.read_text(encoding="utf-8") if guide_path.is_file() else ""

    unfolded = (
        sorted(
            (
                _unfolded_entry(record, design_text, guide_text)
                for record in records
                if _is_architecture_bearing(record, repo_root, checkpoint_number)
            ),
            key=lambda entry: entry["id"],
        )
        if checkpoint_number is not None
        else []
    )
    payload["unfolded"] = unfolded
    payload["count"] = len(unfolded)

    corpus_tip_number = _id_number(corpus_tip) if corpus_tip is not None else None
    if (
        checkpoint_number is not None
        and corpus_tip_number is not None
        and checkpoint_number > corpus_tip_number
    ):
        payload["warning"] = (
            f"checkpoint {checkpoint.checkpoint_id} exceeds the corpus tip "
            f"{corpus_tip} -- asserted a decision the corpus does not contain"
        )

    return 0, payload


# -- Family envelope ----------------------------------------------------------


def _ac14_findings(payload: dict[str, object]) -> list[dict[str, object]]:
    """Build the family findings from the already-computed payload.

    FAIL only on a checkpoint the mechanism could not evaluate at all
    (`unreadable`/`absent`/`malformed`) -- the un-folded suffix itself is
    advisory (`severity: "warn"`) so a merge-day suffix never reads as a gate.
    """
    state = payload["checkpoint_state"]
    if state == "unreadable":
        return [
            {
                "check": CHECK_ID,
                "severity": "fail",
                "entity": str(_DESIGN_DOC),
                "message": payload["message"],
            }
        ]
    if state == "absent":
        return [
            {
                "check": CHECK_ID,
                "severity": "fail",
                "entity": str(_DESIGN_DOC),
                "message": "no `Current as of` row in DESIGN.md section 1",
            }
        ]
    if state == "malformed":
        return [
            {
                "check": CHECK_ID,
                "severity": "fail",
                "entity": str(_DESIGN_DOC),
                "message": f"unparseable `Current as of` cell: {payload['raw']!r}",
            }
        ]
    count = payload.get("count")
    if not count:
        return []
    return [
        {
            "check": CHECK_ID,
            "severity": "warn",
            "entity": str(payload["checkpoint"]),
            "message": (
                f"{count} architecture-bearing ADR(s) sort after checkpoint "
                f"{payload['checkpoint']} and are not yet folded into DESIGN.md"
            ),
        }
    ]


def _ac14_withheld(payload: dict[str, object]) -> list[dict[str, object]]:
    """A `draft` checkpoint makes the un-folded suffix unanswerable, not empty --
    distinct from both a FAIL (unreadable/absent/malformed) and a clean WARN."""
    if payload["checkpoint_state"] != "draft":
        return []
    return [{"field": "unfolded", "reason": payload["message"]}]


def check_design_checkpoint(repo_root: Path) -> tuple[int, dict[str, object]]:
    """Compute the checkpoint report, then add the flat family envelope keys.

    Wraps `_compute_design_checkpoint_payload` in one place rather than
    editing each of its four early returns, so the six envelope keys are
    always present exactly once regardless of which branch produced the
    base payload.
    """
    exit_code, payload = _compute_design_checkpoint_payload(repo_root)
    payload["check"] = CHECK_ID
    payload["skipped"] = None
    payload["examined"] = {
        "checkpoint_state": payload["checkpoint_state"],
        "checkpoint": payload["checkpoint"],
        "corpus_tip": payload.get("corpus_tip"),
        "count": payload.get("count"),
    }
    payload["findings"] = _ac14_findings(payload)
    payload["info"] = {}
    payload["withheld"] = _ac14_withheld(payload)
    payload["bound"] = _AC14_BOUND
    return exit_code, payload


# -- CLI ----------------------------------------------------------------------


def _print_text(payload: dict[str, object]) -> None:
    state = payload["checkpoint_state"]
    if state == "unreadable":
        print(f"error: {payload['message']}")
        return
    if state == "absent":
        print("checkpoint: absent -- no `Current as of` row in DESIGN.md section 1")
        return
    if state == "malformed":
        print(f"checkpoint: malformed -- unparseable cell: {payload['raw']!r}")
        return
    if state == "draft":
        print(f"checkpoint: {payload['checkpoint']} (asserted {payload['asserted']})")
        print(f"checkpoint_state: draft -- {payload['message']}")
        return
    print(f"checkpoint: {payload['checkpoint']} (asserted {payload['asserted']})")
    print(f"corpus tip: {payload['corpus_tip']}")
    print(f"un-folded architecture-bearing ADRs: {payload['count']}")
    for entry in payload["unfolded"]:
        print(f"  {entry['id']} -- {entry['title']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Report the DESIGN.md architecture checkpoint and its un-folded ADR suffix."
    )
    parser.add_argument("--json", action="store_true", help="emit the report as JSON")
    parser.add_argument("--repo-root", help="repository root (defaults to git discovery)")
    args = parser.parse_args(argv)

    repo_root = resolve_repo_root(args.repo_root)
    exit_code, payload = check_design_checkpoint(repo_root)

    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        _print_text(payload)

    if "warning" in payload:
        print(f"warning: {payload['warning']}", file=sys.stderr)

    if payload.get("unparseable"):
        print(
            f"warning: {payload['unparseable']} ADR file(s) could not be parsed and are "
            "excluded from the un-folded computation -- see stderr above for which",
            file=sys.stderr,
        )

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
