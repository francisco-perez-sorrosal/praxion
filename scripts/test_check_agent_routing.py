"""Tests for the routing check's pure core: answer parsing, judging a case
against its expectation and near misses, the baseline comparison, the case
file loader and the invocation. Nothing here spawns a session."""

from __future__ import annotations

import json
from pathlib import Path

import check_agent_routing as car
import pytest

# -- Route.parse ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("agent:praxion:verifier", car.Route("agent", "verifier")),
        ("`agent:verifier`", car.Route("agent", "verifier")),
        ("Agent:Praxion:Verifier\n", car.Route("agent", "verifier")),
        ("skill:praxion:roadmap-planning", car.Route("skill", "roadmap-planning")),
        ("none", car.Route("none")),
        ("I would use agent:verifier for this.", None),
        ("agent:", None),
        ("", None),
    ],
)
def test_an_answer_is_one_line_of_kind_and_final_name(text, expected):
    assert car.Route.parse(text) == expected


def test_a_stated_answer_wins_over_a_denied_tool_call():
    result = {
        "result": "agent:researcher",
        "permission_denials": [
            {"tool_name": "Agent", "tool_input": {"subagent_type": "praxion:verifier"}}
        ],
    }

    assert car.route_from_result(result) == car.Route("agent", "researcher")


def test_a_denied_agent_or_skill_call_is_read_as_the_answer():
    agent = {
        "result": "Let me delegate.",
        "permission_denials": [
            {"tool_name": "Agent", "tool_input": {"subagent_type": "praxion:verifier"}}
        ],
    }
    skill = {
        "result": "",
        "permission_denials": [
            {"tool_name": "Skill", "tool_input": {"skill": "praxion:roadmap-planning"}}
        ],
    }
    other = {
        "result": "Sure.",
        "permission_denials": [{"tool_name": "Bash", "tool_input": {"command": "ls"}}],
    }

    assert car.route_from_result(agent) == car.Route("agent", "verifier")
    assert car.route_from_result(skill) == car.Route("skill", "roadmap-planning")
    assert car.route_from_result(other) is None


# -- judge ---------------------------------------------------------------------------

_CASE = car.Case(
    "verifier-post-implementation",
    "check it",
    car.Route("agent", "verifier"),
    (car.Route("agent", "architect-validator"),),
)


def test_the_majority_route_matching_the_expectation_passes():
    row = car.judge(
        _CASE,
        [
            car.Route("agent", "verifier"),
            car.Route("agent", "verifier"),
            car.Route("agent", "sentinel"),
        ],
    )

    assert row["verdict"] == "pass"
    assert row["route"] == "agent:verifier"
    assert row["agreement"] == 0.67


def test_a_near_miss_is_a_confusion_not_a_miss():
    row = car.judge(_CASE, [car.Route("agent", "architect-validator")])

    assert row["verdict"] == "confusion"


def test_any_other_route_is_a_miss():
    row = car.judge(_CASE, [car.Route("none")])

    assert row["verdict"] == "miss"
    assert row["expect"] == "agent:verifier"


def test_no_readable_answer_is_unreadable_never_a_pass():
    row = car.judge(_CASE, [None, None])

    assert row["verdict"] == "unreadable"
    assert row["route"] is None


# -- compare -----------------------------------------------------------------------------


def test_compare_names_only_the_routes_that_changed():
    today = [
        {"id": "a", "route": "agent:verifier", "verdict": "pass"},
        {"id": "b", "route": "agent:sentinel", "verdict": "miss"},
        {"id": "c", "route": "none", "verdict": "pass"},
    ]

    changed = car.compare({"a": "agent:verifier", "b": "agent:verifier"}, today)

    assert changed == [
        {"id": "b", "before": "agent:verifier", "now": "agent:sentinel", "verdict": "miss"}
    ]


# -- cases file ------------------------------------------------------------------------------


def test_the_shipped_case_file_loads_and_covers_every_agent():
    repo_root = Path(__file__).resolve().parent.parent
    cases = car.load_cases(repo_root.joinpath(*car.CASES_RELATIVE_PATH))
    agents = {
        p.stem for p in (repo_root / "agents").glob("*.md") if p.stem not in {"README", "CLAUDE"}
    }

    # An agent reached through its user-invoked skill (skill-genesis) is covered
    # by the case whose expected route is that skill and whose near miss names it.
    named = {c.expect.name for c in cases} | {n.name for c in cases for n in c.near_miss}
    assert agents <= named, f"agents without a routing case: {sorted(agents - named)}"
    assert any(c.expect.kind == "none" for c in cases), "a direct-tier request must be a case too"


def test_an_unreadable_expectation_or_duplicate_id_is_refused(tmp_path: Path):
    bad_expect = tmp_path / "bad.json"
    bad_expect.write_text(json.dumps([{"id": "x", "request": "r", "expect": "agent:"}]))
    with pytest.raises(ValueError, match="unreadable expect"):
        car.load_cases(bad_expect)

    dupes = tmp_path / "dupes.json"
    dupes.write_text(json.dumps([{"id": "x", "request": "r", "expect": "none"}] * 2))
    with pytest.raises(ValueError, match="duplicate case ids"):
        car.load_cases(dupes)


# -- invocation ---------------------------------------------------------------------------------


def test_the_session_is_single_turn_with_delegation_denied_but_listed():
    argv = car.build_invocation(_CASE, "sonnet", None)

    assert argv[argv.index("--max-turns") + 1] == "1"
    settings = json.loads(argv[argv.index("--settings") + 1])
    assert set(settings["permissions"]["deny"]) >= {"Agent", "Skill"}
    assert "enabledPlugins" not in settings, "the installed plugin is the one measured by default"
    assert "--disallowedTools" not in argv, "a removed tool would take the agent listing with it"
    assert argv[2].endswith("Request: check it")


def test_a_plugin_dir_run_disables_the_marketplace_copy():
    argv = car.build_invocation(_CASE, "sonnet", "/wt")

    settings = json.loads(argv[argv.index("--settings") + 1])
    assert settings["enabledPlugins"] == {car.MARKETPLACE_PLUGIN_KEY: False}
    assert argv[argv.index("--plugin-dir") + 1] == "/wt"
