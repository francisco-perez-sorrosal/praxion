"""The two arms of the refactoring move, built as plugin copies and shown in their preload state.

The builds run over a real materialized copy of this repository, put in the preloaded state with
the repository's own move tool so the tests hold whichever state the checkout is in. Nothing here
starts a ``claude`` process: the copy's own preload reader and spawn hook are the only things run.
"""

from __future__ import annotations

import shutil
import stat
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest
import yaml

from praxion_evals.adherence import axis_runs, refactoring_arms
from praxion_evals.adherence.arms import ArmCopyError, build_refactoring_arm, verify_copy_diff
from praxion_evals.adherence.axis import MOVE_SITES
from praxion_evals.adherence.refactoring_arms import build_refactoring_copy, verify_arm
from praxion_evals.live.materialize import (
    Materialization,
    make_read_only,
    make_writable,
    materialize_path,
    tree_digest,
    tree_entries,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
ROLES = ("implementer", "test-engineer")
LOWERED_CAP = 5
IGNORED_DIRECTORY = "scratch_env"


def _move(root: Path, state: str) -> None:
    subprocess.run(
        [sys.executable, "-B", str(root / "scripts" / "refactoring_move.py")]
        + ["--to", state, "--root", str(root)],
        check=True,
        capture_output=True,
    )


def _as(original: Materialization, state: str, root: Path) -> Materialization:
    """A copy of ``original`` at ``root`` holding ``state``, read-only like any materialization."""
    shutil.copytree(original.root, root, symlinks=True)
    make_writable(root)
    _move(root, state)
    make_read_only(root)
    return replace(original, root=root, tree_digest=tree_digest(root))


@pytest.fixture(scope="module")
def original(tmp_path_factory: pytest.TempPathFactory) -> Materialization:
    checkout = materialize_path(REPO_ROOT, tmp_path_factory.mktemp("source") / "checkout")
    return _as(checkout, "preloaded", tmp_path_factory.mktemp("preloaded") / "checkout")


@pytest.fixture(scope="module")
def built(original: Materialization, tmp_path_factory: pytest.TempPathFactory) -> dict:
    root = tmp_path_factory.mktemp("arms")
    return {
        (arm, cap): build_refactoring_copy(original, root / f"{arm}-{cap}", role, arm, cap)
        for arm, cap, role in (
            ("preloaded", None, "implementer"),
            ("delivered", None, "implementer"),
            ("preloaded", LOWERED_CAP, "test-engineer"),
            ("delivered", LOWERED_CAP, "test-engineer"),
        )
    }


def _frontmatter(root: Path, definition: str) -> dict:
    text = (root / definition).read_text(encoding="utf-8")
    return yaml.safe_load(text.split("---\n", 2)[1])


def test_the_preloaded_copy_is_the_original_and_the_delivered_one_differs_at_the_two_sites(
    original, built
):
    preloaded, delivered = built["preloaded", None], built["delivered", None]

    assert preloaded.patched == ()
    assert delivered.patched == MOVE_SITES
    assert tree_entries(preloaded.copy_root) == tree_entries(original.root)
    verify_copy_diff(preloaded.copy_root, delivered.copy_root, expected=MOVE_SITES)


def test_a_cap_lands_on_the_roles_definition_in_each_arm(built):
    preloaded, delivered = built["preloaded", LOWERED_CAP], built["delivered", LOWERED_CAP]
    uncapped = built["delivered", None]

    assert preloaded.patched == ("agents/test-engineer.md",)
    assert delivered.patched == MOVE_SITES
    for build in (preloaded, delivered):
        assert _frontmatter(build.copy_root, "agents/test-engineer.md")["maxTurns"] == LOWERED_CAP
    other = "agents/implementer.md"
    assert (delivered.copy_root / other).read_bytes() == (uncapped.copy_root / other).read_bytes()


@pytest.mark.parametrize("cap", [None, LOWERED_CAP])
@pytest.mark.parametrize("arm", ["preloaded", "delivered"])
def test_each_copy_is_shown_in_its_arms_preload_state_for_both_roles(built, arm, cap):
    for role in ROLES:
        verify_arm(built[arm, cap].copy_root, arm, role)


@pytest.mark.parametrize("arm", ["preloaded", "delivered"])
def test_a_copy_shown_as_the_other_arm_is_refused(built, arm):
    other = "delivered" if arm == "preloaded" else "preloaded"

    with pytest.raises(ArmCopyError, match=f"the {other} copy"):
        verify_arm(built[arm, None].copy_root, other, "implementer")


def test_a_built_copy_is_read_only_and_names_its_digest(built):
    build = built["delivered", None]

    assert not (build.copy_root / "agents" / "implementer.md").stat().st_mode & stat.S_IWUSR
    assert tree_digest(build.copy_root) == build.tree_digest


def test_an_original_that_is_already_moved_is_refused_and_leaves_nothing(original, tmp_path):
    moved = _as(original, "delivered", tmp_path / "moved")

    with pytest.raises(ArmCopyError, match="the move tool"):
        build_refactoring_copy(moved, tmp_path / "arm", "implementer", "delivered", None)

    assert not (tmp_path / "arm").exists()


def test_an_existing_destination_is_refused_and_left_as_it_was(original, tmp_path):
    (tmp_path / "arm").mkdir()
    (tmp_path / "arm" / "kept").write_text("mine")

    with pytest.raises(ArmCopyError, match="already exists"):
        build_refactoring_copy(original, tmp_path / "arm", "implementer", "delivered", None)

    assert (tmp_path / "arm" / "kept").read_text() == "mine"


@pytest.mark.parametrize(
    ("role", "arm", "cap", "message"),
    [
        ("implementer", "delivered", 0, "turn cap"),
        ("no-such-role", "delivered", None, "unknown role"),
        ("implementer", "full", None, "not an arm"),
    ],
)
def test_a_build_that_cannot_be_asked_for_is_refused_before_anything_is_copied(
    original, tmp_path, role, arm, cap, message
):
    with pytest.raises(ArmCopyError, match=message):
        build_refactoring_copy(original, tmp_path / "arm", role, arm, cap)

    assert not (tmp_path / "arm").exists()


def test_a_copy_that_was_not_moved_is_refused_and_leaves_nothing(original, tmp_path, monkeypatch):
    real = refactoring_arms._move_tool
    monkeypatch.setattr(
        refactoring_arms,
        "_move_tool",
        lambda root, *flags: real(root, *flags) if "--check" in flags else None,
    )

    with pytest.raises(ArmCopyError, match="unchanged"):
        build_refactoring_copy(original, tmp_path / "arm", "implementer", "delivered", None)

    assert not (tmp_path / "arm").exists()


def test_a_delivered_copy_whose_hook_prints_no_block_is_refused_and_leaves_nothing(
    original, tmp_path, monkeypatch
):
    monkeypatch.setattr(refactoring_arms, "_hook_prompt", lambda root, role: None)

    with pytest.raises(ArmCopyError, match="serves no skill block"):
        build_refactoring_copy(original, tmp_path / "arm", "implementer", "delivered", None)

    assert not (tmp_path / "arm").exists()


def test_a_preloaded_copy_whose_hook_prints_a_block_is_refused_and_leaves_nothing(
    original, built, tmp_path, monkeypatch
):
    block = refactoring_arms._hook_prompt(built["delivered", None].copy_root, "implementer")
    monkeypatch.setattr(refactoring_arms, "_hook_prompt", lambda root, role: block)

    with pytest.raises(ArmCopyError, match="serves a skill block"):
        build_refactoring_copy(original, tmp_path / "arm", "implementer", "preloaded", None)

    assert not (tmp_path / "arm").exists()


def test_a_delivered_copy_with_a_silent_hook_is_not_shown(built, tmp_path):
    copy = tmp_path / "copy"
    shutil.copytree(built["delivered", None].copy_root, copy)
    make_writable(copy)
    (copy / "hooks" / "inject_subagent_context.py").write_text("pass\n")

    with pytest.raises(ArmCopyError, match="serves no skill block"):
        verify_arm(copy, "delivered", "implementer")


@pytest.fixture(scope="module")
def committed_checkout(original: Materialization, tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A git checkout of the plugin whose ignore file hides a directory the checkout holds."""
    root = tmp_path_factory.mktemp("repository") / "checkout"
    shutil.copytree(original.root, root, symlinks=True)
    make_writable(root)
    with (root / ".gitignore").open("a", encoding="utf-8") as ignore:
        ignore.write(f"\n{IGNORED_DIRECTORY}/\n")
    (root / IGNORED_DIRECTORY).mkdir()
    (root / IGNORED_DIRECTORY / "site-packages.txt").write_text("a heavy environment")
    identity = ["-c", "user.name=arm-test", "-c", "user.email=arm-test@example.invalid"]
    for command in (["init", "-q"], ["add", "-A"], [*identity, "commit", "-q", "-m", "plugin"]):
        subprocess.run(["git", "-C", str(root), *command], check=True, capture_output=True)
    return root


def _worktree(root: Path) -> dict[str, str]:
    return {k: v for k, v in tree_entries(root).items() if not k.startswith(".git/")}


@pytest.mark.parametrize("arm", ["preloaded", "delivered"])
def test_the_acceptance_wrapper_builds_an_arm_from_a_snapshot_and_leaves_the_checkout_as_it_was(
    committed_checkout, tmp_path, arm
):
    before = _worktree(committed_checkout)

    root = build_refactoring_arm(committed_checkout, arm, tmp_path / arm)

    assert root == tmp_path / arm
    assert not (root / IGNORED_DIRECTORY).exists()
    assert (root / "agents" / "implementer.md").is_file()
    assert _worktree(committed_checkout) == before
    status = subprocess.run(
        ["git", "-C", str(committed_checkout), "status", "--porcelain"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert status.stdout == ""


def test_the_wrapper_leaves_nothing_when_a_later_role_is_not_shown(
    committed_checkout, tmp_path, monkeypatch
):
    real = refactoring_arms.verify_arm

    def refuse_the_second_role(copy_root, arm, role):
        if role == "test-engineer":
            raise ArmCopyError("not shown")
        real(copy_root, arm, role)

    monkeypatch.setattr(refactoring_arms, "verify_arm", refuse_the_second_role)

    with pytest.raises(ArmCopyError, match="not shown"):
        build_refactoring_arm(committed_checkout, "delivered", tmp_path / "arm")

    assert not (tmp_path / "arm").exists()


def test_the_new_axis_builds_its_copies_with_the_refactoring_builder():
    assert axis_runs.axis_run("refactoring-delivery").build is build_refactoring_copy
