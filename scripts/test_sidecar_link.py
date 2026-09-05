"""Behavioral tests for `_sidecar_link.py` -- the `.git/info/exclude`
Praxion block and shadow-symlink target-slot state.

`_sidecar_link.py` does not exist yet (concurrent BDD/TDD with its
implementation) -- this is the RED skeleton, confirmed to fail on
`ModuleNotFoundError` before the module lands. Every fixture drives *real*
`git init` / `git worktree add` under `tmp_path`; nothing about git is
mocked, mirroring `scripts/test_sidecar_mount.py` and the ruling's own
`tmp/probe_harness.sh` discipline.

Decoupling from the two concurrent sibling modules this suite does not own:

- `_sidecar_manifest.py` (the manifest smart constructor) is loaded lazily,
  behind `pytest.importorskip`, inside `_manifest()`/`_build_link_fixture()`
  below -- a test using either helper skips cleanly rather than crashing
  collection if the module is ever unavailable. Real `Manifest` objects are
  built from raw YAML text via `load_manifest()`, never via a hand-rolled
  duck-typed double, so `link()`'s manifest-consumption contract is
  exercised against the actual manifest types.
- `_sidecar_mount.py` (the state-mount lifecycle module) is never imported
  by this file at all. Every fixture that needs a real mount lets
  `_sidecar_link.link()` reach it through its own default wiring (production
  code depending on production code); this suite only injects a *double*
  for the `create_mount` seam when a test's whole point is to observe
  call-time ordering or to prove a clean re-run makes zero mount-creation
  calls.

Import strategy: plain sibling import (`scripts/` has no `__init__.py`, so
pytest's prepend import mode puts it on `sys.path[0]`), matching
`scripts/test_state_repo.py` and `scripts/test_sidecar_mount.py`.
"""

from __future__ import annotations

import dataclasses
import os
import shutil
import subprocess
from pathlib import Path

import _sidecar_link
import pytest

_IDENTITY = ("-c", "user.email=test@example.com", "-c", "user.name=Test")
_MOUNT_DIRNAME = ".praxion-state"

_DEFAULT_MANIFEST_YAML = """\
schema: 1
project:
  origin: null
  id: local--test
  roots: []
paths:
  .ai-state:
    intent: shadow
    kind: dir
  CLAUDE.local.md:
    intent: shadow
    kind: file
  .claude/settings.local.json:
    intent: shadow
    kind: file
  CLAUDE.md:
    intent: shadow
    kind: file
excludes:
  - /.ai-work/
  - /.claude/worktrees/
  - /tmp/
autocommit: on-finalize-and-stop
"""

_SHARE_AND_UNTOUCHED_MANIFEST_YAML = """\
schema: 1
project:
  origin: null
  id: local--test
  roots: []
paths:
  .ai-state:
    intent: shadow
    kind: dir
  CLAUDE.local.md:
    intent: shadow
    kind: file
  .claude/settings.local.json:
    intent: shadow
    kind: file
  CLAUDE.md:
    intent: untouched
    reason: preexisting-team-file
  docs/architecture.md:
    intent: share
excludes:
  - /.ai-work/
  - /.claude/worktrees/
  - /tmp/
autocommit: on-finalize-and-stop
"""

_SHADOW_RELPATHS = (".ai-state", "CLAUDE.local.md", ".claude/settings.local.json", "CLAUDE.md")


# --- git plumbing ------------------------------------------------------------


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=False)


def _git_ok(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    result = _git(cwd, *args)
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} in {cwd} failed: {result.stderr}")
    return result


def _configure_identity(repo: Path) -> None:
    _git_ok(repo, "config", "user.email", "test@example.com")
    _git_ok(repo, "config", "user.name", "Test")


def _commit_all(repo: Path, message: str) -> None:
    _git_ok(repo, "add", "-A")
    _git_ok(repo, *_IDENTITY, "commit", "-q", "-m", message)


# --- fixture builders ---------------------------------------------------------


def _init_sidecar(sidecar_root: Path) -> None:
    """A minimal sidecar repo: `.ai-state/` seeded, committed on `main`, then
    detached -- mirrors `praxion-sidecar init`'s own sequence
    (`ARCH_WT_RULING.md` sec. 5): `main` must stay free for the project's own
    mount to check out.
    """
    sidecar_root.mkdir(parents=True, exist_ok=True)
    _git_ok(sidecar_root, "init", "-q", "-b", "main")
    _configure_identity(sidecar_root)
    (sidecar_root / ".ai-state").mkdir()
    (sidecar_root / ".ai-state" / "DESIGN.md").write_text("seed\n")
    _commit_all(sidecar_root, "seed sidecar state")
    _git_ok(sidecar_root, "checkout", "-q", "--detach")


def _init_project(project_root: Path) -> None:
    """A minimal project repo -- deliberately WITHOUT a pre-populated
    `.git/info/exclude`, unlike `test_sidecar_mount.py`'s fixture: writing
    that block is exactly the behavior under test here.
    """
    project_root.mkdir(parents=True, exist_ok=True)
    _git_ok(project_root, "init", "-q", "-b", "main")
    _configure_identity(project_root)
    (project_root / "app.py").write_text("code\n")
    _commit_all(project_root, "init")


def _init_plain_repo(repo_root: Path) -> None:
    repo_root.mkdir(parents=True, exist_ok=True)
    _git_ok(repo_root, "init", "-q", "-b", "main")
    _configure_identity(repo_root)
    (repo_root / "f.txt").write_text("x\n")
    _commit_all(repo_root, "seed")


def _manifest(tmp_path: Path, yaml_text: str = _DEFAULT_MANIFEST_YAML):
    """Parse `yaml_text` into a real `_sidecar_manifest.Manifest`, for tests
    that only need the manifest object (no full sidecar/project pair).

    `load_manifest()` requires the file to sit two levels under the sidecar
    root (`<sidecar_root>/.git/praxion-sidecar.yaml`) so its on-disk `kind`
    cross-check has somewhere to look; a bare `.git/` directory (no real
    `git init`) is enough since the cross-check only fires when a same-named
    entry already exists on disk.
    """
    sidecar_manifest = pytest.importorskip("_sidecar_manifest")
    git_dir = tmp_path / "manifest-only-sidecar" / ".git"
    git_dir.mkdir(parents=True, exist_ok=True)
    manifest_file = git_dir / "praxion-sidecar.yaml"
    manifest_file.write_text(yaml_text)
    return sidecar_manifest.load_manifest(manifest_file)


@dataclasses.dataclass(frozen=True)
class _LinkFixture:
    sidecar_root: Path
    project_root: Path
    manifest: object


def _build_link_fixture(base: Path, *, manifest_yaml: str = _DEFAULT_MANIFEST_YAML) -> _LinkFixture:
    """A real sidecar + a real project, plus a real `Manifest` parsed from
    `manifest_yaml` -- the shared starting point for every full-`link()`
    test below.
    """
    sidecar_root = base / "sidecar"
    project_root = base / "project"
    _init_sidecar(sidecar_root)
    _init_project(project_root)
    sidecar_manifest = pytest.importorskip("_sidecar_manifest")
    manifest_file = sidecar_root / ".git" / "praxion-sidecar.yaml"
    manifest_file.write_text(manifest_yaml)
    manifest = sidecar_manifest.load_manifest(manifest_file)
    return _LinkFixture(sidecar_root=sidecar_root, project_root=project_root, manifest=manifest)


# --- shadow_target -------------------------------------------------------------


def test_shadow_target_for_a_root_level_slot_points_directly_into_the_mount() -> None:
    assert _sidecar_link.shadow_target(".ai-state") == ".praxion-state/.ai-state"
    assert _sidecar_link.shadow_target("CLAUDE.local.md") == ".praxion-state/CLAUDE.local.md"
    assert _sidecar_link.shadow_target("CLAUDE.md") == ".praxion-state/CLAUDE.md"


def test_shadow_target_for_a_nested_slot_climbs_out_before_entering_the_mount() -> None:
    assert (
        _sidecar_link.shadow_target(".claude/settings.local.json")
        == "../.praxion-state/settings.local.json"
    )


# --- ShadowSlotState classification -------------------------------------


def test_shadow_slot_state_variants_are_frozen_against_mutation() -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        _sidecar_link.RealPath(kind="file").kind = "dir"  # type: ignore[misc]


def test_absent_shadow_slot_classifies_as_absent(tmp_path: Path) -> None:
    checkout = tmp_path / "checkout"
    checkout.mkdir()

    result = _sidecar_link.classify_shadow_slot(
        checkout, ".ai-state", _sidecar_link.shadow_target(".ai-state")
    )

    assert isinstance(result, _sidecar_link.Absent)


def test_a_correct_relative_symlink_classifies_as_link_to_this_sidecar(tmp_path: Path) -> None:
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    target = _sidecar_link.shadow_target(".ai-state")
    (checkout / ".ai-state").symlink_to(target, target_is_directory=True)

    result = _sidecar_link.classify_shadow_slot(checkout, ".ai-state", target)

    assert isinstance(result, _sidecar_link.LinkToThisSidecar)


def test_a_symlink_to_a_different_relative_target_classifies_as_link_elsewhere(
    tmp_path: Path,
) -> None:
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    (checkout / "CLAUDE.local.md").symlink_to(".praxion-state/some-other-file")

    result = _sidecar_link.classify_shadow_slot(
        checkout, "CLAUDE.local.md", _sidecar_link.shadow_target("CLAUDE.local.md")
    )

    assert isinstance(result, _sidecar_link.LinkElsewhere)
    assert result.target == ".praxion-state/some-other-file"


def test_an_absolute_symlink_to_the_correct_file_still_classifies_as_link_elsewhere(
    tmp_path: Path,
) -> None:
    """A link that works today by escaping the checkout is a link that
    breaks the moment a pipeline worktree opens -- the comparison is
    against the raw target *string*, never the resolved realpath.
    """
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    mount = checkout / ".praxion-state"
    mount.mkdir()
    (mount / "CLAUDE.local.md").write_text("x\n")
    (checkout / "CLAUDE.local.md").symlink_to((mount / "CLAUDE.local.md").resolve())

    result = _sidecar_link.classify_shadow_slot(
        checkout, "CLAUDE.local.md", _sidecar_link.shadow_target("CLAUDE.local.md")
    )

    assert isinstance(result, _sidecar_link.LinkElsewhere)


def test_a_real_file_at_a_shadow_slot_classifies_as_real_path_file(tmp_path: Path) -> None:
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    (checkout / "CLAUDE.local.md").write_text("operator notes\n")

    result = _sidecar_link.classify_shadow_slot(
        checkout, "CLAUDE.local.md", _sidecar_link.shadow_target("CLAUDE.local.md")
    )

    assert isinstance(result, _sidecar_link.RealPath)
    assert result.kind == "file"


def test_a_real_directory_at_a_shadow_slot_classifies_as_real_path_dir(tmp_path: Path) -> None:
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    (checkout / ".ai-state").mkdir()

    result = _sidecar_link.classify_shadow_slot(
        checkout, ".ai-state", _sidecar_link.shadow_target(".ai-state")
    )

    assert isinstance(result, _sidecar_link.RealPath)
    assert result.kind == "dir"


# --- sidecar_branch_for --------------------------------------------------------


def test_sidecar_branch_for_a_main_checkout_is_main(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    _init_project(project_root)

    assert _sidecar_link.sidecar_branch_for(project_root) == "main"


def test_sidecar_branch_for_a_linked_worktree_is_wt_prefixed_with_its_directory_name(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "project"
    _init_project(project_root)
    worktree = project_root / "wts" / "wt1"
    _git_ok(project_root, "worktree", "add", "-q", str(worktree), "-b", "feat")

    assert _sidecar_link.sidecar_branch_for(worktree) == "wt/wt1"


# --- rewrite_exclude_block / remove_exclude_block ------------------------------


def test_rewrite_exclude_block_preserves_content_outside_the_markers(tmp_path: Path) -> None:
    exclude_path = tmp_path / "exclude"
    exclude_path.write_text("*.pyc\n/build/\n")

    _sidecar_link.rewrite_exclude_block(exclude_path, ["/.praxion-state/", "/.ai-state"])

    text = exclude_path.read_text()
    assert text.startswith("*.pyc\n/build/\n")


def test_rewrite_exclude_block_replaces_an_existing_block_wholesale_without_duplicating(
    tmp_path: Path,
) -> None:
    exclude_path = tmp_path / "exclude"
    exclude_path.write_text("keep-me\n")
    _sidecar_link.rewrite_exclude_block(exclude_path, ["/.praxion-state/", "/.ai-state"])

    _sidecar_link.rewrite_exclude_block(
        exclude_path, ["/.praxion-state/", "/.ai-state", "/CLAUDE.md"]
    )

    text = exclude_path.read_text()
    assert text.count("praxion:sidecar >>>") == 1
    assert "/CLAUDE.md" in text
    assert text.startswith("keep-me\n")


def test_rewrite_exclude_block_appends_a_new_block_with_exactly_one_trailing_newline(
    tmp_path: Path,
) -> None:
    exclude_path = tmp_path / "info-exclude"

    changed = _sidecar_link.rewrite_exclude_block(exclude_path, ["/.praxion-state/"])

    assert changed is True
    text = exclude_path.read_text()
    assert text.endswith("# <<< praxion:sidecar <<<\n")
    assert not text.endswith("\n\n")


def test_rewrite_exclude_block_is_a_no_op_when_content_is_already_correct(tmp_path: Path) -> None:
    exclude_path = tmp_path / "exclude"
    lines = ["/.praxion-state/", "/.ai-state"]
    first = _sidecar_link.rewrite_exclude_block(exclude_path, lines)
    before = exclude_path.stat().st_mtime_ns

    second = _sidecar_link.rewrite_exclude_block(exclude_path, lines)

    after = exclude_path.stat().st_mtime_ns
    assert first is True
    assert second is False
    assert before == after


def test_remove_exclude_block_deletes_only_the_block(tmp_path: Path) -> None:
    exclude_path = tmp_path / "exclude"
    exclude_path.write_text("keep-before\n")
    _sidecar_link.rewrite_exclude_block(exclude_path, ["/.praxion-state/"])
    with exclude_path.open("a") as handle:
        handle.write("keep-after\n")

    changed = _sidecar_link.remove_exclude_block(exclude_path)

    text = exclude_path.read_text()
    assert changed is True
    assert "praxion:sidecar" not in text
    assert "keep-before" in text
    assert "keep-after" in text


# --- exclude_lines --------------------------------------------------------------


def test_exclude_lines_puts_the_mount_entry_first(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)

    lines = _sidecar_link.exclude_lines(manifest)

    assert lines[0] == "/.praxion-state/"


def test_exclude_lines_includes_the_default_shadow_set(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)

    lines = _sidecar_link.exclude_lines(manifest)

    assert "/.ai-state" in lines
    assert "/CLAUDE.local.md" in lines
    assert "/.claude/settings.local.json" in lines


def test_exclude_lines_includes_claude_md_only_when_its_intent_is_shadow(tmp_path: Path) -> None:
    shadow_lines = _sidecar_link.exclude_lines(
        _manifest(tmp_path / "shadow", _DEFAULT_MANIFEST_YAML)
    )
    untouched_lines = _sidecar_link.exclude_lines(
        _manifest(tmp_path / "untouched", _SHARE_AND_UNTOUCHED_MANIFEST_YAML)
    )

    assert "/CLAUDE.md" in shadow_lines
    assert "/CLAUDE.md" not in untouched_lines


def test_exclude_lines_appends_the_manifests_own_excludes_verbatim(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)

    lines = _sidecar_link.exclude_lines(manifest)

    assert lines[-3:] == ["/.ai-work/", "/.claude/worktrees/", "/tmp/"]


def test_exclude_lines_never_includes_a_share_path(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path, _SHARE_AND_UNTOUCHED_MANIFEST_YAML)

    lines = _sidecar_link.exclude_lines(manifest)

    assert not any("architecture.md" in line for line in lines)


# --- link() on a fresh main checkout ---------------------------------------------


def test_link_writes_the_exclude_block_before_creating_the_mount(tmp_path: Path) -> None:
    fixture = _build_link_fixture(tmp_path)
    exclude_present_at_call_time = []

    def _recording_create_mount(*_args: object, **_kwargs: object) -> None:
        exclude_path = fixture.project_root / ".git" / "info" / "exclude"
        text = exclude_path.read_text() if exclude_path.exists() else ""
        exclude_present_at_call_time.append("praxion:sidecar" in text)

    _sidecar_link.link(
        fixture.project_root,
        fixture.sidecar_root,
        fixture.manifest,
        create_mount=_recording_create_mount,
    )

    assert exclude_present_at_call_time == [True]


def test_link_creates_the_mount_on_the_main_branch_for_the_main_checkout(tmp_path: Path) -> None:
    fixture = _build_link_fixture(tmp_path)

    result = _sidecar_link.link(fixture.project_root, fixture.sidecar_root, fixture.manifest)

    mount = fixture.project_root / _MOUNT_DIRNAME
    assert result.created_mount is True
    assert mount.is_dir()
    branch = _git_ok(mount, "branch", "--show-current").stdout.strip()
    assert branch == "main"


def test_link_creates_all_shadow_symlinks_from_absent_slots(tmp_path: Path) -> None:
    fixture = _build_link_fixture(tmp_path)

    result = _sidecar_link.link(fixture.project_root, fixture.sidecar_root, fixture.manifest)

    assert set(result.linked) == set(_SHADOW_RELPATHS)
    for relpath in _SHADOW_RELPATHS:
        assert (fixture.project_root / relpath).is_symlink()


def test_every_shadow_realpath_resolves_inside_the_checkout(tmp_path: Path) -> None:
    """The in-checkout realpath invariant, asserted directly."""
    fixture = _build_link_fixture(tmp_path)

    _sidecar_link.link(fixture.project_root, fixture.sidecar_root, fixture.manifest)

    checkout_real = os.path.realpath(fixture.project_root)
    for relpath in _SHADOW_RELPATHS:
        shadow_real = os.path.realpath(fixture.project_root / relpath)
        assert shadow_real == checkout_real or shadow_real.startswith(checkout_real + os.sep)


def test_link_creates_the_dot_claude_parent_directory_as_real_even_when_absent(
    tmp_path: Path,
) -> None:
    fixture = _build_link_fixture(tmp_path)
    assert not (fixture.project_root / ".claude").exists()

    _sidecar_link.link(fixture.project_root, fixture.sidecar_root, fixture.manifest)

    claude_dir = fixture.project_root / ".claude"
    assert claude_dir.is_dir()
    assert not claude_dir.is_symlink()


def test_link_result_refused_is_empty_on_a_normal_run(tmp_path: Path) -> None:
    fixture = _build_link_fixture(tmp_path)

    result = _sidecar_link.link(fixture.project_root, fixture.sidecar_root, fixture.manifest)

    assert result.refused == []


# --- link() on a linked project worktree -----------------------------------------


def _link_main_then_add_worktree(tmp_path: Path, branch: str = "feat") -> tuple[_LinkFixture, Path]:
    fixture = _build_link_fixture(tmp_path)
    _sidecar_link.link(fixture.project_root, fixture.sidecar_root, fixture.manifest)
    worktree = fixture.project_root / "wts" / "wt1"
    _git_ok(fixture.project_root, "worktree", "add", "-q", str(worktree), "-b", branch)
    return fixture, worktree


def test_link_on_a_linked_worktree_creates_the_mount_on_a_wt_branch_from_the_base(
    tmp_path: Path,
) -> None:
    fixture, worktree = _link_main_then_add_worktree(tmp_path)
    main_mount = fixture.project_root / _MOUNT_DIRNAME
    main_head = _git_ok(main_mount, "rev-parse", "HEAD").stdout.strip()

    result = _sidecar_link.link(worktree, fixture.sidecar_root, fixture.manifest)

    wt_mount = worktree / _MOUNT_DIRNAME
    branch = _git_ok(wt_mount, "branch", "--show-current").stdout.strip()
    wt_head = _git_ok(wt_mount, "rev-parse", "HEAD").stdout.strip()
    assert result.created_mount is True
    assert branch == "wt/wt1"
    assert wt_head == main_head


def test_link_on_a_linked_worktree_leaves_dot_claude_as_a_real_directory(tmp_path: Path) -> None:
    fixture, worktree = _link_main_then_add_worktree(tmp_path)

    _sidecar_link.link(worktree, fixture.sidecar_root, fixture.manifest)

    claude_dir = worktree / ".claude"
    assert claude_dir.is_dir()
    assert not claude_dir.is_symlink()
    assert (claude_dir / "settings.local.json").is_symlink()


def test_link_on_a_linked_worktree_does_not_rewrite_the_common_dir_exclude_file(
    tmp_path: Path,
) -> None:
    fixture, worktree = _link_main_then_add_worktree(tmp_path)
    exclude_path = fixture.project_root / ".git" / "info" / "exclude"
    before = exclude_path.read_bytes()

    _sidecar_link.link(worktree, fixture.sidecar_root, fixture.manifest)

    after = exclude_path.read_bytes()
    assert after == before


def test_git_status_is_empty_in_the_linked_worktree_after_link(tmp_path: Path) -> None:
    fixture, worktree = _link_main_then_add_worktree(tmp_path)

    _sidecar_link.link(worktree, fixture.sidecar_root, fixture.manifest)

    status = _git_ok(worktree, "status", "--porcelain").stdout
    assert status == ""


# --- no-unlink invariant ----------------------------------------------------------


def test_a_real_directory_at_ai_state_is_left_untouched_by_link(tmp_path: Path) -> None:
    fixture = _build_link_fixture(tmp_path)
    ai_state = fixture.project_root / ".ai-state"
    ai_state.mkdir()
    (ai_state / "DESIGN.md").write_text("operator content\n")
    before_ino = ai_state.stat().st_ino

    result = _sidecar_link.link(fixture.project_root, fixture.sidecar_root, fixture.manifest)

    assert (".ai-state", _sidecar_link.RealPath(kind="dir")) in result.skipped
    assert not ai_state.is_symlink()
    assert (ai_state / "DESIGN.md").read_text() == "operator content\n"
    assert ai_state.stat().st_ino == before_ino


def test_a_symlink_pointing_elsewhere_is_left_untouched_by_link(tmp_path: Path) -> None:
    fixture = _build_link_fixture(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "notes.md").write_text("operator notes\n")
    (fixture.project_root / "CLAUDE.local.md").symlink_to(elsewhere / "notes.md")

    result = _sidecar_link.link(fixture.project_root, fixture.sidecar_root, fixture.manifest)

    link_path = fixture.project_root / "CLAUDE.local.md"
    assert link_path.is_symlink()
    assert os.readlink(link_path) == str(elsewhere / "notes.md")
    assert any(
        relpath == "CLAUDE.local.md" and isinstance(state, _sidecar_link.LinkElsewhere)
        for relpath, state in result.skipped
    )


def test_link_has_no_branch_that_removes_anything_even_when_mixed_with_absent_slots(
    tmp_path: Path,
) -> None:
    """A `RealPath` slot and a `LinkElsewhere` slot coexist with two genuinely
    `Absent` slots in one checkout -- `link()` must leave the occupied two
    untouched while still creating the other two, proving there is no
    all-or-nothing unlink branch hiding behind a refusal.
    """
    fixture = _build_link_fixture(tmp_path)
    (fixture.project_root / ".ai-state").mkdir()
    (fixture.project_root / ".ai-state" / "DESIGN.md").write_text("operator content\n")
    (fixture.project_root / "CLAUDE.local.md").symlink_to(tmp_path / "nowhere")

    result = _sidecar_link.link(fixture.project_root, fixture.sidecar_root, fixture.manifest)

    assert set(result.linked) == {".claude/settings.local.json", "CLAUDE.md"}
    assert (fixture.project_root / ".ai-state" / "DESIGN.md").read_text() == "operator content\n"
    assert os.readlink(fixture.project_root / "CLAUDE.local.md") == str(tmp_path / "nowhere")


# --- idempotence -------------------------------------------------------------------


def test_second_link_run_reports_no_changes(tmp_path: Path) -> None:
    fixture = _build_link_fixture(tmp_path)
    _sidecar_link.link(fixture.project_root, fixture.sidecar_root, fixture.manifest)

    result = _sidecar_link.link(fixture.project_root, fixture.sidecar_root, fixture.manifest)

    assert result.created_mount is False
    assert result.linked == []
    assert result.exclude_changed is False


def test_second_link_run_never_calls_create_mount(tmp_path: Path) -> None:
    fixture = _build_link_fixture(tmp_path)
    _sidecar_link.link(fixture.project_root, fixture.sidecar_root, fixture.manifest)

    def _forbidden_create_mount(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("create_mount called on a clean re-run")

    _sidecar_link.link(
        fixture.project_root,
        fixture.sidecar_root,
        fixture.manifest,
        create_mount=_forbidden_create_mount,
    )


def test_second_link_run_performs_zero_filesystem_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _build_link_fixture(tmp_path)
    _sidecar_link.link(fixture.project_root, fixture.sidecar_root, fixture.manifest)

    def _forbidden_symlink(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("a symlink call was made on a clean re-run")

    monkeypatch.setattr(os, "symlink", _forbidden_symlink)
    monkeypatch.setattr(Path, "symlink_to", _forbidden_symlink)

    def _forbidden_create_mount(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("create_mount called on a clean re-run")

    result = _sidecar_link.link(
        fixture.project_root,
        fixture.sidecar_root,
        fixture.manifest,
        create_mount=_forbidden_create_mount,
    )

    assert result.created_mount is False
    assert result.linked == []
    assert result.exclude_changed is False


# --- foreign `.praxion-state` --------------------------------------------------------------


def test_link_refuses_a_foreign_real_directory_at_the_mount_slot(tmp_path: Path) -> None:
    fixture = _build_link_fixture(tmp_path)
    foreign = fixture.project_root / _MOUNT_DIRNAME
    foreign.mkdir()
    (foreign / "operator-file.txt").write_text("not ours\n")

    with pytest.raises(_sidecar_link.LinkRefused):
        _sidecar_link.link(fixture.project_root, fixture.sidecar_root, fixture.manifest)

    assert (foreign / "operator-file.txt").read_text() == "not ours\n"
    assert not (fixture.project_root / ".ai-state").exists()
    exclude_path = fixture.project_root / ".git" / "info" / "exclude"
    assert not exclude_path.exists() or "praxion:sidecar" not in exclude_path.read_text()


def test_link_refuses_a_worktree_of_a_different_repository_at_the_mount_slot(
    tmp_path: Path,
) -> None:
    fixture = _build_link_fixture(tmp_path)
    other_repo = tmp_path / "unrelated-repo"
    _init_plain_repo(other_repo)
    _git_ok(
        other_repo,
        "worktree",
        "add",
        "-q",
        str(fixture.project_root / _MOUNT_DIRNAME),
        "-b",
        "borrowed",
        "main",
    )

    with pytest.raises(_sidecar_link.LinkRefused):
        _sidecar_link.link(fixture.project_root, fixture.sidecar_root, fixture.manifest)

    assert not (fixture.project_root / ".ai-state").exists()


# --- real git enforces the design's containment claims ------------------------------


def test_git_add_of_a_shadowed_path_fails_beyond_a_symbolic_link(tmp_path: Path) -> None:
    fixture = _build_link_fixture(tmp_path)
    _sidecar_link.link(fixture.project_root, fixture.sidecar_root, fixture.manifest)

    result = _git(
        fixture.project_root, "add", str(fixture.project_root / ".ai-state" / "DESIGN.md")
    )

    assert result.returncode != 0
    assert "beyond a symbolic link" in result.stderr


def test_git_add_dash_a_stages_nothing_after_link(tmp_path: Path) -> None:
    fixture = _build_link_fixture(tmp_path)
    _sidecar_link.link(fixture.project_root, fixture.sidecar_root, fixture.manifest)

    _git_ok(fixture.project_root, "add", "-A")
    status = _git_ok(fixture.project_root, "status", "--porcelain").stdout

    assert status == ""


# --- dry_run ------------------------------------------------------------------------


def test_dry_run_computes_the_same_result_shape_as_a_real_run(tmp_path: Path) -> None:
    dry_fixture = _build_link_fixture(tmp_path / "dry")
    real_fixture = _build_link_fixture(tmp_path / "real")

    dry_result = _sidecar_link.link(
        dry_fixture.project_root, dry_fixture.sidecar_root, dry_fixture.manifest, dry_run=True
    )
    real_result = _sidecar_link.link(
        real_fixture.project_root, real_fixture.sidecar_root, real_fixture.manifest
    )

    assert dry_result.created_mount == real_result.created_mount
    assert set(dry_result.linked) == set(real_result.linked)
    assert dry_result.exclude_changed == real_result.exclude_changed


def test_dry_run_mutates_nothing(tmp_path: Path) -> None:
    fixture = _build_link_fixture(tmp_path)

    _sidecar_link.link(fixture.project_root, fixture.sidecar_root, fixture.manifest, dry_run=True)

    assert not (fixture.project_root / _MOUNT_DIRNAME).exists()
    assert not (fixture.project_root / ".ai-state").exists()
    exclude_path = fixture.project_root / ".git" / "info" / "exclude"
    assert not exclude_path.exists() or "praxion:sidecar" not in exclude_path.read_text()


# --- LIGHT_REVIEW_step-04.md follow-ups (F1-F4) --------------------------------


def test_converge_is_invoked_exactly_once_for_the_main_checkout(tmp_path: Path) -> None:
    fixture = _build_link_fixture(tmp_path)
    calls: list[object] = []

    def _recording_converge(*args: object, **kwargs: object) -> None:
        calls.append((args, kwargs))

    _sidecar_link.link(
        fixture.project_root, fixture.sidecar_root, fixture.manifest, converge=_recording_converge
    )

    assert len(calls) == 1


def test_link_on_a_linked_worktree_never_calls_converge(tmp_path: Path) -> None:
    fixture, worktree = _link_main_then_add_worktree(tmp_path)

    def _forbidden_converge(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("converge called on a linked worktree")

    _sidecar_link.link(
        worktree, fixture.sidecar_root, fixture.manifest, converge=_forbidden_converge
    )


@pytest.mark.parametrize(
    "build_checkout",
    [
        lambda tmp_path: tmp_path / "not-a-worktree-at-all",
        lambda tmp_path: _checkout_with_malformed_git_pointer(tmp_path),
    ],
)
def test_base_sidecar_branch_falls_back_to_main_on_an_unidentifiable_base(
    tmp_path: Path, build_checkout
) -> None:
    checkout = build_checkout(tmp_path)
    checkout.mkdir(parents=True, exist_ok=True)

    assert _sidecar_link._base_sidecar_branch(checkout) == "main"


def _checkout_with_malformed_git_pointer(tmp_path: Path) -> Path:
    """A linked-worktree-shaped ``.git`` pointer whose target does not sit
    under a ``worktrees`` segment -- `common_dir_of_worktree` returns
    ``None`` for it, the second of `_base_sidecar_branch`'s three
    fallback-to-``main`` branches.
    """
    checkout = tmp_path / "malformed-pointer-checkout"
    checkout.mkdir(parents=True, exist_ok=True)
    (checkout / ".git").write_text(f"gitdir: {tmp_path / 'not-a-worktrees-dir'}\n")
    return checkout


def test_base_sidecar_branch_falls_back_to_main_when_the_base_checkout_was_never_linked(
    tmp_path: Path,
) -> None:
    """F2's own proving-test suggestion, driven end to end through `link()`:
    a worktree fixture whose base checkout's mount was never created before
    the worktree link runs still resolves `base_branch` to `main` rather
    than raising.
    """
    fixture = _build_link_fixture(tmp_path)
    worktree = fixture.project_root / "wts" / "wt-no-base-mount"
    _git_ok(fixture.project_root, "worktree", "add", "-q", str(worktree), "-b", "feat")

    result = _sidecar_link.link(worktree, fixture.sidecar_root, fixture.manifest)

    branch = _git_ok(worktree / _MOUNT_DIRNAME, "branch", "--show-current").stdout.strip()
    assert result.created_mount is True
    assert branch == "wt/wt-no-base-mount"


def test_link_sanitises_an_illegal_worktree_dirname_into_a_valid_branch(tmp_path: Path) -> None:
    fixture = _build_link_fixture(tmp_path)
    _sidecar_link.link(fixture.project_root, fixture.sidecar_root, fixture.manifest)
    worktree = fixture.project_root / "wts" / "feat one..two"
    _git_ok(fixture.project_root, "worktree", "add", "-q", str(worktree), "-b", "feat")

    result = _sidecar_link.link(worktree, fixture.sidecar_root, fixture.manifest)

    branch = _git_ok(worktree / _MOUNT_DIRNAME, "branch", "--show-current").stdout.strip()
    assert result.created_mount is True
    assert branch == "wt/feat-one-two"


def test_link_refuses_a_worktree_dirname_that_cannot_be_sanitised(tmp_path: Path) -> None:
    fixture = _build_link_fixture(tmp_path)
    _sidecar_link.link(fixture.project_root, fixture.sidecar_root, fixture.manifest)
    worktree = fixture.project_root / "wts" / "???"
    _git_ok(fixture.project_root, "worktree", "add", "-q", str(worktree), "-b", "feat")

    with pytest.raises(_sidecar_link.LinkRefused) as exc_info:
        _sidecar_link.link(worktree, fixture.sidecar_root, fixture.manifest)

    assert "???" in str(exc_info.value)


def test_link_on_a_detached_head_worktree_never_maps_head_as_the_project_branch(
    tmp_path: Path,
) -> None:
    fixture = _build_link_fixture(tmp_path)
    _sidecar_link.link(fixture.project_root, fixture.sidecar_root, fixture.manifest)
    worktree = fixture.project_root / "wts" / "wt-detached"
    _git_ok(fixture.project_root, "worktree", "add", "-q", "--detach", str(worktree))

    _sidecar_link.link(worktree, fixture.sidecar_root, fixture.manifest)

    branch = _sidecar_link.sidecar_branch_for(worktree)
    mapping = _git(
        fixture.sidecar_root, "config", "--get", f"branch.{branch}.praxion-project-branch"
    )
    assert mapping.returncode != 0


# --- recovering a mount whose directory was removed outside git ----------------------


def test_link_recreates_a_mount_whose_directory_was_deleted_by_hand(tmp_path: Path) -> None:
    """`git clean -ffdx` removes the mount directory and nothing else, leaving
    the sidecar's own worktree record behind -- which git then refuses to add
    over. Recovery must not require the operator to know about `worktree
    prune`, and the committed state must come back with the mount."""
    fixture = _build_link_fixture(tmp_path)
    _sidecar_link.link(fixture.project_root, fixture.sidecar_root, fixture.manifest)
    shutil.rmtree(fixture.project_root / _MOUNT_DIRNAME)

    result = _sidecar_link.link(fixture.project_root, fixture.sidecar_root, fixture.manifest)

    assert result.created_mount
    restored = fixture.project_root / _MOUNT_DIRNAME / ".ai-state" / "DESIGN.md"
    assert restored.read_text(encoding="utf-8") == "seed\n"


# --- repairing the sidecar's record after the project moves --------------------------


def _recorded_worktree_paths(sidecar_root: Path) -> list[str]:
    return [
        gitdir.read_text(encoding="utf-8").strip()
        for gitdir in sorted((sidecar_root / ".git" / "worktrees").glob("*/gitdir"))
    ]


def test_link_repairs_the_sidecar_record_after_the_project_directory_moves(
    tmp_path: Path,
) -> None:
    """Moving a project leaves its mount working -- the forward pointer is
    absolute -- while the sidecar still believes the mount is at the old path.
    `link` is the advertised fix, so it has to actually be one."""
    fixture = _build_link_fixture(tmp_path)
    _sidecar_link.link(fixture.project_root, fixture.sidecar_root, fixture.manifest)
    moved = tmp_path / "project-moved"
    shutil.move(str(fixture.project_root), str(moved))

    result = _sidecar_link.link(moved, fixture.sidecar_root, fixture.manifest)

    assert result.repaired_mount
    assert _recorded_worktree_paths(fixture.sidecar_root) == [str(moved / _MOUNT_DIRNAME / ".git")]
    listing = _git_ok(fixture.sidecar_root, "worktree", "list").stdout
    assert str(moved / _MOUNT_DIRNAME) in listing


def test_link_reports_no_repair_when_the_project_has_not_moved(tmp_path: Path) -> None:
    """The inverse guard: a healthy mount must not provoke a repair on every
    re-run, which would turn the idempotent SessionStart heal into a write."""
    fixture = _build_link_fixture(tmp_path)
    _sidecar_link.link(fixture.project_root, fixture.sidecar_root, fixture.manifest)

    result = _sidecar_link.link(fixture.project_root, fixture.sidecar_root, fixture.manifest)

    assert not result.repaired_mount


# --- the mount name never collides with the team-committed recipes directory ---


def test_the_mount_name_is_the_state_directory_not_the_recipes_directory() -> None:
    """`<repo>/.praxion/` is the documented home of team-committed parallel-session
    recipes, so the state mount must live under a different name."""
    assert _MOUNT_DIRNAME == ".praxion-state"


def test_link_still_mounts_when_the_project_carries_a_committed_recipes_directory(
    tmp_path: Path,
) -> None:
    fixture = _build_link_fixture(tmp_path)
    recipes_dir = fixture.project_root / ".praxion"
    recipes_dir.mkdir()
    (recipes_dir / "recipes.json").write_text("[]\n")
    _git_ok(fixture.project_root, "add", ".praxion/recipes.json")
    _git_ok(fixture.project_root, "commit", "-q", "-m", "team recipes")

    result = _sidecar_link.link(fixture.project_root, fixture.sidecar_root, fixture.manifest)

    assert result.created_mount is True
    assert not result.refused
    assert (fixture.project_root / _MOUNT_DIRNAME).is_dir()
    assert (recipes_dir / "recipes.json").read_text() == "[]\n"
    assert _git_ok(fixture.project_root, "status", "--porcelain", ".praxion").stdout == ""
