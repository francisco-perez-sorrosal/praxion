"""A stop on a blocked return says how it clears, where the orchestrator reads it.

Both the stop block on stderr and the next-action section of HANDOFF.md say that the
stop clears only when the step's block in IMPLEMENTATION_PLAN.md is revised once the
blocker is resolved and the return is recorded, that the following `next` then issues
the step afresh under the revised block, and that an appended iteration-ledger record
or an edit of WIP.md leaves the stop standing. The loop behaves as it says.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.acceptance.drivers.step_loop import (
    Step,
    Work,
    attempt,
    build_loop,
    next_action,
    revise_step,
    step_id_of,
)
from tests.acceptance.drivers.step_loop_recovery import (
    CLEARS_ONLY_BY_REVISING_THE_PLAN,
    LEDGER_OR_WIP_EDITS_LEAVE_IT_STANDING,
    NEXT_ISSUES_THE_STEP_AFRESH,
    append_ledger_record,
    handoff_next_action,
    mark_blocker_resolved_in_wip,
    missing_patterns,
    stop_block,
)

BLOCKED = Work(touches_files=False, final_marker="blocked")

SURFACES = [
    pytest.param(stop_block, id="stop-block-on-stderr"),
    pytest.param(handoff_next_action, id="handoff-next-action"),
]
STATEMENTS = [
    pytest.param(CLEARS_ONLY_BY_REVISING_THE_PLAN, id="clears-only-by-revising-the-plan-block"),
    pytest.param(NEXT_ISSUES_THE_STEP_AFRESH, id="next-then-issues-the-step-afresh"),
    pytest.param(LEDGER_OR_WIP_EDITS_LEAVE_IT_STANDING, id="ledger-or-wip-edits-leave-it-standing"),
]


def _stopped_on_a_blocked_return(tmp_path: Path):
    task = build_loop(tmp_path, Step("1"), Step("2"))
    attempt(task, BLOCKED)
    return task, next_action(task)


@pytest.mark.parametrize("surface", SURFACES)
@pytest.mark.parametrize("statement", STATEMENTS)
def test_the_blocked_stop_says_how_it_clears(tmp_path: Path, surface, statement) -> None:
    _, stopped = _stopped_on_a_blocked_return(tmp_path)

    text = surface(stopped)

    assert stopped.stop["cause"] == "blocked-marker"
    missing = missing_patterns(text, statement)
    assert missing == [], f"the stop text lacks {missing}:\n{text}"


def test_an_appended_ledger_record_alone_leaves_the_stop_standing(tmp_path: Path) -> None:
    task, _ = _stopped_on_a_blocked_return(tmp_path)
    append_ledger_record(task, "1", attempt=2)

    still = next_action(task)

    assert still.exit_code == 2
    assert still.stop["cause"] == "blocked-marker"


def test_an_edit_of_wip_alone_leaves_the_stop_standing(tmp_path: Path) -> None:
    task, _ = _stopped_on_a_blocked_return(tmp_path)
    mark_blocker_resolved_in_wip(task)

    still = next_action(task)

    assert still.exit_code == 2
    assert still.stop["cause"] == "blocked-marker"


def test_revising_the_step_block_lets_next_issue_the_step_afresh(tmp_path: Path) -> None:
    task, _ = _stopped_on_a_blocked_return(tmp_path)
    revise_step(
        task, "1", "Write `src/step_1.py` returning the step id, now that the blocker is resolved."
    )

    resumed = next_action(task)

    assert resumed.outcome == "spawn", resumed.doc
    assert step_id_of(resumed.request["step"]) == "1"
    assert resumed.request["attempt"] == 1
