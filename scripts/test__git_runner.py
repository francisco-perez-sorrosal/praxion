"""Tests for `_git_runner` -- the shared bounded `git` primitive.

The load-bearing property is the **timeout**, not the deduplication: six
`scripts/` modules previously issued unbounded `git` calls, one of them
(`finalize_adrs.py`) on the blocking post-merge hook path where a hung or
credential-prompting `git` would stall ADR finalize forever.

Per `rules/swe/gate-liveness.md`, a guard nobody has seen fail is
indistinguishable from no guard. So the central test here is a **canary**: it
puts a `git` on `PATH` that hangs, and asserts the primitive gives up quickly
rather than blocking. A happy-path test would only prove the code runs.

The timing assertions use a deliberately wide margin (a 30s hang bounded to
0.5s, asserted under 10s) so the canary discriminates "bounded" from
"unbounded" without being sensitive to machine load.
"""

from __future__ import annotations

import ast
import importlib.util
import logging
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest

_SCRIPTS_DIR = Path(__file__).resolve().parent
_MODULE_PATH = _SCRIPTS_DIR / "_git_runner.py"

# The six modules migrated off their private, unbounded `_git`/`_run_git`
# helpers. Named explicitly rather than globbed: the set is the contract the
# fork-regression canary below checks, so it must be a datum, not a scan.
MIGRATED_MODULES = (
    "finalize_adrs.py",
    "check_squash_safety.py",
    "check_calibration_coverage.py",
    "check_release_staleness.py",
    "check_adr_frontmatter_promotion.py",
    "check_aac_golden_rule.py",
)

# Wall-clock bound proving the timeout fired. The shim below hangs for
# HANG_SECONDS; anything under this ceiling means the primitive gave up.
HANG_SECONDS = 30
BOUNDED_TIMEOUT = 0.5
ELAPSED_CEILING = 10.0


def _load_module() -> Any:
    """Load `_git_runner.py` without requiring it on sys.path."""
    spec = importlib.util.spec_from_file_location("_git_runner", _MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


git_runner = _load_module()


# -- Fixtures -----------------------------------------------------------------


@pytest.fixture
def hanging_git(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Put a `git` that hangs at the front of PATH.

    `exec` is load-bearing: it replaces the shell rather than forking, so the
    hanging process is the direct child holding the captured pipes. A forked
    grandchild would keep those pipes open after the kill and make
    `subprocess.run`'s own cleanup block -- the test would then hang for the
    reason it exists to prevent.

    The shim dir is *prepended* to the real PATH rather than replacing it: the
    shim itself needs to resolve `sleep`, and an isolated PATH leaves it
    exiting 127 immediately -- a shim that does not hang cannot prove a timeout.
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    shim = bin_dir / "git"
    shim.write_text(f"#!/bin/sh\nexec sleep {HANG_SECONDS}\n", encoding="utf-8")
    shim.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    return tmp_path


@pytest.fixture
def real_repo(tmp_path: Path) -> Path:
    """A minimal real git repository with one commit."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=tmp_path, check=True)
    (tmp_path / "seed.txt").write_text("seed\n", encoding="utf-8")
    subprocess.run(["git", "add", "seed.txt"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "seed"], cwd=tmp_path, check=True)
    return tmp_path


# -- Canary: the timeout bites -------------------------------------------------


def test_run_git_gives_up_on_a_hanging_git(hanging_git: Path) -> None:
    """A `git` that never returns raises rather than blocking forever."""
    started = time.monotonic()
    with pytest.raises(git_runner.GitUnavailableError):
        git_runner.run_git(hanging_git, "rev-parse", "HEAD", timeout=BOUNDED_TIMEOUT)
    elapsed = time.monotonic() - started
    assert elapsed < ELAPSED_CEILING, (
        f"run_git took {elapsed:.1f}s against a {HANG_SECONDS}s hang -- the timeout did not fire"
    )


def test_git_output_returns_none_on_a_hanging_git(hanging_git: Path) -> None:
    """The swallowing variant is bounded by the same timeout."""
    started = time.monotonic()
    result = git_runner.git_output(hanging_git, "rev-parse", "HEAD", timeout=BOUNDED_TIMEOUT)
    elapsed = time.monotonic() - started
    assert result is None
    assert elapsed < ELAPSED_CEILING, (
        f"git_output took {elapsed:.1f}s against a {HANG_SECONDS}s hang -- the timeout did not fire"
    )


def test_timeout_error_message_names_the_bound(hanging_git: Path) -> None:
    """The raised error says it was a timeout, not a generic failure."""
    with pytest.raises(git_runner.GitUnavailableError, match="timeout"):
        git_runner.run_git(hanging_git, "status", timeout=BOUNDED_TIMEOUT)


# -- The bound cannot be disabled ---------------------------------------------


@pytest.mark.parametrize("bad_timeout", [None, 0, -1])
def test_timeout_cannot_be_disabled(tmp_path: Path, bad_timeout: Any) -> None:
    """`None`/non-positive is rejected, not passed through as "unbounded"."""
    with pytest.raises(ValueError, match="positive"):
        git_runner.run_git(tmp_path, "status", timeout=bad_timeout)


# -- Error contract -----------------------------------------------------------


def test_git_unavailable_error_is_an_os_error() -> None:
    """Callers that already wrote `except OSError` keep catching it.

    This is what lets a timeout -- `subprocess.TimeoutExpired`, which is not an
    `OSError` -- reach `check_adr_frontmatter_promotion.main`'s existing
    handler instead of escaping as an unhandled exception type.
    """
    assert issubclass(git_runner.GitUnavailableError, OSError)


def test_missing_git_binary_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    empty_bin = tmp_path / "empty"
    empty_bin.mkdir()
    monkeypatch.setenv("PATH", str(empty_bin))
    with pytest.raises(git_runner.GitUnavailableError):
        git_runner.run_git(tmp_path, "status")


def test_git_output_swallows_a_missing_git_binary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    empty_bin = tmp_path / "empty"
    empty_bin.mkdir()
    monkeypatch.setenv("PATH", str(empty_bin))
    assert git_runner.git_output(tmp_path, "status") is None


# -- Inverse guards: normal work is unaffected --------------------------------


def test_run_git_returns_completed_process_on_success(real_repo: Path) -> None:
    result = git_runner.run_git(real_repo, "rev-parse", "--is-inside-work-tree")
    assert result.returncode == 0
    assert result.stdout.strip() == "true"


def test_run_git_returns_nonzero_rather_than_raising(real_repo: Path) -> None:
    """A git command that ran and failed is a CompletedProcess, not an error."""
    result = git_runner.run_git(real_repo, "rev-parse", "no-such-ref")
    assert result.returncode != 0


def test_git_output_strips_and_collapses_failure_to_none(real_repo: Path) -> None:
    assert git_runner.git_output(real_repo, "rev-parse", "--is-inside-work-tree") == "true"
    assert git_runner.git_output(real_repo, "rev-parse", "no-such-ref") is None


def test_git_output_treats_empty_stdout_as_no_answer(real_repo: Path) -> None:
    """Whitespace-only output is `None` -- the contract the callers rely on."""
    assert git_runner.git_output(real_repo, "log", "--format=", "-n", "1") is None


def test_git_output_forwards_diagnostics_to_a_supplied_logger(
    real_repo: Path, caplog: pytest.LogCaptureFixture
) -> None:
    logger = logging.getLogger("test__git_runner.diagnostics")
    with caplog.at_level(logging.DEBUG, logger=logger.name):
        git_runner.git_output(real_repo, "rev-parse", "no-such-ref", logger=logger)
    assert any("rev-parse" in record.getMessage() for record in caplog.records)


# -- Fork-regression canary ---------------------------------------------------


def _unbounded_git_calls(source: str) -> list[int]:
    """Line numbers of `subprocess.run(["git", ...])` calls lacking a timeout.

    A direct `subprocess.run` on a `git` argv is how the twelve-way behavioural
    fork formed in the first place -- the helpers were never textual copies, so
    body-hash duplication detection is structurally blind to them. This looks
    for the shape instead.
    """
    findings: list[int] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "run"):
            continue
        if not (isinstance(func.value, ast.Name) and func.value.id == "subprocess"):
            continue
        if not node.args or not isinstance(node.args[0], ast.List):
            continue
        first = node.args[0].elts[0] if node.args[0].elts else None
        if not (isinstance(first, ast.Constant) and first.value == "git"):
            continue
        if any(kw.arg == "timeout" for kw in node.keywords):
            continue
        findings.append(node.lineno)
    return findings


@pytest.mark.parametrize("module_name", MIGRATED_MODULES)
def test_migrated_module_issues_no_unbounded_git_call(module_name: str) -> None:
    """Each migrated module routes git through the shared bounded primitive."""
    source = (_SCRIPTS_DIR / module_name).read_text(encoding="utf-8")
    assert _unbounded_git_calls(source) == [], (
        f"{module_name} re-grew a direct unbounded subprocess.run(['git', ...]) call"
    )


@pytest.mark.parametrize("module_name", MIGRATED_MODULES)
def test_migrated_module_imports_the_shared_primitive(module_name: str) -> None:
    source = (_SCRIPTS_DIR / module_name).read_text(encoding="utf-8")
    assert "from _git_runner import" in source, (
        f"{module_name} no longer imports the shared git primitive"
    )


def test_fork_detector_flags_a_reintroduced_unbounded_call() -> None:
    """Canary for the canary: the detector must bite on the historical shape."""
    reintroduced = (
        "import subprocess\n"
        "def _git(*args):\n"
        "    return subprocess.run(['git', *args], capture_output=True, check=False)\n"
    )
    assert _unbounded_git_calls(reintroduced) == [3]


def test_fork_detector_accepts_a_bounded_call() -> None:
    """Inverse guard: a timeout-carrying call is not a finding."""
    bounded = (
        "import subprocess\n"
        "def _git(*args):\n"
        "    return subprocess.run(['git', *args], timeout=30, check=False)\n"
    )
    assert _unbounded_git_calls(bounded) == []


# -- Canary: the hook environment never redirects a named repository ----------
#
# git exports a RELATIVE `GIT_INDEX_FILE=.git/index` (and friends) to the hooks
# it runs. Inherited by a `run_git(other_repo, ...)` call it resolves
# `.git/index` under that other repo -- and when that repo is a linked worktree
# whose `.git` is a pointer *file*, git dies with `Not a directory`. That is
# the observed failure that silently broke the sidecar post-commit convergence
# channel, so it is pinned as a canary (with its own inverse guard) rather than
# as a happy-path assertion about a list of variable names.


@pytest.fixture
def worktree_of(real_repo: Path, tmp_path: Path) -> Path:
    """A linked worktree of `real_repo` -- its `.git` is a pointer file."""
    linked = tmp_path / "linked"
    subprocess.run(
        ["git", "worktree", "add", "-q", str(linked), "-b", "side"],
        cwd=real_repo,
        check=True,
    )
    assert (linked / ".git").is_file(), "the fixture must produce a pointer-file worktree"
    return linked


def test_relative_git_index_file_does_not_redirect_a_named_repository(
    worktree_of: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mod = _load_module()
    monkeypatch.setenv("GIT_INDEX_FILE", ".git/index")
    monkeypatch.setenv("GIT_DIR", ".git")

    result = mod.run_git(worktree_of, "status", "--porcelain")

    assert result.returncode == 0, result.stderr
    assert "Not a directory" not in result.stderr


def test_the_unscrubbed_environment_really_does_break_that_call(worktree_of: Path) -> None:
    """Canary for the canary: unscrubbed, the same call fails -- so the test
    above discriminates rather than passing vacuously."""
    env = dict(os.environ, GIT_INDEX_FILE=".git/index")
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=str(worktree_of),
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "Not a directory" in result.stderr


def test_scrubbed_set_is_exactly_the_repository_scoping_variables() -> None:
    mod = _load_module()
    assert set(mod.REPOSITORY_SCOPING_ENV_VARS) == {
        "GIT_INDEX_FILE",
        "GIT_DIR",
        "GIT_WORK_TREE",
        "GIT_COMMON_DIR",
        "GIT_OBJECT_DIRECTORY",
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",
        "GIT_PREFIX",
        "GIT_NAMESPACE",
    }


def test_identity_variables_survive_the_scrub(
    real_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The scrub is scoped to *which repository*, never to *who is committing*
    -- every fixture and hook that exports an identity keeps working."""
    monkeypatch.setenv("GIT_INDEX_FILE", ".git/index")
    monkeypatch.setenv("GIT_AUTHOR_NAME", "Scrub Survivor")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "survivor@example.com")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "Scrub Survivor")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "survivor@example.com")
    mod = _load_module()

    (real_repo / "another.txt").write_text("more\n", encoding="utf-8")
    assert mod.run_git(real_repo, "add", "another.txt").returncode == 0
    assert mod.run_git(real_repo, "commit", "-qm", "second").returncode == 0

    assert mod.git_output(real_repo, "log", "-1", "--format=%an <%ae>") == (
        "Scrub Survivor <survivor@example.com>"
    )


def test_a_clean_environment_inherits_rather_than_copying(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Off the hook path there is nothing to scrub and the child inherits the
    parent environment untouched (`env=None`)."""
    mod = _load_module()
    for name in mod.REPOSITORY_SCOPING_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    assert mod._unscoped_environ() is None
