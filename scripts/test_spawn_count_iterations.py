"""The spawn counter reports the loop's agents as iterations, apart from charged spawns.

An attributed agent that the task's iteration ledger records under a request id is listed
among the `iterations` and charges neither the budget nor the verdict. Every other agent is
charged as before, and a task with no such agent reports exactly what it always did.
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest
from iteration_ledger import IterationRecord, render_record_line

_SCRIPT = Path(__file__).resolve().parent / "spawn_count.py"
_SLUG = "loop-task"
_STAMP = "2026-10-08T10:00Z"
_FIRST_MINUTE = 10
_IMPLEMENTER = "praxion:implementer"
_PLANNER = "praxion:implementation-planner"
_STEP_LABEL = "Step "
EXIT_COUNTED, EXIT_OVER = 0, 1


def _wal_row(agent_id: str, agent_type: str, minute: int) -> dict:
    """A spawn written before attribution existed, which counts toward its project."""
    return {
        "timestamp": f"2026-10-08T10:{minute:02d}:00+00:00",
        "session_id": "sess-loop",
        "agent_type": agent_type,
        "agent_id": agent_id,
        "project": _SLUG,
        "event_type": "agent_start",
    }


def _loop_record(agent_id: str, request: str, step: str = "1") -> IterationRecord:
    return IterationRecord(
        step=f"{_STEP_LABEL}{step}",
        attempt=1,
        agent_id=agent_id,
        verdict="verified-complete",
        decided_by="check",
        test_result="Result: pass=1 fail=0 skip=0",
        commit="04569546",
        stop_reason="completed",
        recorded_at=_STAMP,
        request=request,
    )


def _hand_record(agent_id: str) -> IterationRecord:
    """A record appended by hand: the same shape with no request id."""
    return replace(_loop_record(agent_id, "unused"), request=None)


def _task(root: Path, agents: list[tuple[str, str]], ledger_lines: list[str]) -> Path:
    """A git checkout whose log holds one spawn per (agent id, type) and whose task holds
    the given ledger lines (none: no ledger file at all)."""
    root.mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=root, check=True, timeout=30)
    state = root / ".ai-state"
    state.mkdir()
    rows = [_wal_row(i, t, _FIRST_MINUTE + n) for n, (i, t) in enumerate(agents)]
    (state / "observations.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )
    if ledger_lines:
        task_dir = root / ".ai-work" / _SLUG
        task_dir.mkdir(parents=True)
        (task_dir / "ITERATION_LEDGER.jsonl").write_text(
            "\n".join(ledger_lines) + "\n", encoding="utf-8"
        )
    return root


def _count(root: Path, *flags: str, budget: int = 5) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(_SCRIPT),
            "--slug",
            _SLUG,
            "--repo-root",
            str(root),
            "--budget",
            str(budget),
            "--no-context",
            *flags,
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )


def _report(root: Path, budget: int = 5) -> dict:
    result = _count(root, "--json", budget=budget)
    assert result.returncode in (EXIT_COUNTED, EXIT_OVER), result.stderr  # 2 is a withheld count
    return json.loads(result.stdout)


def _iteration_ids(report: dict) -> list[str]:
    return [item["agent_id"] for item in report.get("iterations", [])]


_PLANNED = [("agent-planner", _PLANNER), ("agent-driven", _IMPLEMENTER)]


def test_a_recorded_loop_agent_is_an_iteration_and_charges_nothing(tmp_path: Path) -> None:
    ledger = [render_record_line(_loop_record("agent-driven", "rq-1"))]
    report = _report(_task(tmp_path / "repo", _PLANNED, ledger), budget=1)

    assert report["iterations"] == [
        {
            "agent_id": "agent-driven",
            "agent_type": _IMPLEMENTER,
            "spawned_at": "2026-10-08T10:11:00+00:00",
            "request": "rq-1",
        }
    ]
    assert (report["spawns"], report["charged"], report["verdict"]) == (2, 1, "within")
    assert sorted(a["agent_id"] for a in report["agents"]) == ["agent-driven", "agent-planner"]
    assert report["by_agent_type"] == {_PLANNER: 1, _IMPLEMENTER: 1}


def test_an_agent_the_ledger_has_not_recorded_yet_stays_charged(tmp_path: Path) -> None:
    agents = [*_PLANNED, ("agent-pending", _IMPLEMENTER)]
    ledger = [render_record_line(_loop_record("agent-driven", "rq-1"))]
    report = _report(_task(tmp_path / "repo", agents, ledger), budget=2)

    assert _iteration_ids(report) == ["agent-driven"]
    assert (report["spawns"], report["charged"], report["verdict"]) == (3, 2, "within")


def test_a_task_without_a_ledger_reports_what_it_always_did(tmp_path: Path) -> None:
    root = _task(tmp_path / "repo", _PLANNED, [])

    report = _report(root, budget=1)
    human = _count(root, budget=1).stdout

    assert "iterations" not in report
    assert (report["spawns"], report["charged"], report["verdict"]) == (2, 2, "over")
    assert "iterations" not in human


def test_a_ledger_without_request_ids_charges_every_spawn_as_before(tmp_path: Path) -> None:
    ledger = [render_record_line(_hand_record("agent-driven"))]
    root = _task(tmp_path / "repo", _PLANNED, ledger)

    report = _report(root, budget=1)

    assert "iterations" not in report
    assert (report["spawns"], report["charged"]) == (2, 2)
    assert "iterations" not in _count(root, budget=1).stdout


@pytest.mark.parametrize(
    "rejected",
    [
        pytest.param("{not json", id="not-json"),
        pytest.param(
            json.dumps(
                {**json.loads(render_record_line(_loop_record("agent-late", "rq-2"))), "v": 2}
            ),
            id="foreign-version",
        ),
        pytest.param(
            json.dumps(
                {
                    **json.loads(render_record_line(_loop_record("agent-late", "rq-2"))),
                    "stop_reason": "walked-away",
                }
            ),
            id="unknown-stop-reason",
        ),
    ],
)
def test_a_line_the_ledger_reader_rejects_is_ignored_and_its_agent_stays_charged(
    tmp_path: Path, rejected: str
) -> None:
    agents = [*_PLANNED, ("agent-late", _IMPLEMENTER)]
    ledger = [render_record_line(_loop_record("agent-driven", "rq-1")), rejected]

    report = _report(_task(tmp_path / "repo", agents, ledger), budget=5)

    assert _iteration_ids(report) == ["agent-driven"]
    assert (report["spawns"], report["charged"]) == (3, 2)


def test_the_human_report_names_the_iterations_only_when_there_are_some(tmp_path: Path) -> None:
    ledger = [render_record_line(_loop_record("agent-driven", "rq-1"))]

    looped = _count(_task(tmp_path / "looped", _PLANNED, ledger)).stdout
    plain = _count(_task(tmp_path / "plain", _PLANNED, [])).stdout

    assert "  spawns=2 charged=1 budget=5" in looped
    assert "  iterations=1" in looped.splitlines()
    assert "iterations" not in plain


def test_a_ledger_record_for_an_agent_the_log_does_not_name_lists_nothing(tmp_path: Path) -> None:
    ledger = [render_record_line(_loop_record("agent-elsewhere", "rq-9"))]

    report = _report(_task(tmp_path / "repo", _PLANNED, ledger), budget=5)

    assert "iterations" not in report
    assert (report["spawns"], report["charged"]) == (2, 2)


def test_a_heavy_resume_of_a_loop_agent_is_still_charged() -> None:
    import spawn_count

    loop_agent = spawn_count.AgentTally(
        agent_id="agent-driven",
        agent_type=_IMPLEMENTER,
        spawned_at="",
        resumes=(spawn_count.Resume(at="", context_tokens=300_000),),
        owner=_SLUG,
    )
    other = spawn_count.AgentTally("agent-planner", _PLANNER, "", (), owner=_SLUG)

    result = spawn_count.verdict(
        (other, loop_agent), budget=3, threshold=250_000, iterations=frozenset({"agent-driven"})
    )

    assert (result.spawns, result.resumes_heavy, result.charged) == (2, 1, 2)


def test_the_ledger_requests_map_each_recorded_agent_to_its_request(tmp_path: Path) -> None:
    import spawn_count

    root = _task(
        tmp_path / "repo",
        _PLANNED,
        [
            render_record_line(_loop_record("agent-driven", "rq-1")),
            render_record_line(_hand_record("agent-by-hand")),
        ],
    )

    assert spawn_count._ledger_requests(root, _SLUG) == {"agent-driven": "rq-1"}
    assert spawn_count._ledger_requests(root, "no-such-task") == {}
