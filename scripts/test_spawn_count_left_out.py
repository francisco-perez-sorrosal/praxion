"""The spawn counter's owner rule for a spawn whose prompt states no slug, and what it leaves out.

A spawn stating a slug belongs to it from any checkout and session kind. A slug-less spawn a
headless session made belongs to no slug and is listed apart; any other slug-less spawn belongs
to the checkout it ran in, unless that is another checkout bearing the root's own name.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import spawn_count
from spawn_count import UNATTRIBUTED, LeftOut, Owned, SpawnOrigin, slugless_owner

ROOT = Path("/work/pipeline-a")
OTHER_ROOT_NAME = Path("/elsewhere/pipeline-a")
SIBLING = Path("/work/pipeline-b")
SLUG_STATED = "stated-slug"
PROJECT = "row-project"


def _result_row(
    *, task_slug: object = None, session_kind: object = None, checkout: object = None
) -> dict:
    row = {
        "timestamp": "2026-10-20T09:00:02+00:00",
        "session_id": "sess-1",
        "event_type": "tool_use",
        "tool_name": "Agent",
        "project": PROJECT,
        "spawned_agent_id": "a1",
        "spawned_agent_type": "praxion:implementer",
        "task_slug": task_slug,
    }
    if session_kind is not None:
        row["session_kind"] = session_kind
    if checkout is not None:
        row["checkout"] = checkout
    return row


def _start_row() -> dict:
    return {
        "timestamp": "2026-10-20T09:00:01+00:00",
        "session_id": "sess-1",
        "event_type": "agent_start",
        "agent_id": "a1",
        "agent_type": "praxion:implementer",
        "project": PROJECT,
        "slug_attribution": "spawn-prompt",
    }


def _owner_of(result_row: dict, root: Path | None = ROOT):
    (agent,) = spawn_count.tally([_start_row(), result_row], root)
    return agent.owner


# -- A stated slug owns the agent whatever spawned it ----------------------------------------


@pytest.mark.parametrize("session_kind", ["headless", "interactive", "unknown", None])
@pytest.mark.parametrize("checkout", [str(ROOT), str(SIBLING), str(OTHER_ROOT_NAME), None])
def test_a_stated_slug_owns_the_agent_from_any_session_kind_and_checkout(
    session_kind: str | None, checkout: str | None
) -> None:
    row = _result_row(task_slug=SLUG_STATED, session_kind=session_kind, checkout=checkout)

    assert _owner_of(row) == Owned(SLUG_STATED)


# -- The pure rule for a spawn whose prompt stated no slug -----------------------------------


def _origin(kind: spawn_count.SessionKind, checkout: Path | None = None) -> SpawnOrigin:
    return SpawnOrigin(kind=kind, checkout=checkout, project=PROJECT)


@pytest.mark.parametrize("checkout", [ROOT, SIBLING, None])
def test_a_slugless_headless_spawn_is_left_out_wherever_it_ran(checkout: Path | None) -> None:
    owner = slugless_owner(_origin("headless", checkout), ROOT)

    assert owner == LeftOut(spawn_count.HEADLESS_LEFT_OUT)


def test_a_slugless_headless_spawn_is_left_out_even_without_a_root() -> None:
    assert slugless_owner(_origin("headless"), None) == LeftOut(spawn_count.HEADLESS_LEFT_OUT)


@pytest.mark.parametrize("kind", ["interactive", "unknown"])
def test_a_slugless_spawn_belongs_to_the_checkout_it_ran_in(kind: spawn_count.SessionKind) -> None:
    assert slugless_owner(_origin(kind, SIBLING), ROOT) == Owned("pipeline-b")


@pytest.mark.parametrize("kind", ["interactive", "unknown"])
def test_a_slugless_spawn_in_the_root_itself_belongs_to_the_roots_name(
    kind: spawn_count.SessionKind,
) -> None:
    assert slugless_owner(_origin(kind, ROOT), ROOT) == Owned("pipeline-a")


@pytest.mark.parametrize("kind", ["interactive", "unknown"])
def test_a_slugless_spawn_in_another_checkout_bearing_the_roots_name_is_left_out(
    kind: spawn_count.SessionKind,
) -> None:
    owner = slugless_owner(_origin(kind, OTHER_ROOT_NAME), ROOT)

    assert owner == LeftOut(spawn_count.STRAY_CHECKOUT_LEFT_OUT)


def test_without_a_root_no_checkout_is_a_stray() -> None:
    assert slugless_owner(_origin("interactive", OTHER_ROOT_NAME), None) == Owned("pipeline-a")


@pytest.mark.parametrize("kind", ["interactive", "unknown"])
def test_a_slugless_spawn_with_no_checkout_belongs_to_its_project(
    kind: spawn_count.SessionKind,
) -> None:
    assert slugless_owner(_origin(kind), ROOT) == Owned(PROJECT)


def test_a_slugless_spawn_with_no_checkout_and_no_project_is_unattributed() -> None:
    origin = SpawnOrigin(kind="interactive", checkout=None, project="")

    assert slugless_owner(origin, ROOT) == UNATTRIBUTED


# -- The boundary reads the row into that rule's input --------------------------------------


@pytest.mark.parametrize("session_kind", [None, "surprise", "Headless", 7])
def test_an_unrecognised_session_kind_is_never_read_as_headless(session_kind: object) -> None:
    owner = _owner_of(_result_row(session_kind=session_kind, checkout=str(SIBLING)))

    assert owner == Owned("pipeline-b")


@pytest.mark.parametrize("checkout", ["", 7, ["a"]])
def test_a_checkout_that_is_not_a_path_string_is_not_read(checkout: object) -> None:
    assert _owner_of(_result_row(checkout=checkout)) == Owned(PROJECT)


@pytest.mark.parametrize("task_slug", [7, ["a"]])
def test_a_stated_slug_that_is_not_a_string_is_not_read_as_one(task_slug: object) -> None:
    assert _owner_of(_result_row(task_slug=task_slug)) == Owned(PROJECT)


# -- A row written before the new keys is attributed as it always was -------------------------


def test_a_result_row_without_the_new_keys_belongs_to_its_project() -> None:
    rows = [_start_row(), _result_row()]

    assert [t.owner for t in spawn_count.tally(rows, ROOT)] == [Owned(PROJECT)]


def test_a_start_row_alone_is_unattributed() -> None:
    assert [t.owner for t in spawn_count.tally([_start_row()], ROOT)] == [UNATTRIBUTED]


def test_a_legacy_start_outranks_every_new_key() -> None:
    legacy = _start_row() | {"slug_attribution": None}
    rows = [legacy, _result_row(session_kind="headless", checkout=str(SIBLING))]

    assert spawn_count.tally(rows, ROOT)[0].owner == Owned(PROJECT)


# -- What the rest of the tally does with a left-out agent -----------------------------------


def _left_out_rows() -> list[dict]:
    return [_start_row(), _result_row(session_kind="headless")]


def _left_out_tally() -> tuple[spawn_count.AgentTally, ...]:
    return spawn_count.tally(_left_out_rows(), ROOT)


def test_a_left_out_agent_makes_no_slug_seen_through_its_owner() -> None:
    seen = spawn_count.seen_slugs(_left_out_rows(), _left_out_tally())

    assert seen == {PROJECT}


def test_a_left_out_agent_is_not_attributed_from_its_transcript(tmp_path: Path) -> None:
    (agent,) = _left_out_tally()
    _write_prompt_transcript(tmp_path, agent, "Task slug: some-pipeline\nDo the step.")

    assert spawn_count.resolve_owner(agent, tmp_path).owner == LeftOut(
        spawn_count.HEADLESS_LEFT_OUT
    )


def _write_prompt_transcript(
    projects_dir: Path, agent: spawn_count.AgentTally, prompt: str
) -> None:
    """The agent's own transcript, at the layout the tally globs, opening with `prompt`."""
    transcript_dir = projects_dir / "-fake-project-dir" / agent.session_id / "subagents"
    transcript_dir.mkdir(parents=True)
    row = {"type": "user", "message": {"content": prompt}}
    (transcript_dir / f"agent-{agent.agent_id}.jsonl").write_text(
        json.dumps(row) + "\n", encoding="utf-8"
    )


def test_an_unattributed_agent_stays_unattributed_without_a_transcript(tmp_path: Path) -> None:
    (agent,) = spawn_count.tally([_start_row()], ROOT)

    assert spawn_count.resolve_owner(agent, tmp_path).owner == UNATTRIBUTED


# -- The envelope lists them apart, only when there are any ----------------------------------


def _envelope(left_out: tuple[spawn_count.AgentTally, ...]) -> dict:
    result = spawn_count.verdict((), budget=1, threshold=1)
    return spawn_count._build_envelope(
        slug="slug",
        sources=[],
        repo_root=ROOT,
        rows_skipped=0,
        tallies=(),
        result=result,
        threshold=1,
        left_out=left_out,
    )


def test_the_envelope_has_no_left_out_key_when_nothing_was_left_out() -> None:
    assert "left_out" not in _envelope(())


def test_the_envelope_lists_each_left_out_agent_with_its_reason() -> None:
    envelope = _envelope(_left_out_tally())

    assert envelope["left_out"] == [
        {
            "agent_id": "a1",
            "agent_type": "praxion:implementer",
            "reason": spawn_count.HEADLESS_LEFT_OUT,
        }
    ]
    assert "left_out=1" in spawn_count._format_human(envelope)
