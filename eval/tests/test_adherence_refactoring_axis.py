"""The refactoring-delivery axis: its arms are its own, and a record of either axis round-trips."""

from __future__ import annotations

import json

import pytest

from praxion_evals.adherence import axis, model
from praxion_evals.adherence.model import Errored, NotMeasured, SessionRecord, SessionSetup

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
