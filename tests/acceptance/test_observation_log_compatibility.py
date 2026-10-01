"""Rows already in the log keep their meaning.

History recorded before slug attribution counts toward each row's `project`,
exactly as before; a log mixing old and new rows needs no migration; and the
fields readers rely on keep their names and meaning on new rows, with
`project` still naming the checkout.

The prior rows below have the shape the hooks wrote before this change (the
spawn/resume pair is a real recorded pair). The expected reports are the
tally's own output over this log at the commit where this change began: the
requirement is "the same JSON and exit status as before", so the snapshot is
the oracle.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.acceptance.drivers.observation_harness import (
    STATE_DIR,
    HookHarness,
    Session,
    log_rows,
    new_checkout,
    subdirectory,
    write_log_lines,
)
from tests.acceptance.drivers.spawn_tally import spawn_count

# -- Rows in the shape written before this change ------------------------------

_PRIOR_SPAWN = (
    '{"timestamp": "2026-08-30T23:31:50.032601+00:00", "session_id": '
    '"2bf94c0a-4d02-4788-b750-a4ab0e4076d2", "agent_type": "praxion:systems-architect", '
    '"agent_id": "a65ec99bc016c1ca0", "project": "praxion", "event_type": "agent_start", '
    '"tool_name": null, "summary": "Agent started: praxion:systems-architect", '
    '"file_paths": [], "outcome": null, "classification": null, '
    '"agent_type_source": "payload", "start_correlation": "not-applicable"}'
)
_PRIOR_STOP = (
    '{"timestamp": "2026-08-30T23:43:32.824576+00:00", "session_id": '
    '"2bf94c0a-4d02-4788-b750-a4ab0e4076d2", "agent_type": "praxion:systems-architect", '
    '"agent_id": "a65ec99bc016c1ca0", "project": "praxion", "event_type": "agent_stop", '
    '"tool_name": null, "summary": "Agent completed: praxion:systems-architect", '
    '"file_paths": [], "outcome": null, "classification": null, '
    '"agent_type_source": "payload", "start_correlation": "paired"}'
)
_PRIOR_SENDMESSAGE = (
    '{"timestamp": "2026-08-30T23:45:41.543557+00:00", "session_id": '
    '"2bf94c0a-4d02-4788-b750-a4ab0e4076d2", "agent_type": "main", "agent_id": '
    '"2bf94c0a-4d02-4788-b750-a4ab0e4076d2", "project": "praxion", "event_type": '
    '"tool_use", "tool_name": "SendMessage", "summary": "SendMessage", "file_paths": [], '
    '"outcome": "success", "classification": "tool_use", "trace_id": "", "span_id": "", '
    '"parent_span_id": ""}'
)
_PRIOR_RESUME = (
    '{"timestamp": "2026-08-30T23:45:41.543661+00:00", "session_id": '
    '"2bf94c0a-4d02-4788-b750-a4ab0e4076d2", "agent_type": "praxion:systems-architect", '
    '"agent_id": "a65ec99bc016c1ca0", "project": "praxion", "event_type": "agent_start", '
    '"tool_name": null, "summary": "Agent started: praxion:systems-architect", '
    '"file_paths": [], "outcome": null, "classification": null, '
    '"agent_type_source": "payload", "start_correlation": "not-applicable"}'
)
_PRIOR_OTHER_PROJECT_SPAWN = (
    '{"timestamp": "2026-08-13T07:04:24.695942+00:00", "session_id": '
    '"84edfc44-9ae8-45aa-86c2-bdbcff41aaf9", "agent_type": "praxion:context-engineer", '
    '"agent_id": "adeee2949176052ca", "project": "deep-fix-round", "event_type": '
    '"agent_start", "tool_name": null, "summary": "Agent started: praxion:context-engineer", '
    '"file_paths": [], "outcome": null, "classification": null}'
)

# The fields a prior agent row carries; a new agent row keeps every one of them.
_PRIOR_AGENT_ROW_FIELDS = {
    "timestamp",
    "session_id",
    "agent_type",
    "agent_id",
    "project",
    "event_type",
    "tool_name",
    "summary",
    "file_paths",
    "outcome",
    "classification",
    "agent_type_source",
    "start_correlation",
}

_SOURCES = [".ai-state/observations.jsonl.1", ".ai-state/observations.jsonl"]


def _praxion_report(budget: int | None, verdict: str) -> dict:
    return {
        "slug": "praxion",
        "sources": _SOURCES,
        "rows_skipped": 0,
        "spawns": 1,
        "resumes": {"light": 0, "heavy": 0, "unsized": 1},
        "charged": 1,
        "budget": budget,
        "verdict": verdict,
        "by_agent_type": {"praxion:systems-architect": 1},
        "agents": [
            {
                "agent_id": "a65ec99bc016c1ca0",
                "agent_type": "praxion:systems-architect",
                "spawned_at": "2026-08-30T23:31:50.032601+00:00",
                "resumes": [
                    {
                        "at": "2026-08-30T23:45:41.543661+00:00",
                        "context_tokens": None,
                        "class": "unsized",
                    }
                ],
            }
        ],
    }


def _deep_fix_round_report(budget: int | None, verdict: str) -> dict:
    return {
        "slug": "deep-fix-round",
        "sources": _SOURCES,
        "rows_skipped": 0,
        "spawns": 1,
        "resumes": {"light": 0, "heavy": 0, "unsized": 0},
        "charged": 1,
        "budget": budget,
        "verdict": verdict,
        "by_agent_type": {"praxion:context-engineer": 1},
        "agents": [
            {
                "agent_id": "adeee2949176052ca",
                "agent_type": "praxion:context-engineer",
                "spawned_at": "2026-08-13T07:04:24.695942+00:00",
                "resumes": [],
            }
        ],
    }


def _log_of_prior_rows_only(tmp_path: Path) -> Path:
    """Prior rows split across the archive and the active log, in recorded order."""
    root = new_checkout(tmp_path / "praxion")
    write_log_lines(
        root / STATE_DIR,
        [_PRIOR_SENDMESSAGE, _PRIOR_RESUME, _PRIOR_OTHER_PROJECT_SPAWN],
        archive=[_PRIOR_SPAWN, _PRIOR_STOP],
    )
    return root


@pytest.mark.parametrize(
    ("slug", "budget", "exit_code", "report"),
    [
        ("praxion", None, 0, _praxion_report(None, "no-budget")),
        ("praxion", 0, 1, _praxion_report(0, "over")),
        ("praxion", 1, 0, _praxion_report(1, "indeterminate")),
        ("praxion", 2, 0, _praxion_report(2, "within")),
        ("deep-fix-round", None, 0, _deep_fix_round_report(None, "no-budget")),
        ("deep-fix-round", 1, 0, _deep_fix_round_report(1, "within")),
        ("never-recorded", 3, 2, None),
    ],
    ids=[
        "praxion-no-budget",
        "praxion-over",
        "praxion-indeterminate",
        "praxion-within",
        "other-project-no-budget",
        "other-project-within",
        "unseen-slug-withheld",
    ],
)
def test_a_log_of_prior_rows_reports_exactly_as_before(
    tmp_path: Path, slug: str, budget: int | None, exit_code: int, report: dict | None
) -> None:
    root = _log_of_prior_rows_only(tmp_path)

    tally = spawn_count(root, slug, scratch=tmp_path / "tally", budget=budget)

    assert (tally.exit_code, tally.report) == (exit_code, report), tally.describe()


# -- Prior and new rows side by side -------------------------------------------

CHECKOUT = "parent-repo"
SESSION_ID = "5e551011-0000-4000-8000-00000000c003"


def _prior_spawn_in(project: str, agent_id: str) -> list[str]:
    """A prior spawn and its resume, recorded under `project`."""
    return [
        line.replace('"project": "praxion"', f'"project": "{project}"').replace(
            "a65ec99bc016c1ca0", agent_id
        )
        for line in (_PRIOR_SPAWN, _PRIOR_STOP, _PRIOR_RESUME)
    ]


def _mixed_log(tmp_path: Path) -> Path:
    root = new_checkout(tmp_path / CHECKOUT)
    write_log_lines(root / STATE_DIR, [], archive=_prior_spawn_in(CHECKOUT, "agent-from-before"))
    session = Session(HookHarness(tmp_path / "harness"), SESSION_ID, root)
    session.spawn_foreground("Task slug: split-pipeline\n\nDesign the parser.", "agent-split")
    session.spawn_foreground("Look around the repository.", "agent-adhoc")
    return root


def test_prior_rows_keep_counting_toward_their_project_beside_new_rows(tmp_path: Path) -> None:
    root = _mixed_log(tmp_path)

    parent = spawn_count(root, CHECKOUT, scratch=tmp_path / "tally")

    assert (parent.spawns, parent.resumes, parent.agent_ids()) == (
        2,
        1,
        ["agent-adhoc", "agent-from-before"],
    ), parent.describe()


def test_new_rows_beside_prior_rows_count_toward_their_stated_slug(tmp_path: Path) -> None:
    root = _mixed_log(tmp_path)

    split = spawn_count(root, "split-pipeline", scratch=tmp_path / "tally")

    assert (split.spawns, split.agent_ids()) == (1, ["agent-split"]), split.describe()


# -- New rows keep the fields readers rely on ----------------------------------


def _rows_naming(rows: list[dict], agent_id: str) -> list[dict]:
    return [row for row in rows if row.get("agent_id") == agent_id]


def _agent_rows_of(rows: list[dict], agent_id: str) -> list[dict]:
    """The start and stop rows recorded for the agent itself."""
    return [
        row
        for row in _rows_naming(rows, agent_id)
        if row["event_type"] in ("agent_start", "agent_stop")
    ]


@pytest.mark.parametrize("where", [".", "src/deep"])
def test_new_agent_rows_name_the_checkout_as_project_even_when_a_slug_is_stated(
    tmp_path: Path, where: str
) -> None:
    root = new_checkout(tmp_path / CHECKOUT)
    session = Session(HookHarness(tmp_path / "harness"), SESSION_ID, subdirectory(root, where))

    session.spawn_foreground("Task slug: split-pipeline\n\nDesign the parser.", "agent-split")

    rows = _rows_naming(log_rows(root / STATE_DIR), "agent-split")
    assert rows, "no row names the spawned agent"
    assert {row["project"] for row in rows} == {CHECKOUT}


@pytest.mark.parametrize("where", [".", "src/deep"])
def test_new_agent_rows_keep_every_field_prior_agent_rows_carry(tmp_path: Path, where: str) -> None:
    root = new_checkout(tmp_path / CHECKOUT)
    session = Session(HookHarness(tmp_path / "harness"), SESSION_ID, subdirectory(root, where))

    session.spawn_foreground(
        "Task slug: split-pipeline\n\nDesign the parser.",
        "agent-split",
        "praxion:systems-architect",
    )

    rows = _agent_rows_of(log_rows(root / STATE_DIR), "agent-split")
    assert sorted(row["event_type"] for row in rows) == ["agent_start", "agent_stop"], rows
    assert [sorted(_PRIOR_AGENT_ROW_FIELDS - row.keys()) for row in rows] == [[], []]
    assert {(row["session_id"], row["agent_type"]) for row in rows} == {
        (SESSION_ID, "praxion:systems-architect")
    }
