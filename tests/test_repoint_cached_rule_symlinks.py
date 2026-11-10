"""`repoint_cached_rule_symlinks` moves rule links from another cached version to this one.

A plugin update leaves the user's rule links pointing into the previous version's
directory of the plugin cache. The library function re-points exactly those: a
manifest `install: symlink` place whose link, live or dangling, lies in another
version's cached rules. A link already into the current rules, a live link
outside the cache (a clone install's), a regular file, and a place the manifest
does not link are never touched, and a manifest it cannot read changes nothing.

Each case builds a small rules source with a manifest under a fake plugin cache
and drives the function through bash with the shared library sourced. The
`_managed_rule_rel_path` rows of `tests/fixtures/plugin_cache_targets.tsv` keep
the shell's cache rule equal to the hook's.
"""

from __future__ import annotations

import csv
import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
INSTALL_SHARED = REPO_ROOT / "lib" / "install_shared.sh"
CACHE_TARGETS = REPO_ROOT / "tests" / "fixtures" / "plugin_cache_targets.tsv"

LINKED = "swe/linked.md"
OTHER_LINKED = "swe/other-linked.md"
HOOK_DELIVERED = "swe/hook-delivered.md"

_MANIFEST = """\
version: 1
rules:
- id: swe/linked
  path: rules/swe/linked.md
  install: symlink
- id: swe/other-linked
  path: rules/swe/other-linked.md
  install: symlink
- id: swe/hook-delivered
  path: rules/swe/hook-delivered.md
  install: hook-deliver
"""


def _bash(command: str, home: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", "-c", f'source "{INSTALL_SHARED}"; {command}'],
        capture_output=True,
        text=True,
        env={**os.environ, "HOME": str(home)},
        check=False,
        timeout=60,
    )


def _make_rules(version_dir: Path) -> Path:
    rules = version_dir / "rules"
    (rules / "swe").mkdir(parents=True)
    (rules / "_manifest.yaml").write_text(_MANIFEST, encoding="utf-8")
    for rel in (LINKED, OTHER_LINKED, HOOK_DELIVERED):
        (rules / rel).write_text(f"# {rel} in {version_dir.name}\n", encoding="utf-8")
    return rules


@pytest.fixture
def cache(tmp_path: Path) -> Path:
    return tmp_path / "home" / ".claude" / "plugins" / "cache" / "example-market" / "praxion"


@pytest.fixture
def new_rules(cache: Path) -> Path:
    return _make_rules(cache / "2.0.0")


@pytest.fixture
def old_rules(cache: Path) -> Path:
    return _make_rules(cache / "1.0.0")


@pytest.fixture
def target(tmp_path: Path) -> Path:
    directory = tmp_path / "home" / ".claude" / "rules"
    (directory / "swe").mkdir(parents=True)
    return directory


def _repoint(new_rules: Path, target: Path) -> subprocess.CompletedProcess:
    return _bash(f'repoint_cached_rule_symlinks "{new_rules}" "{target}"', target.parent.parent)


def test_a_live_link_into_another_version_is_repointed(new_rules, old_rules, target):
    link = target / LINKED
    link.symlink_to(old_rules / LINKED)

    result = _repoint(new_rules, target)

    assert result.returncode == 0, result.stderr
    assert os.readlink(link) == str(new_rules / LINKED)


def test_a_dangling_link_into_another_version_is_repointed(new_rules, cache, target):
    link = target / LINKED
    link.symlink_to(cache / "0.9.0" / "rules" / LINKED)

    _repoint(new_rules, target)

    assert os.readlink(link) == str(new_rules / LINKED)


def test_a_relative_link_into_another_version_is_repointed(new_rules, old_rules, target):
    link = target / LINKED
    link.symlink_to(os.path.relpath(old_rules / LINKED, link.parent))

    _repoint(new_rules, target)

    assert os.readlink(link) == str(new_rules / LINKED)


def test_a_link_already_into_the_current_version_keeps_its_inode(new_rules, target):
    link = target / LINKED
    link.symlink_to(new_rules / LINKED)
    before = link.lstat()

    _repoint(new_rules, target)

    assert os.readlink(link) == str(new_rules / LINKED)
    assert link.lstat().st_ino == before.st_ino


def test_a_relative_link_already_into_the_current_version_keeps_its_inode(new_rules, target):
    link = target / LINKED
    link.symlink_to(os.path.relpath(new_rules / LINKED, link.parent))
    before = link.lstat()

    _repoint(new_rules, target)

    assert os.readlink(link) == os.path.relpath(new_rules / LINKED, link.parent)
    assert link.lstat().st_ino == before.st_ino


def test_a_live_link_outside_the_cache_is_left_as_it_is(new_rules, tmp_path, target):
    clone_rule = tmp_path / "src" / "praxion" / "rules" / LINKED
    clone_rule.parent.mkdir(parents=True)
    clone_rule.write_text("# a clone's rule\n", encoding="utf-8")
    link = target / LINKED
    link.symlink_to(clone_rule)
    before = link.lstat()

    _repoint(new_rules, target)

    assert os.readlink(link) == str(clone_rule)
    assert link.lstat().st_ino == before.st_ino


def test_a_regular_file_at_a_rules_place_is_left_byte_identical(new_rules, target):
    own = target / LINKED
    own.write_text("# the operator's own rule\n", encoding="utf-8")

    _repoint(new_rules, target)

    assert not own.is_symlink()
    assert own.read_text(encoding="utf-8") == "# the operator's own rule\n"


def test_a_place_outside_the_keep_set_is_left_to_the_sweep(new_rules, old_rules, target):
    link = target / HOOK_DELIVERED
    link.symlink_to(old_rules / HOOK_DELIVERED)

    _repoint(new_rules, target)

    assert os.readlink(link) == str(old_rules / HOOK_DELIVERED)


def test_a_place_with_no_link_is_not_created(new_rules, target):
    _repoint(new_rules, target)

    assert not os.path.lexists(target / LINKED)


def test_a_rule_the_new_version_lacks_is_not_repointed_to_nothing(new_rules, old_rules, target):
    (new_rules / LINKED).unlink()
    link = target / LINKED
    link.symlink_to(old_rules / LINKED)

    _repoint(new_rules, target)

    assert os.readlink(link) == str(old_rules / LINKED)


def _link_into_old_version(old_rules: Path, target: Path) -> Path:
    link = target / LINKED
    link.symlink_to(old_rules / LINKED)
    return link


def test_an_absent_manifest_changes_nothing_and_succeeds(new_rules, old_rules, target):
    (new_rules / "_manifest.yaml").unlink()
    link = _link_into_old_version(old_rules, target)

    result = _repoint(new_rules, target)

    assert result.returncode == 0, result.stderr
    assert os.readlink(link) == str(old_rules / LINKED)


def test_an_empty_manifest_changes_nothing_and_succeeds(new_rules, old_rules, target):
    (new_rules / "_manifest.yaml").write_text("", encoding="utf-8")
    link = _link_into_old_version(old_rules, target)

    result = _repoint(new_rules, target)

    assert result.returncode == 0, result.stderr
    assert os.readlink(link) == str(old_rules / LINKED)


def _rule_target_rows() -> list:
    with CACHE_TARGETS.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    return [
        pytest.param(row["target_text"], row["is_cache"] == "true", id=row["label"])
        for row in rows
        if "/.claude/rules" in row["link_dir"] and "/rules/" in row["target_text"]
    ]


@pytest.mark.parametrize(("target_text", "is_cache"), _rule_target_rows())
def test_the_shells_cache_rule_agrees_with_the_shared_rows(target_text, is_cache, tmp_path):
    result = _bash(
        f'_managed_rule_rel_path "/nowhere/rules" "{target_text}"',
        tmp_path,
    )

    assert (result.returncode == 0) is is_cache, result.stdout


def test_the_shared_rows_name_rule_targets():
    assert len(_rule_target_rows()) >= 4
