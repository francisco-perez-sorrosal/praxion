"""Outcome algebra for live scenario sessions.

Every session ends in exactly one of three outcomes. ``Passed`` and ``Failed``
are measurements of the context layer; ``Errored`` is the absence of one —
infrastructure failed, so nothing was graded. Errors therefore never enter a
pass rate: a rate-limited run must not read as a behavioral regression.

A capture that never elicited the graded observable becomes a ``Failed`` of
kind ``not_elicited`` without reaching a grader, so an empty value can never
vacuously pass (an empty staging command contains no forbidden token).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal, assert_never

ErrorKind = Literal[
    "exit_nonzero",
    "timeout",
    "no_result_event",
    "result_error",
    "envelope_unparseable",
    "structured_output_missing",
    "isolation_breach",
    "not_run_budget_exhausted",
    "evaluation_exception",  # an infra/judge exception raised after the session ran
]
FailKind = Literal["graded", "not_elicited"]


@dataclass(frozen=True)
class Passed:
    recorded: Any
    findings: tuple[str, ...]


@dataclass(frozen=True)
class Failed:
    """A measured failure: a graded value, or nothing elicited (with the reason)."""

    kind: FailKind
    recorded: Any | None
    findings: tuple[str, ...]
    reason: str | None = None

    def __post_init__(self) -> None:
        if self.kind == "not_elicited" and self.recorded is not None:
            raise ValueError("a not_elicited failure has nothing recorded")
        if self.kind == "graded" and self.reason is not None:
            raise ValueError("a graded failure carries findings, not a not-elicited reason")


@dataclass(frozen=True)
class Errored:
    """No ``recorded`` field by design: an errored session is never graded."""

    kind: ErrorKind
    detail: str


Outcome = Passed | Failed | Errored


@dataclass(frozen=True)
class Captured:
    value: Any
    diagnostics: Mapping[str, Any]


@dataclass(frozen=True)
class NotElicited:
    reason: str
    diagnostics: Mapping[str, Any]


Capture = Captured | NotElicited


def capture_to_outcome(capture: NotElicited) -> Failed:
    """The only path a not-elicited capture takes — it never meets a grader."""
    return Failed(kind="not_elicited", recorded=None, findings=(), reason=capture.reason)


def compute_pass_rate(*, passed: int, failed: int) -> float | None:
    """``pass / (pass + fail)``; ``None`` when nothing was graded (errors excluded)."""
    graded = passed + failed
    if graded == 0:
        return None
    return passed / graded


def compute_lowered(*, head_rate: float | None, canary_rate: float | None) -> bool | None:
    """Whether the degraded copy scored strictly lower; ``None`` if either side is unmeasured."""
    if head_rate is None or canary_rate is None:
        return None
    return canary_rate < head_rate


def to_session_record(outcome: Outcome, *, repeat: int) -> dict[str, Any]:
    """Serialize one session's outcome into its baseline-JSON record.

    An error record carries no ``recorded`` key at all — no capture was attempted.
    """
    record: dict[str, Any] = {"repeat": repeat}
    match outcome:
        case Passed(recorded=recorded, findings=findings):
            record |= {"outcome": "pass", "recorded": recorded, "findings": list(findings)}
        case Failed(kind=kind, recorded=recorded, findings=findings, reason=reason):
            record |= {
                "outcome": "fail",
                "fail_kind": kind,
                "recorded": recorded,
                "findings": list(findings),
            }
            if reason is not None:
                record["reason"] = reason
        case Errored(kind=kind, detail=detail):
            record |= {"outcome": "error", "error_kind": kind, "detail": detail}
        case _:
            assert_never(outcome)
    return record
