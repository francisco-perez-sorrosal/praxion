"""The regeneration command's world-reading edge, `scripts/_diagram_edge.py`, through its real adapters.

The command's other tests drive it with a stub toolchain and a scratch repository the test kit
builds. These tests reach the world the edge reads at run time, `git` as a process and `likec4`
at its pinned version, and pin what the adapters do there: which directory a git call runs in,
how the `GIT_DIR` and the `GIT_INDEX_FILE` a pre-commit hook receives are handled, what `stage`
leaves in the index and where, and what `read_model` returns and raises. A test that needs the
pinned toolchain skips when it is not on PATH.

Public surface these tests assume: `_git(args, cwd) -> str`, `_toplevel() -> Path`,
`stage(rendered: Path) -> None`, `read_model(toolchain, root) -> dict`, `toolchain_problems`,
`Toolchain(likec4, d2, path)` and `RegenerationError` with its `failure` record, all from
`_diagram_edge`; the pins come from the test kit.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import _diagram_edge as edge
import pytest
from _diagram_testkit import D2_PIN, LIKEC4_PIN

IDENTITY = (
    "-c",
    "user.name=Edge Tests",
    "-c",
    "user.email=edge@example.invalid",
    "-c",
    "commit.gpgsign=false",
)
INHERITED_GIT_VARIABLES = ("GIT_DIR", "GIT_INDEX_FILE", "GIT_WORK_TREE")
MINIMAL_MODEL = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "minimal.c4"
RENDERED = "docs/diagrams/x/rendered"
SOURCE = "docs/diagrams/x/src/x.c4"


@pytest.fixture(autouse=True)
def no_inherited_git_environment(monkeypatch):
    """A run inside a git hook inherits `GIT_DIR` and friends; the tests set their own."""
    for name in INHERITED_GIT_VARIABLES:
        monkeypatch.delenv(name, raising=False)


def git(repo: Path, *args: str) -> str:
    """A git call that sees only the repository it is given, never a variable the process holds."""
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    done = subprocess.run(
        ["git", *IDENTITY, *args], cwd=repo, env=env, capture_output=True, text=True, check=True
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


def linked_worktree(path: Path) -> Path:
    """A linked worktree of a fresh repository kept beside it."""
    main = repository(path.with_name(f"{path.name}-main"))
    git(main, "worktree", "add", "-q", "-b", "feature", str(path))
    return path


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def staged(repo: Path) -> set[str]:
    """What the index holds against HEAD, one `<status>\\t<path>` entry each."""
    return set(git(repo, "diff", "--cached", "--name-status").splitlines())


def hook_environment(monkeypatch, worktree: Path) -> None:
    """The variables a pre-commit hook run in a linked `worktree` receives: its own git dir and index."""
    git_dir = Path(git(worktree, "rev-parse", "--absolute-git-dir").strip())
    monkeypatch.setenv("GIT_DIR", str(git_dir))
    monkeypatch.setenv("GIT_INDEX_FILE", str(git_dir / "index"))


@pytest.fixture
def pinned_toolchain() -> edge.Toolchain:
    toolchain = edge.Toolchain(LIKEC4_PIN, D2_PIN, os.environ.get("PATH", ""))
    unusable = [p for p in edge.toolchain_problems(toolchain) if p.tool == "likec4"]
    if unusable:
        pytest.skip(f"likec4 {LIKEC4_PIN} is not on PATH (found: {unusable[0].found})")
    return toolchain


# --- git as a process ------------------------------------------------------------------------


def test_a_git_call_runs_in_the_directory_it_is_given_not_the_process_directory(
    tmp_path, monkeypatch
):
    here, there = repository(tmp_path / "here"), repository(tmp_path / "there")
    monkeypatch.chdir(here)

    top = edge._git(["rev-parse", "--show-toplevel"], there).strip()

    assert Path(top).resolve() == there.resolve()


def test_stage_from_the_top_leaves_exactly_the_renders_in_the_index(tmp_path, monkeypatch):
    repo = repository(tmp_path / "repo")
    rendered = repo / RENDERED
    write(rendered / "refreshed.svg", "render v1\n")
    write(rendered / "unchanged.d2", "unchanged\n")
    write(rendered / "removed.svg", "removed soon\n")
    write(repo / SOURCE, "model\n")
    git(repo, "add", "docs")
    git(repo, "commit", "-q", "-m", "renders")
    write(rendered / "refreshed.svg", "render v2 refreshed\n")
    write(rendered / "created.svg", "created\n")
    (rendered / "removed.svg").unlink()
    write(repo / SOURCE, "model edited\n")
    write(repo / "notes.txt", "untracked\n")
    monkeypatch.chdir(repo)

    edge.stage(rendered)

    assert staged(repo) == {
        f"M\t{RENDERED}/refreshed.svg",
        f"A\t{RENDERED}/created.svg",
        f"D\t{RENDERED}/removed.svg",
    }


def test_stage_in_a_hook_of_a_linked_worktree_stages_the_renders_under_the_top(
    tmp_path, monkeypatch
):
    worktree = linked_worktree(tmp_path / "linked")
    write(worktree / RENDERED / "index.svg", "render\n")
    hook_environment(monkeypatch, worktree)
    monkeypatch.chdir(worktree)

    edge.stage(worktree / RENDERED)

    assert staged(worktree) == {f"A\t{RENDERED}/index.svg"}
    assert not (worktree / "rendered").exists()


def test_the_top_of_a_linked_worktree_is_named_with_the_hook_environment(tmp_path, monkeypatch):
    worktree = linked_worktree(tmp_path / "linked")
    hook_environment(monkeypatch, worktree)
    monkeypatch.chdir(worktree)

    assert edge._toplevel() == worktree.resolve()


# --- likec4 at its pin -----------------------------------------------------------------------


def test_read_model_returns_the_views_and_elements_of_the_source(tmp_path, pinned_toolchain):
    root = tmp_path / "root"
    (root / "src").mkdir(parents=True)
    shutil.copyfile(MINIMAL_MODEL, root / "src" / "minimal.c4")

    model = edge.read_model(pinned_toolchain, root)

    assert set(model["views"]) == {"index"}
    assert {element["title"] for element in model["elements"].values()} == {"User", "App"}


def test_read_model_of_an_empty_source_directory_fails_naming_likec4(tmp_path, pinned_toolchain):
    root = tmp_path / "root"
    (root / "src").mkdir(parents=True)

    with pytest.raises(edge.RegenerationError) as raised:
        edge.read_model(pinned_toolchain, root)

    assert "likec4" in raised.value.failure.what
