"""Where a hook event is recorded, whatever directory the session works from.

A session may work from any subdirectory of a checkout. Its events still belong
to the project whose root holds `.ai-state/`: they land in that project's log,
look exactly like rows recorded from the root, and a nested project keeps its
own log. A directory that has not adopted the log records nothing anywhere.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.acceptance.drivers.observation_harness import (
    STATE_DIR,
    HookHarness,
    Session,
    log_rows,
    logs_under,
    new_checkout,
    subdirectory,
    summary_rows,
)

SESSION_ID = "5e551011-0000-4000-8000-00000000a001"

# Fields that record *when* something happened; rows recorded from different
# directories may differ in these and in nothing else.
_TIME_FIELDS = ("timestamp", "duration_ms")


def _untimed(rows: list[dict]) -> list[dict]:
    return [
        {k: v for k, v in row.items() if k not in _TIME_FIELDS and not k.endswith("_at")}
        for row in rows
    ]


def _agent_starts(rows: list[dict]) -> list[str]:
    return [row["agent_id"] for row in rows if row["event_type"] == "agent_start"]


def _work_a_session(session: Session) -> None:
    """A representative stretch of activity: spawns, tool use, a resume, a stop."""
    session.session_start()
    session.spawn_foreground("Task slug: parser-split\n\nDesign the parser.", "agent-one")
    session.plain_tool_use()
    session.plain_tool_use(inside=("agent-one", "praxion:implementer"))
    session.spawn_background(
        "Review the parser.", "agent-two", "praxion:verifier", result_first=True
    )
    session.resume("agent-one")
    session.stop()


# -- Events from a subdirectory reach the checkout's log ------------------------


@pytest.mark.parametrize("mode", ["standard", "full"])
@pytest.mark.parametrize("below_root", ["src", "src/pkg/module/deep"])
def test_events_from_a_subdirectory_are_recorded_exactly_as_from_the_root(
    tmp_path: Path, mode: str, below_root: str
) -> None:
    at_root = new_checkout(tmp_path / "delivered-at-root" / "proj")
    below = new_checkout(tmp_path / "delivered-below" / "proj")
    _work_a_session(Session(HookHarness(tmp_path / "harness-root", mode), SESSION_ID, at_root))
    _work_a_session(
        Session(
            HookHarness(tmp_path / "harness-below", mode),
            SESSION_ID,
            subdirectory(below, below_root),
        )
    )

    expected = _untimed(log_rows(at_root / STATE_DIR))
    recorded = _untimed(log_rows(below / STATE_DIR))

    assert expected, "the delivery from the root recorded nothing; the comparison is empty"
    assert recorded == expected


def test_a_stop_from_a_subdirectory_updates_the_roots_summary_under_the_checkout_name(
    tmp_path: Path,
) -> None:
    root = new_checkout(tmp_path / "proj")
    session = Session(HookHarness(tmp_path / "harness"), SESSION_ID, subdirectory(root, "docs"))
    session.session_start()
    session.spawn_foreground("Write the guide.", "agent-one")

    session.stop()

    this_session = [r for r in summary_rows(root / STATE_DIR) if r["session_id"] == SESSION_ID]
    assert {row["pipeline_slug"] for row in this_session} == {"proj"}, this_session


def test_rows_from_a_subdirectory_land_through_a_linked_state_directory(tmp_path: Path) -> None:
    root = new_checkout(tmp_path / "proj", recording=False)
    linked_target = tmp_path / "shared-store" / "state"
    linked_target.mkdir(parents=True)
    (root / STATE_DIR).symlink_to(linked_target, target_is_directory=True)
    session = Session(HookHarness(tmp_path / "harness"), SESSION_ID, subdirectory(root, "src"))

    session.spawn_foreground("Implement the parser.", "agent-one")

    rows = log_rows(linked_target)
    assert _agent_starts(rows) == ["agent-one"], rows
    assert {row["project"] for row in rows} == {"proj"}


@pytest.mark.parametrize("where", [".", "src/deep"])
def test_the_off_mode_records_nothing_from_the_root_or_below_it(tmp_path: Path, where: str) -> None:
    root = new_checkout(tmp_path / "proj")
    session = Session(
        HookHarness(tmp_path / "harness", "off"), SESSION_ID, subdirectory(root, where)
    )

    _work_a_session(session)

    assert logs_under(tmp_path) == []


# -- The nearest project wins --------------------------------------------------


@pytest.mark.parametrize("below_nested", [".", "cases/deep"])
def test_a_nested_project_keeps_its_rows_to_itself(tmp_path: Path, below_nested: str) -> None:
    outer = new_checkout(tmp_path / "outer")
    nested = subdirectory(outer, "tests/fixtures/inner")
    (nested / STATE_DIR).mkdir()
    session = Session(
        HookHarness(tmp_path / "harness"), SESSION_ID, subdirectory(nested, below_nested)
    )

    session.spawn_foreground("Implement the parser.", "agent-one")
    session.plain_tool_use()
    session.stop()

    nested_rows = log_rows(nested / STATE_DIR)
    assert _agent_starts(nested_rows) == ["agent-one"], nested_rows
    assert {row["project"] for row in nested_rows} == {"inner"}
    assert log_rows(outer / STATE_DIR) == [], "the enclosing project's log gained rows"


# -- Nothing is recorded where no project is found ----------------------------


def test_a_checkout_without_a_state_directory_records_nothing(tmp_path: Path) -> None:
    root = new_checkout(tmp_path / "proj", recording=False)
    session = Session(HookHarness(tmp_path / "harness"), SESSION_ID, subdirectory(root, "src"))

    _work_a_session(session)

    assert logs_under(tmp_path) == []


def test_a_repository_cloned_inside_a_recording_one_records_nothing(tmp_path: Path) -> None:
    outer = new_checkout(tmp_path / "outer")
    clone = new_checkout(outer / "vendor" / "library", recording=False)
    session = Session(HookHarness(tmp_path / "harness"), SESSION_ID, subdirectory(clone, "src"))

    _work_a_session(session)

    assert logs_under(tmp_path) == []


def test_a_directory_outside_any_checkout_records_nothing_without_its_own_state_directory(
    tmp_path: Path,
) -> None:
    plain = tmp_path / "plain"
    (plain / STATE_DIR).mkdir(parents=True)
    session = Session(HookHarness(tmp_path / "harness"), SESSION_ID, subdirectory(plain, "notes"))

    _work_a_session(session)

    assert logs_under(tmp_path) == []
