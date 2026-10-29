"""Driver for the adr-conventions move's kit: its tasks, its fixtures, its graders, its lean start.

The scenarios speak the specification's words; this module is where they meet the runner.

Bound here, because the specification or the base commit fixes them:

- the move's name, its moved rule, the names of its two governed checks ("decision draft
  placement" and "decision category"), each check's failing parts in the specification's
  words, the four `category` values and the reason a session that left no record is not graded;
- the kit's declaration, read as the git-conventions kit's is (`move_declarations`).

Unbound until a binding step ties them to the designed surface (each raises
`UnboundDriverError` with the assumption's words):

- the kit's task list and each task's fixture project, reached by the move's name;
- the grade of one governed check over a planted end state, given the fixture project as it was
  built and the project as a session left it;
- the observation of a lean copy's own installer linking rules into a sandbox home, and of the
  text a session started from that home receives at session start.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from tests.acceptance.drivers import move_declarations
from tests.acceptance.drivers.adherence_eval import SEED
from tests.acceptance.drivers.move_eval import (
    MOVED_RULES,
    SECOND_MOVE,
    Declared,
    FixtureKind,
    unbound,
)

DECISION_MOVE = SECOND_MOVE
DECISION_RULE = MOVED_RULES[SECOND_MOVE]
DRAFT_PLACEMENT = "decision draft placement"
DECISION_CATEGORY = "decision category"
DECISION_CHECKS = (DRAFT_PLACEMENT, DECISION_CATEGORY)
CATEGORY_VALUES = ("architectural", "behavioral", "implementation", "configuration")
NO_RECORD_REASON = "no decision record written"

NOT_UNDER_DRAFTS = "a record not directly under the draft directory"
MALFORMED_NAME = "a malformed fragment name"
MALFORMED_ID = "a malformed draft id"
SELF_NUMBERED = "a record that numbers itself"
PLACEMENT_PARTS = (NOT_UNDER_DRAFTS, MALFORMED_NAME, MALFORMED_ID, SELF_NUMBERED)
NO_CATEGORY = "no category"
UNKNOWN_CATEGORY = "an unknown category"
NO_DISCONFIRMATION = "an architectural record with no disconfirmation"
CATEGORY_PARTS = (NO_CATEGORY, UNKNOWN_CATEGORY, NO_DISCONFIRMATION)

Sort = Literal["architectural", "not architectural"]
Outcome = Literal["passed", "failed", "nothing to grade"]


# -- The kit's declaration --------------------------------------------------------------------


def kit_payload() -> move_declarations.Payload:
    return move_declarations.kit_payload(DECISION_MOVE)


def declared_phrases(payload: move_declarations.Payload) -> tuple[str, ...]:
    return tuple(phrase for check in payload["checks"] for phrase in check["phrases"])


def rule_lines(text: str, minimum: int = 20) -> frozenset[str]:
    """The rule's body lines, stripped of list markers and folded, long enough to be distinctive."""
    lines = (
        re.sub(r"^[-*\d.\s]+", "", line).strip().casefold()
        for line in move_declarations.body_lines(text)
    )
    return frozenset(line for line in lines if len(line) > minimum)


# -- Tasks and fixtures (unbound) -------------------------------------------------------------


@dataclass(frozen=True)
class DecisionTask:
    task_id: str
    fixture: str
    fixture_kind: FixtureKind
    wording_variant: str
    wording: str  # the request the session is given
    sort: Sort  # the sort the moved rule's test gives the decision the request describes


def decision_tasks(declared: Declared, seed: int = SEED) -> tuple[DecisionTask, ...]:
    unbound(
        "the adr-conventions move's task list is drawn by the move's name and seed, each task"
        " giving its task id, fixture, fixture kind, wording variant, the request's wording and"
        " the sort of the decision the request describes"
    )


def build_decision_fixture(declared: Declared, task: DecisionTask, where: Path) -> Path:
    unbound(
        "the fixture project of an adr-conventions task is built under a given directory and"
        " its root returned"
    )


# -- Grading a planted end state (unbound) ----------------------------------------------------


@dataclass(frozen=True)
class DecisionGrade:
    outcome: Outcome
    failed_parts: frozenset[str]  # in the specification's words, each named once
    reason: str | None  # why there was nothing to grade; None otherwise


def grade_decision_end_state(
    declared: Declared, check: str, fixture: Path, end_state: Path
) -> DecisionGrade:
    """Grade `check` over the project a session left (`end_state`), its fixture as built beside it."""
    unbound(
        "a governed check of the adr-conventions move grades the project a session left against"
        " the fixture project as it was built, answering passed, failed or nothing to grade,"
        " the failing parts in the specification's words, and the reason when nothing is graded"
    )


# -- The lean copy's own installer and session start (unbound) -------------------------------


@dataclass(frozen=True)
class LeanStart:
    linked_rules: frozenset[str]  # repository paths of the rule files linked into the home
    session_start_text: str  # every text the session start injected, joined


def lean_session_start(lean_copy: Path, sandbox: Path) -> LeanStart:
    unbound(
        "a lean copy's own installer is run offline into a sandbox home under a given directory,"
        " reporting which rule files of the copy it linked there, and a session start over that"
        " home is observed offline, reporting the text injected at session start"
    )
