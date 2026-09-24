"""Behavioral tests for the envelope recorder's safety checks.

The recorder spends money, so its `main()` never runs here. These tests load
the script by path and exercise only the pure decisions that guard a paid
recording: fixture repos a session can commit in, the secret scan, the
refusal to keep an errored or breached envelope, the per-scenario Bash
allowlists, and the recorder's spend cap. No `claude` process is started.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "record_live_envelopes.py"
_MODULE_NAME = "record_live_envelopes"
_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "live_scenarios"
_PREFLIGHT_COPY_ROOT = Path(
    "/private/tmp/claude-501/-Users-operator-dev-praxion/"
    "ecca6863-b00e-4005-a781-2c1ba6e8cd2f/scratchpad/probe1/target"
)
_BROAD_BASH = {"Bash", "Bash(*)", "Bash(git *)", "Bash(python3 *)", "Bash(python *)"}


@pytest.fixture(scope="module")
def recorder() -> ModuleType:
    spec = importlib.util.spec_from_file_location(_MODULE_NAME, _SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[_MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


def _envelope(name: str):
    from praxion_evals.live.session import parse_stream

    return parse_stream((_FIXTURES_DIR / f"{name}.stream.jsonl").read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Fixture repos carry their own identity
# ---------------------------------------------------------------------------


def test_fixture_repo_accepts_a_commit_with_an_empty_sandbox_home(recorder, tmp_path):
    """The session's own `git commit` must land even though the sandbox HOME
    holds no git identity — so the identity lives in the repo, not in HOME."""
    repo = tmp_path / "fixture"
    recorder._init_repo(repo, {"a.txt": "a\n"})
    (repo / "a.txt").write_text("b\n", encoding="utf-8")
    empty_home = tmp_path / "home"
    empty_home.mkdir()
    env = {
        "PATH": "/usr/bin:/bin",
        "HOME": str(empty_home),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": str(empty_home / ".gitconfig"),
    }

    done = subprocess.run(
        ["git", "commit", "-q", "-am", "session commit"],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert done.returncode == 0, done.stderr
    assert not (empty_home / ".gitconfig").exists()


# ---------------------------------------------------------------------------
# Secret scan
# ---------------------------------------------------------------------------


def test_secret_scan_rejects_an_sk_ant_shaped_substring(recorder):
    assert recorder._leaked_secret('{"k":"sk-ant-abc123"}', {}) is not None


def test_secret_scan_rejects_a_live_credential_value_without_revealing_it(recorder):
    """A gateway bearer has no fixed prefix; only its literal value identifies it."""
    credentials = {"ANTHROPIC_AUTH_TOKEN": "eyJhbGciOi.gateway-bearer-XYZ"}

    label = recorder._leaked_secret("env: eyJhbGciOi.gateway-bearer-XYZ", credentials)

    assert label is not None
    assert "ANTHROPIC_AUTH_TOKEN" in label
    assert "gateway-bearer" not in label


def test_secret_scan_passes_clean_output_and_ignores_empty_credentials(recorder):
    assert recorder._leaked_secret('{"type":"result"}', {"ANTHROPIC_API_KEY": ""}) is None


def test_credential_values_come_only_from_the_three_credential_variables(recorder):
    environ = {"ANTHROPIC_API_KEY": "k1", "CLAUDE_CODE_OAUTH_TOKEN": "", "PATH": "/usr/bin"}

    assert recorder._credential_values(environ) == {"ANTHROPIC_API_KEY": "k1"}


def test_console_output_redacts_credential_values(recorder):
    redacted = recorder._redact("stderr: bad key k1-secret", {"ANTHROPIC_API_KEY": "k1-secret"})

    assert "k1-secret" not in redacted
    assert "ANTHROPIC_API_KEY" in redacted


# ---------------------------------------------------------------------------
# Only envelopes of the expected outcome, from isolated sessions, are kept
# ---------------------------------------------------------------------------


def _run(stdout: str, exit_code: int | None):
    from praxion_evals.live.session import SessionRun

    return SessionRun(stdout=stdout, stderr="", exit_code=exit_code)


def test_a_clean_isolated_scenario_session_may_be_written(recorder):
    envelope = _envelope("isolated_marker_preflight_sonnet")
    shape = recorder.SHAPES["commit_staging"]

    assert recorder._write_refusal(shape, envelope, _run("", 0), _PREFLIGHT_COPY_ROOT) is None


def test_a_breached_scenario_session_is_never_written(recorder):
    envelope = _envelope("ambient_control_sonnet")
    shape = recorder.SHAPES["commit_staging"]

    refusal = recorder._write_refusal(shape, envelope, _run("", 0), _PREFLIGHT_COPY_ROOT)

    assert refusal is not None
    assert "isolation_breach" in refusal


def test_an_errored_scenario_session_is_never_written(recorder):
    envelope = _envelope("isolated_marker_preflight_sonnet")
    shape = recorder.SHAPES["lightweight_fix"]

    refusal = recorder._write_refusal(shape, envelope, _run("", None), _PREFLIGHT_COPY_ROOT)

    assert refusal is not None
    assert "timeout" in refusal


def test_an_error_shape_is_written_only_when_it_produced_its_error(recorder):
    """The invalid-flag shape exists to capture a non-zero exit with no
    stream; a session that happened to succeed is not that shape."""
    from praxion_evals.live.session import parse_stream

    shape = recorder.SHAPES["error_invalid_flag"]
    failed = recorder._write_refusal(shape, parse_stream(""), _run("", 1), _PREFLIGHT_COPY_ROOT)
    succeeded = recorder._write_refusal(
        shape, _envelope("isolated_marker_preflight_sonnet"), _run("", 0), _PREFLIGHT_COPY_ROOT
    )

    assert failed is None
    assert succeeded is not None


def test_an_error_shape_from_a_breached_session_is_never_written(recorder):
    """A budget stop is only a useful fixture if the session was isolated."""
    import dataclasses

    from praxion_evals.live.session import ResultInfo

    ambient = _envelope("ambient_control_sonnet")
    budget_stop = dataclasses.replace(
        ambient,
        final_result=ResultInfo(
            result_text=None,
            structured_output=None,
            is_error=True,
            subtype="error_max_budget_usd",
            total_cost_usd=0.1,
            session_id="s",
        ),
    )
    shape = recorder.SHAPES["error_budget_stop"]

    refusal = recorder._write_refusal(shape, budget_stop, _run("", 1), _PREFLIGHT_COPY_ROOT)

    assert refusal is not None
    assert "isolation_breach" in refusal


# ---------------------------------------------------------------------------
# Narrow Bash allowlists
# ---------------------------------------------------------------------------


def test_no_shape_grants_unrestricted_execution(recorder):
    granted = {tool for shape in recorder.SHAPES.values() for tool in shape.allowed_tools}

    assert granted.isdisjoint(_BROAD_BASH), sorted(granted & _BROAD_BASH)


def test_commit_staging_can_stage_and_commit_but_nothing_else_in_git(recorder):
    tools = set(recorder.SHAPES["commit_staging"].allowed_tools)
    git_tools = {tool for tool in tools if "git" in tool}

    assert {"Bash(git add *)", "Bash(git commit *)"} <= tools
    assert all(tool.startswith("Bash(git ") for tool in git_tools)


def test_commit_staging_also_grants_the_harmless_inspection_utilities(recorder):
    from praxion_evals.live.scenarios import HARMLESS_UTILITIES

    tools = set(recorder.SHAPES["commit_staging"].allowed_tools)

    assert set(HARMLESS_UTILITIES) <= tools


def test_lightweight_fix_can_run_its_tests_only_through_pytest(recorder):
    tools = set(recorder.SHAPES["lightweight_fix"].allowed_tools)

    assert "Bash(python3 -m pytest *)" in tools
    assert not {tool for tool in tools if tool.startswith("Bash(python3") and "pytest" not in tool}


# ---------------------------------------------------------------------------
# Spend cap
# ---------------------------------------------------------------------------


def test_recorder_spend_cap_defaults_to_ten_dollars(recorder):
    args = recorder._parse_args(["--output-dir", "out"])

    assert args.max_total_usd == 10.0
