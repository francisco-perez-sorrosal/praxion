"""The step-loop driver leaves the harness's file layout behind the way the command reads it.

The command is not asked anything here. These tests read back what the Agent-tool double
and the review double leave in a temporary sandbox: a spawned agent's own transcript in
each of its three states (ended, still running, unreadable), tied to the request that
spawned it, and a light reviewer's verdict file. A reader of those files, later, can use
the same doubles as its contract.
"""

from __future__ import annotations

import json
from pathlib import Path

from tests.acceptance.drivers.step_loop import (
    CONFIG_DIR_VARIABLE,
    END_WAIT_VARIABLE,
    SANDBOX_PROJECT_DIR,
    LoopTask,
    Step,
    Work,
    agent_transcript_path,
    build_loop,
    leave_agent_transcript,
    leave_review_verdict,
    new_agent_id,
    work_on,
)

PROMPT_LINES = (
    "Task slug: loop-task",
    "Spawn request: s1-a1-implement",
    "Read /sandbox/PROMPT_s1-a1-implement.md first and follow it; it holds your step and its constraints.",
)


def _implement_request() -> dict:
    return {
        "id": "s1-a1-implement",
        "kind": "implement",
        "step": "1",
        "agent_call": {"prompt": "\n".join(PROMPT_LINES)},
    }


def _review_request() -> dict:
    prompt = "\n".join(
        (
            "Task slug: loop-task",
            "Spawn request: s1-a1-review-r1",
            "Mode: light-review. Read /sandbox/PROMPT_s1-a1-review-r1.md first and follow it;"
            " it holds the step and the change to review.",
        )
    )
    return {
        "id": "s1-a1-review-r1",
        "kind": "review",
        "step": "1",
        "agent_call": {"prompt": prompt},
    }


def _lines(task: LoopTask, agent_id: str) -> list[str]:
    path = agent_transcript_path(task, agent_id)
    return path.read_text(encoding="utf-8").splitlines()


def _entries(task: LoopTask, agent_id: str) -> list[dict]:
    return [json.loads(line) for line in _lines(task, agent_id)]


def _distinct_requests(entries: list[dict]) -> set[str]:
    return {e["requestId"] for e in entries if e["type"] == "assistant"}


def _leave(task: LoopTask, **kwargs) -> str:
    agent_id = new_agent_id()
    leave_agent_transcript(task, _implement_request(), agent_id, **kwargs)
    return agent_id


def test_the_sandbox_config_directory_and_a_zero_end_wait_reach_the_commands_environment(
    tmp_path,
):
    task = build_loop(tmp_path, Step("1"))

    assert task.env[CONFIG_DIR_VARIABLE] == str(task.sandbox_home / ".claude")
    assert task.env[END_WAIT_VARIABLE] == "0"


def test_a_transcript_lives_under_the_config_directory_at_the_subagents_layout(tmp_path):
    task = build_loop(tmp_path, Step("1"))

    agent_id = _leave(task, requests=3, final_text="Done. [COMPLETE]", ended=True)

    path = agent_transcript_path(task, agent_id)
    config = Path(task.env[CONFIG_DIR_VARIABLE])
    assert path.is_file()
    assert path.relative_to(config).parts[:2] == ("projects", SANDBOX_PROJECT_DIR)
    assert path.parent.name == "subagents"
    assert path.name == f"agent-{agent_id}.jsonl"


def test_a_transcript_opens_with_the_user_line_that_carries_the_requests_prompt(tmp_path):
    task = build_loop(tmp_path, Step("1"))

    agent_id = _leave(task, requests=3, final_text="Done. [COMPLETE]", ended=True)

    first = _entries(task, agent_id)[0]
    assert first["type"] == "user"
    assert first["message"]["content"].splitlines() == list(PROMPT_LINES)


def test_an_ended_transcript_holds_the_requested_requests_and_closes_on_text_only(tmp_path):
    task = build_loop(tmp_path, Step("1"))

    agent_id = _leave(task, requests=7, final_text="All done. [COMPLETE]", ended=True)

    entries = _entries(task, agent_id)
    assert len(_distinct_requests(entries)) == 7
    assert entries[-1]["type"] == "assistant"
    assert entries[-1]["message"]["content"] == [{"type": "text", "text": "All done. [COMPLETE]"}]


def test_each_request_but_the_last_is_a_text_then_a_tool_call_sharing_one_request_id(tmp_path):
    task = build_loop(tmp_path, Step("1"))

    agent_id = _leave(task, requests=4, final_text="Done.", ended=True)

    assistant = [e for e in _entries(task, agent_id) if e["type"] == "assistant"]
    first_request = [e for e in assistant if e["requestId"] == assistant[0]["requestId"]]
    assert [e["message"]["content"][0]["type"] for e in first_request] == ["text", "tool_use"]


def test_a_running_transcript_ends_on_a_tool_call_below_the_cap(tmp_path):
    task = build_loop(tmp_path, Step("1"))

    agent_id = _leave(task, requests=4, final_text="Still editing.", ended=False)

    entries = _entries(task, agent_id)
    assert len(_distinct_requests(entries)) == 4
    assert entries[-1]["type"] == "assistant"
    assert entries[-1]["message"]["content"][0]["type"] == "tool_use"


def test_an_unreadable_transcript_has_a_non_json_line_before_its_ended_final_entry(tmp_path):
    task = build_loop(tmp_path, Step("1"))

    agent_id = _leave(task, requests=5, final_text="[COMPLETE]", ended=True, readable=False)

    lines = _lines(task, agent_id)
    unparseable = [i for i, line in enumerate(lines) if not _is_json(line)]
    assert len(unparseable) == 1
    assert unparseable[0] < len(lines) - 1
    assert json.loads(lines[-1])["message"]["content"][0]["text"] == "[COMPLETE]"


def test_the_double_for_the_agent_tool_returns_the_id_of_the_transcript_it_leaves(tmp_path):
    step = Step("1")
    task = build_loop(tmp_path, step)

    agent_id = work_on(task, _implement_request(), Work(requests=9, final_marker="blocked"))

    entries = _entries(task, agent_id)
    assert len(_distinct_requests(entries)) == 9
    assert entries[-1]["message"]["content"][0]["text"] == f"Step {step.id} done. [BLOCKED]"


def test_an_accepting_reviewer_leaves_an_accept_verdict_and_an_ended_transcript(tmp_path):
    task = build_loop(tmp_path, Step("1"))

    agent_id = leave_review_verdict(task, _review_request(), "accept")

    verdict = (task.task_dir / "LIGHT_REVIEW_step-1.md").read_text(encoding="utf-8")
    assert verdict.splitlines()[0] == "verdict: accept"
    assert _entries(task, agent_id)[0]["message"]["content"].splitlines()[1] == (
        "Spawn request: s1-a1-review-r1"
    )
    assert _entries(task, agent_id)[-1]["message"]["content"][0]["type"] == "text"


def test_a_revising_reviewer_leaves_its_findings_beneath_the_verdict(tmp_path):
    task = build_loop(tmp_path, Step("1"))

    leave_review_verdict(task, _review_request(), "revise")

    verdict = (task.task_dir / "LIGHT_REVIEW_step-1.md").read_text(encoding="utf-8")
    assert verdict.splitlines()[:2] == ["verdict: revise", "findings:"]
    assert "id: F1" in verdict


def test_an_unfinished_review_leaves_a_verdict_still_marked_partial(tmp_path):
    task = build_loop(tmp_path, Step("1"))

    leave_review_verdict(task, _review_request(), "unfinished")

    verdict = (task.task_dir / "LIGHT_REVIEW_step-1.md").read_text(encoding="utf-8")
    assert verdict.splitlines()[0] == "verdict: [PARTIAL]"


def _is_json(line: str) -> bool:
    try:
        json.loads(line)
    except json.JSONDecodeError:
        return False
    return True
