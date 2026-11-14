"""The refactoring-delivery axis: its arms are its own, and a record of either axis round-trips."""

from __future__ import annotations

import json
import random
import re
from dataclasses import replace
from pathlib import Path

import pytest

from praxion_evals.adherence import axis, model, results, session_loop
from praxion_evals.adherence.model import (
    ArmBuild,
    Errored,
    Measured,
    NotMeasured,
    Passed,
    SessionRecord,
    SessionSetup,
)
from tests.test_adherence_results import run_results, session

_FIELDS = ("abc1234", "implementer", "task-1", "tmpl", 7)


def _setup(arm: str, axis_name: str | None = None) -> SessionSetup:
    extra = {} if axis_name is None else {"axis": axis_name}
    return SessionSetup(arm, *_FIELDS, **extra)  # type: ignore[arg-type]


def test_each_axis_holds_exactly_its_own_arms():
    assert axis.ARMS_BY_AXIS["inherited-context"] == ("full", "lean")
    assert axis.ARMS_BY_AXIS["refactoring-delivery"] == ("preloaded", "delivered")
    assert axis.DEFAULT_AXIS == "inherited-context"
    assert set(axis.ARMS_BY_AXIS) == set(axis.AXES)


@pytest.mark.parametrize("arm", ["preloaded", "delivered"])
def test_a_new_arm_is_legal_on_the_new_axis(arm):
    assert _setup(arm, "refactoring-delivery").arm == arm


@pytest.mark.parametrize(
    ("arm", "axis_name"),
    [
        ("preloaded", None),
        ("delivered", "inherited-context"),
        ("full", "refactoring-delivery"),
        ("lean", "refactoring-delivery"),
    ],
    ids=[
        "new arm on the default axis",
        "new arm named on the old axis",
        "full on new",
        "lean on new",
    ],
)
def test_an_arm_of_the_other_axis_is_refused(arm, axis_name):
    with pytest.raises(ValueError, match="axis has arms"):
        _setup(arm, axis_name)


def test_an_unknown_axis_is_refused():
    with pytest.raises(ValueError, match="an axis must be one of"):
        _setup("full", "elsewhere")


@pytest.mark.parametrize("arm", ["preloaded", "delivered"])
def test_a_setup_of_each_new_arm_survives_its_json_round_trip(arm):
    setup = _setup(arm, "refactoring-delivery")

    assert model.setup_from_json(json.loads(json.dumps(model.setup_to_json(setup)))) == setup


@pytest.mark.parametrize(
    "make",
    [lambda setup: NotMeasured("dry", setup), lambda setup: Errored("timeout", "slow", setup)],
)
def test_a_status_echoing_a_new_arm_setup_round_trips(make):
    setup = _setup("delivered", "refactoring-delivery")

    assert model.status_from_json(model.status_to_json(make(setup))).setup == setup


@pytest.mark.parametrize("arm", ["full", "lean"])
def test_the_default_axis_encodes_exactly_as_before(arm):
    assert model.setup_to_json(_setup(arm)) == {
        "arm": arm,
        "checkout_commit": "abc1234",
        "role": "implementer",
        "task_id": "task-1",
        "template_id": "tmpl",
        "seed": 7,
    }


def test_a_record_written_before_the_axis_existed_decodes_on_the_default_axis():
    old = {
        "arm": "lean",
        "checkout_commit": "c",
        "role": "implementer",
        "task_id": "t",
        "template_id": "x",
        "seed": 3,
    }

    assert model.setup_from_json(old) == SessionSetup("lean", "c", "implementer", "t", "x", 3)
    assert model.setup_from_json(old).axis == "inherited-context"


def test_a_decoded_record_of_the_wrong_axis_is_refused_at_the_boundary():
    encoded = model.setup_to_json(_setup("delivered", "refactoring-delivery"))

    with pytest.raises(ValueError, match="axis has arms"):
        model.setup_from_json({**encoded, "axis": "inherited-context"})


def test_a_session_record_of_a_new_arm_keeps_its_setup():
    setup = _setup("preloaded", "refactoring-delivery")
    record = SessionRecord(setup, NotMeasured("dry", setup), 0.0, 0, "2026-11-14T10:00:00Z")

    assert record.status.setup.axis == "refactoring-delivery"


# ---------------------------------------------------------------------------
# Positions and patched paths: what each arm's build changes, and how a pair reads them
# ---------------------------------------------------------------------------

_MOVE_TOOL = Path(__file__).parents[2] / "scripts" / "refactoring_move.py"
_DEFINITION = "agents/implementer.md"
_BOTH_SITES = ("agents/implementer.md", "agents/test-engineer.md")


def test_each_axis_names_its_baseline_and_its_treatment():
    assert axis.POSITIONS["inherited-context"] == axis.Positions("full", "lean")
    assert axis.POSITIONS["refactoring-delivery"] == axis.Positions("preloaded", "delivered")
    for name, positions in axis.POSITIONS.items():
        assert (positions.baseline, positions.treatment) == axis.ARMS_BY_AXIS[name]


def test_every_arm_belongs_to_one_axis_and_the_axes_share_none():
    assert sorted(axis.SESSION_ARMS) == ["delivered", "full", "lean", "preloaded"]
    owners = [axis.axis_of(arm) for arm in axis.SESSION_ARMS]  # type: ignore[arg-type]
    assert owners == ["inherited-context"] * 2 + ["refactoring-delivery"] * 2
    assert set(axis.ARMS_BY_AXIS["inherited-context"]).isdisjoint(
        axis.ARMS_BY_AXIS["refactoring-delivery"]
    )


@pytest.mark.parametrize(
    ("arm", "cap", "expected"),
    [
        ("full", None, ()),
        ("lean", None, (_DEFINITION,)),
        ("full", 5, (_DEFINITION,)),
        ("lean", 5, (_DEFINITION,)),
        ("preloaded", None, ()),
        ("delivered", None, _BOTH_SITES),
        ("preloaded", 5, (_DEFINITION,)),
        ("delivered", 5, _BOTH_SITES),
    ],
    ids=[
        "uncapped full builds nothing",
        "lean builds the definition",
        "capped full builds the definition",
        "capped lean builds it once",
        "uncapped preloaded builds nothing",
        "delivered builds both move sites",
        "capped preloaded builds the definition",
        "capped delivered builds both sites once",
    ],
)
def test_an_arm_build_changes_exactly_these_files(arm, cap, expected):
    assert axis.patched_paths("implementer", arm, cap) == expected


def test_a_capped_delivered_build_of_another_role_adds_its_own_definition():
    paths = axis.patched_paths("verifier", "delivered", 5)

    assert paths == tuple(sorted({"agents/verifier.md", *_BOTH_SITES}))


def test_the_move_sites_are_the_two_definitions_the_move_script_names():
    named = dict(
        re.findall(r'^(IMPLEMENTER|TEST_ENGINEER) = "([^"]+)"', _MOVE_TOOL.read_text(), re.M)
    )

    assert set(axis.MOVE_SITES) == set(named.values()) == set(_BOTH_SITES)


def _build(arm: str, patched: tuple[str, ...], cap: int | None = None) -> ArmBuild:
    return ArmBuild("implementer", arm, Path("/copy"), cap, "digest", patched)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("arm", "patched"),
    [("preloaded", ()), ("delivered", _BOTH_SITES)],
    ids=["preloaded", "delivered"],
)
def test_an_arm_build_accepts_each_new_arm_with_its_exact_patched_files(arm, patched):
    assert _build(arm, patched).patched == patched


@pytest.mark.parametrize(
    ("arm", "patched"),
    [("preloaded", (_DEFINITION,)), ("delivered", ()), ("delivered", (_DEFINITION,))],
    ids=["preloaded patched", "delivered unpatched", "delivered one site"],
)
def test_an_arm_build_refuses_another_patched_list_on_the_new_axis(arm, patched):
    with pytest.raises(ValueError, match="an arm build patches exactly"):
        _build(arm, patched)


def test_the_default_axis_keeps_its_patched_rule_and_its_message():
    with pytest.raises(
        ValueError, match="patches agents/implementer.md exactly when it is lean or capped"
    ):
        _build("lean", ())


def test_an_arm_build_refuses_an_arm_of_neither_axis():
    with pytest.raises(ValueError, match="an arm build's arm"):
        _build("sideways", ())


def _new_axis_session(task: str, arm: str, status: model.SessionStatus) -> SessionRecord:
    setup = SessionSetup(
        arm, *_FIELDS[:1], "researcher", task, "template", 7, "refactoring-delivery"
    )  # type: ignore[arg-type]
    return SessionRecord(setup, status, 0.01, 1000, "2026-10-12T09:00:00Z")


def _new_axis_run(sessions: list[SessionRecord]):
    run = run_results(sessions, extra={"axis": "refactoring-delivery"})
    arms = {"researcher": {"preloaded": {"built": True}, "delivered": {"built": True}}}
    return replace(run, arms=arms)


def test_a_run_of_the_new_axis_pairs_preloaded_as_the_baseline_and_delivered_as_the_treatment():
    measured, treated = Measured({"C1": Passed()}, 1), Measured({"C1": Passed()}, 2)
    run = _new_axis_run(
        [
            _new_axis_session("t1", "delivered", treated),
            _new_axis_session("t1", "preloaded", measured),
        ]
    )

    (pair,) = results.pairs_of(run, "researcher")

    assert (pair.full, pair.lean) == (measured, treated)


def test_a_task_that_ran_in_one_arm_of_the_new_axis_does_not_pair():
    run = _new_axis_run([_new_axis_session("t1", "preloaded", Measured({"C1": Passed()}, 1))])

    assert results.pairs_of(run, "researcher") == []


def test_a_default_run_pairs_full_as_the_baseline_and_lean_as_the_treatment():
    full, lean = Measured({"C1": Passed()}, 1), Measured({"C1": Passed()}, 2)
    run = run_results([session("t1", "full", full), session("t1", "lean", lean)])

    (pair,) = results.pairs_of(run, "researcher")

    assert (pair.full, pair.lean) == (full, lean)


def test_the_default_launch_order_is_unchanged_by_the_axis_argument():
    for task in (f"task-{n}" for n in range(24)):
        drawn = tuple(random.Random(f"7:{task}").sample(("full", "lean"), 2))

        assert session_loop.launch_order(7, task) == drawn
        assert session_loop.launch_order(7, task, "inherited-context") == drawn


def test_the_launch_order_on_the_new_axis_is_the_default_draw_mapped_onto_its_arms():
    onto = {"full": "preloaded", "lean": "delivered"}
    for task in (f"task-{n}" for n in range(24)):
        first, second = session_loop.launch_order(7, task)

        assert session_loop.launch_order(7, task, "refactoring-delivery") == (
            onto[first],
            onto[second],
        )


def test_ordered_arms_keeps_the_launch_order_over_the_axis_arms_it_is_given():
    for task in (f"task-{n}" for n in range(24)):
        order = session_loop.launch_order(7, task, "refactoring-delivery")

        assert session_loop.ordered_arms(
            ["delivered", "preloaded"], 7, task, "refactoring-delivery"
        ) == list(order)
        assert session_loop.ordered_arms(["delivered"], 7, task, "refactoring-delivery") == [
            "delivered"
        ]
