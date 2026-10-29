"""The scratch-project helpers every kit builds its fixtures with."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from praxion_evals.adherence.moves.fixture_project import (
    CANONICAL_BLOCKS,
    git,
    project_instructions,
    write_files,
)


def test_write_files_creates_directories_and_keeps_the_last_write_of_a_path(tmp_path: Path) -> None:
    write_files(tmp_path, (("a/b/c.txt", "one"), ("top.txt", "x"), ("a/b/c.txt", "two")))

    assert (tmp_path / "a/b/c.txt").read_text(encoding="utf-8") == "two"
    assert (tmp_path / "top.txt").read_text(encoding="utf-8") == "x"


def test_git_runs_in_the_repository_and_returns_its_output(tmp_path: Path) -> None:
    git(tmp_path, "init", "--quiet", "-b", "main")

    assert git(tmp_path, "symbolic-ref", "--short", "HEAD").strip() == "main"


def test_git_failure_raises_rather_than_passing_silently(tmp_path: Path) -> None:
    with pytest.raises(subprocess.CalledProcessError):
        git(tmp_path, "log")  # not a repository


def test_git_ignores_the_operators_configuration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    (home / ".gitconfig").write_text("[user]\n\tname = Operator\n", encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("GIT_AUTHOR_NAME", "Operator")
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "--quiet")

    assert "Operator" not in git(repo, "config", "--list")


def test_project_instructions_carries_every_shipped_block_but_the_excluded() -> None:
    names = sorted(p.name for p in CANONICAL_BLOCKS.glob("*.md"))
    skipped = names[0]
    kept = names[1:]

    text = project_instructions(frozenset({skipped}))

    bodies = {n: (CANONICAL_BLOCKS / n).read_text(encoding="utf-8").strip() for n in names}
    assert text.startswith("# Fixture project\n\n")
    assert text.endswith("\n")
    assert not text.endswith("\n\n")
    assert bodies[skipped] not in text
    assert all(bodies[n] in text for n in kept)
    assert [text.index(bodies[n]) for n in kept] == sorted(text.index(bodies[n]) for n in kept)


def test_project_instructions_without_exclusions_carries_all_blocks() -> None:
    text = project_instructions(frozenset())

    assert all(p.read_text(encoding="utf-8").strip() in text for p in CANONICAL_BLOCKS.glob("*.md"))
