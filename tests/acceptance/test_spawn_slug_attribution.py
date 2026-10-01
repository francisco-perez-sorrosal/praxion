"""Which pipeline a spawn is charged to, as the spawn tally reports it.

A spawn whose prompt states `Task slug: <slug>` belongs to that pipeline,
whatever the checkout is named; a spawn that states none belongs to the
checkout. A resume is charged where its spawn is. Every distinct agent counts
once, and a spawn the system cannot attribute yet never lets a budget check
pass on a count lower than the real one.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.acceptance.drivers.observation_harness import (
    HookHarness,
    Session,
    new_checkout,
    subdirectory,
)
from tests.acceptance.drivers.spawn_tally import Tally, spawn_count

CHECKOUT = "parent-repo"
SESSION_ID = "5e551011-0000-4000-8000-00000000b002"
IMPLEMENTER = "praxion:implementer"
PLANNER = "praxion:implementation-planner"


def _checkout(tmp_path: Path) -> Path:
    return new_checkout(tmp_path / CHECKOUT)


def _session(tmp_path: Path, cwd: Path, mode: str | None = None) -> Session:
    return Session(HookHarness(tmp_path / "harness", mode), SESSION_ID, cwd)


def _tally(tmp_path: Path, root: Path, slug: str, budget: int | None = None) -> Tally:
    return spawn_count(root, slug, scratch=tmp_path / "tally", budget=budget)


def _launch_two_alike_in_parallel(
    session: Session, launches: list[tuple[str, str]]
) -> list[tuple[str, dict, str]]:
    """Background spawns of one agent type, launched together, results not yet back.

    Each `SubagentStart` carries no prompt and no tool-call id, and the starts
    arrive in the reverse order of the calls, so nothing delivered so far says
    which started agent got which prompt.
    """
    calls = [
        (*session.agent_call(prompt, IMPLEMENTER, background=True), agent_id)
        for prompt, agent_id in launches
    ]
    for _, _, agent_id in reversed(calls):
        session.subagent_start(agent_id, IMPLEMENTER)
    return calls


def _deliver_results(session: Session, calls: list[tuple[str, dict, str]]) -> None:
    for tool_use_id, tool_input, agent_id in calls:
        session.agent_result(tool_use_id, tool_input, agent_id)


# -- A spawn counts toward the slug its prompt states --------------------------


@pytest.mark.parametrize("mode", ["standard", "full"])
def test_a_spawn_counts_toward_the_slug_its_prompt_states(tmp_path: Path, mode: str) -> None:
    root = _checkout(tmp_path)
    session = _session(tmp_path, root, mode)

    session.spawn_foreground("Task slug: split-pipeline\n\nDesign the parser.", "agent-split")

    split = _tally(tmp_path, root, "split-pipeline")
    assert (split.exit_code, split.spawns, split.agent_ids()) == (0, 1, ["agent-split"])


@pytest.mark.parametrize("mode", ["standard", "full"])
def test_a_slugged_spawn_no_longer_counts_toward_the_checkout(tmp_path: Path, mode: str) -> None:
    root = _checkout(tmp_path)
    session = _session(tmp_path, root, mode)
    session.spawn_foreground("Task slug: split-pipeline\n\nDesign the parser.", "agent-split")
    session.spawn_foreground("Look around the repository.", "agent-adhoc")

    parent = _tally(tmp_path, root, CHECKOUT)

    assert (parent.spawns, parent.agent_ids()) == (1, ["agent-adhoc"]), parent.describe()


def test_a_slug_stated_only_in_spawn_prompts_is_not_withheld_as_unseen(tmp_path: Path) -> None:
    root = _checkout(tmp_path)
    session = _session(tmp_path, root)
    session.spawn_foreground("Task slug: fresh-pipeline\n\nDesign the parser.", "agent-fresh")

    fresh = _tally(tmp_path, root, "fresh-pipeline", budget=8)

    assert fresh.exit_code == 0, fresh.describe()
    assert "slug-unseen" not in fresh.stderr


@pytest.mark.parametrize("result_first", [True, False], ids=["result-first", "start-first"])
def test_a_background_spawn_counts_toward_its_slug_whichever_event_arrives_first(
    tmp_path: Path, result_first: bool
) -> None:
    root = _checkout(tmp_path)
    session = _session(tmp_path, root)

    session.spawn_background(
        "Task slug: bg-pipeline\n\nReview the parser.",
        "agent-bg",
        "praxion:verifier",
        result_first=result_first,
    )

    background = _tally(tmp_path, root, "bg-pipeline")
    assert (background.spawns, background.agent_ids()) == (1, ["agent-bg"]), background.describe()


def test_a_spawn_made_from_inside_a_subagent_counts_toward_its_stated_slug(tmp_path: Path) -> None:
    root = _checkout(tmp_path)
    session = _session(tmp_path, root)
    planner_call = session.agent_call("Plan the work.", PLANNER)
    session.subagent_start("agent-planner", PLANNER)
    inside_planner = ("agent-planner", PLANNER)

    session.spawn_foreground(
        "Task slug: child-pipeline\n\nImplement the first step.",
        "agent-child",
        inside=inside_planner,
    )
    session.subagent_stop("agent-planner", PLANNER)
    session.agent_result(*planner_call, "agent-planner")

    child = _tally(tmp_path, root, "child-pipeline")
    assert (child.spawns, child.agent_ids()) == (1, ["agent-child"]), child.describe()


@pytest.mark.parametrize(
    ("prompt", "slug"),
    [
        ("Task slug: `backticked-slug`\n\nDesign the parser.", "backticked-slug"),
        (
            "Tier: Standard\nTask slug: slug_with_underscores\nDesign the parser.",
            "slug_with_underscores",
        ),
        ("Design the parser for Task slug: sentence-slug.", "sentence-slug"),
        ("Task slug: v2-pipeline", "v2-pipeline"),
    ],
    ids=["backticks", "middle-line", "end-of-sentence", "whole-prompt"],
)
def test_the_stated_slug_is_read_from_every_marker_spelling(
    tmp_path: Path, prompt: str, slug: str
) -> None:
    root = _checkout(tmp_path)
    session = _session(tmp_path, root)

    session.spawn_foreground(prompt, "agent-one")

    stated = _tally(tmp_path, root, slug)
    assert (stated.spawns, stated.agent_ids()) == (1, ["agent-one"]), stated.describe()


def test_the_first_marker_names_the_slug_when_a_prompt_states_two(tmp_path: Path) -> None:
    root = _checkout(tmp_path)
    session = _session(tmp_path, root)

    session.spawn_foreground(
        "Task slug: first-slug\n\nWhen you report, note that the follow-up uses "
        "Task slug: second-slug.",
        "agent-one",
    )

    first = _tally(tmp_path, root, "first-slug")
    second = _tally(tmp_path, root, "second-slug")
    assert (first.spawns, first.agent_ids()) == (1, ["agent-one"]), first.describe()
    assert second.counts_nothing(), second.describe()


# -- A resume counts where its spawn counts -----------------------------------


def _spawn_then_resume_with_another_slug_in_the_message(session: Session) -> None:
    session.spawn_foreground(
        "Task slug: owner-pipeline\n\nDesign the parser.",
        "agent-owner",
        "praxion:systems-architect",
    )
    session.resume(
        "agent-owner",
        "praxion:systems-architect",
        message="Task slug: other-pipeline\n\nResume the design with the new constraint.",
    )


def test_a_resume_is_reported_under_its_spawns_slug_and_never_as_a_new_spawn(
    tmp_path: Path,
) -> None:
    root = _checkout(tmp_path)
    session = _session(tmp_path, root)

    _spawn_then_resume_with_another_slug_in_the_message(session)

    owner = _tally(tmp_path, root, "owner-pipeline")
    assert (owner.spawns, owner.resumes, owner.resumes_of("agent-owner")) == (1, 1, 1), (
        owner.describe()
    )


def test_a_resume_never_counts_under_the_slug_its_message_states(tmp_path: Path) -> None:
    root = _checkout(tmp_path)
    session = _session(tmp_path, root)

    _spawn_then_resume_with_another_slug_in_the_message(session)

    other = _tally(tmp_path, root, "other-pipeline")
    assert other.counts_nothing(), other.describe()


def test_a_resume_of_a_slugged_spawn_adds_nothing_to_the_checkout(tmp_path: Path) -> None:
    root = _checkout(tmp_path)
    session = _session(tmp_path, root)
    session.spawn_foreground("Look around the repository.", "agent-adhoc")

    _spawn_then_resume_with_another_slug_in_the_message(session)

    parent = _tally(tmp_path, root, CHECKOUT)
    assert (parent.spawns, parent.resumes, parent.agent_ids()) == (1, 0, ["agent-adhoc"]), (
        parent.describe()
    )


# -- A spawn that states no slug counts toward the checkout --------------------


@pytest.mark.parametrize("where", [".", "src/deep"])
def test_an_unslugged_spawn_and_its_resume_count_toward_the_checkout(
    tmp_path: Path, where: str
) -> None:
    root = _checkout(tmp_path)
    session = _session(tmp_path, subdirectory(root, where))

    session.spawn_foreground("Look around the repository.", "agent-adhoc")
    session.resume("agent-adhoc")

    parent = _tally(tmp_path, root, CHECKOUT)
    assert (parent.spawns, parent.resumes, parent.agent_ids()) == (1, 1, ["agent-adhoc"]), (
        parent.describe()
    )


# -- Every distinct spawn counts exactly once ----------------------------------

BUSY = "Task slug: busy-pipeline\n\nTake the next step."


def _spawn_whose_start_is_never_delivered(session: Session, agent_id: str) -> None:
    tool_use_id, tool_input = session.agent_call(BUSY, IMPLEMENTER)
    session.subagent_stop(agent_id, IMPLEMENTER)
    session.agent_result(tool_use_id, tool_input, agent_id)


@pytest.mark.parametrize("mode", ["standard", "full"])
def test_every_distinct_spawn_for_a_slug_counts_exactly_once(tmp_path: Path, mode: str) -> None:
    root = _checkout(tmp_path)
    session = _session(tmp_path, root, mode)
    session.spawn_foreground(BUSY, "agent-at-root")
    session.spawn_foreground(BUSY, "agent-from-subdir", cwd=subdirectory(root, "src/deep"))
    parallel = _launch_two_alike_in_parallel(
        session, [(BUSY, "agent-parallel-a"), (BUSY, "agent-parallel-b")]
    )
    _deliver_results(session, parallel)
    session.spawn_foreground(BUSY, "agent-resumed")
    session.resume("agent-resumed")
    _spawn_whose_start_is_never_delivered(session, "agent-start-lost")

    busy = _tally(tmp_path, root, "busy-pipeline")

    assert busy.spawns == 6, busy.describe()
    assert busy.agent_ids() == sorted(
        [
            "agent-at-root",
            "agent-from-subdir",
            "agent-parallel-a",
            "agent-parallel-b",
            "agent-resumed",
            "agent-start-lost",
        ]
    )


def test_a_spawn_whose_start_was_never_delivered_still_counts(tmp_path: Path) -> None:
    root = _checkout(tmp_path)
    session = _session(tmp_path, root)

    _spawn_whose_start_is_never_delivered(session, "agent-start-lost")

    busy = _tally(tmp_path, root, "busy-pipeline")
    assert (busy.spawns, busy.agent_ids()) == (1, ["agent-start-lost"]), busy.describe()


def test_an_agent_named_by_many_records_counts_once(tmp_path: Path) -> None:
    root = _checkout(tmp_path)
    session = _session(tmp_path, root, "full")
    session.spawn_foreground(BUSY, "agent-chatty")
    session.plain_tool_use(inside=("agent-chatty", IMPLEMENTER))
    session.plain_tool_use(inside=("agent-chatty", IMPLEMENTER))

    session.resume("agent-chatty")
    session.resume("agent-chatty")

    busy = _tally(tmp_path, root, "busy-pipeline")
    assert (busy.spawns, busy.resumes, busy.agent_ids()) == (1, 2, ["agent-chatty"]), (
        busy.describe()
    )


# -- A spawn of unknown attribution holds the verdict --------------------------

HELD = "Task slug: held-pipeline\n\nReview the parser."
OTHER = "Task slug: other-pipeline\n\nReview the lexer."


def _one_definite_spawn_and_two_unattributable(
    tmp_path: Path,
) -> tuple[Path, Session, list[tuple[str, dict, str]]]:
    """held-pipeline has one attributed spawn; two more of unknown slug are running."""
    root = _checkout(tmp_path)
    session = _session(tmp_path, root)
    session.spawn_foreground("Look around the repository.", "agent-adhoc")
    session.spawn_foreground(HELD, "agent-definite")
    pending = _launch_two_alike_in_parallel(session, [(HELD, "agent-x"), (OTHER, "agent-y")])
    return root, session, pending


@pytest.mark.parametrize(
    ("slug", "attributed"),
    [("held-pipeline", ["agent-definite"]), (CHECKOUT, ["agent-adhoc"])],
)
def test_spawns_of_unknown_attribution_are_left_out_of_every_slugs_count(
    tmp_path: Path, slug: str, attributed: list[str]
) -> None:
    root, _, _ = _one_definite_spawn_and_two_unattributable(tmp_path)

    tally = _tally(tmp_path, root, slug)

    assert (tally.spawns, tally.agent_ids()) == (1, attributed), tally.describe()


def test_a_slug_with_only_unattributed_spawns_counts_none_of_them(tmp_path: Path) -> None:
    root, _, _ = _one_definite_spawn_and_two_unattributable(tmp_path)

    other = _tally(tmp_path, root, "other-pipeline")

    assert other.counts_nothing(), other.describe()


def test_a_budget_met_only_without_the_unknown_spawns_reads_indeterminate(tmp_path: Path) -> None:
    root, _, _ = _one_definite_spawn_and_two_unattributable(tmp_path)

    held = _tally(tmp_path, root, "held-pipeline", budget=1)

    assert (held.exit_code, held.charged, held.verdict) == (0, 1, "indeterminate"), held.describe()


def test_a_budget_that_holds_with_every_unknown_spawn_charged_reads_within(
    tmp_path: Path,
) -> None:
    root, _, _ = _one_definite_spawn_and_two_unattributable(tmp_path)

    held = _tally(tmp_path, root, "held-pipeline", budget=3)

    assert (held.exit_code, held.spawns, held.verdict) == (0, 1, "within"), held.describe()


def test_a_definite_charge_beyond_the_budget_reads_over_despite_unknown_spawns(
    tmp_path: Path,
) -> None:
    root, _, _ = _one_definite_spawn_and_two_unattributable(tmp_path)

    held = _tally(tmp_path, root, "held-pipeline", budget=0)

    assert (held.exit_code, held.verdict) == (1, "over"), held.describe()


@pytest.mark.parametrize(
    ("slug", "attributed"),
    [
        ("held-pipeline", ["agent-definite", "agent-x"]),
        ("other-pipeline", ["agent-y"]),
        (CHECKOUT, ["agent-adhoc"]),
    ],
)
def test_an_unknown_spawn_is_attributed_once_its_result_arrives(
    tmp_path: Path, slug: str, attributed: list[str]
) -> None:
    root, session, pending = _one_definite_spawn_and_two_unattributable(tmp_path)

    _deliver_results(session, pending)

    tally = _tally(tmp_path, root, slug)
    assert (tally.spawns, tally.agent_ids()) == (len(attributed), attributed), tally.describe()
