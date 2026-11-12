"""A finished run removes the trees it built, read-only and unreadable parts included.

An arm's plugin copy is read-only on disk, and a session can leave a directory without its read
bit. A removal that skips either leaves a directory skeleton in the temp directory, so it must
reopen both, and it must say so when a tree still stays.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from praxion_evals.adherence import session_launch
from praxion_evals.adherence.model import Errored
from praxion_evals.live import materialize
from praxion_evals.live.materialize import make_read_only, make_writable, remove_tree
from praxion_evals.live.session import SessionRun
from praxion_evals.live.spend import SpendLedger

NO_READ = 0o311  # write and search, no read: a glob cannot list it


def _build_hostile_tree(root: Path) -> Path:
    """A read-only plugin copy and a directory that lost its read bit, both under `root`."""
    copy = root / "arm" / "plugin" / "skills"
    copy.mkdir(parents=True)
    (copy / "SKILL.md").write_text("skill\n", encoding="utf-8")
    make_read_only(root / "arm")
    hidden = root / "home" / ".cache"
    (hidden / "inner").mkdir(parents=True)
    (hidden / "inner" / "entry").write_text("entry\n", encoding="utf-8")
    hidden.chmod(NO_READ)
    return root


def test_make_writable_reopens_a_directory_that_lost_its_read_bit(tmp_path: Path):
    root = _build_hostile_tree(tmp_path / "tree")

    make_writable(root)

    assert (root / "home" / ".cache" / "inner" / "entry") in set(root.rglob("*"))


def test_removing_a_tree_takes_its_read_only_and_unreadable_parts(tmp_path: Path):
    root = _build_hostile_tree(tmp_path / "tree")

    remove_tree(root)

    assert not root.exists()


def test_removing_a_tree_that_stays_names_it_in_a_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    root = _build_hostile_tree(tmp_path / "tree")

    def refuse(path, *args, **kwargs):
        raise PermissionError(f"denied: {path}")

    monkeypatch.setattr(materialize.shutil, "rmtree", refuse)

    remove_tree(root)

    assert f"warning: {root} was not removed" in capsys.readouterr().err


def test_removing_an_absent_tree_says_nothing(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    remove_tree(tmp_path / "never-built")

    assert capsys.readouterr().err == ""


def test_a_finished_session_leaves_no_directory_behind(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    def prepare(launch, task, build, populate, page_url, root):
        _build_hostile_tree(root)
        return None, "commit", None

    monkeypatch.setattr(session_launch, "_prepare", prepare)
    monkeypatch.setattr(session_launch, "run_session", lambda spec, env: SessionRun("", "", 1))
    monkeypatch.setattr(session_launch, "_evidence", lambda *args: None)
    launch = session_launch.Launch(
        run_root=tmp_path,
        checkout_commit="0123456789abcdef0123456789abcdef01234567",
        page_url="",
        judge=None,
        seed=7,
        model="m",
        effort="low",
        session_budget_usd=1.0,
        keep_sandbox=False,
        env_for=lambda root, path_first: {},
        tail_chars=40,
    )

    session_launch.attempt(
        launch,
        SpendLedger(cap_usd=10.0),
        SimpleNamespace(role="researcher"),  # type: ignore[arg-type]
        None,  # type: ignore[arg-type]
        lambda root: None,
        None,
        lambda evidence: Errored("no_result_event", "none"),
    )

    assert list((tmp_path / "researcher" / "sessions").iterdir()) == []
