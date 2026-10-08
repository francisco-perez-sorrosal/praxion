"""Tests for hooks/remind_turn_budget.py -- the subagent turn-budget reminder.

Three layers: the payload boundary (text in, sum variant out), the reminder decision (agent
definitions and transcripts laid out in a temporary tree, markers redirected to a temporary
directory), and the process contract (what the hook script prints, exits with and imports).
"""

from __future__ import annotations

import io
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

HOOKS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(HOOKS_DIR))

import remind_turn_budget as hook  # noqa: E402
from remind_turn_budget import (  # noqa: E402
    MainCall,
    SubagentCall,
    Unusable,
    declared_cap,
    parse_payload,
    reminder_line,
)

SCRIPT = HOOKS_DIR / "remind_turn_budget.py"
MANIFEST = HOOKS_DIR / "hooks.json"
IMPLEMENTER_DEFINITION = HOOKS_DIR.parent / "agents" / "implementer.md"
CAP = 100
SESSION = "11111111-2222-3333-4444-555555555555"
AGENT = "a0123456789abcdef"
BARE_AGENT = "reviewer"
PLUGIN_AGENT = "praxion:implementer"
PLUGIN_OTHER = "praxion:verifier"
LINE_PREFIX = "[turn-budget] "


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    """Markers under tmp_path, the user's config directory empty, no opt-out set."""
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path / "tmp"))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.delenv(hook.DISABLE_FLAG, raising=False)
    monkeypatch.setattr(hook, "PLUGIN_AGENTS_DIR", tmp_path / "plugin-agents")
    return tmp_path


def _define(directory: Path, name: str, frontmatter: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{name}.md").write_text(f"---\nname: {name}\n{frontmatter}---\nBody.\n")


def _plugin_agent(tmp_path, name="implementer", cap=CAP):
    _define(tmp_path / "plugin-agents", name, f"maxTurns: {cap}\n")


def _transcript(tmp_path, requests: int, agent_id=AGENT) -> Path:
    """The agent's own transcript with `requests` distinct requests, beside the session's."""
    path = tmp_path / "projects" / "p" / SESSION / "subagents" / f"agent-{agent_id}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {"type": "assistant", "message": {"role": "assistant", "content": []}}
    lines = [json.dumps({**record, "requestId": f"req_{n}"}) for n in range(requests)]
    path.write_text("\n".join(lines) + "\n")
    return path


def _call(tmp_path, agent_type=PLUGIN_AGENT, agent_id=AGENT, cwd=None) -> SubagentCall:
    return SubagentCall(
        session_id=SESSION,
        agent_id=agent_id,
        agent_type=agent_type,
        transcript_path=str(tmp_path / "projects" / "p" / f"{SESSION}.jsonl"),
        cwd=str(cwd or tmp_path / "repo"),
    )


def _payload(**overrides) -> str:
    payload = {
        "session_id": SESSION,
        "agent_id": AGENT,
        "agent_type": PLUGIN_AGENT,
        "transcript_path": "/x/y.jsonl",
        "cwd": "/x",
        "tool_name": "Bash",
    }
    return json.dumps({**payload, **overrides})


# --- the payload boundary -----------------------------------------------------------------


def test_a_subagent_payload_parses_into_its_call():
    assert parse_payload(_payload()) == SubagentCall(
        SESSION, AGENT, PLUGIN_AGENT, "/x/y.jsonl", "/x"
    )


@pytest.mark.parametrize(
    "text",
    [
        json.dumps({"session_id": SESSION, "tool_name": "Bash"}),
        json.dumps({"session_id": SESSION, "agent_type": PLUGIN_AGENT}),
    ],
    ids=["main session", "main session started with --agent"],
)
def test_a_payload_without_an_agent_id_is_a_main_call(text):
    assert parse_payload(text) == MainCall()


@pytest.mark.parametrize(
    "text",
    [
        "{not json",
        "[]",
        '"text"',
        _payload(session_id=None),
        _payload(agent_type=7),
        _payload(cwd=""),
        _payload(agent_id=["a"]),
        _payload(agent_id="../escape"),
        _payload(session_id="a/b"),
    ],
    ids=[
        "not json",
        "array",
        "string",
        "null session",
        "numeric type",
        "empty cwd",
        "list id",
        "id climbs out",
        "session with a separator",
    ],
)
def test_anything_else_is_unusable(text):
    assert parse_payload(text) == Unusable()


# --- the declared cap ---------------------------------------------------------------------


def test_a_plugin_agent_reads_its_cap_from_the_plugin_definition(isolated_state):
    _plugin_agent(isolated_state, cap=70)

    assert declared_cap(PLUGIN_AGENT, str(isolated_state / "repo")) == 70


def test_a_bare_agent_reads_the_project_then_the_user_definition(isolated_state):
    cwd = isolated_state / "repo"
    _define(isolated_state / "config" / "agents", BARE_AGENT, "maxTurns: 30\n")
    assert declared_cap(BARE_AGENT, str(cwd)) == 30

    _define(cwd / ".claude" / "agents", BARE_AGENT, "maxTurns: 50\n")
    assert declared_cap(BARE_AGENT, str(cwd)) == 50


@pytest.mark.parametrize(
    "definition",
    [
        "---\nname: x\n---\nBody.\n",
        "---\nname: x\nmaxTurns: lots\n---\n",
        "---\nname: x\nmaxTurns: 0\n---\n",
        "name: x\nmaxTurns: 40\n",
        "---\nname: x\n---\nmaxTurns: 40\n",
    ],
    ids=["absent", "not a number", "zero", "no frontmatter", "in the body"],
)
def test_a_definition_without_a_usable_cap_in_its_frontmatter_has_none(isolated_state, definition):
    agents = isolated_state / "plugin-agents"
    agents.mkdir()
    (agents / "implementer.md").write_text(definition)

    assert declared_cap(PLUGIN_AGENT, str(isolated_state)) is None


def test_the_project_definition_decides_even_without_a_cap(isolated_state):
    cwd = isolated_state / "repo"
    _define(cwd / ".claude" / "agents", BARE_AGENT, "")
    _define(isolated_state / "config" / "agents", BARE_AGENT, "maxTurns: 30\n")

    assert declared_cap(BARE_AGENT, str(cwd)) is None


@pytest.mark.parametrize("agent_type", ["praxion:missing", "praxion:../x", "x/y", "a:b"])
def test_an_unreadable_or_unsafe_agent_has_no_cap(isolated_state, agent_type):
    assert declared_cap(agent_type, str(isolated_state / "repo")) is None


# --- the reminder decision ----------------------------------------------------------------


@pytest.fixture
def implementer(isolated_state):
    _plugin_agent(isolated_state)
    return isolated_state


def test_below_sixty_percent_there_is_no_reminder(implementer):
    _transcript(implementer, 59)

    assert reminder_line(_call(implementer)) is None


def test_crossing_sixty_percent_states_the_real_count_and_the_checkpoint_action(implementer):
    _transcript(implementer, 61)

    line = reminder_line(_call(implementer))

    assert line == f"{LINE_PREFIX}61 of {CAP} turns used. {hook.IMPLEMENTER_60}"


def test_crossing_eighty_percent_tells_the_implementer_to_stop(implementer):
    _transcript(implementer, 80)

    line = reminder_line(_call(implementer))

    assert line == f"{LINE_PREFIX}80 of {CAP} turns used. {hook.IMPLEMENTER_80}"


def test_each_threshold_fires_once_per_agent(implementer):
    _transcript(implementer, 61)
    first = reminder_line(_call(implementer))
    _transcript(implementer, 75)
    repeat = reminder_line(_call(implementer))
    _transcript(implementer, 85)
    second = reminder_line(_call(implementer))
    _transcript(implementer, 97)
    again = reminder_line(_call(implementer))

    assert [first is None, repeat, second is None, again] == [False, None, False, None]


def test_jumping_past_eighty_gives_one_reminder_and_consumes_the_sixty(implementer):
    _transcript(implementer, 90)
    first = reminder_line(_call(implementer))
    sixty_marker = hook._marker(_call(implementer), 60)

    assert (first.endswith(hook.IMPLEMENTER_80), sixty_marker.exists()) == (True, True)


def test_each_agent_has_its_own_reminder(implementer):
    _transcript(implementer, 65)
    _transcript(implementer, 65, agent_id="b0123456789abcdef")
    first = reminder_line(_call(implementer))
    other = reminder_line(_call(implementer, agent_id="b0123456789abcdef"))

    assert (first is None, other is None) == (False, False)


def test_another_agent_with_a_cap_gets_the_generic_texts(implementer):
    _plugin_agent(implementer, name="verifier", cap=80)
    _transcript(implementer, 48)
    sixty = reminder_line(_call(implementer, agent_type=PLUGIN_OTHER))
    _transcript(implementer, 64)
    eighty = reminder_line(_call(implementer, agent_type=PLUGIN_OTHER))

    assert (sixty, eighty) == (
        f"{LINE_PREFIX}48 of 80 turns used. {hook.OTHER_60}",
        f"{LINE_PREFIX}64 of 80 turns used. {hook.OTHER_80}",
    )


def test_an_agent_with_no_cap_gets_nothing(implementer):
    _define(implementer / "plugin-agents", "verifier", "")
    _transcript(implementer, 99)

    assert reminder_line(_call(implementer, agent_type=PLUGIN_OTHER)) is None


def test_a_missing_transcript_gives_nothing(implementer):
    assert reminder_line(_call(implementer)) is None


def test_a_transcript_with_an_unidentified_request_gives_nothing(implementer):
    path = _transcript(implementer, 90)
    anonymous = json.dumps({"type": "assistant", "message": {"role": "assistant"}})
    path.write_text(path.read_text() + anonymous + "\n")

    assert reminder_line(_call(implementer)) is None


def test_a_transcript_in_another_session_is_not_searched_for(implementer):
    other = implementer / "projects" / "q" / "other-session" / "subagents"
    other.mkdir(parents=True)
    (other / f"agent-{AGENT}.jsonl").write_text("")

    assert reminder_line(_call(implementer)) is None


# --- the process contract -----------------------------------------------------------------


def _run_main(monkeypatch, capsys, text: str) -> str:
    monkeypatch.setattr(sys, "stdin", io.StringIO(text))
    hook.main()
    return capsys.readouterr().out


def test_main_prints_only_the_hook_specific_output_object(implementer, monkeypatch, capsys):
    _transcript(implementer, 65)

    parent = implementer / "projects" / "p" / f"{SESSION}.jsonl"
    out = _run_main(monkeypatch, capsys, _payload(transcript_path=str(parent)))

    context = json.loads(out)["hookSpecificOutput"]
    assert context["hookEventName"] == "PreToolUse"
    assert context["additionalContext"].startswith(f"{LINE_PREFIX}65 of {CAP} turns used. ")
    assert list(json.loads(out)) == ["hookSpecificOutput"]


def test_the_kill_switch_silences_the_hook(implementer, monkeypatch, capsys):
    _transcript(implementer, 90)
    parent = implementer / "projects" / "p" / f"{SESSION}.jsonl"
    monkeypatch.setenv(hook.DISABLE_FLAG, "1")

    silenced = _run_main(monkeypatch, capsys, _payload(transcript_path=str(parent)))
    monkeypatch.delenv(hook.DISABLE_FLAG)

    assert silenced == ""
    assert reminder_line(_call(implementer)) is not None


def test_a_main_call_opens_nothing(monkeypatch, capsys):
    def refuse(*args, **kwargs):
        raise AssertionError("the main-session path touched the filesystem")

    monkeypatch.setattr(Path, "read_text", refuse)
    monkeypatch.setattr(Path, "mkdir", refuse)
    monkeypatch.setattr(hook.os, "open", refuse)

    assert _run_main(monkeypatch, capsys, json.dumps({"session_id": SESSION})) == ""


def _run_script(text: str, *flags: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, *flags, str(SCRIPT)],
        input=text,
        capture_output=True,
        text=True,
        timeout=30,
    )


@pytest.mark.parametrize("text", ["", "{not json", "[]", _payload(agent_id=None)])
def test_the_script_exits_zero_and_silent_on_any_input_it_cannot_use(text):
    run = _run_script(text)

    assert (run.returncode, run.stdout) == (0, "")


def test_the_main_session_path_never_loads_the_transcript_reader():
    run = _run_script(json.dumps({"session_id": SESSION}), "-X", "importtime")

    assert run.returncode == 0
    assert "_agent_transcript" not in run.stderr


def test_the_script_fails_open_when_the_work_raises(tmp_path):
    runner = tmp_path / "boom.py"
    runner.write_text(
        "import runpy, sys\n"
        f"sys.path.insert(0, {str(HOOKS_DIR)!r})\n"
        "import remind_turn_budget as hook\n"
        "hook.reminder_line = lambda call: 1 / 0\n"
        f"runpy.run_path({str(SCRIPT)!r}, run_name='__main__', init_globals=vars(hook))\n"
    )
    run = subprocess.run(
        [sys.executable, str(runner)],
        input=_payload(),
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert (run.returncode, run.stdout) == (0, "")


# --- shipped texts and registration -------------------------------------------------------


def test_the_eighty_percent_implementer_text_keeps_the_clauses_the_agent_prompt_shares():
    prompt = IMPLEMENTER_DEFINITION.read_text(encoding="utf-8").lower()
    clauses = ["finish the current file edit", "[partial]"]

    assert [clause in hook.IMPLEMENTER_80.lower() for clause in clauses] == [True, True]
    assert [clause in prompt for clause in clauses] == [True, True]


def test_no_shipped_text_cites_a_pipeline_identifier():
    texts = " ".join([hook.IMPLEMENTER_60, hook.IMPLEMENTER_80, hook.OTHER_60, hook.OTHER_80])

    assert not any(token in texts for token in ("REQ-", "AC-", "dec-", "td-", "Step "))


def test_the_plugin_registers_the_hook_once_for_every_tool_call_synchronously():
    groups = json.loads(MANIFEST.read_text(encoding="utf-8"))["hooks"]["PreToolUse"]
    found = [
        (group["matcher"], entry)
        for group in groups
        for entry in group["hooks"]
        if SCRIPT.name in entry["command"]
    ]

    assert [(matcher, entry["async"], entry["timeout"]) for matcher, entry in found] == [
        ("", False, 5)
    ]
    assert found[0][1]["command"] == (
        "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/remind_turn_budget.py 2>/dev/null"
    )
