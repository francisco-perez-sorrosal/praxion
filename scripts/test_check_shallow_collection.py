"""Tests for check_shallow_collection.py -- collect a commit's test suite in a depth-1 clone.

CI clones at depth 1, so a test that reads git history while it is being collected raises before
any skip applies, and only CI sees it: every local run has the history. Each scenario runs the
CLI as a subprocess over a real two-commit repository, the way the merge procedure runs it.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "check_shallow_collection.py"

# A test module that asks git for the parent commit while it is imported: fine with history,
# a collection error in a depth-1 clone.
_READS_HISTORY = (
    "import subprocess\n"
    "PARENT = subprocess.run(\n"
    '    ["git", "rev-parse", "--verify", "HEAD~1"], capture_output=True, text=True, check=True\n'
    ").stdout\n"
    "\n"
    "def test_parent_is_known():\n"
    "    assert PARENT\n"
)
_READS_NOTHING = "def test_arithmetic():\n    assert 1 + 1 == 2\n"


def _clean_env() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}


def _git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(cwd), "-c", "user.name=t", "-c", "user.email=t@t", *args],
        capture_output=True,
        text=True,
        check=True,
        env=_clean_env(),
    )
    return result.stdout.strip()


def _repository(root: Path, test_body: str) -> Path:
    """A repository of two commits whose second commit adds `tests/test_probe.py`."""
    root.mkdir(parents=True)
    _git(root, "init", "-q", "-b", "main")
    (root / "README.md").write_text("probe\n")
    _git(root, "add", "README.md")
    _git(root, "commit", "-q", "-m", "first")
    (root / "tests").mkdir()
    (root / "tests" / "test_probe.py").write_text(test_body)
    _git(root, "add", "tests/test_probe.py")
    _git(root, "commit", "-q", "-m", "second")
    return root.resolve()


def _check(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        timeout=180,
        env=env if env is not None else _clean_env(),
    )


def test_a_test_that_reads_history_at_collection_fails_the_check(tmp_path: Path) -> None:
    repo = _repository(tmp_path / "repo", _READS_HISTORY)
    # The same suite collects in the full repository, so the failure is the clone's depth.
    full = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider"],
        cwd=repo,
        capture_output=True,
        text=True,
        env=_clean_env(),
    )
    assert full.returncode == 0, full.stdout + full.stderr

    result = _check("--repo-root", str(repo))

    assert result.returncode == 1, result.stdout + result.stderr
    assert "tests/test_probe.py" in result.stdout


def test_a_suite_that_reads_no_history_passes(tmp_path: Path) -> None:
    repo = _repository(tmp_path / "repo", _READS_NOTHING)

    result = _check("--repo-root", str(repo))

    assert result.returncode == 0, result.stdout + result.stderr
    assert "clean" in result.stdout
    assert _git(repo, "rev-parse", "--short", "HEAD") in result.stdout


def test_the_named_ref_is_checked_not_the_current_one(tmp_path: Path) -> None:
    repo = _repository(tmp_path / "repo", _READS_HISTORY)
    _git(repo, "branch", "fixed", "HEAD")
    _git(repo, "checkout", "-q", "fixed")
    (repo / "tests" / "test_probe.py").write_text(_READS_NOTHING)
    _git(repo, "commit", "-q", "-am", "stop reading history")
    _git(repo, "checkout", "-q", "main")

    assert _check("--repo-root", str(repo), "--ref", "fixed").returncode == 0
    assert _check("--repo-root", str(repo), "--ref", "main").returncode == 1


def test_uncommitted_changes_are_not_checked_and_the_report_says_so(tmp_path: Path) -> None:
    repo = _repository(tmp_path / "repo", _READS_NOTHING)
    (repo / "tests" / "test_probe.py").write_text(_READS_HISTORY)

    result = _check("--repo-root", str(repo))

    assert result.returncode == 0, result.stdout + result.stderr
    assert "uncommitted" in result.stdout


def test_a_git_dir_in_the_environment_does_not_lend_the_clone_its_history(tmp_path: Path) -> None:
    repo = _repository(tmp_path / "repo", _READS_HISTORY)
    # A git hook runs with GIT_DIR set; a leaked one would make HEAD~1 resolve in the source repo.
    env = {**_clean_env(), "GIT_DIR": str(repo / ".git")}

    assert _check("--repo-root", str(repo), env=env).returncode == 1


def test_a_given_collection_command_replaces_the_default(tmp_path: Path) -> None:
    repo = _repository(tmp_path / "repo", _READS_NOTHING)

    failing = _check("--repo-root", str(repo), "--", sys.executable, "-c", "raise SystemExit(3)")
    passing = _check("--repo-root", str(repo), "--", sys.executable, "-c", "pass")

    assert failing.returncode == 1
    assert passing.returncode == 0


def test_an_unresolvable_ref_is_a_usage_error(tmp_path: Path) -> None:
    repo = _repository(tmp_path / "repo", _READS_NOTHING)

    result = _check("--repo-root", str(repo), "--ref", "no-such-branch")

    assert result.returncode == 2
    assert "no-such-branch" in result.stderr
