"""Whether each spawn ran at its definition's floor stays checkable from recorded transcripts.

The check reads each spawn's requested role, any per-spawn model and its prompt markers from the
parent session's transcript, and the model the spawn ran on from the spawn's own transcript. It
classifies each spawn as matching its definition's floor, a sanctioned override (the listed
deviations, or every spawn of a session on one model under the kill switch), unexplained, or
unknown when a model is missing. It exits non-zero on an unexplained spawn and starts no model
session.
"""

from __future__ import annotations

import pytest

from tests.acceptance.drivers import model_routing_move as move
from tests.acceptance.drivers.model_routing_move import RecordedSession, Spawn


def _at_floor(role: str) -> str:
    return move.MODEL_IDS[move.definition_floor(role)]


def _check(tmp_path, *spawns: Spawn, session_id: str = "5e55a1b2-0000-4000-8000-000000000001"):
    transcripts = tmp_path / "projects" / "-sandbox"
    move.record_sessions(transcripts, [RecordedSession(session_id, list(spawns))])
    return move.run_spawn_model_check(transcripts, tmp_path / "scratch")


@pytest.mark.parametrize("role", ["systems-architect", "implementer", "doc-engineer"])
def test_a_spawn_passing_no_model_that_ran_at_its_floor_matches_its_definition(tmp_path, role):
    spawn = Spawn(role, ran_on=_at_floor(role))

    result = _check(tmp_path, spawn)

    assert result.verdicts[spawn.agent_id] == "floor", result.verdicts
    assert result.exit_code == 0


SANCTIONED = {
    "acceptance design at opus": Spawn(
        "test-engineer",
        ran_on="claude-opus-5-5",
        model="opus",
        prompt="Mode: acceptance-design\nTask slug: x",
    ),
    "light review at sonnet": Spawn(
        "verifier",
        ran_on="claude-sonnet-5-5",
        model="sonnet",
        prompt="Mode: light-review\nTask slug: x",
    ),
    "a consult that is not routine at opus": Spawn(
        "discipline-consultant",
        ran_on="claude-opus-5-5",
        model="opus",
        prompt="Consult on the draft.\nTask slug: x",
    ),
    "a researcher mode routed up": Spawn(
        "researcher",
        ran_on="claude-opus-5-5",
        model="opus",
        prompt="Weigh three options.\nTask slug: x",
    ),
    "an implementer step hinted tier: H": Spawn(
        "implementer",
        ran_on="claude-opus-5-5",
        model="opus",
        prompt="Implement the cross-cutting refactor (tier: H)\nTask slug: x",
    ),
}


@pytest.mark.parametrize("case", sorted(SANCTIONED))
def test_a_listed_deviation_reads_as_a_sanctioned_override(tmp_path, case):
    spawn = SANCTIONED[case]

    result = _check(tmp_path, spawn)

    assert result.verdicts[spawn.agent_id] == "override", result.verdicts
    assert result.exit_code == 0


def test_a_per_spawn_model_with_no_listed_deviation_is_unexplained_and_fails_the_check(tmp_path):
    spawn = Spawn(
        "verifier",
        ran_on="claude-sonnet-5-5",
        model="sonnet",
        prompt="Verify the feature.\nTask slug: x",
    )

    result = _check(tmp_path, spawn)

    assert result.verdicts[spawn.agent_id] == "unexplained", result.verdicts
    assert result.exit_code != 0


def test_a_spawn_that_ran_off_its_floor_without_a_per_spawn_model_is_unexplained(tmp_path):
    steady = Spawn("implementer", ran_on=_at_floor("implementer"))
    drifted = Spawn("systems-architect", ran_on="claude-haiku-4-5-20251001")

    result = _check(tmp_path, steady, drifted)

    assert (result.verdicts[steady.agent_id], result.verdicts[drifted.agent_id]) == (
        "floor",
        "unexplained",
    )
    assert result.exit_code != 0


def test_every_spawn_of_a_session_on_one_model_reads_as_the_kill_switch(tmp_path):
    pinned = "claude-haiku-4-5-20251001"
    spawns = [
        Spawn(role, ran_on=pinned) for role in ("systems-architect", "implementer", "verifier")
    ]

    result = _check(tmp_path, *spawns)

    assert sorted(result.verdicts[s.agent_id] for s in spawns) == ["override"] * 3, result.verdicts
    assert result.exit_code == 0


def test_a_spawn_whose_own_transcript_is_missing_is_unknown(tmp_path):
    lost = Spawn("implementer", ran_on=None)

    result = _check(tmp_path, lost)

    assert result.verdicts[lost.agent_id] == "unknown", result.verdicts


def test_the_check_starts_no_model_session(tmp_path):
    result = _check(tmp_path, Spawn("implementer", ran_on=_at_floor("implementer")))

    assert result.claude_launches == []
