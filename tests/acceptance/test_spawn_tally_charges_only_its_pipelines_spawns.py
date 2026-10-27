"""A pipeline's spawn tally charges only that pipeline's own spawns.

A spawn whose prompt states the pipeline's slug is charged to it from any checkout and
any kind of session. A slug-less spawn made by a person's interactive session is charged
to the checkout it ran in, as today; a slug-less spawn a headless session made (a
measurement or probe session run inside the pipeline's worktree) is charged to no slug,
is not pending as unattributed, and is listed apart with the reason. A slug-less spawn
recorded in another checkout is never charged to the pipeline, even when that checkout's
directory bears the slug's name. An agent no rule can attribute still keeps the verdict
from reading `within`, a session whose kind is unknown keeps today's attribution, and a
log written before sessions carried their kind tallies exactly as today.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from tests.acceptance.drivers import session_kind
from tests.acceptance.drivers.observation_harness import Session, write_log_lines
from tests.acceptance.drivers.repository import add_worktree, git, new_repository
from tests.acceptance.drivers.spawn_tally import SPAWN_COUNT, Tally, spawn_count

SLUG = "split-pipeline"
STATED = f"Task slug: {SLUG}\n\nDo the next step."
SLUGLESS = "Measure how long the startup takes."
SESSION_ID = "5e551011-0000-4000-8000-0000000c0001"
FROZEN = Path(__file__).resolve().parent / "fixtures" / "spawn_tally_old_log_before.json"

SessionFactory = Callable[[Path, str, Path], Session]
KINDS: dict[str, SessionFactory] = {
    "headless": session_kind.headless_session,
    "interactive": session_kind.interactive_session,
    "unknown": session_kind.unknown_kind_session,
}


@pytest.fixture
def checkouts(tmp_path: Path) -> dict[str, Path]:
    """The pipeline's worktree (named after the slug) and another checkout of the same name."""
    main = new_repository(tmp_path / "main-repo")
    pipeline = add_worktree(main, SLUG)
    other = tmp_path / "elsewhere" / SLUG
    other.parent.mkdir(parents=True)
    git(main, "worktree", "add", "-q", "-b", "other-checkout", str(other))
    return {"main": main, "pipeline": pipeline, "other": other}


def _session(tmp_path: Path, kind: str, cwd: Path) -> Session:
    return KINDS[kind](tmp_path / f"harness-{kind}", SESSION_ID, cwd)


def _tally(tmp_path: Path, checkouts: dict[str, Path], budget: int = 99) -> Tally:
    return spawn_count(checkouts["pipeline"], SLUG, scratch=tmp_path / "tally", budget=budget)


# -- A headless session's slug-less spawn is left out ------------------------------------------


def test_a_headless_slugless_spawn_in_the_pipelines_checkout_is_not_charged(
    tmp_path: Path, checkouts: dict[str, Path]
) -> None:
    pipeline = checkouts["pipeline"]
    _session(tmp_path, "unknown", pipeline).spawn_foreground(STATED, "a-pipeline-step")
    _session(tmp_path, "headless", pipeline).spawn_foreground(SLUGLESS, "a-headless-probe")

    tally = _tally(tmp_path, checkouts, budget=1)

    assert tally.agent_ids() == ["a-pipeline-step"], tally.describe()
    assert tally.charged == 1, tally.describe()
    assert tally.verdict == "within", tally.describe()


def test_a_headless_slugless_spawn_is_not_pending_as_unattributed(
    tmp_path: Path, checkouts: dict[str, Path]
) -> None:
    _session(tmp_path, "headless", checkouts["pipeline"]).spawn_foreground(
        SLUGLESS, "a-headless-probe"
    )
    _session(tmp_path, "unknown", checkouts["pipeline"]).spawn_foreground(STATED, "a-step")

    tally = _tally(tmp_path, checkouts)

    unattributed = [agent["agent_id"] for agent in tally.report["unattributed"]]
    assert "a-headless-probe" not in unattributed, tally.describe()


def test_a_headless_slugless_spawn_is_listed_apart_with_the_reason_it_was_left_out(
    tmp_path: Path, checkouts: dict[str, Path]
) -> None:
    _session(tmp_path, "headless", checkouts["pipeline"]).spawn_foreground(
        SLUGLESS, "a-headless-probe"
    )
    _session(tmp_path, "unknown", checkouts["pipeline"]).spawn_foreground(STATED, "a-step")

    tally = _tally(tmp_path, checkouts)

    reasons = session_kind.left_out(tally.report)
    assert reasons.get("a-headless-probe", "").strip(), tally.describe()


@pytest.mark.parametrize("kind", ["interactive", "unknown"])
def test_a_slugless_spawn_a_person_made_in_the_pipelines_checkout_is_charged_as_today(
    tmp_path: Path, checkouts: dict[str, Path], kind: str
) -> None:
    _session(tmp_path, kind, checkouts["pipeline"]).spawn_foreground(SLUGLESS, "a-adhoc")

    tally = _tally(tmp_path, checkouts)

    assert tally.agent_ids() == ["a-adhoc"], tally.describe()


# -- A spawn stating the slug is charged wherever it was made -----------------------------------


@pytest.mark.parametrize("kind", ["headless", "interactive", "unknown"])
@pytest.mark.parametrize("where", ["pipeline", "main", "other"])
def test_a_spawn_stating_the_slug_is_charged_from_any_checkout_and_session_kind(
    tmp_path: Path, checkouts: dict[str, Path], kind: str, where: str
) -> None:
    _session(tmp_path, kind, checkouts[where]).spawn_foreground(STATED, "a-stated")

    tally = _tally(tmp_path, checkouts)

    assert tally.agent_ids() == ["a-stated"], tally.describe()


@pytest.mark.parametrize("kind", ["headless", "interactive", "unknown"])
def test_a_slugless_spawn_in_another_checkout_bearing_the_slugs_name_is_never_charged(
    tmp_path: Path, checkouts: dict[str, Path], kind: str
) -> None:
    _session(tmp_path, kind, checkouts["other"]).spawn_foreground(SLUGLESS, "a-elsewhere")
    _session(tmp_path, "unknown", checkouts["pipeline"]).spawn_foreground(STATED, "a-step")

    tally = _tally(tmp_path, checkouts)

    assert "a-elsewhere" not in tally.agent_ids(), tally.describe()


# -- An unattributable spawn still withholds the verdict ---------------------------------------


@pytest.mark.parametrize("kind", ["headless", "unknown"])
def test_an_agent_no_rule_can_attribute_keeps_the_verdict_from_reading_within(
    tmp_path: Path, checkouts: dict[str, Path], kind: str
) -> None:
    pipeline = checkouts["pipeline"]
    _session(tmp_path, "unknown", pipeline).spawn_foreground(STATED, "a-step")
    _session(tmp_path, kind, pipeline).subagent_start("a-unattributable", "praxion:verifier")

    tally = _tally(tmp_path, checkouts, budget=1)

    assert tally.verdict == "indeterminate", tally.describe()


def test_an_unattributable_agent_beside_a_count_already_over_budget_reads_over(
    tmp_path: Path, checkouts: dict[str, Path]
) -> None:
    pipeline = checkouts["pipeline"]
    session = _session(tmp_path, "unknown", pipeline)
    session.spawn_foreground(STATED, "a-step-1")
    session.spawn_foreground(STATED, "a-step-2")
    session.subagent_start("a-unattributable", "praxion:verifier")

    tally = _tally(tmp_path, checkouts, budget=1)

    assert tally.verdict == "over", tally.describe()


# -- A log written before sessions carried their kind tallies as today ----------------------------

T0 = "2026-10-20T09:00:0{}.000000+00:00"
OLD_ROWS = [
    {"timestamp": T0.format(1), "session_id": SESSION_ID, "agent_type": "praxion:implementer",
     "agent_id": "a-stated", "project": SLUG, "event_type": "agent_start", "tool_name": None,
     "summary": "Agent started: praxion:implementer", "file_paths": [], "outcome": None,
     "classification": None, "agent_type_source": "payload",
     "start_correlation": "not-applicable", "slug_attribution": "spawn-prompt",
     "log_mode": "standard"},
    {"timestamp": T0.format(2), "session_id": SESSION_ID, "agent_type": "main",
     "agent_id": SESSION_ID, "project": SLUG, "event_type": "tool_use", "tool_name": "Agent",
     "summary": "Spawn praxion:implementer", "file_paths": [], "outcome": "success",
     "classification": "delegation", "spawned_agent_id": "a-stated",
     "spawned_agent_type": "praxion:implementer", "task_slug": SLUG, "log_mode": "standard"},
    {"timestamp": T0.format(3), "session_id": SESSION_ID, "agent_type": "praxion:researcher",
     "agent_id": "a-slugless", "project": SLUG, "event_type": "agent_start", "tool_name": None,
     "summary": "Agent started: praxion:researcher", "file_paths": [], "outcome": None,
     "classification": None, "agent_type_source": "payload",
     "start_correlation": "not-applicable", "slug_attribution": "spawn-prompt",
     "log_mode": "standard"},
    {"timestamp": T0.format(4), "session_id": SESSION_ID, "agent_type": "main",
     "agent_id": SESSION_ID, "project": SLUG, "event_type": "tool_use", "tool_name": "Agent",
     "summary": "Spawn praxion:researcher", "file_paths": [], "outcome": "success",
     "classification": "delegation", "spawned_agent_id": "a-slugless",
     "spawned_agent_type": "praxion:researcher", "task_slug": None, "log_mode": "standard"},
    {"timestamp": T0.format(5), "session_id": SESSION_ID, "agent_type": "praxion:verifier",
     "agent_id": "a-orphan", "project": SLUG, "event_type": "agent_start", "tool_name": None,
     "summary": "Agent started: praxion:verifier", "file_paths": [], "outcome": None,
     "classification": None, "agent_type_source": "payload",
     "start_correlation": "not-applicable", "slug_attribution": "spawn-prompt",
     "log_mode": "standard"},
]  # fmt: skip


def old_log_output(workspace: Path) -> str:
    """The tally's `--json` stdout over the old rows, with the scratch location replaced."""
    main = new_repository(workspace / "main-repo")
    pipeline = add_worktree(main, SLUG)
    write_log_lines(pipeline / ".ai-state", [json.dumps(row) for row in OLD_ROWS])
    tally = spawn_count(pipeline, SLUG, scratch=workspace / "tally", budget=3)
    assert tally.report is not None, tally.describe()
    text = json.dumps(tally.report, indent=1, sort_keys=True)
    return text.replace(str(workspace.resolve()), "<ROOT>")


def test_a_log_whose_rows_carry_no_session_kind_tallies_exactly_as_today(tmp_path: Path) -> None:
    output = old_log_output(tmp_path)

    expected = json.loads(FROZEN.read_text(encoding="utf-8"))["output"]
    assert output == expected, f"{SPAWN_COUNT.name} reads an old log differently:\n{output}"
