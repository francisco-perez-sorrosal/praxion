"""Tests for check_hackathon_graduation.py -- HK01 gate-liveness canary.

Each test builds a minimal `.claude/settings.json` under `tmp_path` (the check's own
substrate gate) and, where needed, monkeypatches `_count_commits` rather than shelling
out to a real git repo -- `tmp_path` is not one.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import check_hackathon_graduation as hk  # noqa: E402
from check_hackathon_graduation import CHECK_IDS, classify  # noqa: E402


def _write_settings(tmp_path: Path, enabled: bool) -> None:
    settings_dir = tmp_path / ".claude"
    settings_dir.mkdir(parents=True, exist_ok=True)
    value = '"1"' if enabled else '"0"'
    (settings_dir / "settings.json").write_text(
        f'{{"env": {{"PRAXION_HACKATHON_MODE": {value}}}}}', encoding="utf-8"
    )


def _write_source_files(tmp_path: Path, count: int) -> None:
    for i in range(count):
        (tmp_path / f"module_{i}.py").write_text("x = 1\n", encoding="utf-8")


def test_check_ids_declares_hk01() -> None:
    assert CHECK_IDS == ("HK01",)


def test_no_settings_file_is_skipped(tmp_path: Path) -> None:
    """No `.claude/settings.json` at all -- hackathon mode is off by construction."""
    report = classify(tmp_path)
    assert report["skipped"]["HK01"]["reason"] == "hackathon-mode-off"
    assert report["examined"]["HK01"] is None
    assert report["findings"] == []


def test_hackathon_mode_off_is_skipped(tmp_path: Path) -> None:
    _write_settings(tmp_path, enabled=False)
    report = classify(tmp_path)
    assert report["skipped"]["HK01"]["reason"] == "hackathon-mode-off"
    assert report["findings"] == []


def test_hackathon_mode_on_below_both_thresholds_is_clean(tmp_path: Path, monkeypatch) -> None:
    _write_settings(tmp_path, enabled=True)
    _write_source_files(tmp_path, 3)
    monkeypatch.setattr(hk, "_count_commits", lambda _root: 10)
    report = classify(tmp_path)
    assert report["findings"] == []
    assert report["examined"]["HK01"] == {"source_files": 3, "commits": 10}


def test_source_file_count_over_threshold_flags(tmp_path: Path, monkeypatch) -> None:
    """Golden bad-case: source-file count alone crosses the threshold."""
    _write_settings(tmp_path, enabled=True)
    _write_source_files(tmp_path, 41)
    monkeypatch.setattr(hk, "_count_commits", lambda _root: 5)
    report = classify(tmp_path)
    findings = [f for f in report["findings"] if f["check"] == "HK01"]
    assert len(findings) == 1
    assert findings[0]["severity"] == "info"
    assert "source files: 41" in findings[0]["message"]


def test_commit_count_over_threshold_flags(tmp_path: Path, monkeypatch) -> None:
    """Golden bad-case: commit count alone crosses the threshold."""
    _write_settings(tmp_path, enabled=True)
    _write_source_files(tmp_path, 2)
    monkeypatch.setattr(hk, "_count_commits", lambda _root: 151)
    report = classify(tmp_path)
    findings = [f for f in report["findings"] if f["check"] == "HK01"]
    assert len(findings) == 1
    assert "commits: 151" in findings[0]["message"]


def test_test_path_source_files_are_excluded(tmp_path: Path, monkeypatch) -> None:
    """`find -not -path "*/test*"` equivalent: a test-prefixed dir does not count."""
    _write_settings(tmp_path, enabled=True)
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    for i in range(60):
        (tests_dir / f"test_mod_{i}.py").write_text("x = 1\n", encoding="utf-8")
    monkeypatch.setattr(hk, "_count_commits", lambda _root: 1)
    report = classify(tmp_path)
    assert report["findings"] == []
    assert report["examined"]["HK01"]["source_files"] == 0


def test_git_dir_source_files_are_excluded(tmp_path: Path, monkeypatch) -> None:
    """`find -not -path "*/.git/*"` equivalent: files under `.git/` do not count."""
    _write_settings(tmp_path, enabled=True)
    git_dir = tmp_path / ".git" / "hooks"
    git_dir.mkdir(parents=True)
    (git_dir / "sample.py").write_text("x = 1\n", encoding="utf-8")
    monkeypatch.setattr(hk, "_count_commits", lambda _root: 1)
    report = classify(tmp_path)
    assert report["examined"]["HK01"]["source_files"] == 0


def test_unresolvable_commit_count_degrades_to_zero(tmp_path: Path, monkeypatch) -> None:
    """A `git rev-list` failure (e.g. no git repo) must not crash the check."""
    _write_settings(tmp_path, enabled=True)
    _write_source_files(tmp_path, 2)
    report = classify(tmp_path)  # tmp_path is not a real git repo -- real subprocess runs
    assert report["examined"]["HK01"]["commits"] == 0
    assert report["findings"] == []


def test_malformed_settings_json_is_treated_as_off(tmp_path: Path) -> None:
    """Invalid JSON must not crash the check -- it degrades to hackathon-mode-off."""
    settings_dir = tmp_path / ".claude"
    settings_dir.mkdir(parents=True)
    (settings_dir / "settings.json").write_text("{not json", encoding="utf-8")
    report = classify(tmp_path)
    assert report["skipped"]["HK01"]["reason"] == "hackathon-mode-off"
