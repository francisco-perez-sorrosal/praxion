"""The regeneration command's world-reading edge, `scripts/_diagram_edge.py`, through its real adapters.

The command's other tests drive it with a stub toolchain and a scratch repository the test kit
builds. These tests reach the world the edge reads at run time, `git` as a process and `likec4`
at its pinned version, and pin what the adapters do there: which directory a git call runs in,
how the `GIT_DIR` and the relative `GIT_INDEX_FILE` a pre-commit hook receives are handled, what
`stage` leaves in the index and where, and what `read_model` returns and raises. A test that needs
the pinned toolchain skips when it is not on PATH.

Public surface these tests assume: `_git(args, cwd) -> str`, `_toplevel() -> Path`,
`stage(rendered: Path) -> None`, `read_model(toolchain, root) -> dict`, `Toolchain(likec4, d2, path)`
and `RegenerationError` with its `failure` record, all from `_diagram_edge`.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import _diagram_edge as edge

IDENTITY = (
    "-c",
    "user.name=Edge Tests",
    "-c",
    "user.email=edge@example.invalid",
    "-c",
    "commit.gpgsign=false",
)


def git(repo: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", *IDENTITY, *args], cwd=repo, capture_output=True, text=True, check=True
    )
    return done.stdout


def repository(path: Path) -> Path:
    """A fresh repository with one commit, so HEAD exists."""
    path.mkdir(parents=True)
    git(path, "init", "-q", "-b", "main")
    (path / "README").write_text("edge\n", encoding="utf-8")
    git(path, "add", "README")
    git(path, "commit", "-q", "-m", "base")
    return path


# --- git as a process ------------------------------------------------------------------------


def test_a_git_call_runs_in_the_directory_it_is_given_not_the_process_directory(
    tmp_path, monkeypatch
):
    here, there = repository(tmp_path / "here"), repository(tmp_path / "there")
    monkeypatch.chdir(here)

    top = edge._git(["rev-parse", "--show-toplevel"], there).strip()

    assert Path(top).resolve() == there.resolve()
