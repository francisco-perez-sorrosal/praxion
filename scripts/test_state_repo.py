"""Behavioral tests for `_state_repo.py` -- the sidecar-placement resolver.

`resolve_placement(project_root)` answers "which git repository owns
`.ai-state/`?" with a four-variant sum type (`InRepo | SidecarOwned |
Dangling | Foreign`); `require_writable_placement(project_root)` narrows
that to the two writable variants and raises on the other two. Fixtures
build real git repositories under `tmp_path` (a sidecar repo mounted as a
`git worktree` inside a project repo) -- no git subprocess is mocked,
because the resolver's own discovery-path claim ("stdlib and
subprocess-free on the happy path") is exactly what several tests here
verify.

Import strategy: plain sibling import (`scripts/` has no `__init__.py`,
so pytest's prepend import mode puts it on `sys.path[0]`), matching
`scripts/test_repo_root.py`.
"""

from __future__ import annotations

import dataclasses
import subprocess
import sys
from pathlib import Path

import _state_repo
import pytest

_CLI_PATH = Path(__file__).parent / "_state_repo.py"

# --- Fixture builders --------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class _MountFixture:
    project_root: Path
    sidecar_root: Path
    mount_dir: Path
    sidecar_common_dir: Path
    manifest_path: Path


_UNSET = object()


def _run_git(cwd: Path, *args: str) -> None:
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} in {cwd} failed: {result.stderr}")


def _init_sidecar(sidecar_root: Path) -> None:
    """A sidecar repo, seeded, committed on `main`, then detached.

    Mirrors `praxion-sidecar init`'s own sequence (`ARCH_WT_RULING.md` sec.
    5): `main` must be free for the project's own mount to check out.
    """
    sidecar_root.mkdir(parents=True, exist_ok=True)
    _run_git(sidecar_root, "init", "-q", "-b", "main")
    _run_git(sidecar_root, "config", "user.email", "sidecar@example.com")
    _run_git(sidecar_root, "config", "user.name", "Sidecar Test")
    (sidecar_root / ".ai-state").mkdir()
    (sidecar_root / ".ai-state" / "DESIGN.md").write_text("# design\n")
    _run_git(sidecar_root, "add", "-A")
    _run_git(sidecar_root, "commit", "-q", "-m", "seed sidecar state")
    _run_git(sidecar_root, "checkout", "-q", "--detach")


def _mount_project(sidecar_root: Path, project_root: Path, *, branch: str) -> Path:
    """A minimal project repo, plus a real `git worktree` mount of the sidecar."""
    project_root.mkdir(parents=True, exist_ok=True)
    _run_git(project_root, "init", "-q", "-b", "main")
    _run_git(project_root, "config", "user.email", "project@example.com")
    _run_git(project_root, "config", "user.name", "Project Test")
    mount_dir = project_root / ".praxion"
    _run_git(sidecar_root, "worktree", "add", "-q", str(mount_dir), branch)
    return mount_dir


def _write_manifest(
    sidecar_root: Path,
    *,
    schema: int = 1,
    origin: str | None,
    project_id: str,
    roots: list[str],
    extra: str = "",
    block_style_roots: bool = False,
) -> Path:
    """Write a manifest fixture. `block_style_roots` renders `roots:` as a
    YAML block sequence (`roots:\n  - "path"`) instead of the default flow
    list -- covering an operator hand-edit `_parse_roots` must also accept,
    distinct from `_sidecar_manifest.write_manifest()`'s own output style."""
    manifest_path = sidecar_root / ".git" / "praxion-sidecar.yaml"
    origin_yaml = "null" if origin is None else f'"{origin}"'
    if block_style_roots:
        items = "".join(f'    - "{root}"\n' for root in roots)
        roots_block = f"  roots:\n{items}" if roots else "  roots: []\n"
    else:
        roots_yaml = ", ".join(f'"{root}"' for root in roots)
        roots_block = f"  roots: [{roots_yaml}]\n"
    manifest_path.write_text(
        "# managed by praxion-sidecar\n"
        f"schema: {schema}\n"
        "project:\n"
        f"  origin: {origin_yaml}\n"
        f'  id: "{project_id}"\n'
        f"{roots_block}"
        f"{extra}"
    )
    return manifest_path


def _link_shadow(project_root: Path, mount_dir: Path) -> Path:
    link_path = project_root / ".ai-state"
    link_path.symlink_to(Path(mount_dir.name) / ".ai-state", target_is_directory=True)
    return link_path


def _build_sidecar_owned_fixture(
    tmp_path: Path,
    *,
    origin: str | None,
    roots: list[str] | None = None,
    project_id: str = "local--abc123def456",
    extra_manifest: str = "",
    project_remote_origin: str | None | object = _UNSET,
    block_style_roots: bool = False,
) -> _MountFixture:
    """A fully wired `SidecarOwned` fixture: sidecar + mount + manifest + shadow.

    `project_remote_origin` defaults to `origin` (the OriginDerived happy
    path matches by construction); pass an explicit value to build a
    mismatch, or `None` to build a remote-less project regardless of what
    the manifest records.
    """
    sidecar_root = tmp_path / "sidecar"
    project_root = tmp_path / "project"
    _init_sidecar(sidecar_root)
    mount_dir = _mount_project(sidecar_root, project_root, branch="main")

    resolved_remote = origin if project_remote_origin is _UNSET else project_remote_origin
    if resolved_remote:
        _run_git(project_root, "remote", "add", "origin", resolved_remote)

    resolved_roots = roots if roots is not None else [str(project_root.resolve())]
    manifest_path = _write_manifest(
        sidecar_root,
        origin=origin,
        project_id=project_id,
        roots=resolved_roots,
        extra=extra_manifest,
        block_style_roots=block_style_roots,
    )
    _link_shadow(project_root, mount_dir)
    return _MountFixture(
        project_root=project_root,
        sidecar_root=sidecar_root,
        mount_dir=mount_dir,
        sidecar_common_dir=sidecar_root / ".git",
        manifest_path=manifest_path,
    )


def _forbid_subprocess(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin the subprocess-free happy path at the module's only git route.

    The module reaches git solely through the shared runner it imports, so
    that name is the choke point -- patching `subprocess.run` instead would
    silently stop guarding anything the day the module stopped importing
    `subprocess` directly, which is exactly what happened.
    """

    def _boom(*args: object, **kwargs: object) -> None:
        raise AssertionError(f"git must not be run on the happy path (args={args!r})")

    monkeypatch.setattr(_state_repo, "run_git", _boom)


# --- InRepo ------------------------------------------------------------------


def test_real_directory_ai_state_resolves_to_in_repo_with_zero_subprocess_calls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / ".ai-state").mkdir()
    _forbid_subprocess(monkeypatch)

    result = _state_repo.resolve_placement(project_root)

    assert isinstance(result, _state_repo.InRepo)
    assert result.state_git_root == result.project_root == project_root.resolve()


def test_placement_variants_are_frozen_against_mutation(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / ".ai-state").mkdir()

    result = _state_repo.resolve_placement(project_root)

    with pytest.raises(dataclasses.FrozenInstanceError):
        result.project_root = Path("/somewhere/else")  # type: ignore[misc]


# --- SidecarOwned --------------------------------------------------------------


def test_mount_fixture_resolves_to_sidecar_owned_with_mount_as_state_git_root(
    tmp_path: Path,
) -> None:
    fixture = _build_sidecar_owned_fixture(tmp_path, origin="https://github.com/acme/billing")

    result = _state_repo.resolve_placement(fixture.project_root)

    assert isinstance(result, _state_repo.SidecarOwned)
    assert result.state_git_root == result.mount_dir == fixture.mount_dir.resolve()
    assert result.sidecar_common_dir == fixture.sidecar_common_dir.resolve()
    assert result.branch == "main"
    assert result.identity == _state_repo.SidecarIdentity(
        schema=1, id="local--abc123def456", origin="https://github.com/acme/billing"
    )
    assert result.state_dir == (fixture.project_root / ".ai-state").resolve()


def test_sidecar_owned_discovery_performs_zero_subprocess_calls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _build_sidecar_owned_fixture(tmp_path, origin=None)
    _forbid_subprocess(monkeypatch)

    result = _state_repo.resolve_placement(fixture.project_root)

    assert isinstance(result, _state_repo.SidecarOwned)


def test_project_root_reached_through_symlinked_parent_still_resolves_to_sidecar_owned(
    tmp_path: Path,
) -> None:
    """The in-checkout realpath invariant survives macOS-style parent aliasing.

    Compares only resolver-supplied paths against each other (never the
    aliased entry path) -- the fix for `/Users/...` vs
    `/System/Volumes/Data/Users/...` mismatches.
    """
    real_parent = tmp_path / "real_parent"
    real_parent.mkdir()
    fixture = _build_sidecar_owned_fixture(real_parent, origin="https://github.com/acme/billing")
    link_parent = tmp_path / "link_parent"
    link_parent.symlink_to(real_parent, target_is_directory=True)
    aliased_project_root = link_parent / "project"

    result = _state_repo.resolve_placement(aliased_project_root)

    assert isinstance(result, _state_repo.SidecarOwned)
    assert result.mount_dir == fixture.mount_dir.resolve()
    assert result.sidecar_common_dir == fixture.sidecar_common_dir.resolve()


@pytest.mark.parametrize(
    ("origin", "extra_manifest"),
    [
        pytest.param("https://github.com/acme/billing", "", id="with-origin-no-extras"),
        pytest.param(
            None,
            "paths:\n  .ai-state: {intent: shadow, kind: dir}\n"
            "autocommit: on-finalize-and-stop\nremote: null\n",
            id="without-origin-with-extra-keys",
        ),
        pytest.param(
            "https://github.com/acme/other",
            '# a trailing comment\nexcludes: [".ai-work/"]\n',
            id="with-origin-and-comments",
        ),
    ],
)
def test_stdlib_and_yaml_readers_agree_on_frozen_triple(
    tmp_path: Path, origin: str | None, extra_manifest: str
) -> None:
    yaml = pytest.importorskip("yaml")
    fixture = _build_sidecar_owned_fixture(tmp_path, origin=origin, extra_manifest=extra_manifest)

    result = _state_repo.resolve_placement(fixture.project_root)

    assert isinstance(result, _state_repo.SidecarOwned)
    parsed = yaml.safe_load(fixture.manifest_path.read_text())
    assert result.identity.schema == parsed["schema"]
    assert result.identity.id == parsed["project"]["id"]
    assert result.identity.origin == parsed["project"]["origin"]


def test_project_root_that_is_itself_a_linked_worktree_resolves_to_sidecar_owned(
    tmp_path: Path,
) -> None:
    """A pipeline worktree's own `.git` is a pointer file, not a directory.

    The identity check needs `remote.origin.url`, which in this shape lives
    in the *base* repo's common dir, not `<project_root>/.git/config` -- the
    production regime every Praxion pipeline worktree runs in.
    """
    base_project_root = tmp_path / "base-project"
    base_project_root.mkdir()
    _run_git(base_project_root, "init", "-q", "-b", "main")
    _run_git(base_project_root, "config", "user.email", "project@example.com")
    _run_git(base_project_root, "config", "user.name", "Project Test")
    (base_project_root / "README.md").write_text("# project\n")
    _run_git(base_project_root, "add", "-A")
    _run_git(base_project_root, "commit", "-q", "-m", "seed project")
    _run_git(base_project_root, "remote", "add", "origin", "https://github.com/acme/billing")

    project_root = tmp_path / "proj-wt"
    _run_git(base_project_root, "worktree", "add", "-q", "-b", "feat", str(project_root))

    sidecar_root = tmp_path / "sidecar"
    _init_sidecar(sidecar_root)
    mount_dir = project_root / ".praxion"
    _run_git(sidecar_root, "worktree", "add", "-q", str(mount_dir), "main")
    _write_manifest(
        sidecar_root,
        origin="https://github.com/acme/billing",
        project_id="local--linked-worktree",
        roots=[str(project_root.resolve())],
    )
    _link_shadow(project_root, mount_dir)

    result = _state_repo.resolve_placement(project_root)

    assert isinstance(result, _state_repo.SidecarOwned)
    assert result.branch == "main"


@pytest.mark.parametrize(
    "project_remote_origin",
    [
        pytest.param("git@github.com:Acme/Billing.git", id="ssh-scp-style-mixed-case"),
        pytest.param("ssh://git@github.com/acme/billing", id="ssh-url-style"),
        pytest.param(
            "https://user:tok@GitHub.com/acme/billing/",
            id="https-with-credentials-mixed-case-and-trailing-slash",
        ),
        pytest.param("https://github.com/acme/billing.git", id="https-with-git-suffix"),
    ],
)
def test_origin_equivalent_remote_forms_all_resolve_to_sidecar_owned(
    tmp_path: Path, project_remote_origin: str
) -> None:
    """SSH, HTTPS-with-credentials, mixed case, and a `.git` suffix all name
    the same repository as the manifest's recorded
    `https://github.com/acme/billing` -- none of them may read as a foreign
    project.
    """
    fixture = _build_sidecar_owned_fixture(
        tmp_path,
        origin="https://github.com/acme/billing",
        project_remote_origin=project_remote_origin,
    )

    result = _state_repo.resolve_placement(fixture.project_root)

    assert isinstance(result, _state_repo.SidecarOwned)


def test_origin_from_a_genuinely_different_repository_resolves_to_foreign_identity_mismatch(
    tmp_path: Path,
) -> None:
    """The equivalence normalization above must not blur distinct repositories."""
    fixture = _build_sidecar_owned_fixture(
        tmp_path,
        origin="https://github.com/acme/billing",
        project_remote_origin="https://github.com/acme/other",
    )

    result = _state_repo.resolve_placement(fixture.project_root)

    assert isinstance(result, _state_repo.Foreign)
    assert result.reason == "identity-mismatch"


# --- NotYetLinked ------------------------------------------------------------


def _add_project_worktree(project_root: Path, name: str) -> Path:
    """A linked worktree of the project, exactly as `git worktree add` leaves
    it: no `.ai-state` entry of any kind, since the shadow is excluded from
    the project repository and never tracked."""
    _run_git(project_root, "commit", "-q", "--allow-empty", "-m", "seed project")
    checkout = project_root / "wts" / name
    _run_git(project_root, "worktree", "add", "-q", str(checkout), "-b", f"feat/{name}")
    return checkout


def _mount_worktree(sidecar_root: Path, checkout: Path, *, branch: str) -> Path:
    """The mount `praxion-sidecar link` would create in `checkout`."""
    mount_dir = checkout / ".praxion"
    _run_git(sidecar_root, "worktree", "add", "-q", "-b", branch, str(mount_dir), "main")
    return mount_dir


def test_fresh_linked_worktree_of_a_sidecar_project_resolves_to_not_yet_linked(
    tmp_path: Path,
) -> None:
    """A seconds-old worktree has no shadow, which by shape alone is
    indistinguishable from an unmanaged project. The main checkout's mount is
    what names the sidecar this worktree is about to be linked into -- the
    answer the post-checkout and SessionStart heals are gated on."""
    fixture = _build_sidecar_owned_fixture(tmp_path, origin="https://github.com/acme/billing")
    worktree = _add_project_worktree(fixture.project_root, "wt1")

    result = _state_repo.resolve_placement(worktree)

    assert isinstance(result, _state_repo.NotYetLinked)
    assert result.project_root == worktree.resolve()
    assert result.main_checkout_root == fixture.project_root.resolve()
    assert result.sidecar_common_dir == fixture.sidecar_common_dir
    assert result.identity.id == "local--abc123def456"


def test_not_yet_linked_discovery_performs_zero_subprocess_calls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _build_sidecar_owned_fixture(tmp_path, origin="https://github.com/acme/billing")
    worktree = _add_project_worktree(fixture.project_root, "wt1")
    _forbid_subprocess(monkeypatch)

    assert isinstance(_state_repo.resolve_placement(worktree), _state_repo.NotYetLinked)


def test_worktree_resolves_to_sidecar_owned_once_its_own_mount_is_linked(
    tmp_path: Path,
) -> None:
    """`NotYetLinked` is a transition, not a resting state: the same checkout
    resolves to `SidecarOwned` the moment `link` materializes its mount."""
    fixture = _build_sidecar_owned_fixture(tmp_path, origin="https://github.com/acme/billing")
    worktree = _add_project_worktree(fixture.project_root, "wt1")
    assert isinstance(_state_repo.resolve_placement(worktree), _state_repo.NotYetLinked)

    mount_dir = _mount_worktree(fixture.sidecar_root, worktree, branch="wt/feat-wt1")
    _link_shadow(worktree, mount_dir)

    result = _state_repo.resolve_placement(worktree)

    assert isinstance(result, _state_repo.SidecarOwned)
    assert result.state_git_root == mount_dir.resolve()
    assert result.branch == "wt/feat-wt1"


def test_linked_worktree_of_an_in_repo_project_resolves_to_in_repo(tmp_path: Path) -> None:
    """The main checkout owns its own `.ai-state`, so there is no sidecar to
    be unlinked from -- an absent shadow here means unmanaged, as before."""
    project_root = tmp_path / "project"
    project_root.mkdir()
    _run_git(project_root, "init", "-q", "-b", "main")
    _run_git(project_root, "config", "user.email", "project@example.com")
    _run_git(project_root, "config", "user.name", "Project Test")
    (project_root / ".ai-state").mkdir()  # untracked, so the worktree gets none

    worktree = _add_project_worktree(project_root, "wt1")

    assert isinstance(_state_repo.resolve_placement(worktree), _state_repo.InRepo)


def test_linked_worktree_whose_main_shadow_is_foreign_resolves_to_foreign(
    tmp_path: Path,
) -> None:
    """A refusal the main checkout already earned is not softened into
    "unmanaged" for its worktrees: the evidence names the offending path, and
    `project_root` names the checkout that asked."""
    fixture = _build_sidecar_owned_fixture(
        tmp_path,
        origin="https://github.com/acme/billing",
        project_remote_origin="https://github.com/other/unrelated",
    )
    assert isinstance(_state_repo.resolve_placement(fixture.project_root), _state_repo.Foreign)
    worktree = _add_project_worktree(fixture.project_root, "wt1")

    result = _state_repo.resolve_placement(worktree)

    assert isinstance(result, _state_repo.Foreign)
    assert result.reason is _state_repo.ForeignReason.IDENTITY_MISMATCH
    assert result.project_root == worktree.resolve()
    assert result.resolved_target == fixture.mount_dir.resolve()


# --- Dangling ------------------------------------------------------------------


def test_symlink_with_missing_target_resolves_to_dangling(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    link_path = project_root / ".ai-state"
    link_path.symlink_to(Path(".praxion") / ".ai-state")  # .praxion never created

    result = _state_repo.resolve_placement(project_root)

    assert isinstance(result, _state_repo.Dangling)
    assert result.link_path == link_path.resolve()
    assert not result.link_target.exists()


# --- Foreign ---------------------------------------------------------------


def test_mount_without_manifest_resolves_to_foreign_no_manifest(tmp_path: Path) -> None:
    sidecar_root = tmp_path / "sidecar"
    project_root = tmp_path / "project"
    _init_sidecar(sidecar_root)
    mount_dir = _mount_project(sidecar_root, project_root, branch="main")
    _link_shadow(project_root, mount_dir)
    # No manifest written at <sidecar_common_dir>/praxion-sidecar.yaml.

    result = _state_repo.resolve_placement(project_root)

    assert isinstance(result, _state_repo.Foreign)
    assert result.reason == "no-manifest"


def test_manifest_with_undecodable_bytes_resolves_to_foreign_manifest_unreadable(
    tmp_path: Path,
) -> None:
    sidecar_root = tmp_path / "sidecar"
    project_root = tmp_path / "project"
    _init_sidecar(sidecar_root)
    mount_dir = _mount_project(sidecar_root, project_root, branch="main")
    (sidecar_root / ".git" / "praxion-sidecar.yaml").write_bytes(
        b"\xff\xfe\x00schema: this is not decodable utf-8 \xff"
    )
    _link_shadow(project_root, mount_dir)

    result = _state_repo.resolve_placement(project_root)

    assert isinstance(result, _state_repo.Foreign)
    assert result.reason == "manifest-unreadable"


def test_manifest_with_unsupported_schema_resolves_to_foreign_schema_too_new(
    tmp_path: Path,
) -> None:
    """A schema-2 fixture that also renests `project` under another key.

    The stdlib reader must refuse on `schema` alone, before it ever tries to
    locate `project.id`/`project.origin` -- the frozen-triple guarantee
    `SYSTEMS_PLAN.md` DS-2 names.
    """
    sidecar_root = tmp_path / "sidecar"
    project_root = tmp_path / "project"
    _init_sidecar(sidecar_root)
    mount_dir = _mount_project(sidecar_root, project_root, branch="main")
    (sidecar_root / ".git" / "praxion-sidecar.yaml").write_text(
        'schema: 2\nmeta:\n  project:\n    origin: null\n    id: "local--renested"\n    roots: []\n'
    )
    _link_shadow(project_root, mount_dir)

    result = _state_repo.resolve_placement(project_root)

    assert isinstance(result, _state_repo.Foreign)
    assert result.reason == "schema-too-new"


def test_origin_derived_project_with_mismatched_recorded_origin_resolves_to_foreign_identity_mismatch(
    tmp_path: Path,
) -> None:
    fixture = _build_sidecar_owned_fixture(
        tmp_path,
        origin="https://github.com/acme/billing",
        project_remote_origin="https://github.com/acme/other-repo",
    )

    result = _state_repo.resolve_placement(fixture.project_root)

    assert isinstance(result, _state_repo.Foreign)
    assert result.reason == "identity-mismatch"


def test_remote_less_project_root_absent_from_recorded_roots_resolves_to_foreign_identity_mismatch(
    tmp_path: Path,
) -> None:
    """CH-02's remote-less cross-sidecar-pointing case: `roots:` is the only anchor."""
    fixture = _build_sidecar_owned_fixture(
        tmp_path, origin=None, roots=["/some/other/projects/unrelated"]
    )

    result = _state_repo.resolve_placement(fixture.project_root)

    assert isinstance(result, _state_repo.Foreign)
    assert result.reason == "identity-mismatch"


def test_remote_less_project_root_present_in_recorded_roots_resolves_to_sidecar_owned(
    tmp_path: Path,
) -> None:
    fixture = _build_sidecar_owned_fixture(tmp_path, origin=None)

    result = _state_repo.resolve_placement(fixture.project_root)

    assert isinstance(result, _state_repo.SidecarOwned)
    assert result.identity.origin is None


def test_hand_written_block_style_roots_resolves_to_sidecar_owned(tmp_path: Path) -> None:
    """An operator may hand-edit `roots:` as a YAML block sequence
    (`roots:\n  - "path"`) rather than a flow list -- `_parse_roots` must
    accept both, since nothing constrains how a human edits the file."""
    fixture = _build_sidecar_owned_fixture(tmp_path, origin=None, block_style_roots=True)

    result = _state_repo.resolve_placement(fixture.project_root)

    assert isinstance(result, _state_repo.SidecarOwned)
    assert result.identity.origin is None


def test_real_directory_at_mount_slot_without_git_resolves_to_foreign_not_a_git_repo(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    mount_dir = project_root / ".praxion"
    (mount_dir / ".ai-state").mkdir(parents=True)
    # No `.git` entry at all under the mount slot -- not a repo, not a worktree.
    _link_shadow(project_root, mount_dir)

    result = _state_repo.resolve_placement(project_root)

    assert isinstance(result, _state_repo.Foreign)
    assert result.reason == "not-a-git-repo"


def test_mount_git_pointer_with_unrecognized_shape_resolves_to_foreign_unrecognized_mount(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    mount_dir = project_root / ".praxion"
    (mount_dir / ".ai-state").mkdir(parents=True)
    # A `.git` pointer file exists but its shape doesn't match `gitdir:
    # <sidecar>/.git/worktrees/<name>` -- fail-closed, never a guess.
    (mount_dir / ".git").write_text("gitdir: /nowhere/nothing-recognizable\n")
    _link_shadow(project_root, mount_dir)

    result = _state_repo.resolve_placement(project_root)

    assert isinstance(result, _state_repo.Foreign)
    assert result.reason == "unrecognized-mount"


# --- require_writable_placement() -------------------------------------------


def test_require_writable_placement_returns_in_repo(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / ".ai-state").mkdir()

    result = _state_repo.require_writable_placement(project_root)

    assert isinstance(result, _state_repo.InRepo)


def test_require_writable_placement_returns_sidecar_owned(tmp_path: Path) -> None:
    fixture = _build_sidecar_owned_fixture(tmp_path, origin="https://github.com/acme/billing")

    result = _state_repo.require_writable_placement(fixture.project_root)

    assert isinstance(result, _state_repo.SidecarOwned)


def test_require_writable_placement_raises_on_not_yet_linked_naming_the_link_command(
    tmp_path: Path,
) -> None:
    """State must be materialized before it can be written: the refusal names
    the command that materializes it rather than letting a writer proceed."""
    fixture = _build_sidecar_owned_fixture(tmp_path, origin="https://github.com/acme/billing")
    worktree = _add_project_worktree(fixture.project_root, "wt1")

    with pytest.raises(_state_repo.UnwritablePlacementError, match="praxion-sidecar link"):
        _state_repo.require_writable_placement(worktree)


def test_require_writable_placement_raises_naming_dangling_and_target(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    link_path = project_root / ".ai-state"
    link_path.symlink_to(Path(".praxion") / ".ai-state")

    with pytest.raises(_state_repo.UnwritablePlacementError, match="(?i)dangling"):
        _state_repo.require_writable_placement(project_root)


def test_require_writable_placement_raises_naming_foreign_reason_and_target(
    tmp_path: Path,
) -> None:
    sidecar_root = tmp_path / "sidecar"
    project_root = tmp_path / "project"
    _init_sidecar(sidecar_root)
    mount_dir = _mount_project(sidecar_root, project_root, branch="main")
    _link_shadow(project_root, mount_dir)
    # No manifest -- Foreign(no-manifest).

    with pytest.raises(_state_repo.UnwritablePlacementError, match="no-manifest"):
        _state_repo.require_writable_placement(project_root)


# --- CLI (`--print`) --------------------------------------------------------
#
# The finalize chain (`scripts/finalize_chain.sh`) resolves placement via a
# real subprocess call to this CLI, once per entry point, and parses its
# stdout as plain `key=value` lines -- these tests exercise the actual
# subprocess boundary rather than calling `main()` in-process, since the
# shell's parsing contract is what matters.


def _run_print_cli(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(_CLI_PATH), "--print", str(root)],
        capture_output=True,
        text=True,
        check=False,
    )


def _parse_kv(stdout: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for line in stdout.splitlines():
        if not line:
            continue
        key, _, value = line.partition("=")
        parsed[key] = value
    return parsed


def test_print_cli_reports_in_repo_placement(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / ".ai-state").mkdir()

    result = _run_print_cli(project_root)

    assert result.returncode == 0, result.stderr
    fields = _parse_kv(result.stdout)
    assert fields["placement"] == "in-repo"
    assert fields["state_git_root"] == str(project_root.resolve())


def test_print_cli_reports_sidecar_placement_with_mount_and_common_dir(
    tmp_path: Path,
) -> None:
    fixture = _build_sidecar_owned_fixture(tmp_path, origin=None)

    result = _run_print_cli(fixture.project_root)

    assert result.returncode == 0, result.stderr
    fields = _parse_kv(result.stdout)
    assert fields["placement"] == "sidecar"
    assert fields["state_git_root"] == str(fixture.mount_dir.resolve())
    assert fields["mount_dir"] == str(fixture.mount_dir.resolve())
    assert fields["sidecar_common_dir"] == str(fixture.sidecar_common_dir.resolve())


def test_print_cli_reports_not_yet_linked_placement_with_main_checkout_and_common_dir(
    tmp_path: Path,
) -> None:
    """The finalize chain's post-checkout `link` gate reads exactly these
    keys, so they are the shell-facing contract, not an implementation note."""
    fixture = _build_sidecar_owned_fixture(tmp_path, origin="https://github.com/acme/billing")
    worktree = _add_project_worktree(fixture.project_root, "wt1")

    result = _run_print_cli(worktree)

    assert result.returncode == 0, result.stderr
    fields = _parse_kv(result.stdout)
    assert fields["placement"] == "not-yet-linked"
    assert fields["main_checkout_root"] == str(fixture.project_root.resolve())
    assert fields["sidecar_common_dir"] == str(fixture.sidecar_common_dir.resolve())


def test_print_cli_reports_dangling_placement_and_exits_zero(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    link_path = project_root / ".ai-state"
    link_path.symlink_to(Path(".praxion") / ".ai-state")  # .praxion never created

    result = _run_print_cli(project_root)

    assert result.returncode == 0, result.stderr
    fields = _parse_kv(result.stdout)
    assert fields["placement"] == "dangling"
    assert "reason" in fields


def test_print_cli_reports_foreign_placement_and_exits_zero(tmp_path: Path) -> None:
    sidecar_root = tmp_path / "sidecar"
    project_root = tmp_path / "project"
    _init_sidecar(sidecar_root)
    mount_dir = _mount_project(sidecar_root, project_root, branch="main")
    _link_shadow(project_root, mount_dir)
    # No manifest -- Foreign(no-manifest), same fixture shape as the library test above.

    result = _run_print_cli(project_root)

    assert result.returncode == 0, result.stderr
    fields = _parse_kv(result.stdout)
    assert fields["placement"] == "foreign"
    assert fields["reason"].startswith("no-manifest")
