"""Driver for the evidence the flip gate judges: results files, the run index, and forgeries.

Builds on `flip_gate` (planted copies of committed results files, `--reindex` through the
real console entry, switched records with their flag) and adds the edits a scenario makes
to that evidence after it is planted:

- to a results file, before the index is rebuilt (so its digest in the index is intact):
  leaving the role's convention check uncovered by its verdict, recording other complete
  pairs than its sessions give, or adding a later session for a task;
- to the run index, after it is rebuilt (a hand edit whose digests stay intact): another
  lineage root, other complete pairs or another flip label for a run.

Bound here, because the specification or the base commit fixes them: the results file's
`sessions` (each with `setup.role`, `setup.task_id`, `setup.arm`, `status.kind` and
`started_at`) and `verdicts.<role>` (`complete_pairs`, `flip`, `check_verdicts`,
`check_details`, `not_covered`, `not_covered_reasons`); the index's `runs.<id>` (`file`,
`sha256`, `lineage_root`, `ending`, `roles.<role>.complete_pairs`, `roles.<role>.flip`);
a role's convention check named `<role>: it follows the convention its project's
instruction file states`, as the pilot roles' results files name it; a run's scored
checks, read from a legacy verdict, are its per-check verdicts not listed as not covered.

Unbound: where this change records a run's scored checks, in the results file and in the
index entry (`recorded_standing`, `index_scored_checks`), which raise until a binding step
names the fields.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from tests.acceptance.drivers.flip_gate import RESULTS_SUBDIR

INDEX = "index.json"
CONVENTION_SUFFIX = "it follows the convention its project's instruction file states"


class UnboundReadingError(NotImplementedError):
    """A reading of a field this change adds, which no binding step has named yet."""


def convention_check(role: str) -> str:
    return f"{role}: {CONVENTION_SUFFIX}"


def results_path(root: Path, run_id: str) -> Path:
    return root / RESULTS_SUBDIR / f"{run_id}.json"


def _edit_results(root: Path, run_id: str, edit) -> None:
    path = results_path(root, run_id)
    document = json.loads(path.read_text(encoding="utf-8"))
    edit(document)
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")


# -- Edits to a results file (before the index is rebuilt) -------------------------------------


def leave_convention_uncovered(root: Path, run_id: str, role: str) -> None:
    """The role's verdict lists its convention check as not covered, with a reason."""
    check = convention_check(role)

    def edit(document: dict[str, Any]) -> None:
        verdict = document["verdicts"][role]
        assert check in verdict["check_verdicts"], f"the planted run never scored {check!r}"
        del verdict["check_verdicts"][check]
        verdict.get("check_details", {}).pop(check, None)
        verdict["not_covered"] = [*verdict.get("not_covered", []), check]
        reasons = verdict.setdefault("not_covered_reasons", {})
        reasons[check] = "no task of this run stated a project convention"

    _edit_results(root, run_id, edit)


def drop_check_verdicts(root: Path, run_id: str, role: str) -> None:
    """The role's verdict records no per-check verdict at all."""

    def edit(document: dict[str, Any]) -> None:
        verdict = document["verdicts"][role]
        verdict["check_verdicts"] = {}
        verdict["check_details"] = {}

    _edit_results(root, run_id, edit)


def record_complete_pairs(root: Path, run_id: str, role: str, pairs: int) -> None:
    """The role's verdict records `pairs` complete pairs, whatever its sessions give."""

    def edit(document: dict[str, Any]) -> None:
        document["verdicts"][role]["complete_pairs"] = pairs

    _edit_results(root, run_id, edit)


def _later(stamp: str, seconds: int) -> str:
    return (datetime.fromisoformat(stamp) + timedelta(seconds=seconds)).isoformat()


def _lean_measured(document: dict[str, Any], role: str) -> dict[str, Any]:
    return next(
        s
        for s in document["sessions"]
        if s["setup"]["role"] == role
        and s["setup"]["arm"] == "lean"
        and s["status"]["kind"] == "measured"
    )


def _last_start(document: dict[str, Any]) -> str:
    return max(s["started_at"] for s in document["sessions"])


def add_later_errored_lean_session(root: Path, run_id: str, role: str) -> str:
    """One task's lean arm runs again after its measured session and errors; its task id."""

    touched: list[str] = []

    def edit(document: dict[str, Any]) -> None:
        later = copy.deepcopy(_lean_measured(document, role))
        later["status"] = {"kind": "errored", "error_kind": "exit_nonzero", "detail": "exit 1"}
        later["started_at"] = _later(_last_start(document), 60)
        document["sessions"].append(later)
        touched.append(later["setup"]["task_id"])

    _edit_results(root, run_id, edit)
    return touched[0]


def add_earlier_errored_lean_session(root: Path, run_id: str, role: str) -> str:
    """One task's lean arm errored once before the measured session that counts; its task id."""

    touched: list[str] = []

    def edit(document: dict[str, Any]) -> None:
        measured = _lean_measured(document, role)
        earlier = copy.deepcopy(measured)
        earlier["status"] = {"kind": "errored", "error_kind": "exit_nonzero", "detail": "exit 1"}
        earlier["started_at"] = _later(measured["started_at"], -60)
        document["sessions"].insert(document["sessions"].index(measured), earlier)
        touched.append(measured["setup"]["task_id"])

    _edit_results(root, run_id, edit)
    return touched[0]


# -- Hand edits to the run index (after it is rebuilt) -------------------------------------------


def _index_path(root: Path) -> Path:
    return root / RESULTS_SUBDIR / INDEX


def read_index(root: Path) -> dict[str, Any]:
    return json.loads(_index_path(root).read_text(encoding="utf-8"))


def hand_edit_index(root: Path, run_id: str, role: str | None = None, **fields: Any) -> None:
    """Set `fields` on the run's index entry (or its role's), leaving every digest as it is."""
    index = read_index(root)
    entry = index["runs"][run_id]
    (entry["roles"][role] if role else entry).update(fields)
    _index_path(root).write_text(json.dumps(index, indent=1) + "\n", encoding="utf-8")


# -- What a run scored ----------------------------------------------------------------------------


def scored_in_verdict(verdict: dict[str, Any]) -> list[str]:
    """The checks a recorded verdict scored: those it gives a verdict and does not leave uncovered."""
    given = verdict.get("check_verdicts") or {}
    uncovered = set(verdict.get("not_covered") or ())
    return sorted(name for name in given if name not in uncovered)


@dataclass(frozen=True)
class Standing:
    complete_pairs: int
    flip: str | None
    scored_checks: tuple[str, ...]


def recorded_standing(path: Path, role: str) -> Standing:
    """The lineage standing a results file records for `role` (pairs, flip, scored checks)."""
    raise UnboundReadingError(
        "unbound: where a finalized or closed results file records, for a role it measured, "
        "the standing of its whole lineage (complete pairs, flip label and the checks it "
        f"scored) is not named yet; asked of {path.name} for {role}"
    )


def index_scored_checks(root: Path, run_id: str, role: str) -> list[str]:
    """The checks the run index lists as scored for `role` in run `run_id`'s entry."""
    raise UnboundReadingError(
        "unbound: the run index entry's list of the checks a run scored for a role, kept "
        f"beside its complete pairs and flip label, is not named yet; asked of {run_id} "
        f"for {role}"
    )
