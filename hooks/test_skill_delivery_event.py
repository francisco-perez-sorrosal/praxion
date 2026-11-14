"""The ``skill_delivery`` event class: one row per delegation that asked for a skill body.

A served and a failed delivery each round-trip through the writer and the reader, and the
class declares exactly the fields a row may carry, so a row with a field the registry does
not know is the one the registry's own enumeration check flags.
"""

from __future__ import annotations

import pytest

from hooks._observation_log import reader, registry, writer
from hooks._observation_log.modes import Mode
from hooks._observation_log.registry import EventClass

SERVED_ROW = {
    "timestamp": "2026-11-13T10:00:00Z",
    "session_id": "s1",
    "event_type": "skill_delivery",
    "agent_type": "praxion:implementer",
    "skill": "refactoring",
    "outcome": "served",
    "route": "own-words",
    "body_digest": "9f2c41",
    "tool_use_id": "toolu_01",
}
FAILED_ROW = {
    "timestamp": "2026-11-13T10:00:01Z",
    "session_id": "s1",
    "event_type": "skill_delivery",
    "agent_type": "praxion:test-engineer",
    "skill": "refactoring",
    "outcome": "failed",
    "route": "step-request",
    "reason": "step heading not found",
    "tool_use_id": "toolu_02",
}
STANDARD_MODE = {"PRAXION_OBSERVATION_LOG": "standard"}


def _round_trip(tmp_path, row):
    assert writer.record(tmp_path, EventClass.SKILL_DELIVERY, row, env=STANDARD_MODE)
    return reader.read_rows(tmp_path)[-1]


@pytest.mark.parametrize("row", [SERVED_ROW, FAILED_ROW], ids=["served", "failed"])
def test_a_row_of_each_outcome_round_trips_through_the_writer_and_reader(tmp_path, row):
    stored = _round_trip(tmp_path, row)

    assert stored == {**row, "log_mode": "standard"}


@pytest.mark.parametrize("row", [SERVED_ROW, FAILED_ROW], ids=["served", "failed"])
def test_a_row_of_each_outcome_declares_only_fields_the_registry_knows(row):
    spec = registry.EVENTS[EventClass.SKILL_DELIVERY]

    assert set(row) - set(spec.fields) == set()
    assert set(spec.fields) - set(row) - {"log_mode"} - spec.optional == set()


def test_a_field_the_registry_does_not_declare_is_flagged_as_undeclared():
    spec = registry.EVENTS[EventClass.SKILL_DELIVERY]
    row = {**SERVED_ROW, "unplanned_field": 1}

    assert set(row) - set(spec.fields) == {"unplanned_field"}


def test_the_class_writes_its_own_event_type_and_is_recorded_in_standard_mode():
    spec = registry.EVENTS[EventClass.SKILL_DELIVERY]

    assert spec.event_type == EventClass.SKILL_DELIVERY.value == "skill_delivery"
    assert registry.records(EventClass.SKILL_DELIVERY, Mode.STANDARD)


def test_each_outcome_carries_only_its_own_optional_field():
    spec = registry.EVENTS[EventClass.SKILL_DELIVERY]

    assert spec.optional == {"reason", "body_digest"}
    assert "reason" not in SERVED_ROW
    assert "body_digest" not in FAILED_ROW
