"""What this change adds to an adherence results file, as the Seam Contract pins it.

Two halves, both pure over a results document (parsed JSON, never the eval's own types:
a scenario reads what the file says, not what the runner thinks it wrote):

- readers: an errored session's tails (pin W2), the declared stop rule and allowance
  method (W1), the ending of a run (W3), its lineage (W4), the earlier runs it lists and
  the JSON files it skipped (W7), and the tasks its lean sessions failed;
- a builder of a stopped run's document (`stopped_run_document`) from the document the
  runner wrote for the same plan, with every session of every task run to a gradeable end:
  the builder keeps what the runner wrote (declarations, tree, arms, catalog, the sessions
  that ran) and adds the stop's own fields (the errored sessions and their tails, the
  ending, the recorded launch order, the retries, the spend). Whatever the runner declares
  for itself (the stop rule, the allowance method, the measured identity) is the runner's,
  so a continuation compares the runner's declarations with its own, never a stand-in's.

The tail text, the kind names and the ending shapes are the Seam Contract's. The one
translation is in the specification's terms: the runner's `result_error` is the
specification's "error result".
"""

from __future__ import annotations

import copy
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Literal

Document = dict[str, Any]

# -- Types the readers return ---------------------------------------------------------------------


@dataclass(frozen=True)
class LaunchedSession:
    arm: str
    task_id: str
    attempt: int  # 1 for a task's first session in that arm, 2 for its retry


@dataclass(frozen=True)
class ErrorTails:
    task_id: str
    arm: str
    error_output: str
    result_text: str


@dataclass(frozen=True)
class StopReason:
    error_kind: str
    masked_tail: str
    streak: tuple[LaunchedSession, ...]
    other_arm_same: bool  # the other arm ended in the same kind and tail inside the window


@dataclass(frozen=True)
class StopSettings:
    stop_count: int
    counting_kinds: frozenset[str]
    masking_rule: str
    declared_before_first_launch: bool


@dataclass(frozen=True)
class LineagePart:
    run_id: str
    stop: str | None  # the stop that ended this part; None for the part that finished


@dataclass(frozen=True)
class EarlierRun:
    run_ids: tuple[str, ...]  # one id, or every part of a continued lineage
    flip: str  # "clear", "not clear" or "underpowered"
    interim: bool = False  # a closed run, carrying its interim per-check result


@dataclass(frozen=True)
class EarlierRunsListing:
    draws: tuple[EarlierRun, ...]  # same role definition and kernel identity, in order
    apart: Mapping[str, str]  # run id -> how its identity differs ("identity unknown" included)
    calibration: tuple[str, ...]
    skipped_files: tuple[str, ...]  # names of JSON files beside it that are not results files


# -- Readers --------------------------------------------------------------------------------------


def read_document(results_path: Path) -> Document:
    assert results_path.is_file(), f"the run wrote no results file at {results_path}"
    return json.loads(results_path.read_text(encoding="utf-8"))


def _pinned(container: Mapping[str, Any], key: str, what: str) -> Any:
    """A field the Seam Contract pins; its absence is the missing behaviour, named."""
    assert key in container, f"the results file records no {what} (missing {key!r})"
    return container[key]


def _spec_kind(kind: str) -> str:
    """An error kind in the specification's words ("an error result", not `result_error`)."""
    return "error_result" if kind == "result_error" else kind


def error_tails(results_path: Path) -> list[ErrorTails]:
    found = []
    for record in read_document(results_path)["sessions"]:
        status, setup = record["status"], record["setup"]
        if status["kind"] != "errored":
            continue
        tails = _pinned(status, "tails", f"tails for the errored session of {setup['task_id']}")
        found.append(
            ErrorTails(
                setup["task_id"],
                setup["arm"],
                _pinned(tails, "error", "error-output tail"),
                _pinned(tails, "result", "result-text tail"),
            )
        )
    return found


def _stop_rule(document: Document) -> Mapping[str, Any]:
    return _pinned(document["settings"], "stop_rule", "stop rule among its declared settings")


def declared_tail_bound(results_path: Path) -> int:
    return int(_pinned(_stop_rule(read_document(results_path)), "tail_chars", "tail bound"))


def declared_stop_settings(results_path: Path) -> StopSettings:
    document = read_document(results_path)
    rule = _stop_rule(document)
    declared = datetime.fromisoformat(document["settings"]["declared_at"])
    starts = (datetime.fromisoformat(s["started_at"]) for s in document["sessions"])
    return StopSettings(
        stop_count=int(_pinned(rule, "count", "stop count")),
        counting_kinds=frozenset(_spec_kind(k) for k in _pinned(rule, "kinds", "counting kinds")),
        masking_rule=str(_pinned(rule, "masking", "masking rule")),
        declared_before_first_launch=all(declared < start for start in starts),
    )


def declared_allowance_method(results_path: Path) -> str:
    """The allowance method among the declared settings; empty when none is declared."""
    return str(read_document(results_path)["settings"].get("allowance_method") or "")


def allowance_taken_from_calibration(results_path: Path) -> bool:
    settings = read_document(results_path)["settings"]
    return settings.get("allowance_source") is not None or bool(settings.get("allowances"))


def _ending(document: Document) -> Mapping[str, Any] | None:
    return document["run"].get("ending")


def stop_reason(results_path: Path) -> StopReason | None:
    ending = _ending(read_document(results_path))
    if ending is None or ending.get("kind") != "infra_stopped":
        return None
    return StopReason(
        error_kind=_spec_kind(ending["error_kind"]),
        masked_tail=ending["masked_tail"],
        streak=tuple(
            LaunchedSession(s["arm"], s["task_id"], int(s["attempt"])) for s in ending["sessions"]
        ),
        other_arm_same=ending["scope"] == "both-arms",
    )


def lineage(results_path: Path) -> list[LineagePart]:
    """Every part of a continued run's lineage in order; empty for a run that continues none."""
    parts = read_document(results_path)["run"].get("lineage") or []
    return [LineagePart(part["run_id"], part["stop"]) for part in parts]


def lean_failure_tasks(results_path: Path, role: str) -> set[str]:
    """Tasks whose full side was measured and whose lean side ended errored, over the lineage.

    The worst-case recount's own definition, over the latest session of each task and arm
    across every part of the lineage in order.
    """
    parts = [part.run_id for part in lineage(results_path)]
    paths = [results_path.with_name(f"{run_id}.json") for run_id in parts] or [results_path]
    latest: dict[tuple[str, str], str] = {}
    for path in paths:
        for record in read_document(path)["sessions"]:
            setup = record["setup"]
            if setup["role"] == role:
                latest[(setup["task_id"], setup["arm"])] = record["status"]["kind"]
    return {
        task
        for (task, arm), kind in latest.items()
        if arm == "lean" and kind == "errored" and latest.get((task, "full")) == "measured"
    }


def earlier_runs(results_path: Path, role: str) -> EarlierRunsListing:
    extra = read_document(results_path)["run"]
    listed = (extra.get("earlier") or {}).get(role) or {}
    return EarlierRunsListing(
        draws=tuple(
            EarlierRun(tuple(d["run_ids"]), d["flip"], bool(d.get("interim", False)))
            for d in listed.get("draws", ())
        ),
        apart=dict(listed.get("apart", {})),
        calibration=tuple(listed.get("calibration", ())),
        skipped_files=tuple(extra.get("skipped_files") or ()),
    )


COMPLETE_PAIRS_LINE = re.compile(r"^\s+(\d+) complete pairs of \d+ paired tasks;", re.MULTILINE)


def complete_pairs_in_report(role_section: str) -> int:
    """The complete pairs a role's report section states in its headline."""
    found = COMPLETE_PAIRS_LINE.search(role_section)
    assert found, "the report states no complete pairs for the role"
    return int(found[1])


# -- A stopped run's document ---------------------------------------------------------------------

TaskShape = Literal[
    "complete pair",
    "both sessions inside the streak",
    "full complete and lean inside the streak",
    "lean of the stopping kind and tail before the streak",
    "lean-only error of another kind",
    "full-only error of another kind",
    "refused launch",
    "never launched",
]
StopVariant = Literal[
    "both arms in the streak",
    "confined to one arm",
    "operator interrupt",
    "complete",
    "already continued",
]

CRASH_TAIL = "fatal: the session channel closed unexpectedly"
STREAK_SHAPES = frozenset(
    {"both sessions inside the streak", "full complete and lean inside the streak"}
)
SECONDS_BETWEEN_SESSIONS = 1

Outcome = Literal["ran", "stopping error", "lean-side error", "full-side error", "refused"]
# kind, detail, error-output tail, cost: every errored kind but a refusal is retried once
_ERRORS: Mapping[str, tuple[str, str, str, float]] = {
    "stopping error": ("exit_nonzero", "exit_code=1 result_subtype=None", CRASH_TAIL, 3.0),
    "lean-side error": ("no_result_event", "the stream ended without a result event", "", 3.0),
    "full-side error": ("envelope_unparseable", "the stream could not be parsed", "", 3.0),
    "refused": (
        "launch_refused",
        "the run's spend cap leaves no room for another session",
        "",
        0.0,
    ),
}


@dataclass(frozen=True)
class _Session:
    task_id: str
    arm: str
    attempt: int
    outcome: Outcome


def _outcomes(
    shape: TaskShape, *, confined_to_one_arm: bool
) -> tuple[list[Outcome], list[Outcome]]:
    """What a task's full and lean sessions are, retries included, in launch order."""
    stopping: list[Outcome] = ["stopping error"] * 2
    match shape:
        case "complete pair":
            return ["ran"], ["ran"]
        case "lean of the stopping kind and tail before the streak":
            return ["ran"], stopping
        case "lean-only error of another kind":
            return ["ran"], ["lean-side error"] * 2
        case "full-only error of another kind":
            return ["full-side error"] * 2, ["ran"]
        case "full complete and lean inside the streak":
            return ["ran"], stopping
        case "both sessions inside the streak":
            return (["ran"] if confined_to_one_arm else stopping), stopping
        case "refused launch":
            return ["refused"], ["refused"]
        case "never launched":
            return [], []


def _timeline(
    tasks: Sequence[str], shapes: Sequence[TaskShape], variant: StopVariant, stop_count: int
) -> tuple[list[_Session], list[_Session]]:
    """Every session in launch order (a task's full arm, then its lean arm), and the streak.

    The lean arm's stopping errors run until the stop count is reached; the run launches
    nothing after the session that reaches it. A task's full arm precedes its lean arm
    whatever the seed drew, so the stop's composition never depends on the draw.
    """
    sessions: list[_Session] = []
    streak: list[_Session] = []
    remaining = stop_count
    for task, shape in zip(tasks, shapes, strict=True):
        if variant == "operator interrupt" and shape in STREAK_SHAPES:
            break
        full, lean = _outcomes(shape, confined_to_one_arm=variant == "confined to one arm")
        if shape in STREAK_SHAPES:
            lean = lean[:remaining]
        for arm, outcomes in (("full", full), ("lean", lean)):
            for attempt, outcome in enumerate(outcomes, start=1):
                session = _Session(task, arm, attempt, outcome)
                sessions.append(session)
                if arm == "lean" and shape in STREAK_SHAPES:
                    streak.append(session)
        if shape in STREAK_SHAPES:
            remaining -= len(lean)
            if remaining == 0:
                break
    if variant != "operator interrupt":
        assert remaining == 0, f"the shapes form no streak of {stop_count} stopping sessions"
    return sessions, streak


def stopped_run_document(
    template: Document,
    *,
    shapes: Sequence[TaskShape],
    variant: StopVariant,
    launch_orders: Mapping[str, tuple[str, str]],
    swap_first_launch_order: bool = False,
) -> Document:
    """The results document of a run of the template's plan that stopped as `variant` says.

    `template` is the document the runner wrote for the same plan with every session run to a
    gradeable end; the planned tasks take `shapes` in planned order. `launch_orders` is the
    order the seed gives each task; `swap_first_launch_order` records the opposite order for
    the first planned task.
    """
    document = copy.deepcopy(template)
    run, role = document["run"], document["run"]["roles"][0]
    tasks = run["tasks"][role]
    assert len(tasks) == len(shapes), f"{len(tasks)} planned tasks cannot take {len(shapes)} shapes"
    run["launch_order"] = {role: _recorded_orders(tasks, launch_orders, swap_first_launch_order)}
    if variant == "complete":
        return document
    stop_count = int(document["settings"].get("stop_rule", {}).get("count", 3))
    sessions, streak = _timeline(tasks, shapes, variant, stop_count)
    ran = {(r["setup"]["task_id"], r["setup"]["arm"]): r for r in document["sessions"]}
    declared = datetime.fromisoformat(document["settings"]["declared_at"])
    records = [
        _record(session, ran, declared + timedelta(seconds=SECONDS_BETWEEN_SESSIONS * (i + 1)))
        for i, session in enumerate(sessions)
    ]
    document["sessions"] = records
    last = datetime.fromisoformat(records[-1]["started_at"]) if records else declared
    run.update(
        complete=False,
        refused_launches=[
            f"{role} {s.arm} {s.task_id}: {_ERRORS['refused'][1]}"
            for s in sessions
            if s.outcome == "refused"
        ],
        retries=[
            {"role": role, "arm": s.arm, "task_id": s.task_id, "after": _ERRORS[s.outcome][0]}
            for s in sessions
            if s.attempt == 2
        ],
        spend={**run["spend"], "spent_usd": sum(r["cost_usd"] for r in records)},
        finished_at=(last + timedelta(seconds=SECONDS_BETWEEN_SESSIONS)).isoformat(),
        ending=_ending_of(variant, role, streak),
    )
    return document


def _recorded_orders(
    tasks: Sequence[str], orders: Mapping[str, tuple[str, str]], swap_first: bool
) -> dict[str, list[str]]:
    recorded = {task: list(orders[task]) for task in tasks}
    if swap_first:
        recorded[tasks[0]].reverse()
    return recorded


def _record(session: _Session, ran: Mapping[tuple[str, str], Any], at: datetime) -> Document:
    if session.outcome == "ran":
        return {**copy.deepcopy(ran[(session.task_id, session.arm)]), "started_at": at.isoformat()}
    kind, detail, tail, cost = _ERRORS[session.outcome]
    setup = copy.deepcopy(ran[(session.task_id, session.arm)]["setup"])
    status = {
        "kind": "errored",
        "error_kind": kind,
        "detail": detail,
        "setup": setup,
        "tails": {"error": tail, "result": ""},
    }
    return {
        "setup": setup,
        "status": status,
        "cost_usd": cost,
        "duration_ms": 400,
        "started_at": at.isoformat(),
    }


def _ending_of(variant: StopVariant, role: str, streak: Sequence[_Session]) -> Document:
    if variant == "operator interrupt":
        return {"kind": "interrupted"}
    kind, _, tail, _ = _ERRORS["stopping error"]
    return {
        "kind": "infra_stopped",
        "error_kind": kind,
        "masked_tail": tail,
        "role": role,
        "arm": "lean",
        "sessions": [{"task_id": s.task_id, "arm": s.arm, "attempt": s.attempt} for s in streak],
        "scope": "one-arm" if variant == "confined to one arm" else "both-arms",
    }


def stop_description(document: Document) -> str:
    """The stop in the words a lineage names it by."""
    ending = document["run"]["ending"]
    return (
        f"{len(ending['sessions'])} {ending['arm']} sessions in a row ended in"
        f" {ending['error_kind']} with the same evidence"
    )


def continuation_document(stopped: Document, run_id: str) -> Document:
    """A later part of `stopped`'s lineage that has launched nothing yet and was interrupted."""
    part = copy.deepcopy(stopped)
    stopped_id = stopped["run"]["id"]
    run = part["run"]
    began = datetime.fromisoformat(run["finished_at"]) + timedelta(seconds=SECONDS_BETWEEN_SESSIONS)
    part["sessions"] = []
    part["settings"]["declared_at"] = began.isoformat()
    run.update(
        id=run_id,
        started_at=began.isoformat(),
        finished_at=(began + timedelta(seconds=SECONDS_BETWEEN_SESSIONS)).isoformat(),
        complete=False,
        refused_launches=[],
        retries=[],
        spend={**run["spend"], "spent_usd": 0.0},
        ending={"kind": "interrupted"},
        continues=stopped_id,
        lineage=[
            {"run_id": stopped_id, "stop": stop_description(stopped)},
            {"run_id": run_id, "stop": None},
        ],
    )
    return part
