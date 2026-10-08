"""Tests for the iteration ledger's two optional goal keys (``scripts/iteration_ledger.py``).

``cost_usd`` and ``progress_lines`` are additive under the same schema version: a record
without them renders and reads exactly as before, and a record that carries them is
validated where the line is parsed.
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
STAMP = "2026-10-08T11:30Z"
REQUEST_ID = "s5-a1-implement"
BASE = {
    "v": 1,
    "recorded_at": STAMP,
    "step": f"{STEP_LABEL}5",
    "attempt": 1,
    "agent_id": "a3f9c2e17b",
    "verdict": "verified-complete",
    "decided_by": "check",
    "test_result": "Result: pass=12 fail=0 skip=0",
    "commit": "04569546",
    "stop_reason": "completed",
}
GOAL_KEYS = {"cost_usd", "progress_lines"}


def line(**extra) -> str:
    return json.dumps({**BASE, **extra})


def record(**overrides) -> ledger.IterationRecord:
    base = {k: v for k, v in BASE.items() if k not in ("v", "recorded_at")}
    return ledger.IterationRecord(**{**base, "request": REQUEST_ID, **overrides})


def rendered_keys(item: ledger.IterationRecord) -> list[str]:
    return list(json.loads(ledger.render_record_line(item)))


@pytest.fixture
def fixed_clock(monkeypatch):
    monkeypatch.setattr(ledger, "_utc_minute", lambda: STAMP)


def test_cost_round_trips_through_the_line():
    item = record(cost_usd=0.4375, recorded_at=STAMP)

    assert ledger.parse_record_line(ledger.render_record_line(item)).cost_usd == 0.4375


def test_progress_lines_round_trip_through_the_line():
    item = record(progress_lines=14, recorded_at=STAMP)

    assert ledger.parse_record_line(ledger.render_record_line(item)).progress_lines == 14


def test_both_keys_round_trip_together():
    item = record(cost_usd=1.5, progress_lines=0, recorded_at=STAMP)
    back = ledger.parse_record_line(ledger.render_record_line(item))

    assert (back.cost_usd, back.progress_lines) == (1.5, 0)


def test_a_whole_number_cost_reads_as_a_float():
    item = ledger.parse_record_line(line(request=REQUEST_ID, cost_usd=2))

    assert repr(item.cost_usd) == "2.0"


@pytest.mark.parametrize("request_id", [REQUEST_ID, None])
def test_absent_goal_keys_render_nothing(request_id):
    item = record(request=request_id, recorded_at=STAMP)

    assert not GOAL_KEYS & set(rendered_keys(item))


def test_a_record_without_the_keys_renders_the_base_line_byte_for_byte():
    item = ledger.parse_record_line(line())

    assert ledger.render_record_line(item) == line()


def test_a_driver_record_without_the_keys_renders_its_four_keys_only():
    item = record(step_digest="9ac894ba53b8", turns=31, max_turns=100, recorded_at=STAMP)

    assert rendered_keys(item) == [*BASE, "request", "step_digest", "turns", "max_turns"]


def test_the_goal_keys_follow_the_existing_keys():
    item = record(turns=3, max_turns=9, cost_usd=0.5, progress_lines=2, recorded_at=STAMP)

    assert rendered_keys(item)[-3:] == ["max_turns", "cost_usd", "progress_lines"]


@pytest.mark.parametrize("bad", [-0.01, -1, "1.5", True, [1], float("nan"), float("inf")])
def test_a_wrong_cost_is_a_rejected_line(bad):
    text = json.dumps({**BASE, "request": REQUEST_ID, "cost_usd": bad})

    with pytest.raises(ledger.ShapeError, match="cost_usd"):
        ledger.parse_record_line(text)


@pytest.mark.parametrize("bad", [-1, 2.5, "3", True])
def test_a_wrong_progress_count_is_a_rejected_line(bad):
    with pytest.raises(ledger.ShapeError, match="progress_lines"):
        ledger.parse_record_line(line(request=REQUEST_ID, progress_lines=bad))


@pytest.mark.parametrize("extra", [{"cost_usd": 0.1}, {"progress_lines": 3}])
def test_a_goal_key_without_a_request_is_rejected(extra):
    with pytest.raises(ledger.ShapeError, match="need a request"):
        ledger.parse_record_line(line(**extra))


def test_an_unknown_extra_key_stays_ignored():
    item = ledger.parse_record_line(line(request=REQUEST_ID, cost_usd=0.2, wall_clock="soon"))

    assert item.cost_usd == 0.2


def test_read_json_shows_the_goal_keys_on_a_record_that_has_them(tmp_path, fixed_clock, capsys):
    task_dir = tmp_path / ".ai-work" / "demo"
    task_dir.mkdir(parents=True)
    ledger.append_record(task_dir, record(cost_usd=0.75, progress_lines=6))
    ledger.append_record(task_dir, record(attempt=2))

    code = ledger.main(["read", "demo", "--json", "--repo-root", str(tmp_path)])
    with_keys, without_keys = json.loads(capsys.readouterr().out)["records"]

    assert code == ledger.EXIT_CLEAN
    assert (with_keys["cost_usd"], with_keys["progress_lines"]) == (0.75, 6)
    assert not GOAL_KEYS & set(without_keys)
