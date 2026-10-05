"""Tests for the handoff composer's fork point: the newest default-branch merge-base wins.

A pipeline worktree branches from `origin/<default>` or from the local default branch, and the
local one can be ahead of its remote (unpushed commits) or behind it (a fetch since). Whichever
side the branch forked from is the later merge-base; `resolve_base_ref` must return that one.
The command line's `--base-ref` hands a caller's own fork point to the composition unchanged.

Every resolver case builds real repositories: a bare `origin`, a clone of it, and, for the
remote-ahead case, a second clone that pushes. Nothing is mocked but the writer in the
argument-parsing cases.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import NamedTuple

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import _handoff_inputs  # noqa: E402
import compose_handoff  # noqa: E402

SLUG = "demo-task"
BOUNDARY = "planning-to-implementation"
PIPELINE_BRANCH = "pipeline"
NO_STEPS_WIP = "# WIP\n\n## Progress\n\nNo steps tracked yet.\n"


class Fork(NamedTuple):
    """A pipeline checkout and the commits its fork point could be."""

    repo: Path
    pushed: str
    unpushed: str


def _git(repo: Path, *args: str) -> str:
    done = subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)
    return done.stdout.strip()


def _commit(repo: Path, name: str) -> str:
    (repo / name).write_text(name, encoding="utf-8")
    _git(repo, "add", name)
    _git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", name)
    return _git(repo, "rev-parse", "HEAD")


def _clone(tmp_path: Path, bare: Path, name: str) -> Path:
    clone = tmp_path / name
    _git(tmp_path, "clone", "-q", str(bare), name)
    return clone


def _origin_with_one_commit(tmp_path: Path) -> tuple[Path, Path, str]:
    """A bare origin, a clone of it on `main`, and the one commit both hold."""
    bare = tmp_path / "origin.git"
    _git(tmp_path, "init", "-q", "--bare", "-b", "main", str(bare))
    work = _clone(tmp_path, bare, "work")
    pushed = _commit(work, "first")
    _git(work, "push", "-q", "origin", "main")
    # A clone of an empty remote leaves `origin/HEAD` unset; a fetch-cloned one has it.
    _git(work, "remote", "set-head", "origin", "main")
    return bare, work, pushed


@pytest.fixture
def local_default_ahead(tmp_path: Path) -> Fork:
    """The pipeline forked from a local `main` holding a commit `origin/main` lacks."""
    _, work, pushed = _origin_with_one_commit(tmp_path)
    unpushed = _commit(work, "unpushed")
    _git(work, "checkout", "-q", "-b", PIPELINE_BRANCH, "main")
    return Fork(work, pushed, unpushed)


@pytest.fixture
def remote_default_ahead(tmp_path: Path) -> Fork:
    """The pipeline forked from `origin/main`, which a fetch moved past the local `main`."""
    bare, work, pushed = _origin_with_one_commit(tmp_path)
    other = _clone(tmp_path, bare, "other")
    fetched = _commit(other, "elsewhere")
    _git(other, "push", "-q", "origin", "main")
    _git(work, "fetch", "-q", "origin")
    _git(work, "checkout", "-q", "-b", PIPELINE_BRANCH, "origin/main")
    return Fork(work, pushed, fetched)


def test_a_local_default_branch_ahead_of_its_remote_yields_the_local_fork_point(
    local_default_ahead: Fork,
):
    assert (
        _handoff_inputs.resolve_base_ref(local_default_ahead.repo) == local_default_ahead.unpushed
    )


def test_a_remote_default_branch_ahead_of_the_local_one_yields_the_remote_fork_point(
    remote_default_ahead: Fork,
):
    assert (
        _handoff_inputs.resolve_base_ref(remote_default_ahead.repo) == remote_default_ahead.unpushed
    )


def test_a_repository_without_a_remote_yields_the_local_fork_point(tmp_path: Path):
    repo = tmp_path / "solo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    forked = _commit(repo, "first")
    _git(repo, "checkout", "-q", "-b", PIPELINE_BRANCH)
    _commit(repo, "on-branch")

    assert _handoff_inputs.resolve_base_ref(repo) == forked


def test_a_repository_without_a_default_branch_yields_no_fork_point(tmp_path: Path):
    repo = tmp_path / "trunkless"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "trunk")
    _commit(repo, "first")

    assert _handoff_inputs.resolve_base_ref(repo) is None


# -- the command line ------------------------------------------------------------------------


@pytest.fixture
def composed_with(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Run the command line with the writer stubbed; answers the `base_ref` it was handed."""
    seen: dict = {}
    (tmp_path / ".ai-work" / SLUG).mkdir(parents=True)
    (tmp_path / ".ai-work" / SLUG / "WIP.md").write_text(NO_STEPS_WIP, encoding="utf-8")

    def stub(slug: str, repo_root: Path, **kwargs: object) -> dict:
        seen.update(kwargs)
        return {
            "path": tmp_path / "HANDOFF.md",
            "byte_count": 0,
            "over_8kib": False,
            "conflicts": [],
            "continuation_prompt": "",
        }

    monkeypatch.setattr(compose_handoff, "write_handoff", stub)

    def run(*extra: str) -> object:
        argv = [SLUG, "--repo-root", str(tmp_path), "--boundary", BOUNDARY, *extra]
        assert compose_handoff.main(argv) == 0
        return seen["base_ref"]

    return run


@pytest.mark.parametrize(
    ("extra", "expected"),
    [((), None), (("--base-ref", "cb14bddc"), "cb14bddc")],
    ids=["unspecified", "given"],
)
def test_the_command_line_hands_its_base_ref_to_the_writer(composed_with, extra, expected):
    assert composed_with(*extra) == expected


def test_a_base_ref_given_on_the_command_line_names_the_header_fork_point(
    local_default_ahead: Fork,
):
    repo = local_default_ahead.repo
    task_dir = repo / ".ai-work" / SLUG
    task_dir.mkdir(parents=True)
    (task_dir / "WIP.md").write_text(NO_STEPS_WIP, encoding="utf-8")

    code = compose_handoff.main(
        [SLUG, "--repo-root", str(repo), "--boundary", BOUNDARY, "--force", "--base-ref"]
        + [local_default_ahead.pushed]
    )

    written = (task_dir / "HANDOFF.md").read_text(encoding="utf-8")
    assert (code, f"base_sha: {local_default_ahead.pushed}" in written) == (0, True)
