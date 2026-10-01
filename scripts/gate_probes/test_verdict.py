"""Tests for `verdict.py` -- the liveness verdict every probe returns.

The failure mode this closes: a probe that passes by default, or fails without
saying what it expected against what it observed. Expected values come from the
contract in the module docstring, not from running the implementation.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Flat import (siblings by bare name), the layout the mutation sensor reads.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from verdict import GateId, Verdict, parse_json, render_json  # noqa: E402

FAILED_REASON = "expected the dead gate to be caught; observed it passed the bad input"


def _passed(gate: GateId, **overrides: object) -> Verdict:
    return Verdict(gate=gate, passed=True, reason="", elapsed_s=1.5, **overrides)


def _failed(gate: GateId, **overrides: object) -> Verdict:
    return Verdict(gate=gate, passed=False, reason=FAILED_REASON, elapsed_s=2.5, **overrides)


def _gate_position(verdict: Verdict) -> int:
    return list(GateId).index(verdict.gate)


def test_gate_ids_are_the_four_gates_in_the_fixed_order() -> None:
    assert [gate.value for gate in GateId] == [
        "mutation-sensor",
        "observation-hooks",
        "spawn-count",
        "selection-audit",
    ]


def test_passed_verdict_with_a_reason_is_rejected() -> None:
    with pytest.raises(ValueError, match="passed"):
        Verdict(gate=GateId.SPAWN_COUNT, passed=True, reason="all good", elapsed_s=0.1)


def test_passed_verdict_with_unselected_reads_is_rejected() -> None:
    with pytest.raises(ValueError, match="unselected"):
        _passed(GateId.SELECTION_AUDIT, unselected=(("tests/test_a.py", "docs/a.md"),))


@pytest.mark.parametrize(
    "reason",
    [
        "",
        "   ",
        "the gate is dead",
        "expected a catch",
        "observed a pass; expected a catch",
    ],
)
def test_failed_verdict_without_an_expected_and_observed_reason_is_rejected(reason: str) -> None:
    with pytest.raises(ValueError, match="expected"):
        Verdict(gate=GateId.MUTATION_SENSOR, passed=False, reason=reason, elapsed_s=0.1)


def test_negative_elapsed_time_is_rejected() -> None:
    with pytest.raises(ValueError, match="elapsed"):
        Verdict(gate=GateId.SPAWN_COUNT, passed=True, reason="", elapsed_s=-0.1)


def test_json_schema_1_round_trips_in_fixed_gate_order() -> None:
    verdicts = (
        _failed(GateId.SELECTION_AUDIT, unselected=(("tests/test_a.py", "docs/a.md"),)),
        _passed(GateId.MUTATION_SENSOR, notes=("5 mutants",)),
        _failed(GateId.SPAWN_COUNT),
    )

    payload = json.loads(render_json(verdicts))

    assert payload["schema"] == 1
    assert payload["passed"] is False
    assert [entry["gate"] for entry in payload["verdicts"]] == [
        "mutation-sensor",
        "spawn-count",
        "selection-audit",
    ]
    assert payload["verdicts"][2]["unselected"] == [["tests/test_a.py", "docs/a.md"]]
    assert parse_json(render_json(verdicts)) == tuple(sorted(verdicts, key=_gate_position))


def test_all_passed_verdicts_render_a_passed_report() -> None:
    verdicts = (_passed(GateId.MUTATION_SENSOR), _passed(GateId.OBSERVATION_HOOKS))

    assert json.loads(render_json(verdicts))["passed"] is True


def test_empty_report_is_rejected_rather_than_vacuously_passed() -> None:
    with pytest.raises(ValueError, match="no verdicts"):
        render_json(())


def test_duplicate_gate_in_a_report_is_rejected() -> None:
    with pytest.raises(ValueError, match="twice"):
        render_json((_passed(GateId.SPAWN_COUNT), _failed(GateId.SPAWN_COUNT)))


def test_parse_rejects_an_unknown_schema_version() -> None:
    with pytest.raises(ValueError, match="schema"):
        parse_json('{"schema": 2, "passed": true, "verdicts": []}')


def test_parse_rejects_a_top_level_passed_that_disagrees_with_the_verdicts() -> None:
    payload = json.loads(render_json((_failed(GateId.SPAWN_COUNT),)))
    payload["passed"] = True

    with pytest.raises(ValueError, match="disagrees"):
        parse_json(json.dumps(payload))


def test_parse_rejects_verdicts_out_of_the_fixed_order() -> None:
    payload = json.loads(
        render_json((_passed(GateId.MUTATION_SENSOR), _passed(GateId.SPAWN_COUNT)))
    )
    payload["verdicts"].reverse()

    with pytest.raises(ValueError, match="order"):
        parse_json(json.dumps(payload))


def test_parse_rejects_a_verdict_that_breaks_the_constructor_invariants() -> None:
    payload = json.loads(render_json((_failed(GateId.SPAWN_COUNT),)))
    payload["verdicts"][0]["reason"] = ""

    with pytest.raises(ValueError, match="expected"):
        parse_json(json.dumps(payload))


def test_zero_elapsed_time_is_accepted() -> None:
    assert Verdict(gate=GateId.SPAWN_COUNT, passed=True, reason="", elapsed_s=0.0).elapsed_s == 0.0


def test_mixed_report_is_not_passed_and_keeps_every_field_through_a_round_trip() -> None:
    verdicts = (
        Verdict(
            gate=GateId.OBSERVATION_HOOKS,
            passed=True,
            reason="",
            elapsed_s=0.25,
            notes=("first", "second"),
        ),
        Verdict(
            gate=GateId.SELECTION_AUDIT,
            passed=False,
            reason=FAILED_REASON,
            elapsed_s=7.125,
            unselected=(("tests/a.py", "docs/a.md"), ("tests/b.py", "docs/b.md")),
        ),
    )

    report = render_json(verdicts)

    assert json.loads(report)["passed"] is False
    assert parse_json(report) == verdicts


def test_parse_rejects_a_gate_listed_twice() -> None:
    payload = json.loads(render_json((_passed(GateId.SPAWN_COUNT),)))
    payload["verdicts"].append(payload["verdicts"][0])

    with pytest.raises(ValueError, match="order"):
        parse_json(json.dumps(payload))


def test_parse_rejects_a_report_with_no_verdicts() -> None:
    with pytest.raises(ValueError, match="no verdicts"):
        parse_json('{"schema": 1, "passed": true, "verdicts": []}')
