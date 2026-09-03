"""Behavioral tests for `_sidecar_checks.py` -- the D3 single-source check
registry (`INTERFACE_DESIGN.md` sec. 7.3) plus the four DS-11 convergence
rows folded in by `ARCH_WT_RULING.md` sec. 13.6.

`_sidecar_checks.py` does not exist yet (concurrent BDD/TDD with its
implementation) -- this is the RED skeleton, confirmed to fail on
`ModuleNotFoundError` before the module lands.

`evaluate_checks()` is a pure function over *already-classified* inputs --
no git, no filesystem, no subprocess (verified below by monkeypatching both
`subprocess.run` and the `os.stat`-family to raise inside the call). Nearly
every fixture is therefore a plain in-memory `CheckInputs`, not a git
repository -- that is the point of the design (`status`/`doctor`/the
SessionStart banner are all thin projections of the same list this module
returns). The two exceptions are the `hooks-path`/`hooks-chained` rows,
whose fixtures are real `install_git_hooks.build_status()` payloads (that
module already exists, owns its own JSON shape, and is only *re-read* here
-- per `INTERFACE_DESIGN.md` sec. 7.3's "one repairer, two readers" split).

Design decision recorded for the implementer (mirrored in
`LEARNINGS_test-engineer.md` "Assumptions & Constraints Taken"):
`CheckInputs.shadow_slots` / `.shared_slots` take *already-resolved*
per-path state enums (`ShadowState` / `SharedState`, both owned by
`_sidecar_checks.py` itself) rather than the raw `_sidecar_link.ShadowSlotState`
sum type. Two reasons: (1) it decouples this suite from the sibling
shadow-symlink module's landing order -- `_sidecar_link.py` does not exist
yet either; (2) the
`LinkToThisSidecar`-vs-`dangling` distinction needs an `os.path.exists`
probe on the symlink target, which belongs at the CLI wiring layer that
builds a `CheckInputs`, not inside this module's pure `evaluate_checks`.

`CheckInputs.mount` / `.branches` DO use the real `_sidecar_mount` sum
types (`StateMountState`, `StateBranchState`) directly -- that module is
landed and importable, so there is no decoupling reason to shadow it with
a local type.

Import strategy: plain sibling import (`scripts/` has no `__init__.py`, so
pytest's prepend import mode puts it on `sys.path[0]`), matching
`scripts/test_sidecar_mount.py` and `scripts/test_state_repo.py`.
"""

from __future__ import annotations

import dataclasses
import os
import re
import subprocess
from pathlib import Path

import _sidecar_checks
import _sidecar_commit
import _sidecar_mount
import _state_repo
import install_git_hooks
import pytest

# --- shared fixtures: a real install_git_hooks.build_status() payload ------


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    )


def _write_and_chmod(path: Path, content: str) -> None:
    path.write_text(content)
    path.chmod(0o755)


@pytest.fixture
def hooks_repo(tmp_path: Path) -> Path:
    root = tmp_path / "hooks-repo"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@t.t")
    _git(root, "config", "user.name", "t")
    (root / "README.md").write_text("x\n")
    _git(root, "add", "README.md")
    _git(root, "commit", "-q", "-m", "init")
    return root


@pytest.fixture
def hooks_plugin_root(tmp_path: Path) -> Path:
    root = tmp_path / "plugin"
    (root / "scripts" / "assets").mkdir(parents=True)
    _write_and_chmod(
        root / "scripts" / install_git_hooks.FINALIZE_DISPATCHER,
        '#!/usr/bin/env bash\necho "dispatch:$(basename "$0")" >&2\nexit 0\n',
    )
    _write_and_chmod(
        root / "scripts" / "assets" / "praxion-precommit-hook.sh.tmpl",
        "#!/usr/bin/env bash\nexit 0\n",
    )
    return root


def _healthy_hooks_status(repo: Path, plugin_root: Path) -> dict:
    install_git_hooks.install_or_heal(repo, "install", plugin_root)
    return install_git_hooks.build_status(repo, plugin_root)


def _stale_hooks_status(repo: Path, plugin_root: Path) -> dict:
    """One hook slot deleted after a clean install -- `cannot_fire` names it,
    while the remaining slots still fire. A fresh install with no
    pre-existing `core.hooksPath` writes plain slots directly into
    `.git/hooks/<name>` (`hooks_path_state: "Unset"`) -- a wrapper
    *directory* only exists once a `Foreign` `core.hooksPath` is adopted,
    see `test_hooks_chained_with_an_adopted_team_hook_is_pass`."""
    install_git_hooks.install_or_heal(repo, "install", plugin_root)
    (repo / ".git" / "hooks" / "pre-commit").unlink()
    return install_git_hooks.build_status(repo, plugin_root)


def _unresolvable_hooks_status(repo: Path) -> dict:
    """`core.hooksPath` points at a file, not a directory -- `Unresolvable`."""
    bogus = repo / "not-a-dir"
    bogus.write_text("x\n")
    _git(repo, "config", "core.hooksPath", str(bogus))
    return install_git_hooks.build_status(repo, plugin_root=repo)


# --- CheckInputs builder -----------------------------------------------------


def _sidecar_owned_placement() -> _state_repo.SidecarOwned:
    """A minimal-but-real `SidecarOwned` -- only the discriminator (which
    variant, not the path values) matters to `evaluate_checks`."""
    root = Path("/project")
    return _state_repo.SidecarOwned(
        project_root=root,
        state_dir=root / ".ai-state",
        mount_dir=root / ".praxion",
        state_git_root=root / ".praxion",
        sidecar_common_dir=Path("/sidecar-common"),
        branch="main",
        identity=_state_repo.SidecarIdentity(schema=1, id="local--test", origin=None),
    )


def _in_repo_placement() -> _state_repo.InRepo:
    root = Path("/project")
    return _state_repo.InRepo(project_root=root, state_dir=root / ".ai-state", state_git_root=root)


def _healthy_sidecar_owned_inputs(hooks_status: dict) -> _sidecar_checks.CheckInputs:
    """A fully-healthy `SidecarOwned` `CheckInputs` -- every non-hook row at
    its fixed point. Individual tests override one field via
    `dataclasses.replace` to drive a single row into WARN or FAIL.
    """
    return _sidecar_checks.CheckInputs(
        placement=_sidecar_owned_placement(),
        exclude_block=_sidecar_checks.ExcludeBlockState.CURRENT,
        shadow_slots={".ai-state": _sidecar_checks.ShadowState.LINKED},
        shared_slots={"docs/architecture.md": _sidecar_checks.SharedState.SHARED},
        untouched_paths={"CLAUDE.md": "preexisting-team-file"},
        hooks_status=hooks_status,
        mount=_sidecar_mount.SidecarWorktree(branch="main", sidecar_common_dir=Path("/sidecar")),
        branches={},
        orphaned_mounts=(),
        mount_mid_merge=False,
        sidecar_repo=_sidecar_checks.SidecarRepoState(
            is_git_repo=True, dirty_files=0, unpushed_commits=0
        ),
        remote=None,
        guards_roots_stale=False,
        lock_state=None,
    )


@pytest.fixture
def healthy_inputs(hooks_repo: Path, hooks_plugin_root: Path) -> _sidecar_checks.CheckInputs:
    return _healthy_sidecar_owned_inputs(_healthy_hooks_status(hooks_repo, hooks_plugin_root))


def _result(results: list, check_id: str) -> _sidecar_checks.CheckResult:
    matches = [r for r in results if r.id == check_id]
    assert matches, f"no {check_id!r} row in {[r.id for r in results]}"
    return matches[0]


# --- exclude-block -----------------------------------------------------------


def test_exclude_block_present_and_current_is_pass(healthy_inputs) -> None:
    results = _sidecar_checks.evaluate_checks(healthy_inputs)

    row = _result(results, "exclude-block")
    assert row.verdict == _sidecar_checks.Verdict.PASS
    assert row.why is None
    assert row.fix is None


def test_exclude_block_absent_is_fail(healthy_inputs) -> None:
    inputs = dataclasses.replace(
        healthy_inputs, exclude_block=_sidecar_checks.ExcludeBlockState.ABSENT
    )

    row = _result(_sidecar_checks.evaluate_checks(inputs), "exclude-block")

    assert row.verdict == _sidecar_checks.Verdict.FAIL
    assert row.fix == "praxion-sidecar link"


def test_exclude_block_drifted_from_manifest_is_warn(healthy_inputs) -> None:
    inputs = dataclasses.replace(
        healthy_inputs, exclude_block=_sidecar_checks.ExcludeBlockState.DRIFTED
    )

    row = _result(_sidecar_checks.evaluate_checks(inputs), "exclude-block")

    assert row.verdict == _sidecar_checks.Verdict.WARN
    assert row.fix == "praxion-sidecar link"


# --- shadow:<path> ------------------------------------------------------------


def test_shadow_slot_linked_is_pass(healthy_inputs) -> None:
    row = _result(_sidecar_checks.evaluate_checks(healthy_inputs), "shadow:.ai-state")

    assert row.verdict == _sidecar_checks.Verdict.PASS


def test_shadow_slot_missing_is_warn(healthy_inputs) -> None:
    inputs = dataclasses.replace(
        healthy_inputs, shadow_slots={".ai-state": _sidecar_checks.ShadowState.MISSING}
    )

    row = _result(_sidecar_checks.evaluate_checks(inputs), "shadow:.ai-state")

    assert row.verdict == _sidecar_checks.Verdict.WARN
    assert row.fix == "praxion-sidecar link"


def test_shadow_slot_dangling_is_warn(healthy_inputs) -> None:
    inputs = dataclasses.replace(
        healthy_inputs, shadow_slots={".ai-state": _sidecar_checks.ShadowState.DANGLING}
    )

    row = _result(_sidecar_checks.evaluate_checks(inputs), "shadow:.ai-state")

    assert row.verdict == _sidecar_checks.Verdict.WARN
    assert row.fix == "praxion-sidecar link"


def test_shadow_slot_blocked_is_fail_with_a_move_command_naming_the_path(healthy_inputs) -> None:
    inputs = dataclasses.replace(
        healthy_inputs,
        shadow_slots={"CLAUDE.md": _sidecar_checks.ShadowState.BLOCKED},
    )

    row = _result(_sidecar_checks.evaluate_checks(inputs), "shadow:CLAUDE.md")

    assert row.verdict == _sidecar_checks.Verdict.FAIL
    assert row.fix == "mv CLAUDE.md CLAUDE.md.team && praxion-sidecar link"


def test_shadow_slot_foreign_is_fail(healthy_inputs) -> None:
    inputs = dataclasses.replace(
        healthy_inputs,
        shadow_slots={".ai-state": _sidecar_checks.ShadowState.FOREIGN},
    )

    row = _result(_sidecar_checks.evaluate_checks(inputs), "shadow:.ai-state")

    assert row.verdict == _sidecar_checks.Verdict.FAIL
    assert row.fix == "praxion-sidecar link"


# --- shared:<path> ------------------------------------------------------------


def test_shared_slot_shared_is_pass(healthy_inputs) -> None:
    row = _result(_sidecar_checks.evaluate_checks(healthy_inputs), "shared:docs/architecture.md")

    assert row.verdict == _sidecar_checks.Verdict.PASS


def test_shared_slot_unexpected_symlink_is_warn(healthy_inputs) -> None:
    inputs = dataclasses.replace(
        healthy_inputs,
        shared_slots={"docs/architecture.md": _sidecar_checks.SharedState.UNEXPECTED_SYMLINK},
    )

    row = _result(_sidecar_checks.evaluate_checks(inputs), "shared:docs/architecture.md")

    assert row.verdict == _sidecar_checks.Verdict.WARN
    assert row.fix == "praxion-sidecar link"


# --- hooks-path / hooks-chained (P0, unchanged; re-read only) ---------------


def test_hooks_path_freshly_installed_is_pass(healthy_inputs) -> None:
    row = _result(_sidecar_checks.evaluate_checks(healthy_inputs), "hooks-path")

    assert row.verdict == _sidecar_checks.Verdict.PASS


def test_hooks_path_stale_slot_is_warn(hooks_repo: Path, hooks_plugin_root: Path) -> None:
    stale_status = _stale_hooks_status(hooks_repo, hooks_plugin_root)
    inputs = _healthy_sidecar_owned_inputs(stale_status)

    row = _result(_sidecar_checks.evaluate_checks(inputs), "hooks-path")

    assert row.verdict == _sidecar_checks.Verdict.WARN
    assert row.fix == "scripts/upgrade_project_pins.sh"


def test_hooks_path_unresolvable_hookspath_is_fail(hooks_repo: Path) -> None:
    unresolvable_status = _unresolvable_hooks_status(hooks_repo)
    inputs = _healthy_sidecar_owned_inputs(unresolvable_status)

    row = _result(_sidecar_checks.evaluate_checks(inputs), "hooks-path")

    assert row.verdict == _sidecar_checks.Verdict.FAIL
    assert row.fix == "scripts/upgrade_project_pins.sh"


def test_hooks_chained_absent_when_no_wrapper_installed(healthy_inputs) -> None:
    """Nothing to chain, nothing to check -- the `healthy_inputs` baseline (a
    freshly-installed repo with no prior pre-commit hook) writes plain,
    non-chaining slots, so there is no wrapper body a chain call could go
    missing from and the row is skipped entirely."""
    results = _sidecar_checks.evaluate_checks(healthy_inputs)

    assert "hooks-chained" not in {r.id for r in results}


def _adopted_foreign_hooks_status(hooks_repo: Path, hooks_plugin_root: Path) -> dict:
    """A pre-existing team `core.hooksPath` adopted into Praxion's own
    wrapper directory, with the original recorded as `delegate` -- the
    genuine chaining case, whose wrapper files carry a real chain call to
    check (distinct from "nothing to chain")."""
    team_hooks_dir = hooks_repo / "team-hooks"
    team_hooks_dir.mkdir()
    _write_and_chmod(team_hooks_dir / "pre-commit", "#!/usr/bin/env bash\nexit 0\n")
    _git(hooks_repo, "config", "core.hooksPath", str(team_hooks_dir))
    status = _healthy_hooks_status(hooks_repo, hooks_plugin_root)
    assert status["delegate"] is not None, "fixture must produce a real chained delegate"
    return status


def test_hooks_chained_with_an_adopted_team_hook_is_pass(
    hooks_repo: Path, hooks_plugin_root: Path
) -> None:
    status = _adopted_foreign_hooks_status(hooks_repo, hooks_plugin_root)
    inputs = _healthy_sidecar_owned_inputs(status)

    row = _result(_sidecar_checks.evaluate_checks(inputs), "hooks-chained")

    assert row.verdict == _sidecar_checks.Verdict.PASS


def test_hooks_chained_missing_chain_call_is_fail_naming_the_slot(
    hooks_repo: Path, hooks_plugin_root: Path
) -> None:
    """Canary: strip the chain call out of one installed wrapper's body and
    re-read `build_status()` -- `hooks-chained` must FAIL and name the slot."""
    _adopted_foreign_hooks_status(hooks_repo, hooks_plugin_root)
    common_dir = Path(
        _git(hooks_repo, "rev-parse", "--path-format=absolute", "--git-common-dir").stdout.strip()
    )
    wrapper_path = common_dir / "praxion-hooks" / "pre-commit"
    body = wrapper_path.read_text(encoding="utf-8")
    corrupted = body.replace("praxion-precommit-hook.sh.tmpl", "")
    wrapper_path.write_text(corrupted, encoding="utf-8")
    status = install_git_hooks.build_status(hooks_repo, hooks_plugin_root)
    inputs = _healthy_sidecar_owned_inputs(status)

    row = _result(_sidecar_checks.evaluate_checks(inputs), "hooks-chained")

    assert row.verdict == _sidecar_checks.Verdict.FAIL
    assert "pre-commit" in row.detail


# --- sidecar-repo --------------------------------------------------------------


def test_sidecar_repo_clean_is_pass(healthy_inputs) -> None:
    row = _result(_sidecar_checks.evaluate_checks(healthy_inputs), "sidecar-repo")

    assert row.verdict == _sidecar_checks.Verdict.PASS


def test_sidecar_repo_not_a_git_repo_is_fail(healthy_inputs) -> None:
    inputs = dataclasses.replace(
        healthy_inputs,
        sidecar_repo=_sidecar_checks.SidecarRepoState(
            is_git_repo=False, dirty_files=0, unpushed_commits=0
        ),
    )

    row = _result(_sidecar_checks.evaluate_checks(inputs), "sidecar-repo")

    assert row.verdict == _sidecar_checks.Verdict.FAIL
    assert row.fix == "praxion-sidecar commit"


def test_sidecar_repo_dirty_is_warn(healthy_inputs) -> None:
    inputs = dataclasses.replace(
        healthy_inputs,
        sidecar_repo=_sidecar_checks.SidecarRepoState(
            is_git_repo=True, dirty_files=3, unpushed_commits=0
        ),
    )

    row = _result(_sidecar_checks.evaluate_checks(inputs), "sidecar-repo")

    assert row.verdict == _sidecar_checks.Verdict.WARN
    assert row.fix == "praxion-sidecar commit"


def test_sidecar_repo_over_fifty_unpushed_commits_is_warn(healthy_inputs) -> None:
    inputs = dataclasses.replace(
        healthy_inputs,
        sidecar_repo=_sidecar_checks.SidecarRepoState(
            is_git_repo=True, dirty_files=0, unpushed_commits=51
        ),
    )

    row = _result(_sidecar_checks.evaluate_checks(inputs), "sidecar-repo")

    assert row.verdict == _sidecar_checks.Verdict.WARN


# --- state-unmerged (DS-11 convergence row) -------------------------------


@pytest.mark.parametrize(
    "reason",
    [
        _sidecar_mount.IneligibilityReason.PROJECT_BRANCH_NOT_MERGED,
        _sidecar_mount.IneligibilityReason.PROJECT_BRANCH_DELETED,
        _sidecar_mount.IneligibilityReason.MAPPING_MISSING,
        _sidecar_mount.IneligibilityReason.MAPPING_UNRESOLVABLE,
    ],
)
def test_state_unmerged_names_the_exact_ineligibility_reason(healthy_inputs, reason) -> None:
    inputs = dataclasses.replace(
        healthy_inputs,
        branches={"wt/auth-flow": _sidecar_mount.UnmergedIneligible(reason=reason)},
    )

    results = _sidecar_checks.evaluate_checks(inputs)
    row = next(r for r in results if r.id == "state-unmerged")

    assert row.verdict == _sidecar_checks.Verdict.WARN
    assert reason.value in row.detail
    assert row.fix == "praxion-sidecar merge-back --from wt/auth-flow"


def test_state_unmerged_mapping_unresolvable_reason_is_named_verbatim(healthy_inputs) -> None:
    """Every ineligibility reason is *named*, not merely detected -- a bare
    "some reason present" detail would satisfy a looser assertion but not
    this one.
    """
    inputs = dataclasses.replace(
        healthy_inputs,
        branches={
            "wt/spike": _sidecar_mount.UnmergedIneligible(
                reason=_sidecar_mount.IneligibilityReason.MAPPING_UNRESOLVABLE
            )
        },
    )

    row = next(r for r in _sidecar_checks.evaluate_checks(inputs) if r.id == "state-unmerged")

    assert "MappingUnresolvable" in row.detail


# --- state-eligible (DS-11 convergence row) -------------------------------


def test_state_eligible_but_not_converged_is_warn(healthy_inputs) -> None:
    inputs = dataclasses.replace(
        healthy_inputs,
        branches={
            "wt/auth-flow": _sidecar_mount.UnmergedEligible(
                evidence=_sidecar_mount.MergeEvidence.ANCESTOR
            )
        },
    )

    row = next(r for r in _sidecar_checks.evaluate_checks(inputs) if r.id == "state-eligible")

    assert row.verdict == _sidecar_checks.Verdict.WARN
    assert row.fix == "praxion-sidecar link"


# --- mount-orphaned (DS-11 convergence row) --------------------------------


def test_mount_orphaned_entry_is_warn(healthy_inputs) -> None:
    inputs = dataclasses.replace(healthy_inputs, orphaned_mounts=("wt/gone",))

    row = next(r for r in _sidecar_checks.evaluate_checks(inputs) if r.id == "mount-orphaned")

    assert row.verdict == _sidecar_checks.Verdict.WARN
    assert row.fix == "praxion-sidecar link --prune"
    assert "wt/gone" in row.detail


# --- mount-conflict (DS-11 convergence row) --------------------------------


def test_mount_left_mid_merge_is_fail(healthy_inputs) -> None:
    inputs = dataclasses.replace(healthy_inputs, mount_mid_merge=True)

    row = next(r for r in _sidecar_checks.evaluate_checks(inputs) if r.id == "mount-conflict")

    assert row.verdict == _sidecar_checks.Verdict.FAIL


def test_mount_conflict_message_states_the_fact_and_both_exits_without_accusation(
    healthy_inputs,
) -> None:
    """The non-accusatory wording rule (`ARCH_WT_RULING.md` sec. 14,
    objection 5): the explicit `merge-back --from` is a *sanctioned* way to
    reach this state, and a read-only `doctor` cannot tell in-progress
    resolution from an abandoned mount -- the message states the fact and
    both exits, never that a rule was violated.
    """
    inputs = dataclasses.replace(healthy_inputs, mount_mid_merge=True)

    row = next(r for r in _sidecar_checks.evaluate_checks(inputs) if r.id == "mount-conflict")
    rendered = " ".join(filter(None, [row.detail, row.why, row.fix])).lower()

    for forbidden in ("violat", "should not", "must not", "illegal"):
        assert forbidden not in rendered, f"accusatory wording {forbidden!r} in {rendered!r}"
    assert "resolve" in rendered, "resolve-and-commit exit not named"
    assert "commit" in rendered, "resolve-and-commit exit not named"
    assert "abort" in rendered, "abort exit not named"


def test_mount_conflict_absent_when_no_mount_is_mid_merge(healthy_inputs) -> None:
    results = _sidecar_checks.evaluate_checks(healthy_inputs)

    assert "mount-conflict" not in [r.id for r in results]


# --- remote-policy --------------------------------------------------------------


def test_remote_policy_absent_remote_is_pass(healthy_inputs) -> None:
    row = _result(_sidecar_checks.evaluate_checks(healthy_inputs), "remote-policy")

    assert row.verdict == _sidecar_checks.Verdict.PASS


def test_remote_policy_foreign_host_with_no_ack_is_fail(healthy_inputs) -> None:
    inputs = dataclasses.replace(
        healthy_inputs,
        remote=_sidecar_checks.RemoteState(
            url="https://gitlab.example.com/acme/billing",
            push="never",
            host_matches_origin=False,
            foreign_host_ack=False,
            has_upstream=True,
        ),
    )

    row = _result(_sidecar_checks.evaluate_checks(inputs), "remote-policy")

    assert row.verdict == _sidecar_checks.Verdict.FAIL
    assert row.fix == "praxion-sidecar remote --clear, or re-set"


def test_remote_policy_foreign_host_with_recorded_ack_is_pass(healthy_inputs) -> None:
    inputs = dataclasses.replace(
        healthy_inputs,
        remote=_sidecar_checks.RemoteState(
            url="https://gitlab.example.com/acme/billing",
            push="never",
            host_matches_origin=False,
            foreign_host_ack=True,
            has_upstream=True,
        ),
    )

    row = _result(_sidecar_checks.evaluate_checks(inputs), "remote-policy")

    assert row.verdict == _sidecar_checks.Verdict.PASS


def test_remote_policy_push_on_autocommit_without_upstream_is_warn(healthy_inputs) -> None:
    inputs = dataclasses.replace(
        healthy_inputs,
        remote=_sidecar_checks.RemoteState(
            url="https://github.com/acme/billing",
            push="on-autocommit",
            host_matches_origin=True,
            foreign_host_ack=False,
            has_upstream=False,
        ),
    )

    row = _result(_sidecar_checks.evaluate_checks(inputs), "remote-policy")

    assert row.verdict == _sidecar_checks.Verdict.WARN


# --- manifest-roots ---------------------------------------------------------


def test_manifest_roots_current_is_pass(healthy_inputs) -> None:
    row = _result(_sidecar_checks.evaluate_checks(healthy_inputs), "manifest-roots")

    assert row.verdict == _sidecar_checks.Verdict.PASS
    assert "roots:" in row.detail


def test_manifest_roots_stale_is_warn(healthy_inputs) -> None:
    inputs = dataclasses.replace(healthy_inputs, guards_roots_stale=True)

    row = _result(_sidecar_checks.evaluate_checks(inputs), "manifest-roots")

    assert row.verdict == _sidecar_checks.Verdict.WARN
    assert "roots:" in row.detail
    assert row.fix == "praxion-sidecar link"


# --- commit-lock -------------------------------------------------------------


def test_commit_lock_idle_emits_no_row(healthy_inputs) -> None:
    results = _sidecar_checks.evaluate_checks(healthy_inputs)

    assert "commit-lock" not in {r.id for r in results}


def test_commit_lock_held_is_warn(healthy_inputs) -> None:
    inputs = dataclasses.replace(
        healthy_inputs,
        lock_state=_sidecar_commit.Committing(holder_pid=4242, since="2026-09-02T10:00:00Z"),
    )

    row = _result(_sidecar_checks.evaluate_checks(inputs), "commit-lock")

    assert row.verdict == _sidecar_checks.Verdict.WARN
    assert "4242" in row.detail


def test_commit_lock_stale_is_warn(healthy_inputs) -> None:
    """Canary: a planted stale lock record surfaces as a `commit-lock` WARN."""
    inputs = dataclasses.replace(
        healthy_inputs,
        lock_state=_sidecar_commit.StaleLock(holder_pid=4242, since="2026-09-02T10:00:00Z"),
    )

    row = _result(_sidecar_checks.evaluate_checks(inputs), "commit-lock")

    assert row.verdict == _sidecar_checks.Verdict.WARN
    assert "abandoned" in row.detail
    assert row.fix == "praxion-sidecar commit"


# --- InRepo placement gating ------------------------------------------------


def test_in_repo_placement_emits_only_hook_rows(hooks_repo, hooks_plugin_root) -> None:
    """Plain install: only `hooks-path` fires -- no wrapper exists, so
    `hooks-chained` is correctly absent (see
    `test_hooks_chained_absent_when_no_wrapper_installed`)."""
    status = _healthy_hooks_status(hooks_repo, hooks_plugin_root)
    inputs = _sidecar_checks.CheckInputs(
        placement=_in_repo_placement(),
        exclude_block=None,
        shadow_slots={},
        shared_slots={},
        untouched_paths={},
        hooks_status=status,
        mount=_sidecar_mount.Absent(),
        branches={},
        orphaned_mounts=(),
        mount_mid_merge=False,
        sidecar_repo=None,
        remote=None,
        guards_roots_stale=False,
        lock_state=None,
    )

    results = _sidecar_checks.evaluate_checks(inputs)

    assert {r.id for r in results} == {"hooks-path"}


def test_in_repo_placement_with_adopted_wrapper_emits_both_hook_rows(
    hooks_repo, hooks_plugin_root
) -> None:
    """An adopted `core.hooksPath` gives `hooks-chained` a wrapper to check
    even under `InRepo` placement -- the row set is a function of what
    `hooks_status` carries, not of placement itself (both P0 rows apply
    under `InRepo`, sec. 7.3)."""
    status = _adopted_foreign_hooks_status(hooks_repo, hooks_plugin_root)
    inputs = _sidecar_checks.CheckInputs(
        placement=_in_repo_placement(),
        exclude_block=None,
        shadow_slots={},
        shared_slots={},
        untouched_paths={},
        hooks_status=status,
        mount=_sidecar_mount.Absent(),
        branches={},
        orphaned_mounts=(),
        mount_mid_merge=False,
        sidecar_repo=None,
        remote=None,
        guards_roots_stale=False,
        lock_state=None,
    )

    results = _sidecar_checks.evaluate_checks(inputs)

    assert {r.id for r in results} == {"hooks-path", "hooks-chained"}


# --- CheckResult invariant ---------------------------------------------------


def test_check_result_pass_row_with_a_fix_raises() -> None:
    with pytest.raises(ValueError, match="pass"):
        _sidecar_checks.CheckResult(
            id="exclude-block",
            verdict=_sidecar_checks.Verdict.PASS,
            detail="ok",
            why=None,
            fix="praxion-sidecar link",
        )


def test_check_result_warn_row_without_a_fix_raises() -> None:
    with pytest.raises(ValueError, match="fix"):
        _sidecar_checks.CheckResult(
            id="exclude-block",
            verdict=_sidecar_checks.Verdict.WARN,
            detail="drifted",
            why="the manifest changed since the block was written",
            fix=None,
        )


def test_check_result_is_frozen_against_mutation() -> None:
    row = _sidecar_checks.CheckResult(
        id="exclude-block", verdict=_sidecar_checks.Verdict.PASS, detail="ok", why=None, fix=None
    )

    with pytest.raises(dataclasses.FrozenInstanceError):
        row.detail = "mutated"  # type: ignore[misc]


# --- overall_verdict / counts ------------------------------------------------


def test_overall_verdict_is_the_maximum_severity_across_rows() -> None:
    pass_row = _sidecar_checks.CheckResult(
        id="a", verdict=_sidecar_checks.Verdict.PASS, detail="ok", why=None, fix=None
    )
    warn_row = _sidecar_checks.CheckResult(
        id="b", verdict=_sidecar_checks.Verdict.WARN, detail="meh", why="w", fix="f"
    )

    assert _sidecar_checks.overall_verdict([pass_row]) == _sidecar_checks.Verdict.PASS
    assert _sidecar_checks.overall_verdict([pass_row, warn_row]) == _sidecar_checks.Verdict.WARN


def test_overall_verdict_fail_dominates_warn_and_pass() -> None:
    pass_row = _sidecar_checks.CheckResult(
        id="a", verdict=_sidecar_checks.Verdict.PASS, detail="ok", why=None, fix=None
    )
    warn_row = _sidecar_checks.CheckResult(
        id="b", verdict=_sidecar_checks.Verdict.WARN, detail="meh", why="w", fix="f"
    )
    fail_row = _sidecar_checks.CheckResult(
        id="c", verdict=_sidecar_checks.Verdict.FAIL, detail="bad", why="w", fix="f"
    )

    assert (
        _sidecar_checks.overall_verdict([pass_row, warn_row, fail_row])
        == _sidecar_checks.Verdict.FAIL
    )


def test_counts_sums_each_verdict_bucket() -> None:
    results = [
        _sidecar_checks.CheckResult(
            id="a", verdict=_sidecar_checks.Verdict.PASS, detail="ok", why=None, fix=None
        ),
        _sidecar_checks.CheckResult(
            id="b", verdict=_sidecar_checks.Verdict.PASS, detail="ok", why=None, fix=None
        ),
        _sidecar_checks.CheckResult(
            id="c", verdict=_sidecar_checks.Verdict.WARN, detail="meh", why="w", fix="f"
        ),
        _sidecar_checks.CheckResult(
            id="d", verdict=_sidecar_checks.Verdict.FAIL, detail="bad", why="w", fix="f"
        ),
    ]

    assert _sidecar_checks.counts(results) == {"pass": 2, "warn": 1, "fail": 1}


def test_fixed_point_input_yields_zero_warn_or_fail_rows(healthy_inputs) -> None:
    results = _sidecar_checks.evaluate_checks(healthy_inputs)

    assert _sidecar_checks.counts(results)["warn"] == 0
    assert _sidecar_checks.counts(results)["fail"] == 0
    assert _sidecar_checks.overall_verdict(results) == _sidecar_checks.Verdict.PASS


# --- render_doctor_json ------------------------------------------------------


def test_render_doctor_json_has_schema_one_and_max_severity_verdict() -> None:
    fail_row = _sidecar_checks.CheckResult(
        id="sidecar-repo",
        verdict=_sidecar_checks.Verdict.FAIL,
        detail="not a git repository",
        why="init never ran",
        fix="praxion-sidecar commit",
    )

    payload = _sidecar_checks.render_doctor_json([fail_row])

    assert payload["schema"] == 1
    assert payload["verdict"] == "fail"
    assert payload["counts"] == {"pass": 0, "warn": 0, "fail": 1}


def test_render_doctor_json_pass_rows_omit_why_and_fix_keys() -> None:
    pass_row = _sidecar_checks.CheckResult(
        id="exclude-block", verdict=_sidecar_checks.Verdict.PASS, detail="ok", why=None, fix=None
    )

    payload = _sidecar_checks.render_doctor_json([pass_row])
    rendered = payload["checks"][0]

    assert "why" not in rendered
    assert "fix" not in rendered
    assert rendered["id"] == "exclude-block"


# --- render_doctor_text ------------------------------------------------------


def test_render_doctor_text_without_color_has_no_ansi_escapes() -> None:
    fail_row = _sidecar_checks.CheckResult(
        id="sidecar-repo",
        verdict=_sidecar_checks.Verdict.FAIL,
        detail="not a git repository",
        why="init never ran",
        fix="praxion-sidecar commit",
    )

    text = _sidecar_checks.render_doctor_text([fail_row], color=False)

    assert "\x1b[" not in text


def test_render_doctor_text_with_color_contains_ansi_escapes() -> None:
    fail_row = _sidecar_checks.CheckResult(
        id="sidecar-repo",
        verdict=_sidecar_checks.Verdict.FAIL,
        detail="not a git repository",
        why="init never ran",
        fix="praxion-sidecar commit",
    )

    text = _sidecar_checks.render_doctor_text([fail_row], color=True)

    assert "\x1b[" in text


def test_render_doctor_text_color_decorates_without_changing_the_visible_text() -> None:
    """Color wraps the verdict token only -- stripping the escape codes from
    the colored rendering must reproduce the plain rendering exactly, proving
    color is pure decoration rather than a second source of content.
    """
    fail_row = _sidecar_checks.CheckResult(
        id="sidecar-repo",
        verdict=_sidecar_checks.Verdict.FAIL,
        detail="not a git repository",
        why="init never ran",
        fix="praxion-sidecar commit",
    )

    plain = _sidecar_checks.render_doctor_text([fail_row], color=False)
    colored = _sidecar_checks.render_doctor_text([fail_row], color=True)
    stripped = re.sub(r"\x1b\[[0-9;]*m", "", colored)

    assert stripped == plain


def test_render_doctor_text_summary_line_reports_failed_warnings_passed_in_order() -> None:
    results = [
        _sidecar_checks.CheckResult(
            id="a", verdict=_sidecar_checks.Verdict.PASS, detail="ok", why=None, fix=None
        ),
    ]

    text = _sidecar_checks.render_doctor_text(results, color=False)

    assert "0 failed · 0 warnings · 1 passed." in text


# --- path_states --------------------------------------------------------------


def test_path_states_shadow_row_carries_the_mapped_state(healthy_inputs) -> None:
    rows = _sidecar_checks.path_states(healthy_inputs)

    shadow_row = next(r for r in rows if r["path"] == ".ai-state")
    assert shadow_row["intent"] == "shadow"
    assert shadow_row["state"] == "linked"


def test_path_states_dangling_shadow_maps_to_the_dangling_state(healthy_inputs) -> None:
    inputs = dataclasses.replace(
        healthy_inputs, shadow_slots={".ai-state": _sidecar_checks.ShadowState.DANGLING}
    )

    rows = _sidecar_checks.path_states(inputs)

    shadow_row = next(r for r in rows if r["path"] == ".ai-state")
    assert shadow_row["state"] == "dangling"


def test_path_states_share_row_carries_the_mapped_state(healthy_inputs) -> None:
    rows = _sidecar_checks.path_states(healthy_inputs)

    share_row = next(r for r in rows if r["path"] == "docs/architecture.md")
    assert share_row["intent"] == "share"
    assert share_row["state"] == "shared"


def test_path_states_untouched_row_carries_a_reason_and_no_state(healthy_inputs) -> None:
    rows = _sidecar_checks.path_states(healthy_inputs)

    untouched_row = next(r for r in rows if r["path"] == "CLAUDE.md")
    assert untouched_row["intent"] == "untouched"
    assert untouched_row["reason"] == "preexisting-team-file"
    assert "state" not in untouched_row


# --- purity ------------------------------------------------------------------


def test_evaluate_checks_is_deterministic_for_identical_inputs(healthy_inputs) -> None:
    first = _sidecar_checks.evaluate_checks(healthy_inputs)
    second = _sidecar_checks.evaluate_checks(healthy_inputs)

    assert first == second


def test_evaluate_checks_makes_no_subprocess_or_filesystem_calls(
    healthy_inputs, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _boom(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("evaluate_checks must not touch subprocess or the filesystem")

    monkeypatch.setattr(subprocess, "run", _boom)
    monkeypatch.setattr(os, "stat", _boom)
    monkeypatch.setattr(os.path, "exists", _boom)
    monkeypatch.setattr(Path, "exists", _boom)
    monkeypatch.setattr(Path, "stat", _boom)

    _sidecar_checks.evaluate_checks(healthy_inputs)  # must not raise
