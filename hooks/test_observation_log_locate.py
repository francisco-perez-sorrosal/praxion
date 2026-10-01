"""`locate` answers which log, and which `project`, a working directory belongs to.

A directory records into the nearest `.ai-state/` at or above it, never past the
root of its own checkout, and names the project after the directory that holds
that state. A directory that no state directory serves answers `None`.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from hooks._observation_log import location
from hooks._observation_log.location import Location, locate

STATE = ".ai-state"
GIT = ".git"

# `locate` runs on every hook call; nothing beyond these may be imported.
_ALLOWED_IMPORTS = frozenset({"__future__", "collections", "os", "pathlib"})


def _project(root: Path, *, checkout: bool = True) -> Path:
    """A directory that holds a state directory, and a `.git` entry unless told not to."""
    root.mkdir(parents=True, exist_ok=True)
    (root / STATE).mkdir()
    if checkout:
        (root / GIT).mkdir()
    return root


def _deep(root: Path, depth: int) -> Path:
    below = root.joinpath(*(f"level{i}" for i in range(depth)))
    below.mkdir(parents=True)
    return below


# -- the directory that holds the state -------------------------------------------


def test_a_directory_holding_the_state_resolves_to_itself(tmp_path: Path) -> None:
    root = _project(tmp_path / "praxion")

    assert locate(str(root)) == Location(root / STATE, root, "praxion")


def test_the_state_directory_is_enough_without_a_git_entry(tmp_path: Path) -> None:
    root = _project(tmp_path / "plain", checkout=False)

    assert locate(str(root)) == Location(root / STATE, root, "plain")


# -- subdirectories of a checkout --------------------------------------------------


@pytest.mark.parametrize("depth", [1, 4])
def test_a_subdirectory_resolves_to_the_checkout_root(tmp_path: Path, depth: int) -> None:
    root = _project(tmp_path / "praxion")

    found = locate(str(_deep(root, depth)))

    assert found == Location(root / STATE, root, "praxion")


def test_the_nearest_state_directory_wins_for_a_nested_project(tmp_path: Path) -> None:
    outer = _project(tmp_path / "outer")
    inner = _project(outer / "packages" / "inner", checkout=False)

    below_inner = _deep(inner, 2)

    assert locate(str(below_inner)) == Location(inner / STATE, inner, "inner")
    assert locate(str(outer / "packages")) == Location(outer / STATE, outer, "outer")


# -- the walk stops at the checkout root -------------------------------------------


def test_a_clone_inside_a_recording_project_resolves_to_nothing(tmp_path: Path) -> None:
    outer = _project(tmp_path / "outer")
    clone = outer / "vendor" / "clone"
    (clone / GIT).mkdir(parents=True)

    assert locate(str(_deep(clone, 2))) is None
    assert locate(str(clone)) is None


def test_a_linked_worktree_marked_by_a_git_file_also_ends_the_walk(tmp_path: Path) -> None:
    outer = _project(tmp_path / "outer")
    linked = outer / "worktrees" / "feature"
    linked.mkdir(parents=True)
    (linked / GIT).write_text("gitdir: ../../.git/worktrees/feature\n")

    assert locate(str(_deep(linked, 1))) is None


def test_a_linked_worktree_that_holds_its_own_state_records_there(tmp_path: Path) -> None:
    linked = tmp_path / "feature"
    linked.mkdir()
    (linked / GIT).write_text("gitdir: ../main/.git/worktrees/feature\n")
    (linked / STATE).mkdir()

    assert locate(str(_deep(linked, 2))) == Location(linked / STATE, linked, "feature")


def test_a_checkout_without_state_resolves_to_nothing(tmp_path: Path) -> None:
    checkout = tmp_path / "bare"
    (checkout / GIT).mkdir(parents=True)

    assert locate(str(checkout)) is None
    assert locate(str(_deep(checkout, 3))) is None


def test_a_directory_outside_any_checkout_does_not_reach_a_state_above_it(tmp_path: Path) -> None:
    _project(tmp_path / "plain", checkout=False)
    below = _deep(tmp_path / "plain", 2)

    assert locate(str(below)) is None


# -- what counts as a state directory ----------------------------------------------


def test_a_linked_state_directory_names_the_checkout_not_its_target(tmp_path: Path) -> None:
    target = tmp_path / "elsewhere" / "shared-state"
    target.mkdir(parents=True)
    root = tmp_path / "praxion"
    (root / GIT).mkdir(parents=True)
    (root / STATE).symlink_to(target, target_is_directory=True)

    found = locate(str(_deep(root, 2)))

    assert found == Location(root / STATE, root, "praxion")


def test_a_state_entry_that_is_a_regular_file_does_not_count(tmp_path: Path) -> None:
    root = tmp_path / "praxion"
    (root / GIT).mkdir(parents=True)
    (root / STATE).write_text("not a directory")

    assert locate(str(root)) is None
    assert locate(str(_deep(root, 1))) is None


# -- input that is not a usable directory ------------------------------------------


@pytest.mark.parametrize("cwd", [None, "", 42, 3.5, ["/tmp"], {"cwd": "/tmp"}, b"/tmp"])
def test_a_cwd_that_is_not_a_non_empty_string_resolves_to_nothing(cwd: object) -> None:
    assert locate(cwd) is None


def test_a_directory_that_does_not_exist_below_a_recording_checkout_resolves_to_nothing(
    tmp_path: Path,
) -> None:
    root = _project(tmp_path / "praxion")

    assert locate(str(root / "gone" / "deeper")) is None


def test_a_removed_linked_worktree_does_not_leak_into_the_main_checkout(tmp_path: Path) -> None:
    main = _project(tmp_path / "praxion")
    linked = main / ".claude" / "worktrees" / "feature"
    linked.mkdir(parents=True)
    (linked / GIT).write_text("pointer to the main checkout's metadata\n", encoding="utf-8")
    assert locate(str(linked)) is None  # alive: its own checkout, holding no state
    (linked / GIT).unlink()
    linked.rmdir()

    assert locate(str(linked)) is None


@pytest.mark.parametrize("cwd", [".", "sub", "sub/deeper", "~/x", "../up"])
def test_a_relative_directory_resolves_to_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cwd: str
) -> None:
    root = _project(tmp_path / "praxion")
    (root / "sub" / "deeper").mkdir(parents=True)
    monkeypatch.chdir(root)

    assert locate(cwd) is None


def test_an_os_error_while_looking_resolves_to_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _project(tmp_path / "praxion")

    def refuse(self: Path) -> bool:
        raise PermissionError("no access")

    monkeypatch.setattr(Path, "is_dir", refuse)

    assert locate(str(root)) is None


# -- the module stays cheap enough for every hook call -----------------------------


def test_the_module_imports_only_what_a_hot_path_may() -> None:
    tree = ast.parse(Path(location.__file__).read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add((node.module or "").split(".")[0])

    assert imported <= _ALLOWED_IMPORTS


def test_the_module_parses_as_python_3_9() -> None:
    source = Path(location.__file__).read_text(encoding="utf-8")

    ast.parse(source, feature_version=(3, 9))
