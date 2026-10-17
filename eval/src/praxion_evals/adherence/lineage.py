"""How a run ended, and so whether it can be continued.

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

Pure: nothing here touches a process, a file or a clock.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, assert_never, get_args

from praxion_evals.adherence.infra_stop import Launched, Scope, StopReason
from praxion_evals.adherence.model import ARMS, ROLES
from praxion_evals.adherence.results import RunResults

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
