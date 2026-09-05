"""Behavioral tests for `_sidecar_convergence.py` -- the state branch slot
(`classify_branch`) and convergence (`merge_back`, `converge`, `drop_branch`).

Every fixture (see `_sidecar_testkit.py`) drives *real* `git worktree` /
`git merge` / `git branch` commands under `tmp_path`; nothing about git is
mocked, because the whole premise this module exists to prove rests on
verified git behaviour -- a mocked git subprocess would prove nothing about
it. The mount slot itself is covered by `test_sidecar_mount.py`.

Import strategy: plain sibling import (`scripts/` has no `__init__.py`, so
pytest's prepend import mode puts it on `sys.path[0]`), matching
`scripts/test_state_repo.py`.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import _sidecar_convergence
import _sidecar_git
import _sidecar_mount
import pytest
from _sidecar_testkit import (
    NullLock,
    build_diverged_fixture,
    build_mixed_fixture,
    commit_all,
    git,
    git_ok,
    init_project,
    init_sidecar,
    mount_main,
    sidecar_snapshot,
    worktree_git_dir,
)

# --- merge_back -----------------------------------------------------------------


def test_merge_back_makes_a_worktree_edit_visible_in_the_target_checkout(tmp_path: Path) -> None:
    fixture = build_diverged_fixture(tmp_path, name="mb")

    result = _sidecar_convergence.merge_back(
        fixture.sidecar_root,
        fixture.project_root,
        fixture.sidecar_branch,
        allow_conflict_markers=False,
    )

    assert result.conflicted is False
    assert (fixture.main_mount / ".ai-state" / "DESIGN.md").read_text() == "mb-change\n"


# --- StateBranchState / classify_branch ------------------------------


def test_state_branch_state_variants_are_frozen_against_mutation() -> None:
    result = _sidecar_convergence.UnmergedIneligible(reason="ProjectBranchNotMerged")

    with pytest.raises(dataclasses.FrozenInstanceError):
        result.reason = "MappingMissing"  # type: ignore[misc]


def test_classify_branch_reports_not_merged_before_any_project_merge(tmp_path: Path) -> None:
    fixture = build_diverged_fixture(tmp_path, name="pending")

    result = _sidecar_convergence.classify_branch(
        fixture.sidecar_root, fixture.project_root, fixture.sidecar_branch, fixture.project_root
    )

    assert result == _sidecar_convergence.UnmergedIneligible(reason="ProjectBranchNotMerged")


def test_classify_branch_detects_a_regular_merge_as_ancestor_evidence(tmp_path: Path) -> None:
    fixture = build_diverged_fixture(tmp_path, name="anc")
    git_ok(fixture.project_root, "merge", "-q", "--no-ff", "--no-edit", fixture.project_branch)

    result = _sidecar_convergence.classify_branch(
        fixture.sidecar_root, fixture.project_root, fixture.sidecar_branch, fixture.project_root
    )

    assert result == _sidecar_convergence.UnmergedEligible(evidence="Ancestor")


def test_classify_branch_detects_a_github_style_squash_merge_the_ancestor_test_misses(
    tmp_path: Path,
) -> None:
    fixture = build_diverged_fixture(tmp_path, name="sq")

    # A GitHub squash-merge: the feature branch's tree lands in one new
    # commit on main with no ancestry link back to the branch -- exactly the
    # shape the plain ancestor test cannot see.
    git_ok(fixture.project_root, "merge", "-q", "--squash", fixture.project_branch)
    commit_all(fixture.project_root, f"squash-merge {fixture.project_branch}")

    ancestor_only = git(
        fixture.project_root, "merge-base", "--is-ancestor", fixture.project_branch, "HEAD"
    )
    assert ancestor_only.returncode != 0, (
        "fixture invariant: the ancestor test alone must fail here"
    )

    result = _sidecar_convergence.classify_branch(
        fixture.sidecar_root, fixture.project_root, fixture.sidecar_branch, fixture.project_root
    )

    assert result == _sidecar_convergence.UnmergedEligible(evidence="SquashedTree")


def test_squash_probe_writes_nothing_into_the_project_object_store(tmp_path: Path) -> None:
    """The probe is pure: neither a hit nor a miss leaves an object behind."""
    fixture = build_diverged_fixture(tmp_path, name="pure")
    head = git_ok(fixture.project_root, "rev-parse", "HEAD").stdout.strip()
    before = git_ok(fixture.project_root, "count-objects", "-v").stdout

    missed = _sidecar_git.patch_already_applied(fixture.project_root, head, fixture.project_branch)
    git_ok(fixture.project_root, "merge", "-q", "--squash", fixture.project_branch)
    commit_all(fixture.project_root, f"squash-merge {fixture.project_branch}")
    squashed_head = git_ok(fixture.project_root, "rev-parse", "HEAD").stdout.strip()
    after_squash = git_ok(fixture.project_root, "count-objects", "-v").stdout
    hit = _sidecar_git.patch_already_applied(
        fixture.project_root, squashed_head, fixture.project_branch
    )

    assert (missed, hit) == (False, True)
    assert git_ok(fixture.project_root, "count-objects", "-v").stdout == after_squash
    assert before != after_squash  # the squash commit itself is the only write


def test_classify_branch_never_raises_on_an_unresolvable_recorded_ref(tmp_path: Path) -> None:
    sidecar_root = tmp_path / "sidecar"
    project_root = tmp_path / "project"
    init_sidecar(sidecar_root)
    init_project(project_root)
    mount_main(sidecar_root, project_root)
    git_ok(sidecar_root, "branch", "wt/gone", "main")
    git_ok(sidecar_root, "config", "branch.wt/gone.praxion-project-branch", "feat/never-existed")

    result = _sidecar_convergence.classify_branch(
        sidecar_root, project_root, "wt/gone", project_root
    )

    assert result == _sidecar_convergence.UnmergedIneligible(reason="MappingUnresolvable")


def test_classify_branch_reports_missing_mapping_without_raising(tmp_path: Path) -> None:
    sidecar_root = tmp_path / "sidecar"
    project_root = tmp_path / "project"
    init_sidecar(sidecar_root)
    init_project(project_root)
    mount_main(sidecar_root, project_root)
    git_ok(sidecar_root, "branch", "wt/unmapped", "main")  # predates the mapping scheme

    result = _sidecar_convergence.classify_branch(
        sidecar_root, project_root, "wt/unmapped", project_root
    )

    assert result == _sidecar_convergence.UnmergedIneligible(reason="MappingMissing")


def test_classify_branch_reflects_current_tips_not_a_cached_state(tmp_path: Path) -> None:
    """No persisted state: once a branch's sidecar commits move past what
    was converged, the next call re-classifies from the current tips -- it
    does not stay latched at the old result.
    """
    fixture = build_diverged_fixture(tmp_path, name="live")
    git_ok(fixture.project_root, "merge", "-q", "--no-ff", "--no-edit", fixture.project_branch)
    _sidecar_convergence.converge(
        fixture.sidecar_root, fixture.project_root, fixture.project_root, lock=NullLock()
    )
    merged_once = _sidecar_convergence.classify_branch(
        fixture.sidecar_root, fixture.project_root, fixture.sidecar_branch, fixture.project_root
    )
    assert isinstance(merged_once, _sidecar_convergence.MergedLive)

    # The worktree is still live and keeps writing state after convergence.
    (fixture.wt_mount / ".ai-state" / "DESIGN.md").write_text("live-more\n")
    commit_all(fixture.wt_mount, "more state after convergence")

    result = _sidecar_convergence.classify_branch(
        fixture.sidecar_root, fixture.project_root, fixture.sidecar_branch, fixture.project_root
    )

    assert result == _sidecar_convergence.UnmergedEligible(evidence="Ancestor")


# --- converge() ------------------------------------------------------------------


def test_converge_aborts_a_genuine_conflict_and_leaves_the_mount_clean(tmp_path: Path) -> None:
    fixture = build_diverged_fixture(tmp_path, name="conflict")
    # Independent, conflicting edit on the MAIN sidecar branch itself.
    (fixture.main_mount / ".ai-state" / "DESIGN.md").write_text("main-change\n")
    commit_all(fixture.main_mount, "main state, diverging")
    git_ok(fixture.project_root, "merge", "-q", "--no-ff", "--no-edit", fixture.project_branch)

    result = _sidecar_convergence.converge(
        fixture.sidecar_root, fixture.project_root, fixture.project_root, lock=NullLock()
    )

    assert fixture.sidecar_branch in result.aborted
    git_dir = worktree_git_dir(fixture.main_mount)
    assert not (git_dir / "MERGE_HEAD").exists()
    assert git_ok(fixture.main_mount, "status", "--porcelain").stdout == ""
    assert git(fixture.sidecar_root, "rev-parse", fixture.sidecar_branch).returncode == 0


def test_converge_is_a_zero_write_no_op_at_the_fixed_point(tmp_path: Path) -> None:
    """Zero writes means the sidecar, every mount, *and* the project's object
    store: the mixed fixture keeps one branch ineligible forever, so the
    squash probe runs on every call and must leave no object behind.
    """
    fixture = build_mixed_fixture(tmp_path)
    mounts = (fixture.main_mount, fixture.eligible.wt_mount, fixture.ineligible.wt_mount)

    first = _sidecar_convergence.converge(
        fixture.sidecar_root, fixture.project_root, fixture.project_root, lock=NullLock()
    )
    assert fixture.eligible.sidecar_branch in first.merged

    snapshot_after_first = sidecar_snapshot(fixture.sidecar_root, mounts, fixture.project_root)
    _sidecar_convergence.converge(
        fixture.sidecar_root, fixture.project_root, fixture.project_root, lock=NullLock()
    )
    snapshot_after_second = sidecar_snapshot(fixture.sidecar_root, mounts, fixture.project_root)
    _sidecar_convergence.converge(
        fixture.sidecar_root, fixture.project_root, fixture.project_root, lock=NullLock()
    )
    snapshot_after_third = sidecar_snapshot(fixture.sidecar_root, mounts, fixture.project_root)

    assert snapshot_after_second == snapshot_after_first
    assert snapshot_after_third == snapshot_after_second


def test_ineligible_branch_survives_converge_across_three_different_checkouts(
    tmp_path: Path,
) -> None:
    fixture = build_mixed_fixture(tmp_path)
    before_commit = git_ok(
        fixture.sidecar_root, "rev-parse", fixture.ineligible.sidecar_branch
    ).stdout.strip()

    # Channel 1: the project post-merge finalize chain, running in the main checkout.
    _sidecar_convergence.converge(
        fixture.sidecar_root, fixture.project_root, fixture.project_root, lock=NullLock()
    )
    # Channel 2: the SessionStart heal, running inside a linked worktree's own
    # checkout -- a different `checkout` argument, same sidecar repo.
    _sidecar_convergence.converge(
        fixture.sidecar_root, fixture.eligible.wt_checkout, fixture.project_root, lock=NullLock()
    )
    # Channel 3: the main checkout again (mirrors the explicit /merge-worktree
    # channel resolving to the same call shape once nothing new is eligible).
    _sidecar_convergence.converge(
        fixture.sidecar_root, fixture.project_root, fixture.project_root, lock=NullLock()
    )

    after_commit = git_ok(
        fixture.sidecar_root, "rev-parse", fixture.ineligible.sidecar_branch
    ).stdout.strip()
    mapping = git_ok(
        fixture.sidecar_root,
        "config",
        "--get",
        f"branch.{fixture.ineligible.sidecar_branch}.praxion-project-branch",
    ).stdout.strip()

    assert after_commit == before_commit
    assert mapping == fixture.ineligible.project_branch


def test_converge_dry_run_reports_the_plan_and_mutates_nothing(tmp_path: Path) -> None:
    fixture = build_diverged_fixture(tmp_path, name="dry")
    git_ok(fixture.project_root, "merge", "-q", "--no-ff", "--no-edit", fixture.project_branch)
    snapshot_before = sidecar_snapshot(
        fixture.sidecar_root, (fixture.main_mount, fixture.wt_mount), fixture.project_root
    )

    result = _sidecar_convergence.converge(
        fixture.sidecar_root,
        fixture.project_root,
        fixture.project_root,
        dry_run=True,
        lock=NullLock(),
    )

    assert fixture.sidecar_branch in result.merged
    snapshot_after = sidecar_snapshot(
        fixture.sidecar_root, (fixture.main_mount, fixture.wt_mount), fixture.project_root
    )
    assert snapshot_after == snapshot_before


def test_converge_automatically_deletes_a_merged_orphan_branch(tmp_path: Path) -> None:
    fixture = build_diverged_fixture(tmp_path, name="orphan")
    git_ok(fixture.project_root, "merge", "-q", "--no-ff", "--no-edit", fixture.project_branch)
    _sidecar_convergence.converge(
        fixture.sidecar_root, fixture.project_root, fixture.project_root, lock=NullLock()
    )
    # The mount is removed first, then the project worktree -- the lifecycle
    # order that turns MergedLive into MergedOrphan.
    _sidecar_mount.prune_mount(fixture.sidecar_root, fixture.wt_checkout)
    git_ok(fixture.project_root, "worktree", "remove", "--force", str(fixture.wt_checkout))

    _sidecar_convergence.converge(
        fixture.sidecar_root, fixture.project_root, fixture.project_root, lock=NullLock()
    )

    assert git(fixture.sidecar_root, "rev-parse", fixture.sidecar_branch).returncode != 0


def test_converge_never_auto_drops_an_unmerged_ineligible_branch(tmp_path: Path) -> None:
    fixture = build_diverged_fixture(tmp_path, name="keep")
    _sidecar_mount.prune_mount(
        fixture.sidecar_root, fixture.wt_checkout
    )  # unblocks drop_branch, not converge

    for _ in range(3):
        _sidecar_convergence.converge(
            fixture.sidecar_root, fixture.project_root, fixture.project_root, lock=NullLock()
        )

    assert git(fixture.sidecar_root, "rev-parse", fixture.sidecar_branch).returncode == 0


# --- can_drop_branch / drop_branch ------------------------------------------------


def test_can_drop_branch_is_refused_while_its_mount_still_exists(tmp_path: Path) -> None:
    fixture = build_diverged_fixture(tmp_path, name="hold")

    precondition = _sidecar_convergence.can_drop_branch(
        fixture.sidecar_root, fixture.sidecar_branch
    )

    assert precondition.ready is False


def test_can_drop_branch_is_accepted_once_the_mount_is_pruned(tmp_path: Path) -> None:
    fixture = build_diverged_fixture(tmp_path, name="free")
    _sidecar_mount.prune_mount(fixture.sidecar_root, fixture.wt_checkout)

    precondition = _sidecar_convergence.can_drop_branch(
        fixture.sidecar_root, fixture.sidecar_branch
    )

    assert precondition.ready is True


def test_drop_branch_is_the_only_path_that_removes_an_unmerged_branch(tmp_path: Path) -> None:
    fixture = build_diverged_fixture(tmp_path, name="drop")
    _sidecar_mount.prune_mount(fixture.sidecar_root, fixture.wt_checkout)

    _sidecar_convergence.drop_branch(fixture.sidecar_root, fixture.sidecar_branch)

    assert git(fixture.sidecar_root, "rev-parse", fixture.sidecar_branch).returncode != 0
