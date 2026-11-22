"""Tests for the startup-payload probe: stream folding, target selection,
comparison, baseline bookkeeping and the invocation it builds. No test starts a
real session: `run_target`, the only impure function, runs against a stand-in
`claude` script put first on `PATH`."""

from __future__ import annotations

import json
import os
import stat
import sys
from pathlib import Path

import measure_startup_payload as msp
import pytest


def _line(event: dict) -> str:
    return json.dumps(event)


def _assistant(
    tokens: tuple, model: str, parent: str | None = None, subagent: str | None = None
) -> str:
    input_tokens, creation, read = tokens
    event = {
        "type": "assistant",
        "parent_tool_use_id": parent,
        "message": {
            "model": model,
            "usage": {
                "input_tokens": input_tokens,
                "cache_creation_input_tokens": creation,
                "cache_read_input_tokens": read,
            },
        },
    }
    if subagent:
        event["subagent_type"] = subagent
    return _line(event)


_INIT = _line({"type": "system", "subtype": "init", "claude_code_version": "2.1.296"})


# -- parse_stream --------------------------------------------------------------


def test_first_main_and_first_subagent_requests_are_read_once():
    lines = [
        _INIT,
        _assistant((2, 44_000, 11_000), "claude-fable-5-1"),
        _assistant((5, 100, 55_000), "claude-fable-5-1"),
        _assistant(
            (2, 37_300, 0), "claude-sonnet-5-5", parent="tu_1", subagent="praxion:researcher"
        ),
        _assistant(
            (9, 10, 37_300), "claude-sonnet-5-5", parent="tu_1", subagent="praxion:researcher"
        ),
    ]

    seen = msp.parse_stream(lines)

    assert seen.claude_code_version == "2.1.296"
    assert seen.main == msp.FirstRequest(55_002, 2, 44_000, 11_000, "claude-fable-5-1")
    assert seen.agents == {
        "praxion:researcher": msp.FirstRequest(37_302, 2, 37_300, 0, "claude-sonnet-5-5")
    }


def test_malformed_and_unrelated_lines_are_skipped():
    lines = [
        "not json",
        _line({"type": "system", "subtype": "hook_started"}),
        _line({"type": "assistant", "message": {"model": "m"}}),  # no usage block
        _line(["a", "list"]),
        _assistant((1, 2, 3), "m"),
    ]

    seen = msp.parse_stream(lines)

    assert seen.main == msp.FirstRequest(6, 1, 2, 3, "m")
    assert seen.claude_code_version is None


@pytest.mark.parametrize(
    "event",
    [
        pytest.param({"type": "assistant", "message": "text"}, id="a message that is a string"),
        pytest.param(
            {"type": "assistant", "message": ["a", "list"]}, id="a message that is a list"
        ),
        pytest.param(
            {"type": "assistant", "message": {"model": "m", "usage": {"input_tokens": None}}},
            id="a usage count that is not a number",
        ),
        pytest.param(
            {"type": "assistant", "message": {"model": "m", "usage": {"input_tokens": True}}},
            id="a usage count that is a boolean",
        ),
        pytest.param({"type": "user", "message": 7}, id="a tool result message that is a number"),
        pytest.param(
            {"type": "system", "subtype": "init", "mcp_servers": 3}, id="servers that are a number"
        ),
        pytest.param({"type": "result", "permission_denials": 3}, id="denials that are a number"),
        pytest.param(
            {"type": "result", "permission_denials": ["x"]}, id="a denial that is a string"
        ),
    ],
)
def test_a_malformed_event_is_skipped_and_the_stream_still_read(event: dict):
    seen = msp.parse_stream([_line(event), _assistant((1, 2, 3), "m")])

    assert seen.main == msp.FirstRequest(6, 1, 2, 3, "m")
    assert seen.agent_calls == {}
    assert seen.mcp_servers == {}


def test_absent_cache_counts_read_as_zero():
    usage = {"input_tokens": 4}

    seen = msp.parse_stream(
        [_line({"type": "assistant", "message": {"model": "m", "usage": usage}})]
    )

    assert seen.main == msp.FirstRequest(4, 4, 0, 0, "m")


def test_a_later_system_event_leaves_what_the_init_event_gave():
    servers = [{"name": "likec4", "status": "connected"}]
    init = {"type": "system", "subtype": "init", "claude_code_version": "2.1.330"}

    seen = msp.parse_stream(
        [
            _line({**init, "mcp_servers": servers}),
            _line({"type": "system", "subtype": "hook_started"}),
        ]
    )

    assert seen.claude_code_version == "2.1.330"
    assert seen.mcp_servers == {"likec4": "connected"}


def test_a_request_whose_message_names_no_model_records_an_empty_model():
    seen = msp.parse_stream(
        [_line({"type": "assistant", "message": {"usage": {"input_tokens": 1}}})]
    )

    assert seen.main == msp.FirstRequest(1, 1, 0, 0, "")


def test_a_subagent_request_without_its_type_is_kept_under_an_empty_name():
    message = {"model": "m", "usage": {"input_tokens": 2}}

    seen = msp.parse_stream(
        [_line({"type": "assistant", "parent_tool_use_id": "tu_1", "message": message})]
    )

    assert seen.agents == {"": msp.FirstRequest(2, 2, 0, 0, "m")}


def test_an_agent_call_whose_input_is_not_an_object_is_kept_with_no_subagent_type():
    block = {"type": "tool_use", "id": "tu_1", "name": "Agent", "input": "x"}

    seen = msp.parse_stream([_line({"type": "assistant", "message": {"content": [block]}})])

    assert seen.agent_calls == {"tu_1": ""}


# -- refused spawns --------------------------------------------------------------

REFUSAL = "The server-side auto mode classifier gave no verdict (error)"
SUBAGENT = "praxion:verifier"
REFUSED_PREFIX = f"the harness refused the session's Agent call for {SUBAGENT}: "


def _agent_call(call_id: str = "tu_1", subagent: str = SUBAGENT, name: str = "Agent") -> str:
    block = {"type": "tool_use", "id": call_id, "name": name, "input": {"subagent_type": subagent}}
    return _line({"type": "assistant", "message": {"content": [block]}})


def _tool_result(call_id: str, content: object, is_error: bool = True) -> str:
    block = {
        "type": "tool_result",
        "tool_use_id": call_id,
        "is_error": is_error,
        "content": content,
    }
    return _line({"type": "user", "message": {"content": [block]}})


def _result(denials: list | None = None) -> str:
    return _line({"type": "result", "subtype": "success", "permission_denials": denials or []})


def _denial(call_id: str = "tu_1", tool: str = "Agent") -> dict:
    return {"tool_name": tool, "tool_use_id": call_id}


def _agent_reading(lines: list, timeout: int = 5):
    seen = msp.parse_stream(lines)
    return msp.readings_for(seen, "agent:verifier", "praxion", timeout)["agent:verifier"]


def test_an_error_result_answering_an_agent_call_is_the_subagents_refusal():
    seen = msp.parse_stream([_agent_call(), _tool_result("tu_1", REFUSAL)])

    assert seen.agent_calls == {"tu_1": SUBAGENT}
    assert seen.refusals == {SUBAGENT: REFUSAL}


def test_only_the_first_refusal_of_a_subagent_is_kept():
    seen = msp.parse_stream(
        [
            _agent_call("tu_1"),
            _tool_result("tu_1", "first"),
            _agent_call("tu_2"),
            _tool_result("tu_2", "second"),
        ]
    )

    assert seen.refusals == {SUBAGENT: "first"}


def test_a_refusal_text_in_text_blocks_is_joined_on_one_line():
    blocks = [{"type": "text", "text": "line one\n  line two"}, {"type": "text", "text": "three"}]

    seen = msp.parse_stream([_agent_call(), _tool_result("tu_1", blocks)])

    assert seen.refusals == {SUBAGENT: "line one line two three"}


@pytest.mark.parametrize(
    "answer",
    [
        pytest.param(_tool_result("tu_1", "fine", is_error=False), id="a successful result"),
        pytest.param(_tool_result("tu_other", REFUSAL), id="an error answering another call"),
    ],
)
def test_a_result_that_refuses_no_agent_call_records_no_refusal(answer: str):
    seen = msp.parse_stream([_agent_call(), answer])

    assert seen.refusals == {}


def test_an_error_answering_a_call_to_another_tool_is_not_a_refusal():
    seen = msp.parse_stream([_agent_call(name="Bash"), _tool_result("tu_1", REFUSAL)])

    assert seen.agent_calls == {}
    assert seen.refusals == {}


def test_a_denial_in_the_result_event_is_a_refusal_when_no_error_result_gave_one():
    denials = [_denial(), _denial("tu_9"), _denial(tool="Bash")]

    seen = msp.parse_stream([_agent_call(), _result(denials)])

    assert seen.refusals == {SUBAGENT: msp.DENIED_WITHOUT_TEXT}


@pytest.mark.parametrize("content", ["", [], None, [{"type": "image"}]])
def test_an_error_result_without_text_is_a_refusal_the_stream_gives_no_text_for(content: object):
    reading = _agent_reading([_agent_call(), _tool_result("tu_1", content), _result()])

    assert reading.withheld == REFUSED_PREFIX + msp.DENIED_WITHOUT_TEXT


def test_a_denial_alone_names_the_refusal_without_a_text():
    reading = _agent_reading([_agent_call(), _result([_denial()])])

    assert reading.withheld == REFUSED_PREFIX + msp.DENIED_WITHOUT_TEXT


def test_a_refusal_the_error_result_gave_outranks_the_denial_entry():
    seen = msp.parse_stream([_agent_call(), _tool_result("tu_1", REFUSAL), _result([_denial()])])

    assert seen.refusals == {SUBAGENT: REFUSAL}


def test_the_session_has_ended_only_once_the_result_event_arrived():
    assert not msp.parse_stream([_assistant((1, 1, 1), "m")]).ended
    assert msp.parse_stream([_assistant((1, 1, 1), "m"), _result()]).ended


def test_a_spawn_that_follows_a_refused_call_is_a_reading():
    lines = [
        _agent_call("tu_1"),
        _tool_result("tu_1", REFUSAL),
        _agent_call("tu_2"),
        _assistant((2, 2, 2), "s", parent="tu_2", subagent=SUBAGENT),
        _result(),
    ]

    reading = _agent_reading(lines)

    assert reading.first_request.tokens == 6
    assert reading.withheld is None


def test_a_refused_spawn_names_the_refusal_and_its_text_and_not_the_timeout_once_ended():
    reading = _agent_reading([_agent_call(), _tool_result("tu_1", REFUSAL), _result()])

    assert reading.first_request is None
    assert reading.withheld == REFUSED_PREFIX + REFUSAL


def test_a_refused_spawn_in_a_session_still_running_also_names_the_timeout():
    reading = _agent_reading([_agent_call(), _tool_result("tu_1", REFUSAL)], timeout=9)

    assert reading.withheld == REFUSED_PREFIX + REFUSAL + "; no spawn within 9s"


def test_a_refusal_longer_than_the_bound_is_cut_with_a_visible_mark():
    long_text = "x" * (msp.REFUSAL_TEXT_CHARS + 50)

    reading = _agent_reading([_agent_call(), _tool_result("tu_1", long_text), _result()])

    assert reading.withheld == REFUSED_PREFIX + "x" * msp.REFUSAL_TEXT_CHARS + msp.CUT_MARK


def test_a_refusal_exactly_at_the_bound_is_carried_whole():
    text = "y" * msp.REFUSAL_TEXT_CHARS

    reading = _agent_reading([_agent_call(), _tool_result("tu_1", text), _result()])

    assert reading.withheld == REFUSED_PREFIX + text


def test_a_session_that_ended_without_spawning_is_not_said_to_have_timed_out():
    reading = _agent_reading([_assistant((1, 1, 1), "m"), _result()], timeout=9)

    assert reading.withheld == f"the session ended without spawning {SUBAGENT}"


def test_a_spawn_is_no_reason_to_withhold():
    spawned = msp.Spawned(msp.FirstRequest.from_usage({}, "m"))

    with pytest.raises(AssertionError):
        msp.withheld_reason(spawned, SUBAGENT, ended=True, timeout=9)


def test_a_session_that_has_not_ended_is_withheld_for_the_timeout():
    reading = _agent_reading([_assistant((1, 1, 1), "m")], timeout=9)

    assert reading.withheld == f"the session spawned no {SUBAGENT} within 9s"


def test_a_main_target_whose_session_ended_without_a_first_request_is_not_said_to_have_timed_out():
    readings = msp.readings_for(msp.parse_stream([_result()]), "main", "praxion", timeout=7)

    assert readings["main"].withheld == "the session ended without a first request"


# -- target selection ------------------------------------------------------------


def test_main_target_is_satisfied_by_the_session_first_request():
    seen = msp.parse_stream([_assistant((1, 1, 1), "m")])

    assert msp.target_satisfied(seen, "main", "praxion")
    assert not msp.target_satisfied(seen, "agent:verifier", "praxion")


def test_agent_target_needs_the_named_subagent():
    seen = msp.parse_stream(
        [
            _assistant((1, 1, 1), "m"),
            _assistant((1, 1, 1), "m", parent="t", subagent="praxion:verifier"),
        ]
    )

    assert msp.target_satisfied(seen, "agent:verifier", "praxion")
    assert not msp.target_satisfied(seen, "agent:researcher", "praxion")


def test_an_agent_run_yields_the_main_reading_too():
    seen = msp.parse_stream(
        [
            _assistant((1, 1, 1), "m"),
            _assistant((2, 2, 2), "s", parent="t", subagent="praxion:verifier"),
        ]
    )

    readings = msp.readings_for(seen, "agent:verifier", "praxion", timeout=5)

    assert readings["main"].first_request.tokens == 3
    assert readings["agent:verifier"].first_request.tokens == 6


def test_a_missing_subagent_is_withheld_with_a_reason_never_zero():
    seen = msp.parse_stream([_assistant((1, 1, 1), "m")])

    readings = msp.readings_for(seen, "agent:verifier", "praxion", timeout=5)

    assert readings["agent:verifier"].first_request is None
    assert "praxion:verifier" in readings["agent:verifier"].withheld
    assert readings["agent:verifier"].to_json() == {"withheld": readings["agent:verifier"].withheld}


def test_an_empty_stream_withholds_main():
    readings = msp.readings_for(msp.parse_stream([]), "main", "praxion", timeout=7)

    assert readings["main"].withheld == "no first request within 7s"


# -- compare ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("now", "verdict"),
    [(67_000, "regression"), (65_000, "stable"), (60_000, "saving"), (65_900, "stable")],
)
def test_delta_verdict_follows_the_tolerance(now, verdict):
    rows = msp.compare(
        {"main": {"tokens": 65_000}}, {"main": {"tokens": now}}, tolerance_percent=2.0
    )

    assert rows == [
        {"target": "main", "before": 65_000, "now": now, "delta": now - 65_000, "verdict": verdict}
    ]


def test_a_withheld_or_missing_side_is_skipped_not_judged():
    rows = msp.compare(
        {"main": {"tokens": 1}, "agent:a": {"tokens": 1}},
        {"main": {"withheld": "no first request within 1s"}, "agent:b": {"tokens": 1}},
        tolerance_percent=2.0,
    )

    by_target = {row["target"]: row for row in rows}
    assert by_target["main"] == {
        "target": "main",
        "verdict": "skipped",
        "reason": "no first request within 1s",
    }
    assert by_target["agent:a"]["verdict"] == "skipped"
    assert by_target["agent:b"] == {
        "target": "agent:b",
        "verdict": "skipped",
        "reason": "no baseline reading",
    }


# -- cwd classification -----------------------------------------------------------


def test_the_praxion_checkout_is_recognised_by_its_plugin_manifest(tmp_path: Path):
    (tmp_path / ".claude-plugin").mkdir()
    (tmp_path / ".claude-plugin" / "plugin.json").write_text(json.dumps({"name": "praxion"}))
    (tmp_path / ".ai-state").mkdir()

    assert msp.classify_cwd(tmp_path) == "praxion-repo"


def test_a_project_with_ai_state_is_managed(tmp_path: Path):
    (tmp_path / ".ai-state").mkdir()

    assert msp.classify_cwd(tmp_path) == "managed"


def test_anything_else_is_unmanaged(tmp_path: Path):
    (tmp_path / ".claude-plugin").mkdir()
    (tmp_path / ".claude-plugin" / "plugin.json").write_text("{not json")

    assert msp.classify_cwd(tmp_path) == "unmanaged"


# -- invocation --------------------------------------------------------------------


def test_main_invocation_is_a_one_word_headless_stream():
    argv = msp.build_invocation("main", msp.Profile("managed", "sonnet"), "praxion")

    assert argv[:3] == ["claude", "-p", msp.MAIN_PROMPT]
    assert "stream-json" in argv
    assert "--verbose" in argv
    assert "--setting-sources" not in argv
    assert "--strict-mcp-config" not in argv


def test_agent_invocation_names_the_namespaced_subagent():
    argv = msp.build_invocation("agent:verifier", msp.Profile("managed", "opus"), "praxion")

    assert 'subagent_type "praxion:verifier"' in argv[2]
    assert argv[argv.index("--model") + 1] == "opus"


def test_isolation_flags_pass_through_and_plugin_dir_disables_the_marketplace_copy():
    profile = msp.Profile(
        "unmanaged", "sonnet", setting_sources="", strict_mcp_config=True, plugin_dir="/wt"
    )

    argv = msp.build_invocation("main", profile, "praxion")

    assert argv[argv.index("--setting-sources") + 1] == ""
    assert "--strict-mcp-config" in argv
    assert argv[argv.index("--plugin-dir") + 1] == "/wt"
    overlay = json.loads(argv[argv.index("--settings") + 1])
    assert overlay == {"enabledPlugins": {msp.MARKETPLACE_PLUGIN_KEY: False}}


def test_profile_key_separates_every_axis():
    base = msp.Profile("managed", "sonnet")

    assert base.key == "managed|sonnet|default|mcp|installed"
    assert msp.Profile("managed", "sonnet", strict_mcp_config=True).key != base.key
    assert msp.Profile("managed", "sonnet", plugin_dir="/x").key != base.key
    assert msp.Profile("managed", "sonnet", setting_sources="").key != base.key


# -- baseline ------------------------------------------------------------------------


def _reading(key: str, targets: dict) -> dict:
    return {
        "date": "2026-10-11",
        "claude_code_version": "2.1.296",
        "profile": {"key": key, "cwd_kind": "managed", "model": "sonnet"},
        "targets": targets,
    }


def test_recording_replaces_the_profile_entry_and_keeps_withheld_targets_out():
    baseline = {
        "schema": 1,
        "profiles": {"k": {"recorded": "2026-01-01", "targets": {"main": {"tokens": 1}}}},
    }

    updated = msp.record_reading(
        baseline, _reading("k", {"main": {"tokens": 2}, "agent:x": {"withheld": "no spawn"}})
    )

    entry = updated["profiles"]["k"]
    assert entry["recorded"] == "2026-10-11"
    assert entry["targets"] == {"main": {"tokens": 2}}


def test_recording_merges_targets_measured_on_different_days():
    baseline = {
        "schema": 1,
        "profiles": {"k": {"recorded": "2026-01-01", "targets": {"agent:a": {"tokens": 5}}}},
    }

    updated = msp.record_reading(baseline, _reading("k", {"main": {"tokens": 2}}))

    assert updated["profiles"]["k"]["targets"] == {"agent:a": {"tokens": 5}, "main": {"tokens": 2}}


def test_baseline_round_trips_and_rejects_a_foreign_schema(tmp_path: Path):
    path = tmp_path / "startup_baseline.json"
    msp.write_baseline(
        path, msp.record_reading(msp.load_baseline(path), _reading("k", {"main": {"tokens": 3}}))
    )

    assert msp.load_baseline(path)["profiles"]["k"]["targets"]["main"]["tokens"] == 3

    path.write_text(json.dumps({"schema": 99}))
    with pytest.raises(ValueError, match="startup baseline"):
        msp.load_baseline(path)


def test_agent_names_come_from_frontmatter(tmp_path: Path):
    agents = tmp_path / "agents"
    agents.mkdir()
    (agents / "verifier.md").write_text("---\nname: verifier\ndescription: x\n---\nbody\n")
    (agents / "README.md").write_text("# catalog\n")
    (agents / "CLAUDE.md").write_text("notes\n")

    assert msp.agent_names(tmp_path) == ["verifier"]


def test_mcp_server_statuses_are_read_off_the_init_event():
    """The MCP block is the one startup item that varies run to run (a server
    connecting or not in time), so a reading names each server's status."""
    init = _line(
        {
            "type": "system",
            "subtype": "init",
            "claude_code_version": "2.1.296",
            "mcp_servers": [
                {"name": "likec4", "status": "connected"},
                {"name": "ide", "status": "failed"},
            ],
        }
    )

    seen = msp.parse_stream([init])

    assert seen.mcp_servers == {"likec4": "connected", "ide": "failed"}


# -- the subscription token -----------------------------------------------------------

TOKEN = "sk-ant-oat01-unit-test-token-0042"


def _token_file(tmp_path: Path, content: str | bytes | None = TOKEN + "\n") -> Path:
    path = tmp_path / "session-token"
    if isinstance(content, str):
        path.write_text(content, encoding="utf-8")
    elif content is not None:
        path.write_bytes(content)
    return path


def test_the_token_is_the_files_text_without_its_surrounding_whitespace(tmp_path: Path):
    assert msp.read_session_token(_token_file(tmp_path, f"\n  {TOKEN}  \n")) == TOKEN


@pytest.mark.parametrize(
    ("content", "reason"),
    [
        (None, "does not exist"),
        ("", "is blank"),
        (" \n\t\n", "is blank"),
        (b"\xff\xfe" + TOKEN.encode(), "is not text"),
    ],
    ids=["missing", "empty", "whitespace", "binary"],
)
def test_an_unusable_token_file_is_refused_naming_the_file_and_never_its_content(
    tmp_path: Path, content: str | bytes | None, reason: str
):
    path = _token_file(tmp_path, content)

    with pytest.raises(msp.TokenFileError) as refused:
        msp.read_session_token(path)

    assert str(refused.value) == f"{path}: the token file {reason}"


@pytest.mark.skipif(
    not hasattr(os, "geteuid") or os.geteuid() == 0, reason="root reads a file whatever its mode"
)
def test_an_unreadable_token_file_is_refused_with_the_systems_reason(tmp_path: Path):
    path = _token_file(tmp_path)
    path.chmod(0)

    with pytest.raises(msp.TokenFileError) as refused:
        msp.read_session_token(path)

    assert str(refused.value) == f"{path}: the token file cannot be read (Permission denied)"
    assert TOKEN not in str(refused.value)
    path.chmod(stat.S_IRUSR | stat.S_IWUSR)


def test_a_session_with_a_token_holds_it_as_its_only_credential():
    inherited = {
        "ANTHROPIC_API_KEY": "key",
        "ANTHROPIC_AUTH_TOKEN": "auth",
        msp.OAUTH_VARIABLE: "someone-elses",
        "PATH": "/bin",
    }

    env = msp.session_environment(inherited, TOKEN)

    assert env == {msp.OAUTH_VARIABLE: TOKEN, "PATH": "/bin"}
    assert inherited["ANTHROPIC_API_KEY"] == "key", "the inherited environment is left alone"


def test_a_session_without_a_token_inherits_its_environment_but_an_empty_oauth_variable():
    inherited = {"ANTHROPIC_API_KEY": "key", msp.OAUTH_VARIABLE: "", "PATH": "/bin"}

    assert msp.session_environment(inherited, None) == {"ANTHROPIC_API_KEY": "key", "PATH": "/bin"}
    kept = {msp.OAUTH_VARIABLE: "ambient"}
    assert msp.session_environment(kept, None) == kept


def test_redaction_removes_every_occurrence_and_leaves_text_alone_without_a_token():
    text = f"a {TOKEN} b {TOKEN}"

    assert msp.redact(text, TOKEN) == f"a {msp.REDACTED} b {msp.REDACTED}"
    assert msp.redact(text, None) == text


def test_the_subscription_route_is_a_profile_axis_and_absent_otherwise():
    ambient = msp.Profile("managed", "sonnet")
    subscription = msp.Profile("managed", "sonnet", credential=msp.SUBSCRIPTION_CREDENTIAL)

    assert subscription.key == ambient.key + "|subscription"
    assert subscription.to_json()["credential"] == "subscription"
    assert "credential" not in ambient.to_json()
    assert ambient.to_json()["key"] == ambient.key


_STAND_IN = """#!{python}
import os, sys
token = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN", "")
sys.stderr.write("x" * {pad} + token + "\\n")
"""


def _stand_in_claude(tmp_path: Path, monkeypatch, template: str = _STAND_IN, **fields) -> None:
    script = tmp_path / "bin" / "claude"
    script.parent.mkdir()
    script.write_text(template.format(python=sys.executable, **fields))
    script.chmod(0o755)
    monkeypatch.setenv("PATH", f"{script.parent}{os.pathsep}{os.environ['PATH']}")


@pytest.mark.parametrize("pad", [0, msp.STDERR_TAIL_CHARS - len(TOKEN) // 2, 2000])
def test_a_token_a_session_echoes_is_in_no_part_of_the_stderr_tail(
    tmp_path: Path, monkeypatch, pad: int
):
    _stand_in_claude(tmp_path, monkeypatch, pad=pad)

    _, tail = msp.run_target(
        msp.MAIN_TARGET, msp.Profile("unmanaged", "sonnet"), tmp_path, "praxion", 30, TOKEN
    )

    assert tail.count(msp.REDACTED) == 1
    assert not any(TOKEN[:n] in tail for n in (8, 14, len(TOKEN)))


def test_the_session_receives_the_token_in_its_environment(tmp_path: Path, monkeypatch):
    _stand_in_claude(tmp_path, monkeypatch, pad=0)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "operator-key")

    _, tail = msp.run_target(
        msp.MAIN_TARGET, msp.Profile("unmanaged", "sonnet"), tmp_path, "praxion", 30, TOKEN
    )

    assert tail.strip() == msp.REDACTED, "the stand-in saw no token in its environment"


_SLOW_STAND_IN = """#!{python}
import json, time
print(json.dumps({{"type": "assistant", "message": {{"model": "m", "usage": {{}}}}}}), flush=True)
time.sleep({pause})
print(json.dumps({{"type": "result", "subtype": "success"}}), flush=True)
"""


@pytest.mark.parametrize(
    ("pause", "timeout", "ended"),
    [
        pytest.param(0, 30, True, id="a result inside the timeout ends the session"),
        pytest.param(3, 1, False, id="a result after the timeout does not"),
    ],
)
def test_a_result_event_ends_the_session_only_when_it_came_inside_the_timeout(
    tmp_path: Path, monkeypatch, pause: int, timeout: int, ended: bool
):
    _stand_in_claude(tmp_path, monkeypatch, _SLOW_STAND_IN, pause=pause)

    seen, _ = msp.run_target(
        "agent:verifier", msp.Profile("unmanaged", "sonnet"), tmp_path, "praxion", timeout
    )

    assert seen.ended is ended


# Prints one event, then, unless it is stopped first, lives on and leaves a file behind.
_LINGERING_STAND_IN = """#!{python}
import json, pathlib, signal, time
if {ignore_term}:
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
print(json.dumps({event}), flush=True)
time.sleep({pause})
pathlib.Path({outlived!r}).touch()
"""

_SUBAGENT_REQUEST = {
    "type": "assistant",
    "parent_tool_use_id": "tu_1",
    "subagent_type": "praxion:verifier",
    "message": {"model": "m", "usage": {"input_tokens": 3}},
}


def _lingering(tmp_path: Path, monkeypatch, event: dict, ignore_term: bool = False) -> Path:
    outlived = tmp_path / "outlived"
    _stand_in_claude(
        tmp_path,
        monkeypatch,
        _LINGERING_STAND_IN,
        event=repr(event),
        pause=5,
        outlived=str(outlived),
        ignore_term=ignore_term,
    )
    return outlived


def test_a_result_inside_the_timeout_ends_the_reading_and_the_session_there(
    tmp_path: Path, monkeypatch
):
    outlived = _lingering(tmp_path, monkeypatch, {"type": "result", "subtype": "success"})

    seen, _ = msp.run_target(
        "agent:verifier", msp.Profile("unmanaged", "sonnet"), tmp_path, "praxion", 1
    )

    assert seen.ended is True
    assert not outlived.exists(), "the session outlived its result: it was not stopped there"


def test_the_targets_first_request_ends_the_reading_and_the_session_there(
    tmp_path: Path, monkeypatch
):
    outlived = _lingering(tmp_path, monkeypatch, _SUBAGENT_REQUEST)

    seen, _ = msp.run_target(
        "agent:verifier", msp.Profile("unmanaged", "sonnet"), tmp_path, "praxion", 30
    )

    assert seen.agents == {"praxion:verifier": msp.FirstRequest(3, 3, 0, 0, "m")}
    assert not outlived.exists(), "the session outlived the target's first request"


def test_a_session_that_ignores_the_stop_signal_is_killed_after_the_grace(
    tmp_path: Path, monkeypatch
):
    outlived = _lingering(tmp_path, monkeypatch, {"type": "result"}, ignore_term=True)
    monkeypatch.setattr(msp, "STOP_GRACE_SECONDS", 0.2)

    seen, _ = msp.run_target(
        "agent:verifier", msp.Profile("unmanaged", "sonnet"), tmp_path, "praxion", 30
    )

    assert seen.ended is True
    assert not outlived.exists(), "the session that ignored the stop signal was not killed"


_RECORDING_STAND_IN = """#!{python}
import json, os, pathlib, sys
pathlib.Path({record!r}).write_text(json.dumps({{"cwd": os.getcwd(), "argv": sys.argv[1:]}}))
"""


def test_the_session_runs_the_built_invocation_in_the_directory_it_is_given(
    tmp_path: Path, monkeypatch
):
    record = tmp_path / "record.json"
    _stand_in_claude(tmp_path, monkeypatch, _RECORDING_STAND_IN, record=str(record))
    workdir = tmp_path / "project"
    workdir.mkdir()
    profile = msp.Profile("unmanaged", "sonnet")

    seen, _ = msp.run_target("agent:verifier", profile, workdir, "praxion", 30)

    recorded = json.loads(record.read_text())
    assert Path(recorded["cwd"]).resolve() == workdir.resolve()
    assert recorded["argv"] == msp.build_invocation("agent:verifier", profile, "praxion")[1:]
    assert seen == msp.StreamObservation()


def _run_main(tmp_path: Path, monkeypatch, capsys, *extra: str):
    seen = {}

    def fake_measure(targets, profile, cwd, namespace, timeout, today, token=None):
        seen.update(profile=profile, token=token, call=(targets, namespace, timeout, today))
        return {"targets": {}, "claude_code_version": None, "date": "d", "profile": {}}

    monkeypatch.setattr(msp, "measure", fake_measure)
    monkeypatch.setattr(msp.shutil, "which", lambda name: "/stand-in/claude")
    code = msp.main(["main", "--empty-dir", "--json", "--repo-root", str(tmp_path), *extra])
    return code, seen, capsys.readouterr()


def test_the_token_file_sets_the_token_and_the_profile_route_of_the_run(
    tmp_path: Path, monkeypatch, capsys
):
    path = _token_file(tmp_path)

    code, seen, output = _run_main(
        tmp_path, monkeypatch, capsys, "--session-oauth-token-file", str(path)
    )

    assert code == 0
    assert seen["token"] == TOKEN
    targets, namespace, timeout, today = seen["call"]
    assert (targets, namespace, timeout) == (["main"], "praxion", msp.DEFAULT_TIMEOUT_SECONDS)
    assert today == msp.date.today()
    assert seen["profile"].credential == msp.SUBSCRIPTION_CREDENTIAL
    assert TOKEN not in output.out + output.err


def test_a_run_without_the_option_has_no_token_and_the_ambient_route(
    tmp_path: Path, monkeypatch, capsys
):
    code, seen, _ = _run_main(tmp_path, monkeypatch, capsys)

    assert code == 0
    assert seen["token"] is None
    assert seen["profile"].credential is None


def test_a_refused_token_file_stops_the_run_before_any_session(tmp_path: Path, monkeypatch, capsys):
    path = _token_file(tmp_path, "")

    code, seen, output = _run_main(
        tmp_path, monkeypatch, capsys, "--session-oauth-token-file", str(path)
    )

    assert code == 2
    assert seen == {}, "a session was measured"
    assert output.err.strip() == f"measure_startup_payload: {path}: the token file is blank"
