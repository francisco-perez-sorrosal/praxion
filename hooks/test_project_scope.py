"""`scope_of` is the one answer to "is this directory served by a managed project?".

A directory is `Managed` exactly when `locate` finds the `.ai-state/` serving it,
and `Unmanaged` otherwise; the predicate cannot drift from the observation
log's because it is derived from `locate`, and these tests hold it to that on
every layout the log is specified against.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

# Flat import, as the sibling hook tests do: the mutation sensor runs this
# directory's files side by side, so a package-qualified import would escape it.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _project_scope import (  # noqa: E402
    DOC_MANIFEST_FILENAME,
    HOOK_WRITTEN_STATE_FILES,
    STATE_DIRNAME,
    SUMMARY_FILENAME,
    TOKEN_BASELINE_FILENAME,
    Managed,
    Unmanaged,
    is_hook_written_state,
    locate,
    scope_of,
)

STATE = ".ai-state"
GIT = ".git"


def _project(root: Path, *, checkout: bool = True) -> Path:
    """A directory holding a state directory, and a `.git` directory unless told not to."""
    root.mkdir(parents=True, exist_ok=True)
    (root / STATE).mkdir()
    if checkout:
        (root / GIT).mkdir()
    return root


def _managed(root: Path) -> Managed:
    return Managed(root, root / STATE)


# -- each layout builds its tree and returns the directory a session starts in ----


def _project_root(base: Path) -> Path:
    return _project(base / "praxion")


def _subdirectory(base: Path) -> Path:
    below = _project(base / "praxion") / "packages" / "app"
    below.mkdir(parents=True)
    return below


def _linked_worktree_carrying_state(base: Path) -> Path:
    worktree = base / "wt"
    (worktree / STATE).mkdir(parents=True)
    (worktree / GIT).write_text("gitdir: /elsewhere/.git/worktrees/wt\n")
    return worktree


def _linked_state(base: Path) -> Path:
    kept = base / "kept-state"
    kept.mkdir()
    project = base / "linked"
    project.mkdir()
    (project / STATE).symlink_to(kept, target_is_directory=True)
    (project / GIT).mkdir()
    return project


def _nested_repository_without_state(base: Path) -> Path:
    inner = _project(base / "outer") / "vendor" / "inner"
    (inner / GIT).mkdir(parents=True)
    return inner


def _nested_repository_with_state(base: Path) -> Path:
    inner = _project(base / "outer") / "vendor" / "inner"
    inner.mkdir(parents=True)
    _project(inner)
    return inner


def _non_repository_with_state(base: Path) -> Path:
    return _project(base / "plain", checkout=False)


def _below_state_outside_a_repository(base: Path) -> Path:
    below = _project(base / "plain", checkout=False) / "src"
    below.mkdir()
    return below


def _no_state_anywhere(base: Path) -> Path:
    bare = base / "bare"
    bare.mkdir()
    return bare


_LAYOUTS: dict[str, Callable[[Path], Path]] = {
    "project-root": _project_root,
    "subdirectory": _subdirectory,
    "linked-worktree": _linked_worktree_carrying_state,
    "linked-state": _linked_state,
    "nested-repository-without-state": _nested_repository_without_state,
    "nested-repository-with-state": _nested_repository_with_state,
    "non-repository-with-state": _non_repository_with_state,
    "below-state-outside-repository": _below_state_outside_a_repository,
    "no-state-anywhere": _no_state_anywhere,
}


@pytest.fixture(params=sorted(_LAYOUTS))
def start(request: pytest.FixtureRequest, tmp_path: Path) -> str:
    return str(_LAYOUTS[request.param](tmp_path))


# -- managed layouts ---------------------------------------------------------------


def test_a_directory_holding_the_state_is_managed_by_itself(tmp_path: Path) -> None:
    root = _project_root(tmp_path)

    assert scope_of(str(root)) == _managed(root)


def test_a_subdirectory_is_managed_by_the_checkout_root(tmp_path: Path) -> None:
    assert scope_of(str(_subdirectory(tmp_path))) == _managed(tmp_path / "praxion")


def test_a_linked_worktree_carrying_the_state_is_managed(tmp_path: Path) -> None:
    worktree = _linked_worktree_carrying_state(tmp_path)

    assert scope_of(str(worktree)) == _managed(worktree)


def test_a_linked_state_directory_counts_and_is_not_resolved(tmp_path: Path) -> None:
    project = _linked_state(tmp_path)

    assert scope_of(str(project)) == _managed(project)


def test_a_nested_repository_with_its_own_state_is_managed_by_it(tmp_path: Path) -> None:
    inner = _nested_repository_with_state(tmp_path)

    assert scope_of(str(inner)) == _managed(inner)


def test_a_directory_outside_a_repository_holding_the_state_is_managed(tmp_path: Path) -> None:
    plain = _non_repository_with_state(tmp_path)

    assert scope_of(str(plain)) == _managed(plain)


# -- unmanaged layouts -------------------------------------------------------------


def test_a_nested_repository_does_not_borrow_its_hosts_state(tmp_path: Path) -> None:
    assert scope_of(str(_nested_repository_without_state(tmp_path))) == Unmanaged()


def test_below_a_state_directory_outside_a_repository_is_unmanaged(tmp_path: Path) -> None:
    assert scope_of(str(_below_state_outside_a_repository(tmp_path))) == Unmanaged()


def test_a_directory_with_no_state_anywhere_is_unmanaged(tmp_path: Path) -> None:
    assert scope_of(str(_no_state_anywhere(tmp_path))) == Unmanaged()


def test_a_relative_path_is_unmanaged(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _project_root(tmp_path)
    monkeypatch.chdir(tmp_path)

    assert scope_of("praxion") == Unmanaged()
    assert scope_of(".") == Unmanaged()


def test_a_missing_path_is_unmanaged_even_below_a_managed_project(tmp_path: Path) -> None:
    root = _project_root(tmp_path)

    assert scope_of(str(root / "removed" / "worktree")) == Unmanaged()


@pytest.mark.parametrize("cwd", ["", None, 7, b"/tmp"])
def test_an_empty_or_non_string_cwd_is_unmanaged(cwd: object) -> None:
    assert scope_of(cwd) == Unmanaged()


@pytest.mark.skipif(os.geteuid() == 0, reason="root reads past permission bits")
def test_an_unreadable_path_is_unmanaged(tmp_path: Path) -> None:
    root = _project_root(tmp_path)
    inside = root / "src"
    inside.mkdir()
    root.chmod(0)
    try:
        assert scope_of(str(inside)) == Unmanaged()
    finally:
        root.chmod(0o755)


# -- the predicate is the log's, by construction -----------------------------------


def test_scope_of_equals_locate_on_every_layout(start: str) -> None:
    found = locate(start)
    expected = Unmanaged() if found is None else Managed(found.project_dir, found.state_dir)

    assert scope_of(start) == expected


def test_the_answer_is_evaluated_afresh_on_every_call(tmp_path: Path) -> None:
    bare = _no_state_anywhere(tmp_path)
    assert scope_of(str(bare)) == Unmanaged()

    (bare / STATE).mkdir()
    assert scope_of(str(bare)) == _managed(bare)

    (bare / STATE).rmdir()
    assert scope_of(str(bare)) == Unmanaged()


def test_managed_names_the_root_and_its_state_directory(tmp_path: Path) -> None:
    scope = scope_of(str(_subdirectory(tmp_path)))

    assert isinstance(scope, Managed)
    assert scope.state_dir == scope.root / STATE


def test_the_two_cases_are_told_apart_by_type_and_never_mutate(tmp_path: Path) -> None:
    managed = scope_of(str(_project_root(tmp_path)))
    unmanaged = scope_of("relative")

    assert isinstance(managed, Managed)
    assert not isinstance(managed, Unmanaged)
    assert isinstance(unmanaged, Unmanaged)
    assert not isinstance(unmanaged, Managed)
    with pytest.raises(AttributeError):
        managed.root = tmp_path  # type: ignore[misc]


# -- Hook-written state ---------------------------------------------------------


@pytest.mark.parametrize("filename", sorted(HOOK_WRITTEN_STATE_FILES))
def test_a_hook_written_file_is_recognised_in_the_state_directory(filename: str) -> None:
    assert is_hook_written_state(f"{STATE_DIRNAME}/{filename}")


def test_a_nested_project_keeps_its_own_hook_written_state() -> None:
    assert is_hook_written_state(f"services/billing/{STATE_DIRNAME}/{SUMMARY_FILENAME}")


def test_a_path_git_quoted_for_its_space_is_still_recognised() -> None:
    assert is_hook_written_state(f'"my project/{STATE_DIRNAME}/{SUMMARY_FILENAME}"')


@pytest.mark.parametrize(
    "path",
    [
        SUMMARY_FILENAME,  # at the checkout root, outside any state directory
        f"exports/{SUMMARY_FILENAME}",
        f"{STATE_DIRNAME}/archive/{SUMMARY_FILENAME}",  # below the state directory, not in it
        f"{STATE_DIRNAME}/TECH_DEBT_LEDGER.md",  # state the work itself edits
        f"not{STATE_DIRNAME}/{SUMMARY_FILENAME}",
        "",
    ],
)
def test_any_other_path_is_ordinary_work(path: str) -> None:
    assert not is_hook_written_state(path)


def test_each_hook_written_name_is_the_one_its_writer_writes() -> None:
    # The set is declared here once; two of its files are written from scripts/,
    # which carry their own path. A writer that renames its file must fail here,
    # or the renamed file silently reads as the session's work again.
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    import check_doc_manifest_freshness
    import measure_token_budget

    assert measure_token_budget._BASELINE_RELATIVE_PATH == (STATE_DIRNAME, TOKEN_BASELINE_FILENAME)
    assert check_doc_manifest_freshness.MANIFEST_REL == f"{STATE_DIRNAME}/{DOC_MANIFEST_FILENAME}"
