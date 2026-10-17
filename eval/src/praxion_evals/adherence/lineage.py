"""How a run ended, and so whether it can be continued; what it was measured on.

A results file used to say only ``complete: bool`` plus a list of refused launches. That cannot
tell a run that stopped itself on a dead credential (worth continuing) from one the operator
interrupted or one that merely finished with errors (not worth continuing), so the end of a run
is now a value of its own, ``RunEnding``, written to the file by the runner:

- ``Finished``: the loop reached the end of its plan. Sessions may have errored; ``complete``
  says whether any did.
- ``InfraStopped``: the run stopped itself on a repeated identical infrastructure failure.
- ``SpendRefused``: the spend cap refused a launch.
- ``Interrupted``: the operator interrupted it; the file holds every session that had ended.
- ``Closed``: the operator gave up on a stopped run and said why.
- ``Legacy``: a file written before endings existed. It has no wire form and is never
  continuable: nothing recorded says why that run ended.

Whether an ending can be continued is derived by ``continuable``, never stored, so it cannot
disagree with the ending it summarises.

What a run was measured on lives in ``run_identity``; the names other modules use are re-exported
here. A continued run is a lineage of parts, each part's results file naming the one it continues
(``Lineage``); a continuation launches again only the tasks nobody finished (``relaunch_tasks``)
and is refused, naming every reason, unless the stopped run was continuable and still measures
the same thing (``continuation_refusals``). A stopped run left neither continued nor closed
blocks a fresh run of its role (``pending_stop``); ``close`` is how the operator resolves it.

The ending, refusal and relaunch halves are pure: nothing in them touches a process, a file or a
clock, and none reads a graded outcome to decide whether a run continues. ``Lineage.parse`` and
``pending_stop`` read a results directory.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, assert_never, get_args

from praxion_evals.adherence.infra_stop import (
    Failure,
    FoldState,
    Launched,
    Scope,
    StopReason,
    StopRule,
    step,
)
from praxion_evals.adherence.model import (
    ARMS,
    CLEARING_VERDICTS,
    ROLES,
    Assessed,
    Errored,
    Measured,
    SessionRecord,
    SessionStatus,
)
from praxion_evals.adherence.results import RunResults, flip_label, instant, load, role_verdicts
from praxion_evals.adherence.run_identity import (  # noqa: F401  (re-exported for session_loop)
    MeasuredIdentity,
    current_identity,
    diff,
    measured_identity,
)

# ---------------------------------------------------------------------------
# The ending
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Finished:
    pass


@dataclass(frozen=True)
class InfraStopped:
    reason: StopReason


@dataclass(frozen=True)
class SpendRefused:
    """``tasks`` are the ids of the tasks whose session the cap refused (none when only an
    arm's proof launch was refused)."""

    tasks: tuple[str, ...] = ()


@dataclass(frozen=True)
class Interrupted:
    pass


@dataclass(frozen=True)
class Legacy:
    pass


# What can be closed: a run that stopped before its plan ran out. Closing a run that finished,
# was closed already or predates endings means nothing.
StoppedEnding = InfraStopped | SpendRefused | Interrupted


@dataclass(frozen=True)
class Closed:
    """A stopped run the operator gave up on, with the reason, the time and the per-check
    result it had reached (check name to flip-label-style outcome) when it was closed."""

    reason: str
    at: str
    interim: Mapping[str, str]
    stopped: StoppedEnding

    def __post_init__(self) -> None:
        if not self.reason.strip():
            raise ValueError("closing a run needs a reason")


RunEnding = Finished | InfraStopped | SpendRefused | Interrupted | Closed | Legacy


def continuable(ending: RunEnding) -> bool:
    """An infrastructure stop seen in both arms (a one-arm stop is a failure to count against the
    lean arm, not an outage) or a spend refusal can be picked up again; nothing else can."""
    match ending:
        case InfraStopped(reason=reason):
            return reason.scope == "both-arms"
        case SpendRefused():
            return True
        case Finished() | Interrupted() | Closed() | Legacy():
            return False
        case _:
            assert_never(ending)


def ending_of(results: RunResults) -> RunEnding:
    """The ending a results file recorded; ``Legacy`` for one written before endings."""
    return ending_from_json(results.run.extra.get("ending"))


# ---------------------------------------------------------------------------
# The wire form: ``run.ending`` in the results file
# ---------------------------------------------------------------------------

_Json = Mapping[str, Any]
_SCOPES: tuple[str, ...] = get_args(Scope)


def ending_to_json(ending: RunEnding) -> dict[str, Any]:
    match ending:
        case Finished():
            return {"kind": "finished"}
        case InfraStopped(reason=reason):
            return _stop_to_json(reason)
        case SpendRefused(tasks=tasks):
            return {"kind": "spend_refused", "tasks": list(tasks)}
        case Interrupted():
            return {"kind": "interrupted"}
        case Closed(reason=reason, at=at, interim=interim, stopped=stopped):
            return {
                "kind": "closed",
                "reason": reason,
                "at": at,
                "interim": dict(interim),
                "stopped": ending_to_json(stopped),
            }
        case Legacy():
            raise ValueError("a legacy ending is the absence of one and is never written")
        case _:
            assert_never(ending)


def ending_from_json(data: _Json | None) -> RunEnding:
    """``None`` (no ending recorded) is ``Legacy``; anything else must be a well-formed ending."""
    if data is None:
        return Legacy()
    kind = _field(data, "kind", "a run ending")
    match kind:
        case "finished":
            return Finished()
        case "infra_stopped":
            return InfraStopped(_stop_from_json(data))
        case "spend_refused":
            return SpendRefused(tuple(data.get("tasks", ())))
        case "interrupted":
            return Interrupted()
        case "closed":
            return _closed_from_json(data)
        case _:
            raise ValueError(f"unknown run ending {kind!r}")


def _closed_from_json(data: _Json) -> Closed:
    stopped = ending_from_json(_field(data, "stopped", "a closed ending"))
    if not isinstance(stopped, InfraStopped | SpendRefused | Interrupted):
        raise ValueError(f"a closed ending closes a stopped run, not {type(stopped).__name__}")
    return Closed(
        reason=_field(data, "reason", "a closed ending"),
        at=_field(data, "at", "a closed ending"),
        interim=dict(_field(data, "interim", "a closed ending")),
        stopped=stopped,
    )


def _stop_to_json(reason: StopReason) -> dict[str, Any]:
    return {
        "kind": "infra_stopped",
        "error_kind": reason.kind,
        "masked_tail": reason.masked_tail,
        "role": reason.role,
        "arm": reason.arm,
        "sessions": [
            {"task_id": s.task_id, "arm": s.arm, "attempt": s.attempt} for s in reason.sessions
        ],
        "scope": reason.scope,
    }


def _stop_from_json(data: _Json) -> StopReason:
    what = "an infrastructure stop"
    return StopReason(
        kind=_field(data, "error_kind", what),
        masked_tail=_field(data, "masked_tail", what),
        role=_choice(_field(data, "role", what), ROLES, "role"),
        arm=_choice(_field(data, "arm", what), ARMS, "arm"),
        sessions=tuple(_launched_from_json(s) for s in _field(data, "sessions", what)),
        scope=_choice(_field(data, "scope", what), _SCOPES, "scope"),
    )


def _launched_from_json(data: _Json) -> Launched:
    what = "a session of a stop"
    return Launched(
        task_id=_field(data, "task_id", what),
        arm=_choice(_field(data, "arm", what), ARMS, "arm"),
        attempt=int(_field(data, "attempt", what)),
    )


def _field(data: _Json, key: str, what: str) -> Any:
    if key not in data:
        raise ValueError(f"{what} lacks {key!r}")
    return data[key]


def _choice(value: Any, choices: tuple[str, ...], name: str) -> Any:
    if value not in choices:
        raise ValueError(f"unknown {name} {value!r}; the choices are {list(choices)}")
    return value


# ---------------------------------------------------------------------------
# A run's lineage: the parts of one declared run
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PartRef:
    """One results file of a lineage: the run it holds and the run it continues."""

    run_id: str
    path: Path
    continues: str | None


@dataclass(frozen=True)
class Lineage:
    """The parts of one declared run, oldest first: the first continues nothing, every later
    part names its predecessor. Only the tip may be continued or closed.

    The chain is checked here, at construction; ``parse`` is how a results directory becomes one.
    """

    parts: tuple[PartRef, ...]

    def __post_init__(self) -> None:
        if not self.parts:
            raise ValueError("a lineage has at least one part")
        predecessor = None
        for part in self.parts:
            if part.continues != predecessor:
                raise ValueError(
                    f"run {part.run_id} continues {part.continues!r}, not its predecessor"
                    f" {predecessor!r}"
                )
            predecessor = part.run_id

    @property
    def tip(self) -> PartRef:
        return self.parts[-1]

    @classmethod
    def parse(cls, results_dir: Path, run_id: str) -> Lineage:
        """The whole lineage ``run_id`` belongs to, whichever of its parts that is.

        Refused: a run no readable results file holds, a part continuing a run that is missing
        (a gap) or itself, and a run that two parts continue (a fork, even on a branch the
        named run is not on).
        """
        parts = {held: ref for held, (ref, _) in _runs_in(results_dir).items()}
        if run_id not in parts:
            raise ValueError(f"no results file in {results_dir} holds run {run_id}")
        chain = [_root_of(parts, run_id, results_dir)]
        while later := [p for p in parts.values() if p.continues == chain[-1].run_id]:
            if len(later) > 1:
                names = ", ".join(sorted(p.run_id for p in later))
                raise ValueError(f"the lineage forks: {names} all continue {chain[-1].run_id}")
            chain.append(later[0])
        return cls(tuple(chain))


def _runs_in(results_dir: Path) -> dict[str, tuple[PartRef, RunResults]]:
    """Every readable results file of ``results_dir`` by the run it holds, oldest file first."""
    runs: dict[str, tuple[PartRef, RunResults]] = {}
    for path in sorted(results_dir.glob("*.json")):
        try:
            results = load(path)
        except (OSError, ValueError, KeyError, TypeError):
            continue  # not a results file: the run's listing names it, and no lineage runs through it
        run = results.run
        if run.id in runs:
            raise ValueError(f"{runs[run.id][0].path.name} and {path.name} both hold run {run.id}")
        runs[run.id] = (PartRef(run.id, path, run.extra.get("continues")), results)
    return runs


def _root_of(parts: Mapping[str, PartRef], run_id: str, results_dir: Path) -> PartRef:
    part, walked = parts[run_id], {run_id}
    while part.continues is not None:
        earlier = parts.get(part.continues)
        if earlier is None:
            raise ValueError(
                f"the lineage has a gap: run {part.run_id} continues {part.continues}, which no"
                f" readable results file in {results_dir} holds"
            )
        if earlier.run_id in walked:
            raise ValueError(f"the lineage loops: run {earlier.run_id} continues itself")
        walked.add(earlier.run_id)
        part = earlier
    return part


# ---------------------------------------------------------------------------
# What a continuation launches again
# ---------------------------------------------------------------------------

LAUNCH_REFUSED = "launch_refused"  # the error kind of a session the spend cap refused


def relaunch_tasks(
    results: RunResults, role: str, earlier: Sequence[RunResults] = ()
) -> tuple[str, ...]:
    """The role's planned tasks a continuation launches again, whole in every arm, in planned
    order: those with no complete pair and no session that ended otherwise.

    ``results`` is the part being continued and ``earlier`` the parts before it, oldest first: each
    part holds only the sessions it launched, so a task an earlier part finished stays finished. A
    session ``never_launched`` in its own part does not count either way. Every other session keeps
    its outcome, so a task whose lean side alone errored is not launched again and stays a lean
    failure in the worst-case recount.
    """
    latest: dict[str, dict[str, SessionStatus]] = {}
    for part in (*earlier, results):
        ignored = never_launched(part)
        for position, record in enumerate(part.sessions):
            if record.setup.role == role and position not in ignored:
                latest.setdefault(record.setup.task_id, {})[record.setup.arm] = record.status
    planned = _field(_field(results.run.extra, "tasks", "a run"), role, "a run's planned tasks")
    return tuple(task for task in planned if _unfinished(latest.get(task, {})))


def _unfinished(latest: Mapping[str, SessionStatus]) -> bool:
    """``latest`` is a task's last status per arm: unfinished when every one was measured and
    they do not make a pair."""
    measured = all(isinstance(status, Measured) for status in latest.values())
    return measured and set(latest) != set(ARMS)


def never_launched(results: RunResults) -> frozenset[int]:
    """Positions in ``results.sessions`` a continuation treats as never launched: the sessions
    the spend cap refused, the stopping streak, and the other arm's errors of the streak's kind
    and masked tail inside the streak's window. A session of that kind and tail before the
    streak is not among them: the failure stands."""
    refused = {
        position
        for position, record in enumerate(results.sessions)
        if isinstance(record.status, Errored) and record.status.kind == LAUNCH_REFUSED
    }
    return frozenset(refused | _inside_the_stop(results))


def _inside_the_stop(results: RunResults) -> set[int]:
    ending = ending_of(results)
    if not isinstance(ending, InfraStopped):
        return set()
    stop, sessions, rule = ending.reason, results.sessions, results.settings.stop_rule
    if rule is None:
        raise ValueError(f"run {results.run.id} stopped but declares no stop rule")
    of_arm = [
        i for i, r in enumerate(sessions) if (r.setup.role, r.setup.arm) == (stop.role, stop.arm)
    ]
    streak = of_arm[len(of_arm) - len(stop.sessions) :]
    named = [(sessions[i].setup.task_id, sessions[i].setup.arm) for i in streak]
    if not streak or named != [(s.task_id, s.arm) for s in stop.sessions]:
        raise ValueError(
            f"the stop names sessions that the {stop.role} {stop.arm} arm did not end on"
        )
    last = sessions[streak[-1]]
    alike = {
        i
        for i in range(streak[0], streak[-1] + 1)
        if sessions[i].setup.role == stop.role
        and sessions[i].setup.arm != stop.arm
        and _fails_alike(rule, sessions[i], last)
    }
    return {*streak, *alike}


def _fails_alike(rule: StopRule, record: SessionRecord, streak_session: SessionRecord) -> bool:
    """Whether ``record`` failed as ``streak_session`` did, by the stop's own reading: the same
    kind and masked evidence, and only a session that counted as a failure at all. A session its
    own spend budget stopped ran, so it is never a failure of the stop."""
    failure = _failure_of(rule, record)
    return failure is not None and failure == _failure_of(rule, streak_session)


def _failure_of(rule: StopRule, record: SessionRecord) -> Failure | None:
    folded, _ = step(rule, FoldState(), record)
    return folded.seen[0].failure


# ---------------------------------------------------------------------------
# Whether a stopped run may be continued, and closing one
# ---------------------------------------------------------------------------

# The options a continuation may be given beside the run it continues: they bound what it spends
# or where it writes, never what it measures.
CONTINUATION_OPTIONS = frozenset(
    {
        "--max-total-usd",
        "--session-budget-usd",
        "--keep-sandbox",
        "--session-oauth-token-file",
        "--output",
    }
)


@dataclass(frozen=True)
class ReadTip:
    """The latest part of a lineage, read: its results, the identity it was measured on, and the
    run that continues it (``None`` when none does, which is what a tip is)."""

    results: RunResults
    identity: MeasuredIdentity
    continued_by: str | None = None


@dataclass(frozen=True)
class UnreadableTip:
    """A results file named for continuation that is missing or does not read as one."""

    path: Path
    reason: str


Tip = ReadTip | UnreadableTip


def continuation_refusals(
    tip: Tip,
    identity_now: MeasuredIdentity,
    supplied_options: Collection[str],
    changed_paths: Collection[str] = (),
) -> tuple[str, ...]:
    """Every reason ``tip`` cannot be continued now, one line each; empty when it can.

    Refused: a results file that cannot be read; a run that did not stop continuably (it
    finished, stopped in one arm alone, was interrupted or crashed, was closed, or predates
    endings); a run something already continues; an option beyond ``CONTINUATION_OPTIONS``; and
    any way ``identity_now`` differs from what the run was measured on, each path of the tree in
    ``changed_paths`` named beside the tree's own difference. Only the ending and the identity
    decide: how well the run did is never read.
    """
    match tip:
        case UnreadableTip(path=path, reason=reason):
            return (f"{path.name} cannot be read as a results file: {reason}",)
        case ReadTip():
            return (
                *_ending_refusals(tip),
                *_continued_refusals(tip),
                *_option_refusals(supplied_options),
                *(f"changed since the stop: {line}" for line in diff(tip.identity, identity_now)),
                *(
                    f"changed since the stop: tree: {path} differs from the run's commit"
                    for path in changed_paths
                ),
            )
        case _:
            assert_never(tip)


def _ending_refusals(tip: ReadTip) -> tuple[str, ...]:
    ending, run = ending_of(tip.results), tip.results.run.id
    if continuable(ending):
        return ()
    match ending:
        case Finished():
            return (f"run {run} finished its plan; a complete run has nothing left to continue",)
        case InfraStopped(reason=reason):
            return (
                f"run {run} stopped in the {reason.arm} arm alone; a stop confined to one arm is a"
                " failure to count against the lean arm, not an outage to continue",
            )
        case Interrupted():
            return (
                f"run {run} was interrupted, not stopped; only an infrastructure stop in both arms"
                " or a spend refusal is continued",
            )
        case Closed(reason=reason, at=at):
            return (f"run {run} was closed on {at}: {reason}",)
        case Legacy():
            return (f"run {run} was recorded before runs recorded how they ended",)
        case SpendRefused():
            raise AssertionError("a spend refusal is continuable")
        case _:
            assert_never(ending)


def _continued_refusals(tip: ReadTip) -> tuple[str, ...]:
    if tip.continued_by is None:
        return ()
    return (
        f"run {tip.results.run.id} already has a continuation, {tip.continued_by}; only the"
        " latest part of a lineage is continued",
    )


def _option_refusals(supplied: Collection[str]) -> tuple[str, ...]:
    allowed = ", ".join(sorted(CONTINUATION_OPTIONS))
    return tuple(
        f"{option} would change what the run measures; a continuation takes only {allowed}"
        for option in sorted(set(supplied) - CONTINUATION_OPTIONS)
    )


def pending_stop(results_dir: Path, role: str) -> PartRef | None:
    """The oldest stopped run of ``role`` that was continuable when it stopped and has been
    neither continued nor closed, or ``None``.

    Keyed on the role alone, not on what the tree holds now: a commit elsewhere makes a stopped
    run no longer continuable, and would otherwise release the operator from choosing between
    continuing and closing. Closing is always possible, so this cannot deadlock a role.
    """
    runs = _runs_in(results_dir).values()
    continued = {ref.continues for ref, _ in runs}
    for ref, results in runs:
        stopped = continuable(ending_of(results)) and ref.run_id not in continued
        if stopped and role in results.catalog:
            return ref
    return None


def close(tip: ReadTip, reason: str, now: datetime) -> Closed:
    """The ending that closes a stopped run, carrying the per-check result it had reached.

    Refused: an empty reason; a run that is not at the end of its lineage; a run that did not
    stop (a finished, closed or pre-ending run has nothing to give up on).
    """
    ending, run = ending_of(tip.results), tip.results.run.id
    if tip.continued_by is not None:
        raise ValueError(
            f"run {run} is continued by {tip.continued_by}; only the latest part is closed"
        )
    if not isinstance(ending, InfraStopped | SpendRefused | Interrupted):
        raise ValueError(
            f"run {run} did not stop ({type(ending).__name__}), so there is nothing to close"
        )
    return Closed(
        reason,
        instant(now.isoformat(), "the closing time").isoformat(),
        _interim(tip.results),
        ending,
    )


def _interim(results: RunResults) -> dict[str, str]:
    """Each role's per-check outcome as the flip would label it, keyed ``role.check``; a role
    short of pairs has no checks to label and stands as itself."""
    interim: dict[str, str] = {}
    for role, role_verdict in role_verdicts(results).items():
        if not isinstance(role_verdict, Assessed):
            interim[role] = flip_label(role_verdict)
            continue
        for check, verdict in role_verdict.check_verdicts.items():
            clears = (
                isinstance(verdict, CLEARING_VERDICTS) and check not in role_verdict.not_covered
            )
            interim[f"{role}.{check}"] = "clear" if clears else "not clear"
    return interim
