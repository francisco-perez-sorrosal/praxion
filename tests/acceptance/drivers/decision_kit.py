"""Driver for the adr-conventions move's kit: its tasks, its fixtures, its graders, its lean start.

The scenarios speak the specification's words; this module is where they meet the runner.

Bound here, because the specification or the base commit fixes them:

- the move's name, its moved rule, the names of its two governed checks ("decision draft
  placement" and "decision category"), each check's failing parts in the specification's
  words, the four `category` values and the reason a session that left no record is not graded;
- the kit's declaration, read as the git-conventions kit's is (`move_declarations`).

- the kit's task list and each task's fixture project, reached by the move's name through
  `move_pocket`, the one seam into the eval pocket (the modules live in a Python 3.13 project this
  suite's interpreter does not import, so each is imported inside the code string run there);
- the grade of one governed check over a planted end state, given the fixture project as it was
  built and the project as a session left it, answered as `DecisionGrade`.

Unbound until a binding step ties it to the designed surface (it raises `UnboundDriverError`
with the assumption's words):

- the observation of a lean copy's own installer linking rules into a sandbox home, and of the
  text a session started from that home receives at session start.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from tests.acceptance.drivers import adherence_eval, move_declarations, move_pocket
from tests.acceptance.drivers.adherence_eval import SEED
from tests.acceptance.drivers.move_eval import (
    FIXTURE_KINDS,
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


# -- Tasks and fixtures ------------------------------------------------------------------------


@dataclass(frozen=True)
class DecisionTask:
    task_id: str
    fixture: str
    fixture_kind: FixtureKind
    wording_variant: str
    wording: str  # the request the session is given
    sort: Sort  # the sort the moved rule's test gives the decision the request describes


# The sort is told apart by a total match over the kit's two sort types; a third sort would fail
# type checking where it is added and fail here at once, never be read as one of the two.
_TASKS = """
from typing import assert_never
from praxion_evals.adherence.moves import kit_adr

def sort_word(task):
    match kit_adr.sort_of(task):
        case kit_adr.Architectural():
            return "architectural"
        case kit_adr.WithinComponent():
            return "not architectural"
        case unreachable:
            assert_never(unreachable)

emit(
    [
        {**dataclasses.asdict(task), "sort": sort_word(task)}
        for task in kit_adr.tasks(declared, request["seed"])
    ]
)
"""

_BUILD_FIXTURE = """
from praxion_evals.adherence.moves import kit_adr
task = next(t for t in kit_adr.tasks(declared, request["seed"]) if t.task_id == request["task_id"])
emit(str(kit_adr.build_fixture(declared, task, Path(request["where"]))))
"""


def decision_tasks(declared: Declared, seed: int = SEED) -> tuple[DecisionTask, ...]:
    drawn = move_pocket.call_with_declaration(_TASKS, declared.move, declared.path, {"seed": seed})
    return tuple(
        DecisionTask(
            task["task_id"],
            task["fixture"],
            _fixture_kind(task["fixture_kind"]),
            task["wording_variant"],
            task["wording"],
            _sort(task["sort"]),
        )
        for task in drawn
    )


def build_decision_fixture(declared: Declared, task: DecisionTask, where: Path) -> Path:
    """The fixture project of `task`, built under `where` from the default seed's task list."""
    request = {"seed": SEED, "task_id": task.task_id, "where": str(where)}
    built = move_pocket.call_with_declaration(_BUILD_FIXTURE, declared.move, declared.path, request)
    return Path(built)


def _fixture_kind(word: str) -> FixtureKind:
    for kind in FIXTURE_KINDS:
        if word == kind:
            return kind
    raise ValueError(f"fixture kind {word!r} is neither managed nor unmanaged")


def _sort(word: str) -> Sort:
    match word:
        case "architectural" | "not architectural":
            return word
        case _:
            raise ValueError(f"sort {word!r} is neither architectural nor not architectural")


# -- Grading a planted end state ---------------------------------------------------------------


@dataclass(frozen=True)
class DecisionGrade:
    outcome: Outcome
    failed_parts: frozenset[str]  # in the specification's words, each named once
    reason: str | None  # why there was nothing to grade; None otherwise


# The grade is told apart by a total match over what the grader may answer.
_GRADE = """
from typing import assert_never
from praxion_evals.adherence.moves import checks_adr, checks_git, model

answer = checks_adr.grade_records(
    request["check"],
    frozenset(request["before"]),
    request["branch"],
    Path(request["end_state"]),
)
match answer:
    case checks_git.Grade(outcome=outcome, failed_parts=parts):
        emit({"outcome": outcome, "failed_parts": list(parts), "reason": None})
    case model.NothingToGrade(reason=reason):
        emit({"outcome": "nothing to grade", "failed_parts": [], "reason": reason})
    case unreachable:
        assert_never(unreachable)
"""


def grade_decision_end_state(
    declared: Declared, check: str, fixture: Path, end_state: Path
) -> DecisionGrade:
    """Grade `check` over the project a session left (`end_state`), its fixture as built beside it."""
    request = {
        "check": check,
        "before": _files_as_built(fixture),
        "branch": _branch_as_built(fixture),
        "end_state": str(end_state),
    }
    answer = move_pocket.call_with_declaration(_GRADE, declared.move, declared.path, request)
    return DecisionGrade(
        _outcome(answer["outcome"]), frozenset(answer["failed_parts"]), answer["reason"]
    )


def _outcome(word: str) -> Outcome:
    match word:
        case "passed" | "failed" | "nothing to grade":
            return word
        case _:
            raise ValueError(f"outcome {word!r} is not passed, failed or nothing to grade")


def _files_as_built(fixture: Path) -> list[str]:
    """Every file of the fixture project, repository-relative with forward slashes."""
    listed = []
    for directory, subdirectories, names in os.walk(fixture):
        if Path(directory) == fixture and ".git" in subdirectories:
            subdirectories.remove(".git")
        listed.extend((Path(directory) / name).relative_to(fixture).as_posix() for name in names)
    return sorted(listed)


def _branch_as_built(fixture: Path) -> str:
    """The branch the fixture project is on, read apart from the operator's git configuration."""
    return adherence_eval._git(fixture, "symbolic-ref", "--short", "HEAD").strip()


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
