"""A cited run's results files as the commit gate reads them: plain JSON, no eval code.

The adoption gate judges a run a switched record cites from the results files themselves, never
from the run index's own standing (the index is only a locator and a digest). `read_run_files`
parses the files of a results directory once, at the boundary, into frozen values; everything
after it works on those values.

What the gate derives itself: a run's lineage (the chain of `continues` links over the files) and
its complete pairs, which restate the eval's `pairs_of` rule (the latest session of each arm for a
task of the role, counted when both were measured; a parity test pins the two together). What it
reads as recorded, without recomputing: the flip label and the checks a verdict scored. A results
file records them in one of two ways:

- `Lineage`: the file's `standing` key, written by the part that ends a lineage (pin: per role,
  `lineage_root`, `parts`, `complete_pairs`, `flip`, `scored_checks`).
- `LegacyOnePart`: a file written before `standing` existed and neither continuing nor continued
  by another file, whose verdict for each role is the standing of the run itself.

Any other file without a `standing` is `Unrecorded`, and the evidence it cannot give is refused,
never guessed. A file that is not a results file at all (the index among them) is passed over.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Literal, get_args

from kernel_run_standing import (
    NOT_CLEAR,
    UNDERPOWERED,
    Flip,
    Standing,
    as_list,
    as_mapping,
    as_text,
    read_standing,
)

RESULTS_SCHEMA = "adherence/1"
RESULTS_GLOB = "*.json"
CLOSED_ENDING = "closed"
LEGACY_ENDING = "legacy"  # a file written before runs recorded how they ended
_UNRECORDED_PART = "run {} is part of a continued run and records no standing"
CONVENTION_CHECK_TEMPLATE = (
    "<role>: it follows the convention its project's instruction file states"
)

Arm = Literal["full", "lean"]
ARMS: tuple[Arm, ...] = get_args(Arm)


class RunEvidenceError(ValueError):
    """The results files cannot give the evidence asked of them; the message says why."""


def convention_check_name(role: str) -> str:
    """The name of the check that reads whether `role` followed its task's project convention."""
    return CONVENTION_CHECK_TEMPLATE.replace("<role>", role)


# -- The values a results directory parses into ---------------------------------------


@dataclass(frozen=True)
class SessionRow:
    """One session a results file records: whose it was, and whether it was measured."""

    role: str
    task_id: str
    template_id: str
    arm: Arm
    measured: bool


@dataclass(frozen=True)
class LineageStanding:
    """A `standing` entry: the parts of the lineage it was written for, and what they reached."""

    parts: tuple[str, ...]
    figures: Standing


@dataclass(frozen=True)
class Lineage:
    """The standing a file records for its whole lineage, by role."""

    standing: Mapping[str, LineageStanding]


@dataclass(frozen=True)
class LegacyOnePart:
    """The standing of a one-part file written before `standing`, read from its verdicts."""

    roles: Mapping[str, Standing]


@dataclass(frozen=True)
class Unrecorded:
    """A file that records no standing it can be trusted to give, and why."""

    reason: str


Recorded = Lineage | LegacyOnePart | Unrecorded


@dataclass(frozen=True)
class RunFile:
    """A results file: its run, the run it continues, how it ended, its sessions in file order."""

    run_id: str
    continues: str | None
    ending: str
    sessions: tuple[SessionRow, ...]
    recorded: Recorded


@dataclass(frozen=True)
class Derived:
    """What the gate counts itself for one role of one run: the lineage's parts, oldest first,
    and its complete pairs."""

    parts: tuple[str, ...]
    complete_pairs: int


# -- Reading: the boundary ---------------------------------------------------------------


def read_run_files(results_dir: Path) -> tuple[RunFile, ...]:
    """The results files of `results_dir` in file-name order; JSON that is no results file is
    passed over."""
    files = []
    for path in sorted(results_dir.glob(RESULTS_GLOB)):
        try:
            data = json.loads(path.read_bytes())
            if isinstance(data, Mapping) and data.get("schema_version") == RESULTS_SCHEMA:
                files.append(_parse_file(data))
        except (OSError, ValueError, KeyError, TypeError):  # whatever its shape, it is no run
            continue
    continued = {file.continues for file in files if file.continues is not None}
    return tuple(_unless_continued(file, continued) for file in files)


def _parse_file(data: Mapping[str, Any]) -> RunFile:
    run = as_mapping(data["run"], "run")
    continues = run.get("continues")
    run_id = as_text(run["id"], "run id")
    return RunFile(
        run_id,
        None if continues is None else as_text(continues, "continues"),
        as_text(as_mapping(run.get("ending") or {}, "ending").get("kind", LEGACY_ENDING), "ending"),
        tuple(_session(row) for row in as_list(data["sessions"], "sessions")),
        _recorded(data, run_id, continues is None),
    )


def _session(row: Any) -> SessionRow:
    row = as_mapping(row, "session")
    setup, status = as_mapping(row["setup"], "setup"), as_mapping(row["status"], "status")
    arm = setup["arm"]
    if arm not in ARMS:
        raise ValueError(f"arm {arm!r} is none of {', '.join(ARMS)}")
    return SessionRow(
        as_text(setup["role"], "role"),
        as_text(setup["task_id"], "task_id"),
        as_text(setup["template_id"], "template_id"),
        arm,
        status["kind"] == "measured",
    )


def _recorded(data: Mapping[str, Any], run_id: str, starts_a_run: bool) -> Recorded:
    """The standing a file records, before the files beside it say whether anything continues it."""
    try:
        if "standing" in data:
            return Lineage(_standing_entries(data["standing"]))
        if starts_a_run:
            return LegacyOnePart(_legacy_roles(data["verdicts"]))
    except (ValueError, KeyError, TypeError) as exc:
        return Unrecorded(f"run {run_id} records a standing this gate cannot read: {exc}")
    return Unrecorded(_UNRECORDED_PART.format(run_id))


def _unless_continued(file: RunFile, continued: set[str]) -> RunFile:
    """A one-part reading holds only for a file nothing continues."""
    if isinstance(file.recorded, LegacyOnePart) and file.run_id in continued:
        return replace(file, recorded=Unrecorded(_UNRECORDED_PART.format(file.run_id)))
    return file


def _standing_entries(value: Any) -> dict[str, LineageStanding]:
    entries = {}
    for role, entry in as_mapping(value, "standing").items():
        entry = as_mapping(entry, "standing entry")
        parts = tuple(as_text(part, "parts") for part in as_list(entry["parts"], "parts"))
        if not parts or as_text(entry["lineage_root"], "lineage_root") != parts[0]:
            raise ValueError(
                f"the standing of {role} does not name its lineage root as its first part"
            )
        entries[as_text(role, "role")] = LineageStanding(
            parts, read_standing(entry["complete_pairs"], entry["flip"], entry["scored_checks"])
        )
    return entries


def _legacy_roles(verdicts: Any) -> dict[str, Standing]:
    roles = {}
    for role, verdict in as_mapping(verdicts, "verdicts").items():
        verdict = as_mapping(verdict, "verdict")
        flip = verdict.get("flip")
        if flip is None and verdict.get("underpowered") is True:
            flip = UNDERPOWERED
        names = verdict.get("check_verdicts") or verdict.get("check_details") or {}
        left_out = set(as_list(verdict["not_covered"], "not_covered"))
        scored = sorted(set(as_mapping(names, "check verdicts")) - left_out)
        roles[as_text(role, "role")] = read_standing(verdict["complete_pairs"], flip, scored)
    return roles


# -- Deriving and judging ------------------------------------------------------------------


def derive(files: Sequence[RunFile], run_id: str, role: str) -> Derived:
    """The lineage `run_id` is part of and the role's complete pairs over it; raises when the
    files give no one lineage (a missing file, a gap, a fork, a loop)."""
    lineage = _lineage_of(files, run_id)
    return Derived(tuple(part.run_id for part in lineage), _complete_pairs(lineage, role))


def recorded_standing(files: Sequence[RunFile], run_id: str, role: str) -> Standing:
    """What the last part of `run_id`'s lineage records for `role`; raises when it records none."""
    tip = _lineage_of(files, run_id)[-1]
    match tip.recorded:
        case Lineage(standing=entries) if role in entries:
            return entries[role].figures
        case LegacyOnePart(roles=roles) if role in roles:
            return roles[role]
        case Unrecorded(reason=reason):
            raise RunEvidenceError(reason)
        case _:
            raise RunEvidenceError(f"run {tip.run_id} records no standing for {role}")


def judged_standing(files: Sequence[RunFile], run_id: str, role: str) -> Flip:
    """The flip standing the gate judges: not clear for a lineage closed on request, else the
    standing its last part records; raises when none is recorded."""
    tip = _lineage_of(files, run_id)[-1]
    if tip.ending == CLOSED_ENDING:
        return NOT_CLEAR
    return recorded_standing(files, run_id, role).flip


def _lineage_of(files: Sequence[RunFile], run_id: str) -> tuple[RunFile, ...]:
    """The chain of `continues` links through `run_id`, oldest part first."""
    held = _held_by_id(files)
    root = _root_of(held, run_id)
    children: dict[str, list[str]] = {}
    for file in files:
        if file.continues is not None:
            children.setdefault(file.continues, []).append(file.run_id)
    chain = [held[root]]
    while next_ids := children.get(chain[-1].run_id):
        if len(next_ids) > 1:
            raise RunEvidenceError(
                f"run {chain[-1].run_id} is continued by {len(next_ids)} runs: {', '.join(next_ids)}"
            )
        chain.append(held[next_ids[0]])
    return tuple(chain)


def _held_by_id(files: Sequence[RunFile]) -> dict[str, RunFile]:
    held: dict[str, RunFile] = {}
    for file in files:
        if file.run_id in held:
            raise RunEvidenceError(f"two results files hold run {file.run_id}")
        held[file.run_id] = file
    return held


def _root_of(held: Mapping[str, RunFile], run_id: str) -> str:
    if run_id not in held:
        raise RunEvidenceError(f"no results file holds run {run_id}")
    file, seen = held[run_id], {run_id}
    while file.continues is not None:
        if file.continues in seen:
            raise RunEvidenceError(
                f"run {file.run_id} continues {file.continues}, which continues it"
            )
        if file.continues not in held:
            raise RunEvidenceError(
                f"run {file.run_id} continues {file.continues}, which no results file holds"
            )
        seen.add(file.continues)
        file = held[file.continues]
    return file.run_id


def _complete_pairs(lineage: Sequence[RunFile], role: str) -> int:
    """A task of the role is one complete pair when the latest session of each arm, across the
    parts in order, was measured (the eval's pairing rule)."""
    latest: dict[tuple[str, str], dict[Arm, bool]] = {}
    for part in lineage:
        for session in part.sessions:
            if session.role == role:
                task = (session.task_id, session.template_id)
                latest.setdefault(task, {})[session.arm] = session.measured
    return sum(1 for arms in latest.values() if set(arms) == set(ARMS) and all(arms.values()))
