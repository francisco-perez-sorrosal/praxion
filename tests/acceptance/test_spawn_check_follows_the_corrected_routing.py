"""The spawn-model check reads spawns against the routing the corrected rule states.

A spawn on the L tier runs on any Haiku model; a researcher in its simple-lookup mode and an
implementer step hinted `tier: L` that passed `haiku` are sanctioned overrides, and a
doc-engineer routed up is unexplained. A marker written as a whole phrase anywhere in the prompt (mid-line,
indented, negated or inside backticks) reads as present; one held only inside a longer word
sanctions nothing. A spawn the step-loop driver issued (its prompt opens with
`Task slug:` and names a `Spawn request:`) is held to the model its request implies: `sonnet`
for a light review, `opus` for a step hinted `tier: H`, `haiku` for `tier: L`, its floor with no
hint; another model reads unexplained, and a request the transcripts do not show reads unknown.
A session whose spawns all ran on one model, whose floors differ and where nothing records forcing
reads unknown off the floor and `floor` on it, with a reason saying the forcing setting cannot be
excluded. Exit codes and output shape stay as they are, and no model session starts.
"""

from __future__ import annotations

import pytest

from tests.acceptance.drivers import routing_facts as rf
from tests.acceptance.drivers.model_routing_move import RecordedSession, Spawn

SESSION = "5e55a1b2-0000-4000-8000-0000000000f1"
HAIKU_MODELS = ("claude-haiku-5-5", "claude-haiku-4-5-20251001")


def _check(tmp_path, *spawns: Spawn) -> rf.SpawnReading:
    return rf.check_recorded([RecordedSession(SESSION, list(spawns))], tmp_path / "check")


# -- The L tier is the haiku alias ----------------------------------------------------------------


@pytest.mark.parametrize("ran_on", HAIKU_MODELS)
def test_a_doc_engineer_passing_no_model_on_any_haiku_model_reads_floor(tmp_path, ran_on):
    spawn = Spawn("doc-engineer", ran_on=ran_on, prompt="Check the catalog links.\nTask slug: x")

    reading = _check(tmp_path, rf.steady_spawn(), spawn)

    assert reading.verdicts[spawn.agent_id] == "floor", reading.verdicts
    assert reading.exit_code == 0


@pytest.mark.parametrize("ran_on", HAIKU_MODELS)
def test_a_researcher_in_simple_lookup_mode_passing_haiku_reads_override(tmp_path, ran_on):
    spawn = Spawn(
        "researcher",
        ran_on=ran_on,
        model="haiku",
        prompt="Find the line in the parity gate that reads the tier table.\nTask slug: x",
    )

    reading = _check(tmp_path, rf.steady_spawn(), spawn)

    assert reading.verdicts[spawn.agent_id] == "override", reading.verdicts
    assert reading.exit_code == 0


@pytest.mark.parametrize("ran_on", HAIKU_MODELS)
def test_an_implementer_step_hinted_tier_l_passing_haiku_reads_override(tmp_path, ran_on):
    spawn = Spawn(
        "implementer",
        ran_on=ran_on,
        model="haiku",
        prompt="Fix the typo in the README.\ntier: L\nTask slug: x",
    )

    reading = _check(tmp_path, rf.steady_spawn(), spawn)

    assert reading.verdicts[spawn.agent_id] == "override", reading.verdicts
    assert reading.exit_code == 0


def test_a_doc_engineer_routed_up_to_sonnet_reads_unexplained_and_fails_the_check(tmp_path):
    spawn = Spawn(
        "doc-engineer",
        ran_on="claude-sonnet-5-5",
        model="sonnet",
        prompt="Check the catalog links.\nTask slug: x",
    )

    reading = _check(tmp_path, rf.steady_spawn(), spawn)

    assert reading.verdicts[spawn.agent_id] == "unexplained", reading.verdicts
    assert reading.exit_code == 1


# -- Markers written mid-line or in backticks -----------------------------------------------------

# Each marker with the spawn it sanctions: role, model passed, model ran on.
MARKED = {
    "Mode: acceptance-design": ("test-engineer", "opus", "claude-opus-5-5"),
    "Mode: light-review": ("verifier", "sonnet", "claude-sonnet-5-5"),
    "tier: H": ("implementer", "opus", "claude-opus-5-5"),
    "tier: L": ("implementer", "haiku", "claude-haiku-5-5"),
}
SHAPES = {
    "opening-a-sentence-mid-line": "Read the brief first. {marker}.",
    "inside-backticks": "Step hint: `{marker}`.",
    "negated": "This is not {marker} work.",
    "mentioned-inside-a-sentence": "The step is {marker} and a small one.",
    "on-an-indented-line": "Review the step.\n  {marker}",
    "in-backticks-inside-a-negation": "This is not `{marker}` work.",
}


@pytest.mark.parametrize("shape", sorted(SHAPES))
@pytest.mark.parametrize("marker", sorted(MARKED))
def test_a_marker_written_mid_line_or_in_backticks_sanctions_its_deviation(tmp_path, marker, shape):
    role, model, ran_on = MARKED[marker]
    prompt = SHAPES[shape].format(marker=marker) + "\nTask slug: x"
    spawn = Spawn(role, ran_on=ran_on, model=model, prompt=prompt)

    reading = _check(tmp_path, rf.steady_spawn(), spawn)

    assert reading.verdicts[spawn.agent_id] == "override", (prompt, reading.verdicts)
    assert reading.exit_code == 0


# Text holding a marker only inside a longer word, each with the off-floor spawn it must not sanction.
NO_MARKER = {
    "part of a longer word": ("implementer", "opus", "Follow a tier: High hint."),
    "a longer marker": ("test-engineer", "opus", "Mode: acceptance-designs"),
}
RAN_ON = {"opus": "claude-opus-5-5", "sonnet": "claude-sonnet-5-5"}


@pytest.mark.parametrize("case", sorted(NO_MARKER))
def test_a_marker_held_only_inside_a_longer_word_sanctions_nothing(tmp_path, case):
    role, model, text = NO_MARKER[case]
    spawn = Spawn(role, ran_on=RAN_ON[model], model=model, prompt=f"{text}\nTask slug: x")

    reading = _check(tmp_path, rf.steady_spawn(), spawn)

    assert reading.verdicts[spawn.agent_id] == "unexplained", reading.verdicts
    assert reading.exit_code == 1


# -- Driver-issued spawns are held to the routing their request implies ---------------------------


def _review(ran_on: str, model: str) -> rf.DriverSpawn:
    """A light review the driver issued for a risky step (its block carries `tier: H`)."""
    return rf.DriverSpawn(
        "verifier",
        ran_on=ran_on,
        request_id="s7-a1-review-r1",
        model=model,
        pointer_mode="Mode: light-review. ",
        rendered=rf.rendered_review_prompt("7", "tier: H"),
    )


def _implement(ran_on: str, model: str, hint: str | None) -> rf.DriverSpawn:
    return rf.DriverSpawn(
        "implementer",
        ran_on=ran_on,
        request_id="s7-a1-implement",
        model=model,
        rendered=rf.rendered_implement_prompt("7", hint),
    )


ON_THEIR_IMPLIED_MODEL = {
    "a light review on sonnet": _review("claude-sonnet-5-5", "sonnet"),
    "a step hinted tier: H on opus": _implement("claude-opus-5-5", "opus", "tier: H"),
    "a step hinted tier: L on haiku": _implement("claude-haiku-5-5", "haiku", "tier: L"),
}


@pytest.mark.parametrize("case", sorted(ON_THEIR_IMPLIED_MODEL))
def test_a_driver_spawn_off_its_floor_on_the_model_its_request_implies_reads_override(
    tmp_path, case
):
    reading, spawn = rf.check_driver_session(ON_THEIR_IMPLIED_MODEL[case], tmp_path)

    assert reading.verdicts[spawn.agent_id] == "override", reading.verdicts
    assert reading.exit_code == 0


OFF_THEIR_IMPLIED_MODEL = {
    "a light review on haiku": _review("claude-haiku-5-5", "haiku"),
    "a step hinted tier: H on haiku": _implement("claude-haiku-5-5", "haiku", "tier: H"),
    "a step hinted tier: L on opus": _implement("claude-opus-5-5", "opus", "tier: L"),
    "a step with no hint on opus": _implement("claude-opus-5-5", "opus", None),
}


@pytest.mark.parametrize("case", sorted(OFF_THEIR_IMPLIED_MODEL))
def test_a_driver_spawn_on_another_model_than_its_request_implies_reads_unexplained(tmp_path, case):
    reading, spawn = rf.check_driver_session(OFF_THEIR_IMPLIED_MODEL[case], tmp_path)

    assert reading.verdicts[spawn.agent_id] == "unexplained", reading.verdicts
    assert reading.exit_code == 1


def test_a_driver_spawn_whose_transcripts_do_not_show_its_step_reads_unknown(tmp_path):
    unseen = rf.DriverSpawn(
        "implementer", ran_on="claude-opus-5-5", request_id="s7-a1-implement", model="opus"
    )

    reading, spawn = rf.check_driver_session(unseen, tmp_path)

    assert reading.verdicts[spawn.agent_id] == "unknown", reading.verdicts
    assert reading.exit_code == 0


ON_THEIR_FLOOR = {
    "a light review on its opus floor": _review("claude-opus-5-5", "opus"),
    "a step with no hint on its sonnet floor": _implement("claude-sonnet-5-5", "sonnet", None),
    "a step hinted tier: L on its sonnet floor": _implement(
        "claude-sonnet-5-5", "sonnet", "tier: L"
    ),
}


@pytest.mark.parametrize("case", sorted(ON_THEIR_FLOOR))
def test_a_driver_spawn_on_its_floor_is_never_a_finding(tmp_path, case):
    reading, spawn = rf.check_driver_session(ON_THEIR_FLOOR[case], tmp_path)

    assert reading.verdicts[spawn.agent_id] in ("floor", "override"), reading.verdicts
    assert reading.exit_code == 0


# -- A one-model session reads unknown, not the kill switch ---------------------------------------


def _one_model_session(ran_on: str) -> dict[str, Spawn]:
    """Spawns of differing floors, none passing a model, all recorded on `ran_on`."""
    return {
        role: Spawn(role, ran_on=ran_on, prompt=f"Do the {role} work.\nTask slug: x")
        for role in ("systems-architect", "implementer", "verifier")
    }


def test_a_one_model_session_reads_unknown_off_the_floor_and_floor_on_it(tmp_path):
    spawns = _one_model_session("claude-sonnet-5-5")

    reading = _check(tmp_path, *spawns.values())

    by_role = {role: reading.verdicts[s.agent_id] for role, s in spawns.items()}
    assert by_role == {
        "systems-architect": "unknown",
        "implementer": "floor",
        "verifier": "unknown",
    }
    assert reading.exit_code == 0


def test_a_one_model_session_on_haiku_reads_every_off_floor_spawn_unknown(tmp_path):
    spawns = _one_model_session("claude-haiku-4-5-20251001")

    reading = _check(tmp_path, *spawns.values())

    assert sorted(reading.verdicts[s.agent_id] for s in spawns.values()) == ["unknown"] * 3
    assert reading.exit_code == 0


def test_an_unknown_one_model_spawns_reason_says_forcing_cannot_be_excluded(tmp_path):
    spawns = _one_model_session("claude-sonnet-5-5")
    off_floor = spawns["systems-architect"]

    reading = _check(tmp_path, *spawns.values())

    row = reading.rows[off_floor.agent_id]
    assert "unknown" in row, row
    assert "forc" in row.lower(), row


def test_the_checks_text_output_keeps_one_row_per_spawn_naming_its_role_and_verdict(tmp_path):
    spawns = _one_model_session("claude-sonnet-5-5")

    reading = _check(tmp_path, *spawns.values())

    missing = {
        s.agent_id: reading.rows[s.agent_id]
        for s in spawns.values()
        if s.role not in reading.rows[s.agent_id]
        or reading.verdicts[s.agent_id] not in reading.rows[s.agent_id]
    }
    assert missing == {}


def test_reading_a_one_model_session_starts_no_model_session(tmp_path):
    reading = _check(tmp_path, *_one_model_session("claude-sonnet-5-5").values())

    assert reading.claude_launches == []
