"""An arm's take is proven from each session's own record, and each governed check records
what arrived, when, and what it left.

Over planted session records the runner refuses to score, with the reason, a full session
lacking the moved rule at session start, a lean session carrying the rule's full text or
lacking its resident kernel, and a floor session carrying any line of the rule; a lean session
whose point-of-use text never arrived is scored, as a trigger failure. Over frozen copies of
recorded real sessions (the research probes, Claude Code 2.1.302) the trigger record reads:
an amended commit as arrived before execution, history repaired, final state passed; a commit
a gate refused with a reason and the session then recomposed as arrived before execution,
right first time, final state passed, the refusal recorded; a session-start rule as arrived
before composition; a path-matched load on a creating write as arrived after execution (read
as the adr-conventions move's governed action). A record from which arrivals cannot be read
reads as unknown, never as never arrived.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.acceptance.drivers.move_eval import FIRST_MOVE, SECOND_MOVE, Declared, declare
from tests.acceptance.drivers.move_scoring import (
    PlantedSession,
    probe_record,
    prove_take,
    trigger_records,
    unreadable_record,
)

SECOND_MOVE_SHAPE = "a resident line and a path-matched rule for the decision records"


@pytest.fixture(scope="module")
def first_move(tmp_path_factory: pytest.TempPathFactory) -> Declared:
    return declare(FIRST_MOVE, "as declared", tmp_path_factory.mktemp("first-move"))


@pytest.fixture(scope="module")
def second_move(tmp_path_factory: pytest.TempPathFactory) -> Declared:
    return declare(SECOND_MOVE, SECOND_MOVE_SHAPE, tmp_path_factory.mktemp("second-move"))


@pytest.fixture(params=("first", "second"))
def move(request, first_move, second_move) -> Declared:
    return {"first": first_move, "second": second_move}[request.param]


# -- The take: refused with the reason --------------------------------------------------------

UNTAKEN = [
    pytest.param(PlantedSession("full", "the resident kernel only"), id="full-lacking-the-rule"),
    pytest.param(PlantedSession("full", "no line of the rule"), id="full-with-nothing"),
    pytest.param(PlantedSession("lean", "the whole rule"), id="lean-carrying-the-whole-rule"),
    pytest.param(PlantedSession("lean", "no line of the rule"), id="lean-lacking-its-kernel"),
    pytest.param(PlantedSession("floor", "one line of the rule"), id="floor-carrying-a-line"),
    pytest.param(
        PlantedSession("floor", "the resident kernel only"), id="floor-carrying-the-kernel"
    ),
]


@pytest.mark.parametrize("planted", UNTAKEN)
def test_a_session_whose_arm_did_not_take_is_refused_scoring_with_the_reason(move, planted):
    take = prove_take(move, planted)

    assert not take.scored, f"{planted} was scored"
    assert take.reason, f"{planted} was refused with no reason"


# -- The take: scored -------------------------------------------------------------------------

TAKEN = [
    pytest.param(PlantedSession("full", "the whole rule"), id="full"),
    pytest.param(PlantedSession("lean", "the resident kernel only"), id="lean"),
    pytest.param(PlantedSession("floor", "no line of the rule"), id="floor"),
]


@pytest.mark.parametrize("planted", TAKEN)
def test_a_session_whose_arm_took_is_scored(move, planted):
    take = prove_take(move, planted)

    assert take.scored, f"{planted} was refused: {take.reason}"
    assert not take.trigger_failure


def test_a_lean_session_whose_point_of_use_text_never_arrived_is_scored_as_a_trigger_failure(
    move,
):
    planted = PlantedSession("lean", "the resident kernel only", point_of_use_arrived=False)

    take = prove_take(move, planted)

    assert take.scored, f"a lean session missing its point-of-use text was refused: {take.reason}"
    assert take.trigger_failure


# -- The trigger record over recorded sessions ------------------------------------------------


def test_a_commit_amended_after_its_point_of_use_context_arrived_reads_as_repaired(first_move):
    record = probe_record("a commit composed before its point-of-use context arrived, then amended")

    triggers = trigger_records(first_move, record)

    assert any(
        "before execution" in t.arrivals.values()
        and t.history == "repaired"
        and t.final == "passed"
        for t in triggers
    ), triggers


def test_a_commit_a_gate_refused_and_the_session_recomposed_reads_as_right_first_time(first_move):
    record = probe_record("a commit refused by a gate with a reason, then recomposed conforming")

    triggers = trigger_records(first_move, record)

    assert any(
        "before execution" in t.arrivals.values()
        and t.history == "right first time"
        and t.final == "passed"
        and t.refusals
        for t in triggers
    ), triggers


def test_a_rule_delivered_at_session_start_reads_as_arrived_before_composition(first_move):
    triggers = trigger_records(first_move, probe_record("a rule delivered at session start"))

    assert any(t.arrivals.get("session start") == "before composition" for t in triggers), triggers


def test_a_path_matched_load_on_a_creating_write_reads_as_arrived_after_execution(second_move):
    triggers = trigger_records(second_move, probe_record("a path-matched load on a creating write"))

    assert any(t.arrivals.get("path-matched load") == "after execution" for t in triggers), triggers


def test_a_record_whose_arrivals_cannot_be_read_reads_as_unknown_never_as_never(
    first_move, tmp_path: Path
):
    triggers = trigger_records(first_move, unreadable_record(tmp_path))

    timings = {timing for t in triggers for timing in t.arrivals.values()}

    assert triggers, "an unreadable record yielded no trigger record at all"
    assert timings == {"unknown"}, timings
