"""Behavioral tests for `_sidecar_identity.py` -- DS-7 project identity.

Every test builds a real git repository in `tmp_path` and asserts on the
*slug* a checkout derives, because the slug is the observable: it names the
directory under `${PRAXION_SIDECAR_ROOT}` that a project's whole state lives
in, and two checkouts of one project agreeing on it is the property the mount
lifecycle rests on.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import _sidecar_identity as identity
import pytest


def _git_ok(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} in {cwd} failed: {result.stderr}")
    return result


def _repo(root: Path, *, origin: str | None = None) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    _git_ok(root, "init", "-q", "-b", "main")
    _git_ok(root, "config", "user.email", "test@example.com")
    _git_ok(root, "config", "user.name", "Test")
    (root / "README.md").write_text("hello\n", encoding="utf-8")
    _git_ok(root, "add", "README.md")
    _git_ok(root, "commit", "-q", "-m", "seed")
    if origin is not None:
        _git_ok(root, "remote", "add", "origin", origin)
    return root


def _slug(root: Path) -> str:
    return identity.slug(identity.derive_project_id(root))


# --- OriginDerived ------------------------------------------------------------


def test_ssh_and_https_spellings_of_one_repo_derive_the_same_slug(tmp_path: Path) -> None:
    over_ssh = _repo(tmp_path / "ssh", origin="git@github.com:acme/billing.git")
    over_https = _repo(tmp_path / "https", origin="https://github.com/acme/billing")

    assert _slug(over_ssh) == "github.com--acme--billing"
    assert _slug(over_ssh) == _slug(over_https)


def test_origin_case_and_credentials_do_not_change_the_slug(tmp_path: Path) -> None:
    shouty = _repo(tmp_path / "shouty", origin="https://user:tok@GitHub.com/ACME/Billing.git/")
    assert _slug(shouty) == "github.com--acme--billing"


def test_a_nested_group_keeps_its_depth_in_the_slug(tmp_path: Path) -> None:
    nested = _repo(tmp_path / "nested", origin="git@gitlab.com:team/sub/billing.git")
    project_id = identity.derive_project_id(nested)

    assert isinstance(project_id, identity.OriginDerived)
    assert project_id.owner == "team/sub"
    assert identity.slug(project_id) == "gitlab.com--team--sub--billing"


def test_recorded_origin_is_the_remote_verbatim_not_the_normalized_form(tmp_path: Path) -> None:
    repo = _repo(tmp_path / "verbatim", origin="git@github.com:acme/billing.git")
    project_id = identity.derive_project_id(repo)

    assert identity.recorded_origin(project_id) == "git@github.com:acme/billing.git"


def test_a_remote_that_names_only_a_host_falls_back_to_a_path_hash(tmp_path: Path) -> None:
    hostonly = _repo(tmp_path / "hostonly", origin="https://github.com")
    project_id = identity.derive_project_id(hostonly)

    assert isinstance(project_id, identity.PathDerived)
    assert identity.recorded_origin(project_id) is None


# --- PathDerived ------------------------------------------------------------


def test_remote_less_project_derives_a_local_prefixed_twelve_hex_slug(tmp_path: Path) -> None:
    scratch = _repo(tmp_path / "scratch")
    project_id = identity.derive_project_id(scratch)

    assert isinstance(project_id, identity.PathDerived)
    assert identity.slug(project_id) == f"local--{project_id.hash}"


def test_path_hash_is_stable_when_the_project_is_reached_through_a_symlinked_parent(
    tmp_path: Path,
) -> None:
    real_parent = tmp_path / "real"
    real_parent.mkdir()
    scratch = _repo(real_parent / "scratch")

    aliased_parent = tmp_path / "alias"
    aliased_parent.symlink_to(real_parent, target_is_directory=True)

    assert _slug(aliased_parent / "scratch") == _slug(scratch)


def test_a_linked_worktree_derives_the_same_identity_as_its_main_checkout(
    tmp_path: Path,
) -> None:
    scratch = _repo(tmp_path / "scratch")
    worktree = tmp_path / "scratch" / ".claude" / "worktrees" / "wt1"
    worktree.parent.mkdir(parents=True, exist_ok=True)
    _git_ok(scratch, "worktree", "add", str(worktree), "-b", "feat")

    assert identity.main_worktree_root(worktree) == scratch.resolve()
    assert _slug(worktree) == _slug(scratch)


def test_two_distinct_remote_less_projects_derive_distinct_slugs(tmp_path: Path) -> None:
    first = _repo(tmp_path / "one")
    second = _repo(tmp_path / "two")

    assert _slug(first) != _slug(second)


# --- --id override ------------------------------------------------------------


def test_valid_id_override_is_returned_unchanged(tmp_path: Path) -> None:
    del tmp_path
    assert identity.validate_id_override("acme-billing_2.0") == "acme-billing_2.0"


@pytest.mark.parametrize(
    "raw",
    ["", "   ", "Acme/Billing", "acme billing", ".", "..", "acme:billing"],
)
def test_id_override_is_refused_rather_than_silently_sanitized(raw: str) -> None:
    with pytest.raises(identity.InvalidProjectId) as refusal:
        identity.validate_id_override(raw)
    assert refusal.value.reason == "id-not-sanitized"


def test_a_malformed_path_hash_cannot_be_constructed() -> None:
    with pytest.raises(identity.InvalidProjectId) as refusal:
        identity.PathDerived(hash="NOTHEX")
    assert refusal.value.reason == "path-hash-malformed"


def test_main_worktree_root_refuses_a_directory_that_is_not_a_checkout(tmp_path: Path) -> None:
    scratch = tmp_path / "not-a-repo"
    scratch.mkdir()
    with pytest.raises(identity.InvalidProjectId) as refusal:
        identity.main_worktree_root(scratch)
    assert refusal.value.reason == "not-a-git-checkout"
