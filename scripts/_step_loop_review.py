"""The light-review state of one verified step, derived from counts and the review file's text.

Pure and independent of the loop state: the caller counts the review and revise returns of the
step's current series and passes the text of `LIGHT_REVIEW_step-<id>.md` (None when absent).

Normative reading of the review file: its last line starting `verdict:` decides, because the
reviewer writes `verdict: [PARTIAL]` first and the verdict last. `accept` and `revise` are
verdicts; `[PARTIAL]` or any other word is unfinished; no such line is no verdict. Only the
current round counts: a later round keeps the earlier round's record below a heading of level
one to six whose text holds the word `superseded` (any case; `SUPERSEDED_HEADING` is the form the
round-2 prompt names), and the file is read down to the first such heading. A separator line
before it is above the boundary and holds no verdict. A file with no such heading is read whole.

Normative reading of the state, first match wins:

1. The trigger is off: `NotRequired`. The trigger is `review: force` or `tier: H`, and
   `review: off` beats both.
2. The file reads `accept` and at least one review has returned in the series: `Accepted`. A
   file left over from an earlier series cannot accept a new one, and a person may set the
   verdict by hand after a stop.
3. The latest revision did not pass its gate: `RevisionFailed`.
4. A review has returned that no revision has answered: `revise` is `ReviseDue` after the
   first review and `RevisedTwice` after the second; any other file is `Unfinished`.
5. Otherwise the next review is due: `Requested` when the reviewer's file already reads
   `[PARTIAL]` (the request went out, so it is reissued), else `Due`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Union

from _plan_steps import PlanStep

if TYPE_CHECKING:
    from iteration_ledger import IterationRecord

REVIEW_FORCED = "force"
REVIEW_OFF = "off"
ACCEPT = "accept"
REVISE = "revise"
UNFINISHED = "partial"
# The most review-side requests one series issues before a human stop: the first review, the
# revision it asks for and the second review (a second `revise` is `RevisedTwice`, a stop).
REVIEW_CYCLE = 3

SUPERSEDED_HEADING = "## Superseded round-<n> record"

_VERDICT_RE = re.compile(r"^verdict:[ \t]*(\S+)", re.MULTILINE)
_SUPERSEDED_BOUNDARY_RE = re.compile(r"^#{1,6}[ \t]+.*\bsuperseded\b", re.MULTILINE | re.IGNORECASE)


def needs_review(step: PlanStep) -> bool:
    """Whether the plan-local trigger marks the step for a light review."""
    return step.review == REVIEW_FORCED or (step.review != REVIEW_OFF and step.routing == "opus")


def current_round(text: str) -> str:
    """The text above the first superseded-record heading, or all of it when there is none."""
    boundary = _SUPERSEDED_BOUNDARY_RE.search(text)
    return text if boundary is None else text[: boundary.start()]


def file_verdict(text: str | None) -> str | None:
    """`accept`, `revise` or `partial` (anything else) from the last verdict line of the
    file's current round."""
    found = _VERDICT_RE.findall(current_round(text or ""))
    return None if not found else found[-1] if found[-1] in (ACCEPT, REVISE) else UNFINISHED


@dataclass(frozen=True)
class NotRequired:
    """The trigger is off."""


@dataclass(frozen=True)
class Due:
    """A review is required and its request has not gone out."""

    round: int


@dataclass(frozen=True)
class Requested:
    """The review request went out and no return is recorded."""

    round: int


@dataclass(frozen=True)
class Accepted:
    """The review file reads `accept`."""


@dataclass(frozen=True)
class ReviseDue:
    """The first review asked for a revision no request has answered."""

    round: int


@dataclass(frozen=True)
class RevisedTwice:
    """The second review asked for a revision again."""


@dataclass(frozen=True)
class Unfinished:
    """A review returned and its file carries no verdict."""


@dataclass(frozen=True)
class RevisionFailed:
    """The latest revision did not pass its gate."""


ReviewState = Union[  # noqa: UP007 -- runtime value, 3.9 floor
    NotRequired, Due, Requested, Accepted, ReviseDue, RevisedTwice, Unfinished, RevisionFailed
]


def satisfied(state: ReviewState) -> bool:
    """A verified step is done only once no review stands between it and the next step."""
    return isinstance(state, (NotRequired, Accepted))


def review_state(
    required: bool, reviews: int, revises: int, revision_failed: bool, file_text: str | None
) -> ReviewState:
    """The review state from the trigger, the returns counted in the series and the file."""
    verdict = file_verdict(file_text)
    if not required:
        return NotRequired()
    if reviews and verdict == ACCEPT:
        return Accepted()
    if revision_failed:
        return RevisionFailed()
    if reviews > revises:
        if verdict != REVISE:
            return Unfinished()
        return ReviseDue(reviews) if revises == 0 else RevisedTwice()
    return Requested(reviews + 1) if verdict == UNFINISHED else Due(reviews + 1)


def review_record(
    reviewed: IterationRecord,
    request: str,
    agent_id: str,
    stop_reason: str,
    turns: int | None,
    max_turns: int | None,
) -> IterationRecord:
    """The ledger record of a reviewer's return. The review does not re-judge the work: the
    attempt, verdict, deciding source and evidence are the reviewed record's, and no commit
    holds the review (it changed nothing the loop commits). What the reviewer decided is in
    its file, read by `file_verdict`."""
    return replace(
        reviewed,
        agent_id=agent_id,
        commit=None,
        stop_reason=stop_reason,
        request=request,
        turns=turns,
        max_turns=max_turns,
    )
