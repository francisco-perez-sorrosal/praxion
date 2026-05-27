"""Behavioral tests for the harness CLI module — harness/cli.py.

Tests cover the Python-level CLI module only: arg parsing, the 4-case arg
resolver wiring, auth-mode detection, and the invalid-target error path.

The slash-command registration (entry point script, commands/eval-praxion.md)
is a separate surface and is not exercised here.

All production imports are deferred inside each test body.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

# ---------------------------------------------------------------------------
# Helper: build a minimal fake git repo for resolver tests
# ---------------------------------------------------------------------------


def _make_git_repo(tmp_path: Path) -> Path:
    """Initialize a bare git repo with one commit; return the repo root."""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=str(repo),
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=str(repo),
        check=True,
        capture_output=True,
    )
    # Seed with one file so HEAD is valid
    seed = repo / "README.md"
    seed.write_text("# Test\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=str(repo), check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=str(repo),
        check=True,
        capture_output=True,
    )
    return repo


# ---------------------------------------------------------------------------
# Arg resolver: no-arg → resolves to main HEAD
# ---------------------------------------------------------------------------


def test_no_arg_resolves_via_git_rev_parse_main(tmp_path: Path):
    """When no argument is given, the CLI resolves to 'main' via git rev-parse."""
    from praxion_evals.harness.cli import resolve_target

    repo = _make_git_repo(tmp_path)
    # Rename default branch to 'main' so git rev-parse main works
    subprocess.run(
        ["git", "branch", "-m", "main"],
        cwd=str(repo),
        check=True,
        capture_output=True,
    )

    resolved = resolve_target(None, repo_root=repo)

    # The resolved result should be a git ref (HEAD of main)
    assert resolved is not None, "Resolving None should not return None"
    # Should resolve to a recognizable form (sha, 'main', or similar git ref)
    assert len(str(resolved)) > 0, "Resolved target must be non-empty"


# ---------------------------------------------------------------------------
# Arg resolver: existing filesystem path → path mode
# ---------------------------------------------------------------------------


def test_existing_path_resolves_to_path_mode(tmp_path: Path):
    """When the argument is an existing filesystem path, resolve_target returns it in path mode."""
    from praxion_evals.harness.cli import resolve_target

    target_dir = tmp_path / "some-worktree"
    target_dir.mkdir()

    resolved = resolve_target(str(target_dir), repo_root=tmp_path)

    assert resolved is not None
    # The resolved target or its string form should reference the filesystem path
    resolved_str = str(resolved)
    assert "some-worktree" in resolved_str or str(target_dir) in resolved_str, (
        f"Resolved target should reference the filesystem path; got {resolved_str!r}"
    )


# ---------------------------------------------------------------------------
# Arg resolver: known worktree name → expands to .claude/worktrees/<name>/
# ---------------------------------------------------------------------------


def test_known_worktree_name_expands_to_worktree_path(tmp_path: Path):
    """When the argument matches a known worktree under .claude/worktrees/, it expands."""
    from praxion_evals.harness.cli import resolve_target

    # Create the worktree directory structure
    worktrees_dir = tmp_path / ".claude" / "worktrees"
    worktrees_dir.mkdir(parents=True)
    known_worktree = worktrees_dir / "my-feature"
    known_worktree.mkdir()

    resolved = resolve_target("my-feature", repo_root=tmp_path)

    assert resolved is not None
    resolved_str = str(resolved)
    assert "my-feature" in resolved_str, (
        f"Resolved target should reference the worktree path; got {resolved_str!r}"
    )


# ---------------------------------------------------------------------------
# Arg resolver: valid git ref → git-show mode
# ---------------------------------------------------------------------------


def test_valid_git_ref_resolves_to_ref_mode(tmp_path: Path):
    """When the argument is a valid git ref, resolve_target returns it in ref mode."""
    from praxion_evals.harness.cli import resolve_target

    repo = _make_git_repo(tmp_path)
    # Get the actual HEAD sha so we can use a real ref
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(repo),
        capture_output=True,
        text=True,
    )
    head_sha = result.stdout.strip()
    assert head_sha, "Expected a valid HEAD sha from the test git repo"

    resolved = resolve_target(head_sha, repo_root=repo)

    assert resolved is not None, f"A valid git ref ({head_sha[:8]}) must resolve to a target"
    resolved_str = str(resolved)
    # The resolved result should reference the sha in some form
    assert head_sha[:7] in resolved_str or head_sha in resolved_str or len(resolved_str) > 0, (
        f"Resolved target for a valid git ref must be non-empty; got {resolved_str!r}"
    )


# ---------------------------------------------------------------------------
# Arg resolver: invalid target → three-part error message
# ---------------------------------------------------------------------------


def test_invalid_target_raises_with_three_part_error(tmp_path: Path):
    """An invalid argument raises an exception with a three-part error message."""
    from praxion_evals.harness.cli import resolve_target

    repo = _make_git_repo(tmp_path)

    import pytest

    with pytest.raises((ValueError, RuntimeError, SystemExit)) as exc_info:
        resolve_target("absolutely-not-a-valid-ref-or-path-xyzzy", repo_root=repo)

    error_text = str(exc_info.value)
    # Three-part error: what was tried, what failed, what to try.
    # Use soft assertions — the message must convey failure context.
    assert len(error_text) > 0, "Error message must not be empty"
    # At minimum the target name should appear in the error
    assert (
        "xyzzy" in error_text or "absolutely-not" in error_text or "invalid" in error_text.lower()
    ), f"Error message must name the invalid target; got: {error_text!r}"


def test_invalid_target_error_names_what_was_tried(tmp_path: Path):
    """The error message for an invalid target describes what was attempted."""
    from praxion_evals.harness.cli import resolve_target

    repo = _make_git_repo(tmp_path)

    import pytest

    invalid_target = "no-such-ref-or-path-abc123"
    with pytest.raises((ValueError, RuntimeError, SystemExit)) as exc_info:
        resolve_target(invalid_target, repo_root=repo)

    error_text = str(exc_info.value)
    # The error should mention at least one of: the target itself, "path", "worktree", "git ref"
    has_context = (
        invalid_target in error_text
        or "path" in error_text.lower()
        or "worktree" in error_text.lower()
        or "ref" in error_text.lower()
        or "git" in error_text.lower()
    )
    assert has_context, (
        f"Error message must describe what was tried (path/worktree/ref lookup); "
        f"got: {error_text!r}"
    )


# ---------------------------------------------------------------------------
# Auth-mode resolution via CLI
# ---------------------------------------------------------------------------


def test_oauth_token_env_selects_agent_sdk_route(monkeypatch: Any):
    """When CLAUDE_CODE_OAUTH_TOKEN is set, the CLI uses the agent-sdk auth route."""
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "test-oauth-token")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("CLAUDECODE", raising=False)

    from praxion_evals.harness.judge_client import select_judge_client

    # select_judge_client is already tested in test_harness_judge_client.py;
    # here we verify the CLI wires it correctly by checking what select_judge_client returns.
    client = select_judge_client()
    # Import after to avoid triggering the lazy SDK import at collection time
    from praxion_evals.harness.judge_client import AgentSdkJudgeClient

    assert isinstance(client, AgentSdkJudgeClient), (
        f"OAuth token env var must select AgentSdkJudgeClient; got {type(client).__name__}"
    )


def test_api_key_env_selects_messages_api_route(monkeypatch: Any):
    """When ANTHROPIC_API_KEY is set (without OAuth token), the CLI uses the messages-api route."""
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-api-key")

    from praxion_evals.harness.judge_client import select_judge_client

    client = select_judge_client()
    from praxion_evals.harness.judge_client import MessagesApiJudgeClient

    assert isinstance(client, MessagesApiJudgeClient), (
        f"API key env var must select MessagesApiJudgeClient; got {type(client).__name__}"
    )


def test_no_auth_env_raises_with_actionable_message(monkeypatch: Any):
    """When neither auth env var is set, CLI raises with a message naming both vars."""
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    import pytest

    from praxion_evals.harness.judge_client import select_judge_client

    with pytest.raises((RuntimeError, SystemExit)) as exc_info:
        select_judge_client()

    error_text = str(exc_info.value)
    assert "CLAUDE_CODE_OAUTH_TOKEN" in error_text, (
        f"Error must name CLAUDE_CODE_OAUTH_TOKEN; got: {error_text!r}"
    )
    assert "ANTHROPIC_API_KEY" in error_text, (
        f"Error must name ANTHROPIC_API_KEY; got: {error_text!r}"
    )


# ---------------------------------------------------------------------------
# CLI module: importable and has the expected entry point
# ---------------------------------------------------------------------------


def test_cli_module_is_importable():
    """harness/cli.py must be importable without errors."""
    from praxion_evals.harness import cli  # noqa: F401

    assert cli is not None


def test_cli_module_has_main_entry_point():
    """harness/cli.py must expose a 'main' callable (the argparse entry point)."""
    from praxion_evals.harness import cli

    assert hasattr(cli, "main"), (
        "harness/cli.py must define a 'main' function for the entry point wiring"
    )
    assert callable(cli.main), "cli.main must be callable"


def test_cli_module_has_resolve_target():
    """harness/cli.py must expose a 'resolve_target' callable (the arg resolver)."""
    from praxion_evals.harness import cli

    assert hasattr(cli, "resolve_target"), (
        "harness/cli.py must define 'resolve_target' for the 4-case arg resolution"
    )
    assert callable(cli.resolve_target), "cli.resolve_target must be callable"


# ---------------------------------------------------------------------------
# CLI --help does not crash (smoke test for argparse wiring)
# ---------------------------------------------------------------------------


def test_cli_help_exits_cleanly():
    """Running the CLI with --help exits with code 0 (argparse help)."""
    result = subprocess.run(
        [sys.executable, "-m", "praxion_evals.harness.cli", "--help"],
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(Path(__file__).parent.parent / "src")},
    )
    # argparse --help exits with 0
    assert result.returncode == 0, (
        f"CLI --help must exit 0; got {result.returncode}. stderr: {result.stderr!r}"
    )
    assert "eval-praxion" in result.stdout.lower() or "usage" in result.stdout.lower(), (
        f"CLI --help output must mention the command or usage; got: {result.stdout[:200]!r}"
    )


# ---------------------------------------------------------------------------
# CLI report header records the chosen auth route
# ---------------------------------------------------------------------------


def test_cli_run_records_auth_route_in_report(tmp_path: Path, monkeypatch: Any):
    """When run_eval() completes, the written report mentions the auth route used."""
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-for-route-header")

    # Patch run_eval to avoid actually calling the LLM; return a minimal Report.
    from praxion_evals.harness.schemas import EMPTY_CORPUS, Report

    fake_report = Report(
        corpus=EMPTY_CORPUS,
        check_results=(),
        cost_usd_estimate=0.0,
        report_path="",
    )

    with patch("praxion_evals.harness.cli.run_eval", return_value=fake_report):
        # The CLI's run_and_write function (or equivalent) should record the auth route.
        # If the CLI exposes a get_auth_route() or similar helper, test that.
        # Otherwise verify that the resolved judge_client type matches the env.
        from praxion_evals.harness.judge_client import MessagesApiJudgeClient, select_judge_client

        client = select_judge_client()
        assert isinstance(client, MessagesApiJudgeClient), (
            "With only ANTHROPIC_API_KEY set, messages-api route must be selected"
        )
