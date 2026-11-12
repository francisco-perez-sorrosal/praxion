"""Tests for the routing check's pure core: answer parsing, judging a case
against its expectation and near misses, the baseline comparison, the case
file loader and the invocation. Nothing here spawns a session."""

from __future__ import annotations

import json
import subprocess
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


# -- credentials and spend (the session launch is stubbed; nothing here is billed) ---------------

FAKE_TOKEN = "fake-oauth-token-for-tests"
OAUTH_VARIABLE = "CLAUDE_CODE_OAUTH_TOKEN"
API_KEY_VARIABLES = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")


class FakeClaude:
    """Stands in for `subprocess.run`: hands out the queued results and keeps each session's env."""

    def __init__(self, results: list):
        self._results = iter(results)
        self.envs: list = []

    def __call__(self, argv, **kwargs):
        self.envs.append(kwargs["env"])
        return subprocess.CompletedProcess(
            argv, 0, stdout=json.dumps(next(self._results)), stderr=""
        )


def _answer(route: str = "none", cost: float | None = None) -> dict:
    result = {"result": route}
    if cost is not None:
        result["total_cost_usd"] = cost
    return result


@pytest.fixture
def three_cases(tmp_path: Path) -> Path:
    path = tmp_path / "cases.json"
    cases = [{"id": name, "request": f"request {name}", "expect": "none"} for name in "abc"]
    path.write_text(json.dumps(cases))
    return path


@pytest.fixture
def token_file(tmp_path: Path) -> Path:
    path = tmp_path / "token"
    path.write_text(FAKE_TOKEN + "\n")
    return path


@pytest.fixture
def run_main(tmp_path: Path, three_cases: Path, monkeypatch, capsys):
    """Run `main` over the three cases with the given session results; returns (exit, out, err, claude)."""
    monkeypatch.setattr(car.shutil, "which", lambda name: "/stand-in/claude")
    for name in (OAUTH_VARIABLE, *API_KEY_VARIABLES):
        monkeypatch.delenv(name, raising=False)

    def run(results: list, *flags: str):
        claude = FakeClaude(results)
        monkeypatch.setattr(car.subprocess, "run", claude)
        argv = ["--repo-root", str(tmp_path), "--cases", str(three_cases), *flags]
        code = car.main(argv)
        captured = capsys.readouterr()
        return code, captured.out, captured.err, claude

    return run


def test_the_token_files_token_is_each_sessions_oauth_credential(run_main, token_file):
    _, _, _, claude = run_main([_answer()] * 3, "--session-oauth-token-file", str(token_file))

    assert [env[OAUTH_VARIABLE] for env in claude.envs] == [FAKE_TOKEN] * 3


def test_the_api_key_variables_do_not_reach_a_session_that_has_a_token(
    run_main, token_file, monkeypatch
):
    for name in API_KEY_VARIABLES:
        monkeypatch.setenv(name, "fake-api-credential")

    _, _, _, claude = run_main([_answer()] * 3, "--session-oauth-token-file", str(token_file))

    assert [set(API_KEY_VARIABLES) & set(env) for env in claude.envs] == [set()] * 3


def test_without_a_token_file_the_session_environment_is_inherited(run_main, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-api-credential")

    _, _, _, claude = run_main([_answer()] * 3)

    assert claude.envs[0]["ANTHROPIC_API_KEY"] == "fake-api-credential"
    assert OAUTH_VARIABLE not in claude.envs[0]


@pytest.mark.parametrize("flags", [(), ("--json",)])
def test_the_token_is_in_neither_stdout_nor_stderr(run_main, token_file, flags):
    echoed = _answer(f"agent:{FAKE_TOKEN}", 0.01)

    _, out, err, _ = run_main([echoed] * 3, "--session-oauth-token-file", str(token_file), *flags)

    assert FAKE_TOKEN not in out + err


@pytest.mark.parametrize("content", [None, "", "  \n"], ids=["missing", "empty", "blank"])
def test_an_unusable_token_file_is_a_usage_error_before_any_session(run_main, tmp_path, content):
    path = tmp_path / "token"
    if content is not None:
        path.write_text(content)

    code, _, err, claude = run_main([], "--session-oauth-token-file", str(path))

    assert code == 2
    assert claude.envs == []
    assert str(path) in err


@pytest.mark.parametrize("cap", ["0", "-1", "nan", "inf"])
def test_a_cap_that_is_not_a_positive_number_is_a_usage_error_before_any_session(run_main, cap):
    code, _, err, claude = run_main([], "--max-total-usd", cap)

    assert code == 2
    assert claude.envs == []
    assert "--max-total-usd" in err


def test_a_run_that_reaches_the_cap_starts_no_further_session(run_main):
    code, _, _, claude = run_main([_answer(cost=0.04)] * 3, "--max-total-usd", "0.05")

    assert len(claude.envs) == 2
    assert code == 3


def test_a_capped_run_names_the_cases_it_never_asked_and_says_it_stopped(run_main):
    _, out, _, _ = run_main([_answer(cost=0.04)] * 3, "--max-total-usd", "0.05")

    assert "stopped at the --max-total-usd cap of $0.05" in out
    assert "not asked (1): c" in out


def test_a_capped_run_reports_not_asked_in_json_and_has_no_row_for_them(run_main):
    _, out, _, _ = run_main([_answer(cost=0.04)] * 3, "--max-total-usd", "0.05", "--json")

    payload = json.loads(out)
    assert payload["stopped_at_cap"] is True
    assert payload["not_asked"] == ["c"]
    assert [row["id"] for row in payload["cases"]] == ["a", "b"]


def test_a_miss_found_before_the_cap_is_still_a_regression_not_a_capped_run(run_main):
    code, _, _, _ = run_main([_answer("agent:verifier", 0.06)] * 3, "--max-total-usd", "0.05")

    assert code == 1


def test_a_case_cut_short_of_its_repeats_is_not_asked(run_main):
    code, out, _, claude = run_main(
        [_answer(cost=0.06)] * 6, "--repeat", "2", "--max-total-usd", "0.05"
    )

    assert len(claude.envs) == 1
    assert "not asked (3): a, b, c" in out
    assert code == 3


def test_a_run_under_the_cap_is_unaffected(run_main):
    code, out, _, claude = run_main([_answer(cost=0.01)] * 3, "--max-total-usd", "10")

    assert len(claude.envs) == 3
    assert code == 0
    assert "not asked" not in out
    assert "stopped" not in out


def test_a_run_whose_last_session_reaches_the_cap_is_complete(run_main):
    code, out, _, _ = run_main([_answer(cost=0.05)] * 3, "--max-total-usd", "0.15")

    assert code == 0
    assert "stopped" not in out


def test_the_total_spend_is_reported_in_the_summary(run_main):
    _, out, _, _ = run_main([_answer(cost=c) for c in (0.04, 0.03, 0.02)])

    assert "spend: $0.0900 over 3 sessions" in out


def test_the_total_spend_is_reported_in_json(run_main):
    _, out, _, _ = run_main(
        [_answer(cost=c) for c in (0.04, 0.03, 0.02)], "--max-total-usd", "5", "--json"
    )

    assert json.loads(out)["spend"] == {
        "total_usd": 0.09,
        "sessions": 3,
        "unknown_cost_sessions": 0,
        "cap_usd": 5.0,
    }


def test_a_session_with_no_reported_cost_is_said_to_be_unknown_not_free(run_main):
    _, out, _, _ = run_main([_answer(cost=0.04), _answer(), _answer(cost=0.02)])

    assert "spend: $0.0600 over 3 sessions (1 reported no cost: the total is a lower bound)" in out


def test_a_session_with_no_reported_cost_is_counted_in_json(run_main):
    _, out, _, _ = run_main([_answer(cost=0.04), _answer(), _answer(cost=0.02)], "--json")

    spend = json.loads(out)["spend"]
    assert (spend["total_usd"], spend["unknown_cost_sessions"], spend["cap_usd"]) == (0.06, 1, None)
