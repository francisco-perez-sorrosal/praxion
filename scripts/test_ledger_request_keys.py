"""Tests for the iteration ledger's optional driver keys (``scripts/iteration_ledger.py``).

The keys `request`, `step_digest`, `turns` and `max_turns` are additive under the
same schema version: a record written without them reads exactly as before, and a
record that carries them is validated where the line is parsed.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import iteration_ledger as ledger  # noqa: E402

STEP_LABEL = "Step "
STAMP = "2026-10-05T09:15Z"
HAND_APPENDED = {
    "v": 1,
    "recorded_at": STAMP,
    "step": f"{STEP_LABEL}7",
    "attempt": 1,
    "agent_id": "a3f9c2e17b",
    "verdict": "verified-complete",
    "decided_by": "check",
    "test_result": "Result: pass=12 fail=0 skip=0",
    "commit": "04569546",
    "stop_reason": "completed",
}
DRIVER_KEYS = {
    "request": "s7-a1-implement",
    "step_digest": "9ac894ba53b8",
    "turns": 31,
    "max_turns": 100,
}


def line(**extra) -> str:
    return json.dumps({**HAND_APPENDED, **extra})


def driver_record(**overrides) -> ledger.IterationRecord:
    base = {k: v for k, v in HAND_APPENDED.items() if k not in ("v", "recorded_at")}
    return ledger.IterationRecord(**{**base, **DRIVER_KEYS, **overrides})


@pytest.fixture
def fixed_clock(monkeypatch):
    monkeypatch.setattr(ledger, "_utc_minute", lambda: STAMP)


def test_a_hand_appended_record_reads_with_every_driver_key_absent():
    item = ledger.parse_record_line(line())

    assert (item.request, item.step_digest, item.turns, item.max_turns) == (None,) * 4


def test_a_record_without_a_request_renders_exactly_the_ten_original_keys():
    item = ledger.parse_record_line(line())

    assert json.loads(ledger.render_record_line(item)) == HAND_APPENDED


def test_a_driver_record_survives_a_write_and_a_read(tmp_path, fixed_clock):
    ledger.append_record(tmp_path, driver_record())

    (stored,) = ledger.read_ledger(tmp_path).records

    assert stored == driver_record(recorded_at=STAMP)


def test_an_unknown_turn_count_is_written_as_null_and_reads_back_as_none(tmp_path, fixed_clock):
    ledger.append_record(tmp_path, driver_record(turns=None))

    written = json.loads((tmp_path / ledger.LEDGER_FILE).read_text())
    (stored,) = ledger.read_ledger(tmp_path).records

    assert (written["turns"], stored.turns) == (None, None)


def test_the_reader_exposes_the_set_of_recorded_request_ids(tmp_path, fixed_clock):
    ledger.append_record(tmp_path, driver_record(request="s7-a1-implement"))
    ledger.append_record(tmp_path, driver_record(request="s7-a2-implement", attempt=2))
    ledger.append_record(tmp_path, ledger.parse_record_line(line()))

    assert ledger.read_ledger(tmp_path).requests == {"s7-a1-implement", "s7-a2-implement"}


def test_a_ledger_of_hand_appended_records_holds_no_request_ids(tmp_path):
    (tmp_path / ledger.LEDGER_FILE).write_text(line() + "\n")

    assert ledger.read_ledger(tmp_path).requests == frozenset()


@pytest.mark.parametrize("stop_reason", ["partial", "conflict"])
def test_the_new_stop_reasons_are_accepted(stop_reason):
    assert ledger.parse_record_line(line(stop_reason=stop_reason)).stop_reason == stop_reason


@pytest.mark.parametrize(
    ("key", "bad"),
    [
        ("request", "S7 Bad"),
        ("request", ""),
        ("request", 7),
        ("step_digest", "XYZ"),
        ("step_digest", "abc"),
        ("step_digest", 12345678),
        ("turns", -1),
        ("turns", True),
        ("turns", "31"),
        ("turns", 3.5),
        ("max_turns", 0),
        ("max_turns", False),
        ("max_turns", "100"),
    ],
)
def test_a_driver_key_that_breaks_its_shape_is_a_finding(key, bad):
    with pytest.raises(ledger.ShapeError, match=key):
        ledger.parse_record_line(line(**{**DRIVER_KEYS, key: bad}))


@pytest.mark.parametrize("key", ["step_digest", "turns", "max_turns"])
def test_a_driver_fact_without_a_request_is_a_finding(key):
    with pytest.raises(ledger.ShapeError, match="need a request"):
        ledger.parse_record_line(line(**{key: DRIVER_KEYS[key]}))


@pytest.mark.parametrize("key", ["step_digest", "turns", "max_turns"])
def test_a_record_cannot_be_constructed_with_a_driver_fact_and_no_request(key):
    with pytest.raises(ledger.ShapeError, match="need a request"):
        driver_record(request=None, **{key: DRIVER_KEYS[key]})


def test_a_driver_record_with_null_facts_is_valid():
    item = ledger.parse_record_line(
        line(request="s7-a1-implement", step_digest=None, turns=None, max_turns=None)
    )

    assert (item.request, item.step_digest, item.turns, item.max_turns) == (
        "s7-a1-implement",
        None,
        None,
        None,
    )


def test_an_unknown_extra_key_is_still_ignored():
    assert ledger.parse_record_line(line(future_key="x")).step == f"{STEP_LABEL}7"


def test_the_append_command_line_accepts_the_new_stop_reasons():
    parser = ledger._build_parser()

    args = parser.parse_args(
        ["append", "slug", "--step", "7", "--attempt", "1", "--agent-id", "a1"]
        + ["--stop-reason", "partial", "--no-commit"]
    )

    assert args.stop_reason == "partial"
