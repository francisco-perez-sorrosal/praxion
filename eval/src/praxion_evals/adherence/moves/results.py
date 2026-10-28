"""A move run's results file (``move-results/1``), the index beside it, and the runs it lists.

One file per run in ``moves/``, rewritten whole and atomically after every session, with the
index (``moves/index.json``) regenerated whole after each write and by ``--reindex``. A move
never writes outside ``moves/``: every role reader globs the role directory without recursing,
so the flip gate and the role index stay byte-identical.

The ``run_kind`` tag selects one of two shapes and refuses the other's fields: a floor run
carries no pairs, no verdicts and no citation; a paired run always cites a floor lineage. A
paired run's complete pairs are derived from its sessions on every write, never read back; its
verdicts and flip are stored as the runner computed them over the whole lineage, since that rule
lives in ``verdict``. Raw JSON becomes typed values once, in :func:`from_json`.

A run's ``identity`` is the declaration's whole (the rule text and every arm's changes), whatever
the run kind, so a floor run and a paired run of one declaration list each other.
"""

from __future__ import annotations

import json
import re
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any, ClassVar, Literal, assert_never, get_args

from praxion_evals.adherence.lineage import Finished, Interrupted, PartRef, SpendRefused, chain_of
from praxion_evals.adherence.model import (
    DeclaredSettings,
    Failed,
    Passed,
    _frozen,
    _non_empty,
    _one_of,
    _require,
    settings_from_json,
    settings_to_json,
)
from praxion_evals.adherence.moves.lineage import (
    ChangeDigest,
    Closed,
    MoveEnding,
    MoveIdentity,
    Stopped,
)
from praxion_evals.adherence.moves.model import (
    ARMS_OF,
    MOVE_ARMS,
    Arrival,
    ArrivalTiming,
    Arrived,
    Channel,
    CheckTrigger,
    History,
    MoveArm,
    MoveName,
    NeverArrived,
    Pinned,
    RunKind,
    Unknown,
)
from praxion_evals.adherence.moves.stop import Launched, MoveStopReason, Scope
from praxion_evals.adherence.results import (
    CLOSED_ENDING_KIND,
    FLIP_LABELS,
    RUN_INDEX_NAME,
    FlipLabel,
    _need,
    instant,
    write_text_atomic,
)

SCHEMA = "move-results/1"
INDEX_SCHEMA = 1
MOVES_DIR_NAME = "moves"
ALLOWANCE_METHOD: Mapping[RunKind, str] = {"floor": "none", "paired": "own-discordance-exact"}

SessionStatus = Literal["scored", "refused", "errored"]
FloorStanding = Literal["finished", "stopped", "closed"]
Standing = FlipLabel | FloorStanding

_RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
_NEVER, _UNKNOWN = "never", "unknown"
_TIMINGS: tuple[str, ...] = get_args(ArrivalTiming)
_HISTORIES: tuple[str, ...] = get_args(History)
_CHANNELS: tuple[str, ...] = get_args(Channel)
_STATUSES: tuple[str, ...] = get_args(SessionStatus)
_SCOPES: tuple[str, ...] = get_args(Scope)

# ---------------------------------------------------------------------------
# The values
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MoveSession:
    """One launched session: scored (with what each governed check saw and left), refused scoring
    by the take, or errored. ``reason`` and ``checks`` are legal in exactly one of those shapes."""

    session_id: str
    task_id: str
    arm: MoveArm
    attempt: int
    status: SessionStatus
    reason: str | None
    checks: Mapping[str, CheckTrigger]
    started_at: str
    cost_usd: float = 0.0
    duration_ms: int = 0

    def __post_init__(self) -> None:
        _non_empty(self.session_id, "a session's identifier")
        _non_empty(self.task_id, "a session's task")
        _one_of(self.arm, MOVE_ARMS, "a session's arm")
        _one_of(self.status, _STATUSES, "a session's status")
        _require(self.attempt >= 1, "a session's attempt counts from 1")
        _require(self.cost_usd >= 0 and self.duration_ms >= 0, "a session's spend is not negative")
        instant(self.started_at, "a session's started_at")
        if self.status == "scored":
            _require(self.reason is None, "a scored session has no reason")
            _require(bool(self.checks), "a scored session records the checks it graded")
        else:
            _non_empty(self.reason or "", f"the {self.status} session's reason")
            _require(not self.checks, f"a {self.status} session graded no check")
        for name, trigger in self.checks.items():
            _require(name == trigger.check, f"the record under {name!r} is for {trigger.check!r}")
        _frozen(self, "checks", self.checks)


@dataclass(frozen=True)
class EarlierMoveRuns:
    """The move's earlier runs by lineage: floor runs apart from paired draws, and apart from both
    the runs of another identity, each with how it differs."""

    floor: tuple[str, ...] = ()
    paired: tuple[str, ...] = ()
    apart: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _frozen(self, "apart", self.apart)


@dataclass(frozen=True)
class MoveRunCommon:
    run_id: str
    move: MoveName
    identity: MoveIdentity
    settings: DeclaredSettings
    pinned: Mapping[MoveArm, Pinned]
    declared_at: str
    first_launch_at: str | None  # None until the first launch
    seed: int
    launch_orders: Mapping[str, tuple[MoveArm, MoveArm]]
    sessions: tuple[MoveSession, ...]
    continues: str | None
    ending: MoveEnding
    harness_version: str
    earlier: EarlierMoveRuns

    def __post_init__(self) -> None:
        _require(bool(_RUN_ID.fullmatch(self.run_id)), f"{self.run_id!r} is not a file-safe run id")
        _require(self.continues != self.run_id, "a run cannot continue itself")
        _non_empty(self.harness_version, "the harness version")
        declared = instant(self.declared_at, "the declared_at")
        if self.first_launch_at is None:
            _require(not self.sessions, "a run with sessions records its first launch")
        else:
            first = instant(self.first_launch_at, "the first_launch_at")
            _require(declared < first, "the settings are declared before the first launch")
            for session in self.sessions:
                _require(
                    first <= instant(session.started_at, "a session's started_at"),
                    f"the session {session.session_id} began before the first launch",
                )
        keys = [(s.task_id, s.arm, s.attempt) for s in self.sessions]
        _require(len(set(keys)) == len(keys), "a task's attempt in an arm is recorded once")
        _frozen(self, "pinned", self.pinned)
        _frozen(self, "launch_orders", self.launch_orders)


@dataclass(frozen=True)
class FloorRun:
    run_kind: ClassVar[RunKind] = "floor"
    common: MoveRunCommon

    def __post_init__(self) -> None:
        _arms_agree(self.common, self.run_kind)
        _require(not self.common.launch_orders, "a floor run has one arm, so no launch order")


@dataclass(frozen=True)
class PairedRun:
    run_kind: ClassVar[RunKind] = "paired"
    common: MoveRunCommon
    cited_floor: tuple[str, ...]  # every part of the cited floor lineage, oldest first
    flip: FlipLabel  # the lineage's reading so far, as the runner computed it
    verdicts: Mapping[str, str]  # governed check -> verdict word; none while underpowered

    def __post_init__(self) -> None:
        common = self.common
        _arms_agree(common, self.run_kind)
        _require(bool(self.cited_floor), "a paired run cites a floor lineage")
        _require(len(set(self.cited_floor)) == len(self.cited_floor), "a floor part is cited once")
        _one_of(self.flip, FLIP_LABELS, "the flip")
        _require(
            self.flip != "underpowered" or not self.verdicts,
            "an underpowered run has no per-check verdicts",
        )
        for task, order in common.launch_orders.items():
            _require(sorted(order) == ["full", "lean"], f"the order of {task} names both arms")
        for session in common.sessions:
            _require(
                session.task_id in common.launch_orders,
                f"the task {session.task_id} launched without a recorded order",
            )
        _frozen(self, "verdicts", self.verdicts)

    @property
    def complete_pairs(self) -> int:
        """Tasks whose latest session in each arm was scored; a later record replaces an earlier."""
        latest: dict[tuple[str, MoveArm], bool] = {}
        for session in self.common.sessions:
            latest[(session.task_id, session.arm)] = session.status == "scored"
        tasks = {task for task, _ in latest}
        return sum(latest.get((t, "full"), False) and latest.get((t, "lean"), False) for t in tasks)


MoveRun = FloorRun | PairedRun


def _arms_agree(common: MoveRunCommon, kind: RunKind) -> None:
    arms = set(ARMS_OF[kind])
    _require(set(common.pinned) == arms, f"a {kind} run pins the settings of {sorted(arms)}")
    stray = {s.arm for s in common.sessions} - arms
    _require(not stray, f"a {kind} run launched no session in {sorted(stray)}")


# ---------------------------------------------------------------------------
# Writing and reading, under moves/ alone
# ---------------------------------------------------------------------------


def write(moves_dir: Path, run: MoveRun) -> Path:
    """Replace the run's file whole, then the index; nothing outside ``moves_dir`` is touched."""
    _require(moves_dir.name == MOVES_DIR_NAME, f"move results are written under {MOVES_DIR_NAME}/")
    path = moves_dir / f"{run.common.run_id}.json"
    _refuse_changed_declaration(path, run)
    write_text_atomic(path, json.dumps(to_json(run), indent=2) + "\n")
    write_index(moves_dir)
    return path


def _refuse_changed_declaration(path: Path, run: MoveRun) -> None:
    if not path.exists():
        return
    try:
        before = load(path)
    except ValueError:
        return  # not a move results file: nothing declared there to protect
    if _declared(before) != _declared(run):
        raise ValueError(f"what run {run.common.run_id} declared cannot change once written")


def _declared(run: MoveRun) -> tuple[object, ...]:
    common = run.common
    return (
        run.run_kind,
        common.identity,
        common.settings,
        common.pinned,
        common.declared_at,
        common.seed,
    )


def load(path: Path) -> MoveRun:
    """Read a move results file; refuses what is not one, naming why."""
    try:
        return from_json(json.loads(path.read_text(encoding="utf-8")))
    except json.JSONDecodeError as error:
        raise ValueError(f"{path.name} is not a JSON move results file: {error}") from error


def read_directory(moves_dir: Path) -> tuple[list[MoveRun], list[str]]:
    """The runs in ``moves_dir`` and the names of the other JSON files; never refuses a directory.

    A file whose name is not its run's identifier is not trusted to be that run's file.
    """
    runs: list[MoveRun] = []
    skipped: list[str] = []
    for path in sorted(moves_dir.glob("*.json")):
        if path.name == RUN_INDEX_NAME:
            continue
        try:
            run = load(path)
        except (OSError, ValueError, KeyError, TypeError):  # whatever its shape, it is named
            skipped.append(path.name)
            continue
        if path.stem == run.common.run_id:
            runs.append(run)
        else:
            skipped.append(path.name)
    return runs, skipped


# ---------------------------------------------------------------------------
# Lineages, the index and the listing of earlier runs
# ---------------------------------------------------------------------------


def lineage_groups(runs: Sequence[MoveRun], moves_dir: Path) -> list[tuple[MoveRun, ...]]:
    """The runs grouped into lineages, each oldest part first, in the order first met. A run whose
    chain has a gap, a loop or a fork stands alone: a listing names what it finds."""
    held = {run.common.run_id: run for run in runs}
    refs = {
        run_id: PartRef(run_id, moves_dir / f"{run_id}.json", run.common.continues)
        for run_id, run in held.items()
    }
    chains: dict[tuple[str, ...], None] = {}
    for run_id in held:
        try:
            chains[tuple(part.run_id for part in chain_of(refs, run_id))] = None
        except ValueError:
            chains[(run_id,)] = None
    return [tuple(held[run_id] for run_id in chain) for chain in chains]


def write_index(moves_dir: Path) -> Path:
    """Regenerate ``index.json`` whole from the files in ``moves_dir``; the one place it is built."""
    runs, skipped = read_directory(moves_dir)
    path = moves_dir / RUN_INDEX_NAME
    write_text_atomic(path, json.dumps(index_of(runs, skipped, moves_dir), indent=2) + "\n")
    return path


def index_of(runs: Sequence[MoveRun], skipped: Sequence[str], moves_dir: Path) -> dict[str, Any]:
    entries: dict[str, Any] = {}
    for lineage in lineage_groups(runs, moves_dir):
        standing = standing_of(lineage)
        for run in lineage:
            entries[run.common.run_id] = {
                "move": run.common.move.value,
                "run_kind": run.run_kind,
                "lineage_root": lineage[0].common.run_id,
                "continues": run.common.continues,
                "ending": ending_to_json(run.common.ending)["kind"],
                "standing": standing,
            }
    return {"schema": INDEX_SCHEMA, "runs": entries, "skipped": list(skipped)}


def standing_of(lineage: Sequence[MoveRun]) -> Standing:
    """What a lineage stands on, read from its tip; a floor run never has a flip label and a
    paired run closed on request stands not clear however its sessions would read."""
    tip = lineage[-1]
    ending = tip.common.ending
    match tip:
        case FloorRun():
            return _floor_standing(ending)
        case PairedRun(flip=flip):
            return "not clear" if isinstance(ending, Closed) else flip
        case _:
            assert_never(tip)


def _floor_standing(ending: MoveEnding) -> FloorStanding:
    match ending:
        case Finished():
            return "finished"
        case Closed():
            return "closed"
        case Stopped() | SpendRefused() | Interrupted():
            return "stopped"
        case _:
            assert_never(ending)


def earlier_runs(
    moves_dir: Path,
    move: MoveName,
    identity: MoveIdentity,
    exclude: Collection[str] = (),
) -> EarlierMoveRuns:
    """Every earlier lineage of ``move`` in ``moves_dir``, listed by what it measured: those of
    ``identity`` as floor runs or paired draws, the rest apart with how they differ. ``exclude``
    names run ids that are not earlier evidence (a run's own predecessors, one it replaces)."""
    runs = [
        run
        for run in read_directory(moves_dir)[0]
        if run.common.move == move and run.common.run_id not in exclude
    ]
    floor: list[str] = []
    paired: list[str] = []
    apart: dict[str, str] = {}
    for lineage in lineage_groups(runs, moves_dir):
        tip = lineage[-1]
        label = " + ".join(run.common.run_id for run in lineage)
        if differing := identity.differences(tip.common.identity):
            apart[label] = "; ".join(differing)
        elif isinstance(tip, FloorRun):
            floor.append(label)
        else:
            paired.append(label)
    return EarlierMoveRuns(tuple(floor), tuple(paired), apart)


# ---------------------------------------------------------------------------
# JSON out
# ---------------------------------------------------------------------------


def to_json(run: MoveRun) -> dict[str, Any]:
    common = run.common
    cited, flip, verdicts, pairs = _kind_fields(run)
    return {
        "schema": SCHEMA,
        "subject": {"kind": "move", "name": common.move.value},
        "run_kind": run.run_kind,
        "run_id": common.run_id,
        "continues": common.continues,
        "harness_version": common.harness_version,
        "identity": {
            "moved_rule_text": common.identity.moved_rule_text,
            "arms": {
                arm: [{"path": c.path, "sha256": c.sha256} for c in changes]
                for arm, changes in common.identity.arms.items()
            },
        },
        "allowance_method": ALLOWANCE_METHOD[run.run_kind],
        "settings": settings_to_json(common.settings),
        "pinned": {
            arm: {f.name: getattr(p, f.name) for f in fields(p)} for arm, p in common.pinned.items()
        },
        "declared_at": common.declared_at,
        "first_launch_at": common.first_launch_at,
        "seed": common.seed,
        "launch_orders": {task: list(order) for task, order in common.launch_orders.items()},
        "sessions": [_session_to_json(s) for s in common.sessions],
        "complete_pairs": pairs,
        "verdicts": verdicts,
        "cited_floor": cited,
        **({} if flip is None else {"flip": flip}),
        "ending": ending_to_json(common.ending),
        "earlier_runs": {
            "floor": list(common.earlier.floor),
            "paired": list(common.earlier.paired),
            "apart": dict(common.earlier.apart),
        },
    }


def _kind_fields(run: MoveRun) -> tuple[list[str], FlipLabel | None, dict[str, str], int]:
    match run:
        case FloorRun():
            return [], None, {}, 0
        case PairedRun():
            return list(run.cited_floor), run.flip, dict(run.verdicts), run.complete_pairs
        case _:
            assert_never(run)


def _session_to_json(session: MoveSession) -> dict[str, Any]:
    return {
        "session_id": session.session_id,
        "task_id": session.task_id,
        "arm": session.arm,
        "attempt": session.attempt,
        "status": session.status,
        "reason": session.reason,
        "started_at": session.started_at,
        "cost_usd": session.cost_usd,
        "duration_ms": session.duration_ms,
        "checks": {name: _trigger_to_json(t) for name, t in session.checks.items()},
    }


def _trigger_to_json(trigger: CheckTrigger) -> dict[str, Any]:
    final = trigger.final
    return {
        "final": None if final is None else ("passed" if isinstance(final, Passed) else "failed"),
        **({"detail": final.detail} if isinstance(final, Failed) else {}),
        "history": trigger.history,
        "arrivals": {channel: _arrival_word(a) for channel, a in trigger.arrivals.items()},
        "refusals": list(trigger.refusals),
    }


def _arrival_word(arrival: Arrival) -> str:
    match arrival:
        case Arrived(timing=timing):
            return timing
        case NeverArrived():
            return _NEVER
        case Unknown():
            return _UNKNOWN
        case _:
            assert_never(arrival)


def ending_to_json(ending: MoveEnding) -> dict[str, Any]:
    match ending:
        case Finished():
            return {"kind": "finished"}
        case Stopped(reason=reason):
            return {
                "kind": "stopped",
                "error_kind": reason.kind,
                "masked_tail": reason.masked_tail,
                "arm": reason.arm,
                "sessions": [
                    {"task_id": s.task_id, "arm": s.arm, "attempt": s.attempt}
                    for s in reason.sessions
                ],
                "scope": reason.scope,
            }
        case SpendRefused(tasks=tasks):
            return {"kind": "spend_refused", "tasks": list(tasks)}
        case Interrupted():
            return {"kind": "interrupted"}
        case Closed(reason=reason, at=at, interim=interim, stopped=stopped):
            return {
                "kind": CLOSED_ENDING_KIND,
                "reason": reason,
                "at": at,
                "interim": dict(interim),
                "stopped": ending_to_json(stopped),
            }
        case _:
            assert_never(ending)


# ---------------------------------------------------------------------------
# JSON in: the one place raw values become typed ones
# ---------------------------------------------------------------------------


def from_json(data: Mapping[str, Any]) -> MoveRun:
    what = "a move results file"
    _require(isinstance(data, Mapping), f"{what} is a JSON object")
    version = data.get("schema")
    _require(version == SCHEMA, f"unknown results schema {version!r}, expected {SCHEMA!r}")
    subject = _object(_need(data, "subject", what), "the subject")
    _require(
        subject.get("kind") == "move",
        f"a move results file names a move as its subject, not {subject.get('kind')!r}",
    )
    kind = _need(data, "run_kind", what)
    _require(
        data.get("allowance_method") == ALLOWANCE_METHOD.get(kind),
        f"a {kind} run's allowance method is {ALLOWANCE_METHOD.get(kind)!r}",
    )
    common = _common_from_json(data, MoveName(_need(subject, "name", "the subject")))
    match kind:
        case "floor":
            _refuse_paired_fields(data)
            return FloorRun(common)
        case "paired":
            return _paired_from_json(common, data)
        case _:
            raise ValueError(f"the run kind {kind!r} is neither floor nor paired")


def _refuse_paired_fields(data: Mapping[str, Any]) -> None:
    held = [key for key in ("cited_floor", "verdicts") if data.get(key)]
    held += ["flip"] if "flip" in data else []
    held += ["complete_pairs"] if data.get("complete_pairs") else []
    _require(not held, f"a floor run carries none of a paired run's fields, but holds {held}")


def _paired_from_json(common: MoveRunCommon, data: Mapping[str, Any]) -> PairedRun:
    what = "a paired run"
    return PairedRun(
        common,
        cited_floor=tuple(_list(_need(data, "cited_floor", what), "the cited floor")),
        flip=_need(data, "flip", what),
        verdicts=dict(_object(_need(data, "verdicts", what), "the verdicts")),
    )


def _common_from_json(data: Mapping[str, Any], move: MoveName) -> MoveRunCommon:
    what = "a move results file"
    return MoveRunCommon(
        run_id=_need(data, "run_id", what),
        move=move,
        identity=_identity_from_json(_object(_need(data, "identity", what), "the identity")),
        settings=settings_from_json(_object(_need(data, "settings", what), "the settings")),
        pinned={
            _arm(arm): Pinned(
                **{f.name: _need(values, f.name, "the pinned settings") for f in fields(Pinned)}
            )
            for arm, values in _object(_need(data, "pinned", what), "the pinned settings").items()
        },
        declared_at=_need(data, "declared_at", what),
        first_launch_at=_need(data, "first_launch_at", what),
        seed=_whole(_need(data, "seed", what), "the seed"),
        launch_orders={
            task: _order(order)
            for task, order in _object(_need(data, "launch_orders", what), "the orders").items()
        },
        sessions=tuple(
            _session_from_json(_object(s, "a session"))
            for s in _list(_need(data, "sessions", what), "the sessions")
        ),
        continues=_need(data, "continues", what),
        ending=ending_from_json(_object(_need(data, "ending", what), "the ending")),
        harness_version=_need(data, "harness_version", what),
        earlier=_earlier_from_json(_object(_need(data, "earlier_runs", what), "the earlier runs")),
    )


def _identity_from_json(identity: Mapping[str, Any]) -> MoveIdentity:
    what = "the identity"
    return MoveIdentity(
        _need(identity, "moved_rule_text", what),
        {
            _arm(arm): tuple(
                ChangeDigest(
                    _need(change, "path", "a declared change"),
                    _need(change, "sha256", "a declared change"),
                )
                for change in _list(changes, "an arm's changes")
            )
            for arm, changes in _object(_need(identity, "arms", what), "the arms").items()
        },
    )


def _earlier_from_json(earlier: Mapping[str, Any]) -> EarlierMoveRuns:
    what = "the earlier runs"
    return EarlierMoveRuns(
        floor=tuple(_list(_need(earlier, "floor", what), "the floor runs")),
        paired=tuple(_list(_need(earlier, "paired", what), "the paired runs")),
        apart=dict(_object(earlier.get("apart", {}), "the runs apart")),
    )


def _session_from_json(record: Mapping[str, Any]) -> MoveSession:
    what = "a session"
    return MoveSession(
        session_id=_need(record, "session_id", what),
        task_id=_need(record, "task_id", what),
        arm=_need(record, "arm", what),
        attempt=_whole(_need(record, "attempt", what), "the attempt"),
        status=_need(record, "status", what),
        reason=_need(record, "reason", what),
        started_at=_need(record, "started_at", what),
        cost_usd=float(_need(record, "cost_usd", what)),
        duration_ms=_whole(_need(record, "duration_ms", what), "the duration"),
        checks={
            name: _trigger_from_json(name, _object(t, "a check record"))
            for name, t in _object(_need(record, "checks", what), "the checks").items()
        },
    )


def _trigger_from_json(name: str, record: Mapping[str, Any]) -> CheckTrigger:
    what = f"the record of {name}"
    final = _need(record, "final", what)
    history = _need(record, "history", what)
    _require(history is None or history in _HISTORIES, f"{what} has an unknown history {history!r}")
    return CheckTrigger(
        check=name,
        arrivals={
            _channel(channel): _arrival_from_word(word)
            for channel, word in _object(_need(record, "arrivals", what), "the arrivals").items()
        },
        final=_final_from_json(final, record, what),
        history=history,
        refusals=tuple(_list(_need(record, "refusals", what), "the refusals")),
    )


def _final_from_json(
    word: str | None, record: Mapping[str, Any], what: str
) -> Passed | Failed | None:
    match word:
        case None:
            return None
        case "passed":
            return Passed()
        case "failed":
            return Failed(_need(record, "detail", what))
        case _:
            raise ValueError(f"{what} has an unknown final {word!r}")


def _arrival_from_word(word: str) -> Arrival:
    if word == _NEVER:
        return NeverArrived()
    if word == _UNKNOWN:
        return Unknown()
    _one_of(word, _TIMINGS, "an arrival's timing")
    return Arrived(word)  # type: ignore[arg-type]  # narrowed by the check above


def ending_from_json(data: Mapping[str, Any]) -> MoveEnding:
    what = "a run ending"
    kind = _need(data, "kind", what)
    match kind:
        case "finished":
            return Finished()
        case "stopped":
            return Stopped(_stop_reason_from_json(data))
        case "spend_refused":
            return SpendRefused(tuple(data.get("tasks", ())))
        case "interrupted":
            return Interrupted()
        case "closed":
            return _closed_from_json(data)
        case _:
            raise ValueError(f"unknown run ending {kind!r}")


def _closed_from_json(data: Mapping[str, Any]) -> Closed:
    what = "a closed ending"
    stopped = ending_from_json(_object(_need(data, "stopped", what), "the stopped ending"))
    _require(
        isinstance(stopped, Stopped | SpendRefused | Interrupted),
        f"a closed ending closes a stopped run, not {type(stopped).__name__}",
    )
    return Closed(
        reason=_need(data, "reason", what),
        at=_need(data, "at", what),
        interim=dict(_object(_need(data, "interim", what), "the interim result")),
        stopped=stopped,  # type: ignore[arg-type]  # narrowed by the check above
    )


def _stop_reason_from_json(data: Mapping[str, Any]) -> MoveStopReason:
    what = "a stop"
    scope = _need(data, "scope", what)
    _one_of(scope, _SCOPES, "a stop's scope")
    return MoveStopReason(
        kind=_need(data, "error_kind", what),
        masked_tail=_need(data, "masked_tail", what),
        arm=_arm(_need(data, "arm", what)),
        sessions=tuple(
            Launched(
                _need(s, "task_id", "a session of a stop"),
                _arm(_need(s, "arm", "a session of a stop")),
                _whole(_need(s, "attempt", "a session of a stop"), "the attempt"),
            )
            for s in _list(_need(data, "sessions", what), "the stop's sessions")
        ),
        scope=scope,
    )


# -- Small parsers ------------------------------------------------------------------------------


def _object(value: Any, what: str) -> Mapping[str, Any]:
    _require(isinstance(value, Mapping), f"{what} is a JSON object")
    return value


def _list(value: Any, what: str) -> list[Any]:
    _require(isinstance(value, list), f"{what} is a JSON list")
    return value


def _whole(value: Any, what: str) -> int:
    _require(isinstance(value, int) and not isinstance(value, bool), f"{what} is a whole number")
    return value


def _arm(value: Any) -> MoveArm:
    _one_of(value, MOVE_ARMS, "an arm")
    return value


def _channel(value: Any) -> Channel:
    _one_of(value, _CHANNELS, "a channel")
    return value


def _order(order: Any) -> tuple[MoveArm, MoveArm]:
    first, second = _list(order, "a launch order")
    return _arm(first), _arm(second)
