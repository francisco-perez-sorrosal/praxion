"""Tests for the startup-payload probe's pure core: stream folding, target
selection, comparison, baseline bookkeeping and the invocation it builds.
No test here spawns a session; `run_target` is the only impure function and
it is exercised by hand (`--json`) rather than under pytest."""

from __future__ import annotations

import json
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
