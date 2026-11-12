"""The shared source scan behind the observation-log inventory tests."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from hooks._observation_scan_testkit import candidate_modules, importers_of

IGNORED_SCRATCH = "tmp/hooks_copy/rogue.py"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def _write(root: Path, rel: str, text: str = "x = 1\n") -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _rels(root: Path) -> list[str]:
    return [rel for rel, _ in candidate_modules(root)]


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q")
    _write(tmp_path, ".gitignore", "tmp/\n")
    _write(tmp_path, "scripts/tracked.py")
    _git(tmp_path, "add", "--", ".gitignore", "scripts/tracked.py")
    return tmp_path


def test_a_gitignored_scratch_copy_is_not_a_candidate(repo: Path) -> None:
    _write(repo, IGNORED_SCRATCH)

    assert _rels(repo) == ["scripts/tracked.py"]


def test_an_untracked_unignored_module_is_a_candidate(repo: Path) -> None:
    _write(repo, "scripts/new_untracked.py")

    assert _rels(repo) == ["scripts/new_untracked.py", "scripts/tracked.py"]


def test_a_tracked_module_deleted_from_disk_is_not_a_candidate(repo: Path) -> None:
    (repo / "scripts" / "tracked.py").unlink()

    assert _rels(repo) == []


def test_outside_a_git_repository_every_python_file_is_walked(tmp_path: Path) -> None:
    _write(tmp_path, "scripts/a.py")
    _write(tmp_path, "tmp/b.py")
    _write(tmp_path, "hooks/_observation_log/owner.py")
    _write(tmp_path, "scripts/test_a.py")

    assert _rels(tmp_path) == ["scripts/a.py"]


def test_a_directory_inside_a_repository_is_walked_not_listed_by_git(repo: Path) -> None:
    sub = repo / "scripts"
    _write(sub, "inner.py")

    assert _rels(sub) == ["inner.py", "tracked.py"]


@pytest.mark.parametrize(
    "source",
    [
        "from _observation_log import writer\n",
        "from _observation_log import (\n    reader,\n    writer,\n)\n",
        "from hooks._observation_log import (\n    modes,\n    writer as w,\n)\n",
        "from _observation_log import reader, \\\n    writer\n",
        "import _observation_log.writer\n",
        "from _observation_log.writer import append_observation\n",
        "def load():\n    from _observation_log import writer\n    return writer\n",
    ],
)
def test_every_import_form_binding_the_submodule_is_found(tmp_path: Path, source: str) -> None:
    _write(tmp_path, "scripts/user.py", source)

    assert importers_of(tmp_path, "writer") == (frozenset({"scripts/user.py"}), ())


@pytest.mark.parametrize(
    "source",
    [
        "from _observation_log import reader\n",
        "from _observation_log import writer_helpers\n",
        "# from _observation_log import writer\n",
        'text = "import _observation_log.writer"\n',
    ],
)
def test_a_module_not_binding_the_submodule_is_not_found(tmp_path: Path, source: str) -> None:
    _write(tmp_path, "scripts/user.py", source)

    assert importers_of(tmp_path, "writer") == (frozenset(), ())


def test_a_candidate_that_does_not_parse_is_reported(tmp_path: Path) -> None:
    _write(tmp_path, "scripts/broken.py", "from _observation_log import (writer\n")

    assert importers_of(tmp_path, "writer") == (frozenset(), ("scripts/broken.py",))
