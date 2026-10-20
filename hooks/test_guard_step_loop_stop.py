"""Unit tests for guard_step_loop_stop.py -- the Stop guard for an ended, unrecorded step-loop request.

The message, the cheap test that decides whether a step loop is in play, the fail-open body and
the registration are tested in-process; one subprocess run proves the hook as the harness starts
it (stdin JSON, a working directory, no output when nothing is held). The scenarios that hold a
stop against a real driver-issued loop are the acceptance tests'.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

HOOKS_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = HOOKS_DIR.parent / "scripts"
HOOK = HOOKS_DIR / "guard_step_loop_stop.py"
HOOKS_JSON = HOOKS_DIR / "hooks.json"

sys.path.insert(0, str(HOOKS_DIR))
sys.path.insert(0, str(SCRIPTS_DIR))

import guard_step_loop_stop as guard  # noqa: E402
from _step_loop_cli import SCRIPT, SELF_HOST_INVOCATION  # noqa: E402
from _step_loop_outstanding import Held, Outstanding  # noqa: E402

STEP_ID = "3"


def _attempts(request: str | None = "s3-a1-implement") -> str:
    """The `Attempts:` line the driver writes ahead of a spawn (`request=` only for its own)."""
    suffix = f" request={request}" if request else ""
    return f"- Attempts: Step {STEP_ID} count=1{suffix}\n"


def _held(slug="loop-task", request="s3-a1-implement", agent_id="a" * 17, marker="complete"):
    command = (
        f"{guard.DRIVER_IN_CHECKOUT} record {slug} --request {request} "
        f"--agent-id {agent_id} --marker {marker}"
    )
    return Held(Outstanding(slug, STEP_ID, request, 0.0), agent_id, marker, command)


def _sentences(message: str) -> list[str]:
    return re.split(r"(?<=\.)\s+", message.strip())


# -- The message ----------------------------------------------------------------------------


@pytest.mark.parametrize("marker", ["complete", "blocked", "none"])
def test_message_stays_within_the_cap_for_long_slugs_and_ids(marker):
    held = _held(slug="s" * 60, request="r" * 40, agent_id="f" * 32, marker=marker)

    message = guard._message(held)

    assert len(message.encode("utf-8")) <= guard.MAX_MESSAGE_BYTES, len(message.encode("utf-8"))


def test_message_is_three_sentences_naming_the_fact_the_call_and_the_rule():
    held = _held()

    facts, call, rule = _sentences(guard._message(held))

    assert facts.startswith(guard.MESSAGE_PREFIX)
    assert "s3-a1-implement" in facts
    assert f"step {STEP_ID}" in facts
    assert held.agent_id in facts
    assert re.search(r"not recorded", facts)
    assert call == f"Run `{held.command}`."
    assert rule == guard.RULE


def test_message_says_a_marker_less_agent_carries_none():
    message = guard._message(_held(marker="none"))

    assert "ended with no terminal marker" in message


def test_message_names_the_marker_an_agent_ended_with():
    message = guard._message(_held(marker="blocked"))

    assert "ended with the marker blocked" in message


def test_driver_forms_equal_the_ones_the_driver_prints():
    assert guard.DRIVER_ON_PATH == SCRIPT
    assert guard.DRIVER_IN_CHECKOUT == SELF_HOST_INVOCATION


# -- Letting a stop through ------------------------------------------------------------------


def test_a_stop_already_held_once_reads_nothing(monkeypatch):
    def refuse(*_args, **_kwargs):
        raise AssertionError("the guard looked at the world")

    monkeypatch.setattr(guard, "_find_work_root", refuse)

    assert guard._hold_message(json.dumps({"stop_hook_active": True})) == ""


@pytest.mark.parametrize("raw", ["", "not json", "[1, 2]", "null", '"text"'])
def test_input_that_is_not_a_json_object_lets_the_stop_through(raw, monkeypatch):
    monkeypatch.setattr(guard, "_find_work_root", lambda: pytest.fail("looked at the world"))

    assert guard._hold_message(raw) == ""


def test_no_pipeline_directory_lets_the_stop_through(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    assert guard._find_work_root() is None
    assert guard._hold_message("{}") == ""


def test_a_step_record_naming_a_request_marks_a_loop_in_play(tmp_path):
    task = tmp_path / "task"
    task.mkdir()
    (task / "WIP.md").write_text(f"# WIP\n\n{_attempts()}", encoding="utf-8")

    assert guard._any_request_issued(tmp_path)


@pytest.mark.parametrize(
    "text",
    [_attempts(request=None), "request=s3-a1-implement\n", "# WIP\n"],
    ids=["attempt without a request", "request outside an attempt", "no attempt"],
)
def test_a_step_record_without_an_issued_request_marks_no_loop(tmp_path, text):
    task = tmp_path / "task"
    task.mkdir()
    (task / "WIP.md").write_text(text, encoding="utf-8")

    assert not guard._any_request_issued(tmp_path)


def test_an_unreadable_step_record_marks_no_loop(tmp_path):
    (tmp_path / "task" / "WIP.md").mkdir(parents=True)

    assert not guard._any_request_issued(tmp_path)


@pytest.mark.parametrize(
    "stop",
    [
        {},
        {"session_id": "sess"},
        {"transcript_path": "/t/sess.jsonl"},
        {"session_id": "", "transcript_path": "/t/sess.jsonl"},
        {"session_id": "../x", "transcript_path": "/t/sess.jsonl"},
        {"session_id": 7, "transcript_path": "/t/sess.jsonl"},
    ],
    ids=["empty", "no transcript", "no session", "empty id", "path-like id", "non-string id"],
)
def test_a_stop_that_does_not_locate_its_session_has_no_agent_transcripts_to_read(stop):
    assert guard._subagents_dir(stop) is None


def test_the_session_directory_sits_beside_the_main_transcript():
    stop = {"session_id": "sess", "transcript_path": "/cfg/projects/p/sess.jsonl"}

    assert guard._subagents_dir(stop) == Path("/cfg/projects/p/sess/subagents")


# -- Failing open ----------------------------------------------------------------------------


def test_a_failing_probe_prints_nothing_and_does_not_raise(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", _Stdin(json.dumps({"session_id": "s"})))
    monkeypatch.setattr(guard, "_hold_message", _raise_runtime_error)

    guard.main()

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_a_held_stop_prints_one_block_decision(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", _Stdin("{}"))
    monkeypatch.setattr(guard, "_hold_message", lambda _raw: "held")

    guard.main()

    assert json.loads(capsys.readouterr().out) == {"decision": "block", "reason": "held"}


def test_the_hook_started_as_the_harness_starts_it_prints_nothing_when_nothing_is_held(tmp_path):
    task = tmp_path / ".ai-work" / "task"
    task.mkdir(parents=True)
    (task / "WIP.md").write_text(_attempts(), encoding="utf-8")
    stop = {
        "session_id": "sess",
        "transcript_path": str(tmp_path / "cfg" / "sess.jsonl"),
        "stop_hook_active": False,
    }

    result = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(stop),
        capture_output=True,
        text=True,
        cwd=tmp_path,
        timeout=30,
        check=False,
    )

    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")


class _Stdin:
    def __init__(self, text: str) -> None:
        self._text = text

    def read(self) -> str:
        return self._text


def _raise_runtime_error(_raw: str) -> str:
    raise RuntimeError("the probe failed")


# -- Registration ----------------------------------------------------------------------------


def _stop_entries() -> list[dict]:
    groups = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))["hooks"]["Stop"]
    return [hook for group in groups for hook in group["hooks"]]


def test_the_guard_is_registered_once_under_stop_as_a_synchronous_command_with_a_timeout():
    entries = [
        e for e in _stop_entries() if e["command"].endswith("/hooks/guard_step_loop_stop.py")
    ]

    assert len(entries) == 1
    (entry,) = entries
    assert entry["command"] == "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/guard_step_loop_stop.py"
    assert entry["async"] is False
    assert isinstance(entry["timeout"], (int, float))
    assert entry["timeout"] > 0


def test_the_guard_is_registered_after_every_other_synchronous_stop_entry():
    entries = _stop_entries()
    synchronous = [e["command"] for e in entries if not e.get("async", False)]

    assert synchronous[-1].endswith("/hooks/guard_step_loop_stop.py")
