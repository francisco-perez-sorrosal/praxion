"""How a move run ended, whether it can be continued, and which floor run a paired run may cite.

A move run is a role run's twin in the machinery that surrounds a session: the same lineage of
parts (``lineage.chain_of``), the same stop, continuation and close. What differs is what a
continuation must reproduce and what a fresh run is blocked by:

- ``MoveEnding``: ``Finished``, ``Stopped`` (the move's own infrastructure stop), a spend
  refusal, an interruption, or ``Closed`` with the operator's reason. Whether one can be
  continued is derived by ``continuable``, never stored.
- ``continuation_refusals`` names every reason a stopped run cannot be continued now. A move's
  identity is the moved rule's text and every arm's declared changes with their content; the
  run's ending and that identity decide, never how well the run did.
- ``pending_stop`` is keyed on the move alone, floor and paired runs alike (dec-462 clause 6): a
  continuable stopped run blocks every fresh run of its move until it is continued or closed.
- ``cite`` resolves the floor run a paired run cites. Any part of a finished floor lineage
  resolves to the whole lineage; a stopped or closed lineage, a floor run of another identity,
  or a floor run that never failed a governed check the paired run declares is refused naming
  why. ``FloorIdentity`` leaves the lean declaration out: the lean arm never loads into a floor
  run, so a change confined to it leaves a floor run citable. Only a lineage that finished its
  plan is citable: a floor closed after its counts were seen would bias the sensitivity line by
  optional stopping.

Pure: nothing here touches a process, a file or a clock; the caller reads results files.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, fields
from datetime import datetime
from typing import Any, assert_never

from praxion_evals.adherence.lineage import (
    Finished,
    Interrupted,
    PartRef,
    SpendRefused,
    UnreadableTip,
    _option_refusals,  # the role's own wording of "this option would change what the run measures"
    chain_of,
)
from praxion_evals.adherence.model import _require
from praxion_evals.adherence.moves.model import MOVE_ARMS, MoveArm
from praxion_evals.adherence.moves.stop import MoveStopReason
from praxion_evals.adherence.results import instant

DIGEST_SHOWN = 12  # characters of a digest a difference names

# ---------------------------------------------------------------------------
# The ending
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stopped:
    reason: MoveStopReason


# What can be closed: a run that stopped before its plan ran out.
StoppedEnding = Stopped | SpendRefused | Interrupted


@dataclass(frozen=True)
class Closed:
    """A stopped run the operator gave up on, with the reason, the time and the per-check
    result it had reached when it was closed."""

    reason: str
    at: str
    interim: Mapping[str, str]
    stopped: StoppedEnding

    def __post_init__(self) -> None:
        _require(bool(self.reason.strip()), "closing a run needs a reason")


MoveEnding = Finished | Stopped | SpendRefused | Interrupted | Closed


def continuable(ending: MoveEnding) -> bool:
    """A floor stop, a paired stop seen in both arms, or a spend refusal can be picked up again."""
    match ending:
        case Stopped(reason=reason):
            return reason.continuable
        case SpendRefused():
            return True
        case Finished() | Interrupted() | Closed():
            return False
        case _:
            assert_never(ending)


# ---------------------------------------------------------------------------
# What a continuation must reproduce
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ChangeDigest:
    """One declared change of an arm, by the path it touches and the content it leaves there."""

    path: str
    sha256: str


@dataclass(frozen=True)
class MoveIdentity:
    """The moved rule's text and every arm's declared changes with their content."""

    moved_rule_text: str
    arms: Mapping[MoveArm, tuple[ChangeDigest, ...]]

    def differences(self, other: MoveIdentity) -> tuple[str, ...]:
        """Every way ``other`` differs from this identity, one line each; empty when none."""
        found = [] if self.moved_rule_text == other.moved_rule_text else [_RULE_TEXT_CHANGED]
        for arm in MOVE_ARMS:
            then = {c.path: c.sha256 for c in self.arms.get(arm, ())}
            now = {c.path: c.sha256 for c in other.arms.get(arm, ())}
            found += [
                _change_line(arm, path, then.get(path), now.get(path))
                for path in sorted(then | now)
                if then.get(path) != now.get(path)
            ]
        return tuple(found)


_RULE_TEXT_CHANGED = "the moved rule's text differs"


def _change_line(arm: MoveArm, path: str, then: str | None, now: str | None) -> str:
    if then is None:
        return f"the {arm} arm now changes {path}, which it did not"
    if now is None:
        return f"the {arm} arm no longer changes {path}"
    return f"the {arm} arm's change to {path} has other content ({then[:DIGEST_SHOWN]} -> {now[:DIGEST_SHOWN]})"


@dataclass(frozen=True)
class ReadTip:
    """The latest part of a lineage, read: its ending, the identity it was measured on, and the
    run that continues it (``None`` when none does, which is what a tip is)."""

    run_id: str
    ending: MoveEnding
    identity: MoveIdentity
    continued_by: str | None = None


Tip = ReadTip | UnreadableTip


def continuation_refusals(
    tip: Tip,
    identity_now: MoveIdentity,
    supplied_options: Collection[str],
    changed_elsewhere: Collection[str] = (),
) -> tuple[str, ...]:
    """Every reason ``tip`` cannot be continued now, one line each; empty when it can.

    Refused: a results file that cannot be read; a run that did not stop continuably; a run
    something already continues; an option that would change what the run measures; any way the
    moved rule's text or an arm's declared changes differ from what the run was measured on; and
    each line of ``changed_elsewhere`` (the model, seed, tasks or tree, which the caller reads).
    """
    match tip:
        case UnreadableTip(path=path, reason=reason):
            return (f"{path.name} cannot be read as a results file: {reason}",)
        case ReadTip():
            return (
                *_ending_refusals(tip),
                *_continued_refusals(tip),
                *_option_refusals(supplied_options),
                *(
                    f"changed since the stop: {line}"
                    for line in tip.identity.differences(identity_now)
                ),
                *(f"changed since the stop: {line}" for line in changed_elsewhere),
            )
        case _:
            assert_never(tip)


def _ending_refusals(tip: ReadTip) -> tuple[str, ...]:
    ending, run = tip.ending, tip.run_id
    match ending:
        case SpendRefused():
            return ()
        case Stopped(reason=reason) if reason.continuable:
            return ()
        case Stopped(reason=reason):
            return (
                f"run {run} stopped in the {reason.arm} arm alone; a stop confined to one arm is a"
                " failure to count against the lean arm, not an outage to continue",
            )
        case Finished():
            return (f"run {run} finished its plan; a complete run has nothing left to continue",)
        case Interrupted():
            return (
                f"run {run} was interrupted, not stopped; only an infrastructure stop that is an"
                " outage or a spend refusal is continued",
            )
        case Closed(reason=reason, at=at):
            return (f"run {run} was closed on {at}: {reason}",)
        case _:
            assert_never(ending)


def _continued_refusals(tip: ReadTip) -> tuple[str, ...]:
    if tip.continued_by is None:
        return ()
    return (
        f"run {tip.run_id} already has a continuation, {tip.continued_by}; only the latest part"
        " of a lineage is continued",
    )


# ---------------------------------------------------------------------------
# What a stopped run blocks, and closing one
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StoredRun:
    """One move run's results file as the listing needs it."""

    ref: PartRef
    move: str
    ending: MoveEnding


def pending_stop(runs: Sequence[StoredRun], move: str) -> PartRef | None:
    """The oldest stopped run of ``move`` that was continuable when it stopped and has been
    neither continued nor closed, or ``None``.

    Keyed on the move alone, floor and paired runs alike, and not on what the tree holds now.
    Closing is always possible, so this cannot deadlock a move.
    """
    continued = {stored.ref.continues for stored in runs}
    for stored in runs:
        if (
            stored.move == move
            and continuable(stored.ending)
            and stored.ref.run_id not in continued
        ):
            return stored.ref
    return None


def close(tip: ReadTip, reason: str, now: datetime, interim: Mapping[str, str]) -> Closed:
    """The ending that closes a stopped run, carrying the per-check result it had reached.

    Refused: an empty reason; a run that is not at the end of its lineage; a run that did not
    stop (a finished or closed run has nothing to give up on).
    """
    if tip.continued_by is not None:
        raise ValueError(
            f"run {tip.run_id} is continued by {tip.continued_by}; only the latest part is closed"
        )
    if not isinstance(tip.ending, Stopped | SpendRefused | Interrupted):
        raise ValueError(
            f"run {tip.run_id} did not stop ({type(tip.ending).__name__}), so there is nothing to close"
        )
    at = instant(now.isoformat(), "the closing time").isoformat()
    return Closed(reason, at, dict(interim), tip.ending)


# ---------------------------------------------------------------------------
# The floor run a paired run cites
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FloorIdentity:
    """What a floor run was measured on: the floor arm's built tree, its tasks and wordings, the
    governed checks and their sections, the model, the effort and the declared settings. The
    lean declaration is outside it. Pairs are (name, value), so a difference names the part."""

    tree: str
    tasks: tuple[tuple[str, str], ...]
    checks: tuple[tuple[str, str], ...]
    model: str
    effort: str
    settings: tuple[tuple[str, str], ...]

    def differences(self, other: FloorIdentity) -> tuple[str, ...]:
        found: list[str] = []
        for field in fields(self):
            a, b = getattr(self, field.name), getattr(other, field.name)
            if a != b:
                found.append(f"the floor's {field.name} differs: {_shown(field.name, a, b)}")
        return tuple(found)


def _shown(name: str, then: Any, now: Any) -> str:
    if name in ("model", "effort"):
        return f"{then} -> {now}"
    if name == "tree":
        return f"{then[:DIGEST_SHOWN]} -> {now[:DIGEST_SHOWN]}"
    return ", ".join(sorted({key for key, _ in set(then) ^ set(now)}))


@dataclass(frozen=True)
class CheckCounts:
    """A governed check's final-state failures out of the floor sessions scored on it."""

    failed: int
    scored: int

    def __post_init__(self) -> None:
        _require(0 <= self.failed <= self.scored, "failures are among the scored sessions")


@dataclass(frozen=True)
class FloorPart:
    """One floor results file, read."""

    ref: PartRef
    identity: FloorIdentity
    ending: MoveEnding
    counts: Mapping[str, CheckCounts]


@dataclass(frozen=True)
class CitedFloor:
    """The whole floor lineage a citation resolved to, its counts per check summed over its
    parts, and every other floor run of the same identity, listed beside it."""

    lineage: tuple[str, ...]
    counts: Mapping[str, CheckCounts]
    others: tuple[str, ...]


@dataclass(frozen=True)
class NoCitation: ...


@dataclass(frozen=True)
class Unreadable:
    run_id: str
    reason: str


@dataclass(frozen=True)
class OtherIdentity:
    differences: tuple[str, ...]


@dataclass(frozen=True)
class NotFinished:
    run_id: str
    ending: MoveEnding


@dataclass(frozen=True)
class Blind:
    """Governed checks the cited floor never failed: it cannot show the move's room to move."""

    checks: tuple[str, ...]


CitationRefusal = NoCitation | Unreadable | OtherIdentity | NotFinished | Blind


def cite(
    floor_runs: Mapping[str, FloorPart],
    cited: str | None,
    identity: FloorIdentity,
    declared_checks: Collection[str],
) -> CitedFloor | CitationRefusal:
    """Resolve the floor run ``cited`` names, among ``floor_runs`` (every floor run of the move,
    oldest first), for a paired run on ``identity`` that declares ``declared_checks``."""
    if cited is None:
        return NoCitation()
    if cited not in floor_runs:
        return Unreadable(cited, f"no readable floor run holds run {cited}")
    try:
        chain = chain_of({run: part.ref for run, part in floor_runs.items()}, cited)
    except ValueError as error:
        return Unreadable(cited, str(error))
    members = tuple(floor_runs[ref.run_id] for ref in chain)
    tip = members[-1]
    if differences := tip.identity.differences(identity):
        return OtherIdentity(differences)
    if not isinstance(tip.ending, Finished):
        return NotFinished(tip.ref.run_id, tip.ending)
    counts = _summed(members)
    if blind := tuple(check for check in declared_checks if counts.get(check, _NONE).failed == 0):
        return Blind(blind)
    lineage = tuple(part.ref.run_id for part in members)
    others = tuple(
        run for run, part in floor_runs.items() if run not in lineage and part.identity == identity
    )
    return CitedFloor(lineage, counts, others)


_NONE = CheckCounts(0, 0)


def _summed(parts: Sequence[FloorPart]) -> dict[str, CheckCounts]:
    summed: dict[str, CheckCounts] = {}
    for part in parts:
        for check, counts in part.counts.items():
            so_far = summed.get(check, _NONE)
            summed[check] = CheckCounts(
                so_far.failed + counts.failed, so_far.scored + counts.scored
            )
    return summed


def refusal_text(refusal: CitationRefusal) -> str:
    """The line that tells the operator why a citation was refused."""
    match refusal:
        case NoCitation():
            return "a paired run cites a finished floor run; none was cited"
        case Unreadable(run_id=run, reason=reason):
            return f"the cited floor run {run} cannot be used: {reason}"
        case OtherIdentity(differences=differences):
            return "the cited floor run was measured on another identity: " + "; ".join(differences)
        case NotFinished(run_id=run, ending=ending):
            return (
                f"the floor lineage ending in run {run} did not finish its plan"
                f" ({type(ending).__name__.lower()}); only a finished floor lineage is cited"
            )
        case Blind(checks=checks):
            return (
                "the cited floor run never failed "
                + ", ".join(checks)
                + " on final state, so it shows no room for the move to show on that check"
            )
        case _:
            assert_never(refusal)
