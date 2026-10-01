"""Tests for `hook_replay.py` -- delivering a hook event the way the harness does.

The failure this closes: hook checks that fed the hooks a payload in the wrong
shape, from the wrong directory, with the wrong environment, and so proved
nothing about a real session. The replay must run every command the
registration lists for the event (matcher permitting) through `/bin/sh -c`,
payload as one JSON object on stdin, in the session's working directory, with
the plugin root set and the session's own variables scrubbed. Expected values
come from that contract, not from running the implementation.
"""

from __future__ import annotations

import json
import sys
import textwrap
from pathlib import Path

import pytest

# Flat import (siblings by bare name), the layout the mutation sensor reads.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import hook_replay  # noqa: E402

RECORDER = """\
    import json, os, sys
    from pathlib import Path
    record = {
        "event": json.load(sys.stdin)["hook_event_name"],
        "cwd": os.getcwd(),
        "home": os.environ.get("HOME"),
        "plugin_root": os.environ.get("CLAUDE_PLUGIN_ROOT"),
        "project_dir": os.environ.get("CLAUDE_PROJECT_DIR"),
        "opt_outs": [os.environ.get(k) for k in (
            "PRAXION_DISABLE_EVENT_POSTING",
            "PRAXION_DISABLE_AUTO_COMPLETE",
            "PRAXION_DISABLE_SIDECAR_AUTOCOMMIT",
        )],
        "leaked": sorted(k for k in os.environ if k in ("ANTHROPIC_API_KEY", "GITHUB_TOKEN")
                         or k.startswith(("CLAUDE_CODE", "GIT_"))),
        "python3": sys.executable,
    }
    with open(os.path.join(os.environ["HOME"], "records.jsonl"), "a") as handle:
        handle.write(json.dumps(record) + "\\n")
"""


def _registration(tmp_path: Path, hooks: dict) -> Path:
    """A stand-in plugin root holding `hooks.json` and the recording hook."""
    repo = tmp_path / "plugin"
    (repo / "hooks").mkdir(parents=True)
    (repo / "hooks" / "hooks.json").write_text(json.dumps({"hooks": hooks}))
    (repo / "hooks" / "rec.py").write_text(textwrap.dedent(RECORDER))
    return repo


def _command(timeout: int = 5, script: str = "rec.py") -> dict:
    return {
        "type": "command",
        "command": f"python3 ${{CLAUDE_PLUGIN_ROOT}}/hooks/{script}",
        "timeout": timeout,
    }


def _records(home: Path) -> list[dict]:
    log = home / "records.jsonl"
    return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []


def _deliver(repo: Path, tmp_path: Path, event: str, payload: dict, **overrides):
    project = tmp_path / "project"
    cwd = project / "sub"
    cwd.mkdir(parents=True, exist_ok=True)
    home = tmp_path / "home"
    base_env = overrides.pop(
        "base_env",
        {
            "PATH": "/usr/bin:/bin",
            "ANTHROPIC_API_KEY": "secret",
            "GITHUB_TOKEN": "secret",
            "CLAUDE_CODE_SESSION": "live",
            "GIT_DIR": "/elsewhere",
            "KEEP_ME": "kept",
        },
    )
    runs = hook_replay.deliver(
        event, payload, repo=repo, project=project, cwd=cwd, home=home, base_env=base_env
    )
    return runs, home, cwd, project


# -- which commands run -----------------------------------------------------------


def test_registered_commands_follow_the_matcher_the_way_the_harness_applies_it(tmp_path):
    repo = _registration(
        tmp_path,
        {
            "PostToolUse": [
                {"matcher": "Write|Edit", "hooks": [_command(7, "write_only.py")]},
                {"matcher": "", "hooks": [_command(9)]},
                {"matcher": "Ag.*", "hooks": [_command(11, "agent_only.py")]},
            ]
        },
    )

    commands = hook_replay.registered_commands(repo, "PostToolUse", {"tool_name": "Agent"})

    assert [timeout for _, timeout in commands] == [9, 11]
    assert all("write_only" not in command for command, _ in commands)


def test_a_registration_without_the_event_lists_no_commands(tmp_path):
    repo = _registration(tmp_path, {"SubagentStart": [{"matcher": "", "hooks": [_command()]}]})

    assert hook_replay.registered_commands(repo, "PostToolUse", {"tool_name": "Agent"}) == ()


def test_a_missing_registration_is_an_error_not_an_empty_list(tmp_path):
    with pytest.raises(FileNotFoundError):
        hook_replay.registered_commands(tmp_path / "nowhere", "SubagentStart", {})


def test_a_hook_without_a_timeout_gets_the_default(tmp_path):
    hook = {"type": "command", "command": "true"}
    repo = _registration(tmp_path, {"SubagentStart": [{"matcher": "", "hooks": [hook]}]})

    (command,) = hook_replay.registered_commands(repo, "SubagentStart", {"agent_type": "x"})

    assert command == ("true", hook_replay.DEFAULT_TIMEOUT_S)


# -- how a command is run ---------------------------------------------------------


def test_every_registered_command_runs_with_the_payload_on_stdin_from_the_session_directory(
    tmp_path,
):
    repo = _registration(
        tmp_path,
        {"SubagentStart": [{"matcher": "", "hooks": [_command(), _command()]}]},
    )

    runs, home, cwd, _ = _deliver(
        repo, tmp_path, "SubagentStart", {"hook_event_name": "SubagentStart", "agent_type": "x"}
    )

    records = _records(home)
    assert [run.exit_code for run in runs] == [0, 0]
    assert [record["event"] for record in records] == ["SubagentStart", "SubagentStart"]
    assert {Path(record["cwd"]).resolve() for record in records} == {cwd.resolve()}


def test_the_hook_sees_the_plugin_root_the_scratch_home_and_the_opt_outs(tmp_path):
    repo = _registration(tmp_path, {"SubagentStart": [{"matcher": "", "hooks": [_command()]}]})

    _, home, _, project = _deliver(
        repo, tmp_path, "SubagentStart", {"hook_event_name": "SubagentStart", "agent_type": "x"}
    )

    (record,) = _records(home)
    assert record["plugin_root"] == str(repo)
    assert record["project_dir"] == str(project)
    assert record["home"] == str(home)
    assert record["opt_outs"] == ["1", "1", "1"]


def test_session_credential_and_git_variables_never_reach_the_hook(tmp_path):
    repo = _registration(tmp_path, {"SubagentStart": [{"matcher": "", "hooks": [_command()]}]})

    _, home, _, _ = _deliver(
        repo, tmp_path, "SubagentStart", {"hook_event_name": "SubagentStart", "agent_type": "x"}
    )

    (record,) = _records(home)
    assert record["leaked"] == []


def test_a_bare_python3_in_a_hook_command_is_the_probes_own_interpreter(tmp_path):
    repo = _registration(tmp_path, {"SubagentStart": [{"matcher": "", "hooks": [_command()]}]})

    _, home, _, _ = _deliver(
        repo, tmp_path, "SubagentStart", {"hook_event_name": "SubagentStart", "agent_type": "x"}
    )

    (record,) = _records(home)
    assert Path(record["python3"]).resolve() == Path(sys.executable).resolve()


def test_a_command_that_fails_reports_its_exit_code_and_the_next_one_still_runs(tmp_path):
    failing = {"type": "command", "command": "exit 3", "timeout": 5}
    repo = _registration(
        tmp_path, {"SubagentStart": [{"matcher": "", "hooks": [failing, _command()]}]}
    )

    runs, home, _, _ = _deliver(
        repo, tmp_path, "SubagentStart", {"hook_event_name": "SubagentStart", "agent_type": "x"}
    )

    assert [run.exit_code for run in runs] == [3, 0]
    assert len(_records(home)) == 1


def test_a_command_past_its_timeout_reports_no_exit_code(tmp_path, monkeypatch):
    monkeypatch.setattr(hook_replay, "TIMEOUT_GRACE_S", 0)
    slow = {"type": "command", "command": "sleep 20", "timeout": 1}
    repo = _registration(tmp_path, {"SubagentStart": [{"matcher": "", "hooks": [slow]}]})

    runs, _, _, _ = _deliver(
        repo, tmp_path, "SubagentStart", {"hook_event_name": "SubagentStart", "agent_type": "x"}
    )

    assert [run.exit_code for run in runs] == [None]


def test_the_run_records_the_command_it_ran(tmp_path):
    repo = _registration(tmp_path, {"SubagentStart": [{"matcher": "", "hooks": [_command()]}]})

    runs, _, _, _ = _deliver(
        repo, tmp_path, "SubagentStart", {"hook_event_name": "SubagentStart", "agent_type": "x"}
    )

    assert runs[0].command == "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/rec.py"


# -- the payloads -----------------------------------------------------------------


def test_subagent_start_payload_has_the_harness_shape():
    payload = hook_replay.subagent_start_payload(
        session_id="s1", cwd=Path("/p/sub"), transcript_path=Path("/p/s1.jsonl"),
        agent_id="a1", agent_type="praxion:implementer",
    )  # fmt: skip

    assert payload == {
        "session_id": "s1",
        "cwd": "/p/sub",
        "hook_event_name": "SubagentStart",
        "transcript_path": "/p/s1.jsonl",
        "agent_id": "a1",
        "agent_type": "praxion:implementer",
    }


def test_agent_result_payload_has_the_harness_shape_for_a_completed_foreground_spawn():
    payload = hook_replay.agent_result_payload(
        session_id="s1", cwd=Path("/p/sub"), transcript_path=Path("/p/s1.jsonl"),
        tool_use_id="toolu_1", prompt="Task slug: x", agent_id="a1",
        agent_type="praxion:implementer",
    )  # fmt: skip

    assert payload["hook_event_name"] == "PostToolUse"
    assert payload["tool_name"] == "Agent"
    assert payload["tool_use_id"] == "toolu_1"
    assert payload["tool_input"] == {
        "prompt": "Task slug: x",
        "subagent_type": "praxion:implementer",
        "description": "liveness spawn",
        "run_in_background": False,
    }
    assert payload["tool_response"] == {
        "agentId": "a1",
        "status": "completed",
        "prompt": "Task slug: x",
    }
