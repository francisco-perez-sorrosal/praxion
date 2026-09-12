"""Tests for check_hook_installation.py -- F10 gate-liveness canary.

Each test builds a minimal `.git/hooks/` + `scripts/git-*-hook.sh` pair under
`tmp_path` (no real git repo needed -- `classify` only ever reads
`<repo_root>/.git/hooks` and `<repo_root>/scripts`, and the resolver is
exercised separately since it shells out to `git`).
"""

from __future__ import annotations

import stat
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import check_hook_installation as chi  # noqa: E402
from check_hook_installation import CHECK_IDS, _installed_hooks  # noqa: E402


def _make_source(repo_root: Path, name: str, body: str, *, executable: bool = True) -> Path:
    scripts_dir = repo_root / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    source = scripts_dir / name
    source.write_text(body, encoding="utf-8")
    if executable:
        source.chmod(source.stat().st_mode | stat.S_IEXEC)
    return source


def _make_hooks_dir(repo_root: Path) -> Path:
    hooks_dir = repo_root / ".git" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    return hooks_dir


def test_check_ids_declares_f10() -> None:
    assert CHECK_IDS == ("F10",)


def test_no_hooks_dir_is_skipped(tmp_path: Path, monkeypatch) -> None:
    """Conditional: `.git/hooks` cannot be resolved -> skip, not a finding."""
    monkeypatch.setattr(chi, "_resolve_hooks_dir", lambda _root: None)
    report = chi.classify(tmp_path)
    assert report["skipped"]["F10"]["reason"] == "substrate-absent"
    assert report["examined"]["F10"] is None
    assert report["findings"] == []


def test_multiplexed_source_installed_under_three_names_is_clean(
    tmp_path: Path, monkeypatch
) -> None:
    """Golden bad-case: one source correctly installed under 3 hook names.

    Filename derivation (`git-finalize-hook.sh` -> `.git/hooks/finalize`)
    would find no such file and report the source MISSING -- the exact
    false-positive content resolution exists to close. Content resolution
    finds it installed under post-merge/post-commit/post-checkout and
    reports zero findings.
    """
    source = _make_source(tmp_path, "git-finalize-hook.sh", "#!/bin/sh\necho finalize\n")
    hooks_dir = _make_hooks_dir(tmp_path)
    for name in ("post-merge", "post-commit", "post-checkout"):
        (hooks_dir / name).write_bytes(source.read_bytes())
    monkeypatch.setattr(chi, "_resolve_hooks_dir", lambda _root: hooks_dir)

    report = chi.classify(tmp_path)
    assert report["findings"] == []
    assert report["examined"]["F10"]["sources"] == 1


def test_source_matching_no_hook_and_executable_warns(tmp_path: Path, monkeypatch) -> None:
    _make_source(tmp_path, "git-orphan-hook.sh", "#!/bin/sh\necho orphan\n", executable=True)
    hooks_dir = _make_hooks_dir(tmp_path)
    monkeypatch.setattr(chi, "_resolve_hooks_dir", lambda _root: hooks_dir)

    report = chi.classify(tmp_path)
    findings = [f for f in report["findings"] if f["check"] == "F10"]
    assert len(findings) == 1
    assert "matches no installed hook" in findings[0]["message"]


def test_source_not_executable_and_no_derived_hook_is_silent(tmp_path: Path, monkeypatch) -> None:
    _make_source(tmp_path, "git-helper-hook.sh", "#!/bin/sh\necho helper\n", executable=False)
    hooks_dir = _make_hooks_dir(tmp_path)
    monkeypatch.setattr(chi, "_resolve_hooks_dir", lambda _root: hooks_dir)

    report = chi.classify(tmp_path)
    assert report["findings"] == []


def test_derived_name_hook_exists_but_differs_warns(tmp_path: Path, monkeypatch) -> None:
    _make_source(tmp_path, "git-refresh-hook.sh", "#!/bin/sh\necho new\n", executable=True)
    hooks_dir = _make_hooks_dir(tmp_path)
    (hooks_dir / "refresh").write_text("#!/bin/sh\necho old\n", encoding="utf-8")
    monkeypatch.setattr(chi, "_resolve_hooks_dir", lambda _root: hooks_dir)

    report = chi.classify(tmp_path)
    findings = [f for f in report["findings"] if f["check"] == "F10"]
    assert len(findings) == 1
    assert "differs from source" in findings[0]["message"]


def test_dangling_symlink_in_hooks_dir_is_unreadable_not_a_crash(
    tmp_path: Path, monkeypatch
) -> None:
    hooks_dir = _make_hooks_dir(tmp_path)
    (hooks_dir / "post-merge").symlink_to(tmp_path / "does-not-exist.sh")
    _make_source(tmp_path, "git-finalize-hook.sh", "#!/bin/sh\necho finalize\n", executable=True)
    monkeypatch.setattr(chi, "_resolve_hooks_dir", lambda _root: hooks_dir)

    report = chi.classify(tmp_path)
    assert "post-merge" not in _installed_hooks(hooks_dir)
    findings = [f for f in report["findings"] if f["check"] == "F10"]
    assert len(findings) == 1  # unreadable dangling symlink does not stand in as a match


def test_sample_hooks_are_ignored(tmp_path: Path, monkeypatch) -> None:
    hooks_dir = _make_hooks_dir(tmp_path)
    (hooks_dir / "pre-commit.sample").write_text("#!/bin/sh\n", encoding="utf-8")
    monkeypatch.setattr(chi, "_resolve_hooks_dir", lambda _root: hooks_dir)

    report = chi.classify(tmp_path)
    assert "pre-commit.sample" not in _installed_hooks(hooks_dir)
    assert report["examined"]["F10"]["sources"] == 0
    assert report["findings"] == []


def test_no_sources_is_not_a_skip(tmp_path: Path, monkeypatch) -> None:
    """Zero `scripts/git-*-hook.sh` files is an empty walk, not a skip."""
    hooks_dir = _make_hooks_dir(tmp_path)
    monkeypatch.setattr(chi, "_resolve_hooks_dir", lambda _root: hooks_dir)

    report = chi.classify(tmp_path)
    assert report["skipped"]["F10"] is None
    assert report["examined"]["F10"]["sources"] == 0
    assert report["findings"] == []


def test_resolve_hooks_dir_uses_git_common_dir(tmp_path: Path) -> None:
    """Live integration: resolves against the real repo (a worktree here)."""
    hooks_dir = chi._resolve_hooks_dir(REPO_ROOT)
    assert hooks_dir is not None
    assert hooks_dir.name == "hooks"
    assert hooks_dir.is_dir()
