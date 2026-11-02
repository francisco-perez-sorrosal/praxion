"""Tests for spawn_transcripts.py -- recorded subagent transcripts parsed into spawn values.

The fixtures write the layout Claude Code records (`<session>.jsonl` holding each Agent call and
its result, `<session>/subagents/agent-<id>.jsonl` holding the spawn's own turns), the same shape
the outer-loop driver's `record_sessions` writes.
"""

from __future__ import annotations

import dataclasses
import json
import sys
from pathlib import Path
from typing import NamedTuple

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import spawn_transcripts as st  # noqa: E402
from _plan_steps import parse_plan_steps  # noqa: E402
from _step_loop_render import PromptInputs, RequestKey, render_prompt, spawn_request  # noqa: E402

FLOOR_MODEL = "claude-sonnet-5-5"
SESSION = "5e55a1b2-0000-4000-8000-000000000001"


def _call(use_id: str, role: str, prompt: str = "Do the step.", model: str | None = None) -> dict:
    spawn_input = {"subagent_type": f"praxion:{role}", "prompt": prompt}
    if model is not None:
        spawn_input["model"] = model
    block = {"type": "tool_use", "id": use_id, "name": "Agent", "input": spawn_input}
    return {"type": "assistant", "message": {"role": "assistant", "content": [block]}}


def _result(use_id: str, agent_id: str) -> dict:
    block = {"type": "tool_result", "tool_use_id": use_id, "content": f"agentId: {agent_id}"}
    return {
        "type": "user",
        "message": {"role": "user", "content": [block]},
        "toolUseResult": {"status": "completed", "agentId": agent_id},
    }


def _blob_copy(record: dict) -> dict:
    """The `api-request-blob` record Claude Code writes for the same message: same content blocks,
    a different record kind."""
    return {
        "type": "api-request-blob",
        "sessionId": SESSION,
        "hash": "0" * 8,
        "message": record["message"],
    }


def _own_transcript(model: str | None) -> list[dict]:
    reply = {"role": "assistant", "content": [{"type": "text", "text": "Done."}]}
    if model is not None:
        reply["model"] = model
    return [
        {"type": "user", "message": {"role": "user", "content": "Do the step."}},
        {"type": "assistant", "message": reply},
    ]


def _write_lines(path: Path, lines: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(line if isinstance(line, str) else json.dumps(line) for line in lines) + "\n",
        encoding="utf-8",
    )


def _record(
    directory: Path,
    session: str,
    role: str,
    agent_id: str,
    ran_model: str | None = FLOOR_MODEL,
    *,
    prompt: str = "Do the step.",
    model: str | None = None,
) -> None:
    """One session holding one spawn, with its own transcript when it ran on a model."""
    use_id = f"toolu_{agent_id}"
    _write_lines(
        directory / f"{session}.jsonl",
        [_call(use_id, role, prompt, model), _result(use_id, agent_id)],
    )
    if ran_model is not None:
        own = directory / session / "subagents" / f"agent-{agent_id}.jsonl"
        _write_lines(own, _own_transcript(ran_model))


def test_a_spawn_that_passed_no_model_reads_back_with_the_model_it_ran_on(tmp_path):
    _record(tmp_path, SESSION, "implementer", "a1", ran_model=FLOOR_MODEL)

    spawns = st.read_spawns(tmp_path)

    assert spawns == [
        st.Spawn(
            session=SESSION,
            agent_id="a1",
            role="implementer",
            requested_model=None,
            ran_model=FLOOR_MODEL,
            prompt_markers=frozenset(),
        )
    ]


def test_a_per_spawn_model_is_the_requested_model_apart_from_the_ran_model(tmp_path):
    _record(tmp_path, SESSION, "researcher", "a1", ran_model="claude-opus-5-5", model="opus")

    (spawn,) = st.read_spawns(tmp_path)

    assert (spawn.requested_model, spawn.ran_model) == ("opus", "claude-opus-5-5")


def test_prompt_markers_are_the_closed_phrases_the_prompt_states(tmp_path):
    prompt = "Task slug: x\nMode: acceptance-design\ntier: H\nroutine consult"
    _record(tmp_path, SESSION, "test-engineer", "a1", prompt=prompt)

    (spawn,) = st.read_spawns(tmp_path)

    assert spawn.prompt_markers == {"Mode: acceptance-design", "tier: H", "routine"}


@pytest.mark.parametrize(
    "prompt",
    [
        "a tier: High hint",
        "routinely",
        "Mode: acceptance-designs",
        "frontier: H step",
        "non-routine work",
        "routine-check",
        "Mode: light-review-r2",
    ],
)
def test_a_marker_inside_a_longer_word_is_no_marker(tmp_path, prompt):
    _record(tmp_path, SESSION, "implementer", "a1", prompt=prompt)

    (spawn,) = st.read_spawns(tmp_path)

    assert spawn.prompt_markers == frozenset()


@pytest.mark.parametrize(
    ("prompt", "markers"),
    [
        ("This is not Mode: light-review work.", {"Mode: light-review"}),
        ("The step is tier: H and a routine one.", {"tier: H", "routine"}),
        ("Task slug: x\n  Mode: light-review", {"Mode: light-review"}),
        ("Implement the refactor (tier: H)", {"tier: H"}),
    ],
)
def test_a_marker_written_as_a_whole_phrase_is_a_marker_wherever_it_stands(
    tmp_path, prompt, markers
):
    _record(tmp_path, SESSION, "implementer", "a1", prompt=prompt)

    (spawn,) = st.read_spawns(tmp_path)

    assert spawn.prompt_markers == markers


def test_one_agent_call_is_one_spawn_whatever_record_kinds_carry_a_copy_of_it(tmp_path):
    call = _call("toolu_a1", "implementer")
    _write_lines(
        tmp_path / f"{SESSION}.jsonl",
        [call, _blob_copy(call), _result("toolu_a1", "a1"), _blob_copy(call)],
    )

    spawns = st.read_spawns(tmp_path)

    assert [s.agent_id for s in spawns] == ["a1"]


def test_a_driver_pointer_prompt_names_the_request_it_answers(tmp_path):
    issued = _issued()
    _record(tmp_path, SESSION, "implementer", "a1", prompt=issued.prompt)

    (spawn,) = st.read_spawns(tmp_path)

    assert spawn.driver == st.DriverRequest("s7-a1-implement", None)


@pytest.mark.parametrize(
    "prompt",
    [
        "Do the step.",
        "Spawn request: s7-a1\nTask slug: x",
        "Task slug: x\nWe answer the Spawn request: s7-a1 today.",
        "Intro\nTask slug: x\nSpawn request: s7-a1",
        "Task slug: x\nNo request here.",
    ],
)
def test_a_prompt_that_is_not_a_driver_pointer_names_no_request(tmp_path, prompt):
    _record(tmp_path, SESSION, "verifier", "a1", prompt=prompt)

    (spawn,) = st.read_spawns(tmp_path)

    assert spawn.driver is None


SLUG = "x"
WORK = "/sandbox/.ai-work/x"
STEP_HEADING = "### Step 7"  # id-citation-discipline:ignore
STEP_TEXT = (
    STEP_HEADING + ": Write the widget\n\n**Assignee**: implementer\n{hint}**Done when**: ok\n"
)
REVIEW_RANGE = ("base", "head")


class Issued(NamedTuple):
    """A request as the step-loop driver builds it: the pointer prompt the Agent call carries, the
    file it names and the text rendered into that file. All three come from the driver's own
    builders, so a change to the pointer or the rendered shape reaches these fixtures too."""

    id: str
    prompt: str
    path: str
    rendered: str

    def read(self, **options) -> list[dict]:
        return _read_of_rendered(self.rendered, path=self.path, **options)


def _issued(hint: str = "", *, kind: str = "implement", wip_text: str = "") -> Issued:
    (step,) = parse_plan_steps(STEP_TEXT.format(hint=hint))
    key = RequestKey("7", 1, kind, round=None if kind == "implement" else 1)
    request = spawn_request(SLUG, step, key, 3, WORK)
    inputs = PromptInputs(request, step, WORK, wip_text=wip_text, review_range=REVIEW_RANGE)
    rendered, _ = render_prompt(inputs)
    return Issued(key.id, request.agent_call.prompt, request.prompt_path, rendered)


def _numbered(text: str) -> str:
    return "".join(f"{n:>6}\t{line}\n" for n, line in enumerate(text.splitlines(), 1))


def _read_of_rendered(
    text: str,
    *,
    raw: bool = True,
    counts: bool = True,
    path: str,
    total_lines: int | None = None,
    asked: dict | None = None,
    use_id: str = "toolu_r",
) -> list[dict]:
    """The spawn's own records of reading its rendered request: the call (with the `offset` or
    `limit` it `asked` for), then the result with the numbered lines in the message and, when `raw`,
    the file itself in `toolUseResult`, with line counts when `counts`; `total_lines` above the
    lines read makes it a part of a longer file."""
    call_input = {"file_path": path, **(asked or {})}
    call = {
        "type": "assistant",
        "message": {
            "role": "assistant",
            "model": FLOOR_MODEL,
            "content": [{"type": "tool_use", "id": use_id, "name": "Read", "input": call_input}],
        },
    }
    result_block = {"type": "tool_result", "tool_use_id": use_id, "content": _numbered(text)}
    result = {"type": "user", "message": {"role": "user", "content": [result_block]}}
    if raw:
        file_result = {"filePath": path, "content": text}
        if counts:
            lines_read = len(text.splitlines())
            file_result |= {"numLines": lines_read, "totalLines": total_lines or lines_read}
        result["toolUseResult"] = {"type": "text", "file": file_result}
    return [call, result]


def _driver_spawn(directory: Path, own_records: list[dict], prompt: str) -> st.Spawn:
    _record(directory, SESSION, "implementer", "a1", prompt=prompt)
    own = directory / SESSION / "subagents" / "agent-a1.jsonl"
    _write_lines(own, [*_own_transcript(FLOOR_MODEL), *own_records])
    (spawn,) = st.read_spawns(directory)
    return spawn


def _implied(tmp_path, issued: Issued, records: list[dict] | None = None):
    spawn = _driver_spawn(tmp_path, issued.read() if records is None else records, issued.prompt)
    assert spawn.driver.id == issued.id
    return spawn.driver.implied


@pytest.mark.parametrize(
    ("hint", "implied"),
    [
        ("", "floor"),
        ("tier: H\n", "opus"),
        ("**tier**: H\n", "opus"),
        ("- **Tier**: L\n", "haiku"),
        ("tier: L\n", "haiku"),
        ("tier: High\n", "floor"),
    ],
)
def test_a_driver_request_implies_the_routing_of_its_steps_own_tier_field(tmp_path, hint, implied):
    assert _implied(tmp_path, _issued(hint)) == implied


def test_a_light_review_the_pointer_states_implies_sonnet_whatever_the_step_hints(tmp_path):
    issued = _issued("tier: H\n", kind="review")

    assert _implied(tmp_path, issued) == "sonnet"


def test_a_light_review_the_spawn_never_read_still_implies_sonnet_from_its_pointer(tmp_path):
    assert _implied(tmp_path, _issued(kind="review"), records=[]) == "sonnet"


def test_a_light_review_marker_inside_the_rendered_request_sets_nothing(tmp_path):
    issued = _issued("Mode: light-review\n")

    assert _implied(tmp_path, issued) == "floor"


@pytest.mark.parametrize(
    "hint",
    [
        "The step says to treat `tier: H` as a hint.\n",
        "```\ntier: H\n```\n",
        "Follow the tier: H hint, a routine one.\n",
    ],
)
def test_a_marker_in_step_prose_or_a_code_fence_sets_nothing(tmp_path, hint):
    assert _implied(tmp_path, _issued(hint)) == "floor"


def test_a_tier_line_in_a_section_after_the_step_block_sets_nothing(tmp_path):
    wip_text = "## Corrections in force\n\ntier: H\n"

    assert _implied(tmp_path, _issued(wip_text=wip_text)) == "floor"


def test_a_driver_request_read_back_only_as_numbered_lines_implies_the_same_routing(tmp_path):
    issued = _issued("tier: H\n")

    assert _implied(tmp_path, issued, issued.read(raw=False)) == "opus"


def _lines_until_the_step_heading(issued: Issued) -> tuple[str, str]:
    """The rendered request split just after the step's heading line: the part before the step's
    fields, and the rest."""
    lines = issued.rendered.splitlines()
    cut = next(n for n, line in enumerate(lines) if line.startswith(STEP_HEADING)) + 1
    return "\n".join(lines[:cut]), "\n".join(lines[cut:])


def test_a_first_part_of_a_longer_request_that_stops_short_of_the_tier_does_not_show_it(tmp_path):
    issued = _issued("tier: H\n")
    before_fields, _ = _lines_until_the_step_heading(issued)
    first_part = _read_of_rendered(before_fields, path=issued.path, total_lines=40)

    assert _implied(tmp_path, issued, first_part) is None


def test_a_part_of_a_longer_request_that_holds_the_tier_field_shows_it(tmp_path):
    issued = _issued("tier: H\n")
    part = _read_of_rendered("**Assignee**: implementer\ntier: L", path=issued.path, total_lines=40)

    assert _implied(tmp_path, issued, part) == "haiku"


def test_the_tier_field_in_a_later_part_of_the_request_is_found_across_reads(tmp_path):
    issued = _issued("tier: H\n")
    before_fields, fields = _lines_until_the_step_heading(issued)
    records = [
        *_read_of_rendered(before_fields, path=issued.path, total_lines=40),
        *_read_of_rendered(fields, path=issued.path, total_lines=40, use_id="toolu_2"),
    ]

    assert _implied(tmp_path, issued, records) == "opus"


@pytest.mark.parametrize("asked", [{"limit": 3}, {"offset": 20}, {"offset": 2, "limit": 5}])
def test_a_read_with_no_line_counts_that_asked_for_a_part_is_not_the_whole_request(tmp_path, asked):
    issued = _issued()
    part = _read_of_rendered("# Widget\n\nWrite it.", path=issued.path, counts=False, asked=asked)

    assert _implied(tmp_path, issued, part) is None


def test_a_read_with_no_line_counts_that_asked_for_no_part_is_the_whole_request(tmp_path):
    issued = _issued()

    assert _implied(tmp_path, issued, issued.read(counts=False)) == "floor"


def test_a_driver_request_the_spawn_never_read_implies_nothing(tmp_path):
    issued = _issued("tier: H\n")

    assert _implied(tmp_path, issued, records=[]) is None


def test_a_read_of_another_file_does_not_show_the_request(tmp_path):
    issued = _issued("tier: H\n")
    other = _read_of_rendered(issued.rendered, path="/sandbox/other.md")

    assert _implied(tmp_path, issued, other) is None


def test_a_read_that_errored_does_not_show_the_request(tmp_path):
    issued = _issued("tier: H\n")
    records = _read_of_rendered("File does not exist.", raw=False, path=issued.path)
    records[1]["message"]["content"][0]["is_error"] = True

    assert _implied(tmp_path, issued, records) is None


def test_a_driver_prompt_with_no_third_line_names_no_file_to_read(tmp_path):
    _record(tmp_path, SESSION, "implementer", "a1", prompt="Task slug: x\nSpawn request: s7-a1")

    (spawn,) = st.read_spawns(tmp_path)

    assert spawn.driver == st.DriverRequest("s7-a1", None)


def test_a_driver_request_is_a_frozen_value():
    request = st.DriverRequest("s7-a1", "opus")

    with pytest.raises(dataclasses.FrozenInstanceError):
        request.implied = "floor"  # type: ignore[misc]


def test_a_spawn_with_no_transcript_of_its_own_has_no_ran_model(tmp_path):
    _record(tmp_path, SESSION, "implementer", "a1", ran_model=None)

    (spawn,) = st.read_spawns(tmp_path)

    assert spawn.ran_model is None


def test_an_own_transcript_with_no_model_on_its_assistant_entries_has_no_ran_model(tmp_path):
    _record(tmp_path, SESSION, "implementer", "a1", ran_model=None)
    own = tmp_path / SESSION / "subagents" / "agent-a1.jsonl"
    _write_lines(own, _own_transcript(None) + _own_transcript(st.SYNTHETIC_MODEL))

    (spawn,) = st.read_spawns(tmp_path)

    assert spawn.ran_model is None


def test_an_unreadable_line_is_skipped_and_the_rest_of_the_session_still_reads(tmp_path):
    _write_lines(
        tmp_path / f"{SESSION}.jsonl",
        [
            '{"type": "assistant", "message": {"content": [{"typ',
            "[1, 2]",
            _call("toolu_a1", "implementer"),
            "not json",
            _result("toolu_a1", "a1"),
        ],
    )
    _write_lines(
        tmp_path / SESSION / "subagents" / "agent-a1.jsonl",
        ["{broken", *_own_transcript(FLOOR_MODEL)],
    )

    (spawn,) = st.read_spawns(tmp_path)

    assert (spawn.agent_id, spawn.ran_model) == ("a1", FLOOR_MODEL)


def test_two_sessions_in_one_directory_keep_their_spawns_apart(tmp_path):
    other = "5e55a1b2-0000-4000-8000-000000000002"
    _record(tmp_path, SESSION, "implementer", "a1", ran_model=FLOOR_MODEL)
    _record(tmp_path, other, "verifier", "a2", ran_model="claude-opus-5-5")

    spawns = st.read_spawns(tmp_path)

    assert [(s.session, s.role, s.agent_id, s.ran_model) for s in spawns] == [
        (SESSION, "implementer", "a1", FLOOR_MODEL),
        (other, "verifier", "a2", "claude-opus-5-5"),
    ]


def test_two_spawns_in_one_session_each_read_their_own_transcript(tmp_path):
    _write_lines(
        tmp_path / f"{SESSION}.jsonl",
        [
            _call("toolu_a1", "implementer"),
            _result("toolu_a1", "a1"),
            _call("toolu_a2", "verifier"),
            _result("toolu_a2", "a2"),
        ],
    )
    subagents = tmp_path / SESSION / "subagents"
    _write_lines(subagents / "agent-a1.jsonl", _own_transcript(FLOOR_MODEL))
    _write_lines(subagents / "agent-a2.jsonl", _own_transcript("claude-opus-5-5"))

    spawns = st.read_spawns(tmp_path)

    assert [(s.agent_id, s.ran_model) for s in spawns] == [
        ("a1", FLOOR_MODEL),
        ("a2", "claude-opus-5-5"),
    ]


def test_a_call_that_names_no_agent_id_or_is_not_a_praxion_agent_is_no_spawn(tmp_path):
    other_tool = _call("toolu_b", "implementer")
    other_tool["message"]["content"][0]["input"]["subagent_type"] = "Explore"
    _write_lines(
        tmp_path / f"{SESSION}.jsonl",
        [
            _call("toolu_a", "implementer"),  # no result: it never ran
            other_tool,
            _result("toolu_b", "b1"),
        ],
    )

    assert st.read_spawns(tmp_path) == []


def test_an_empty_directory_holds_no_spawns(tmp_path):
    assert st.read_spawns(tmp_path) == []


def test_a_spawn_is_a_frozen_value():
    spawn = st.Spawn("s", "a1", "implementer", None, None, frozenset())

    with pytest.raises(dataclasses.FrozenInstanceError):
        spawn.ran_model = "x"  # type: ignore[misc]


def test_floors_are_each_definitions_frontmatter_model_by_agent_name(tmp_path):
    agents = tmp_path / "agents"
    agents.mkdir()
    (agents / "implementer.md").write_text(
        "---\nname: implementer\nmodel: sonnet\n---\nBody\n", encoding="utf-8"
    )
    (agents / "researcher.md").write_text(
        "---\nname: researcher\nmodel: opus  # why\n---\nBody\n", encoding="utf-8"
    )
    (agents / "README.md").write_text("# Agents\n", encoding="utf-8")
    (agents / "no-model.md").write_text("---\nname: no-model\n---\n", encoding="utf-8")

    assert st.read_floors(tmp_path) == {"implementer": "sonnet", "researcher": "opus"}
