"""Tests for prune_reports.py -- retain-last-N report pruning.

Import strategy: deferred via importlib.util so collection never requires the
script on sys.path (mirrors the sibling detector tests).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

_SCRIPT_PATH = Path(__file__).resolve().parent / "prune_reports.py"

# Fixed-width run timestamps, oldest-first; lexical order == chronological here.
_TIMESTAMPS = [
    "2026-01-01_00-00-00",
    "2026-02-01_00-00-00",
    "2026-03-01_00-00-00",
    "2026-04-01_00-00-00",
    "2026-05-01_00-00-00",
]


def _load_module() -> Any:
    sys.modules.pop("prune_reports", None)
    spec = importlib.util.spec_from_file_location("prune_reports", _SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["prune_reports"] = mod
    spec.loader.exec_module(mod)
    return mod


def _make_metrics(root: Path, timestamps: list[str]) -> Path:
    """Build .ai-state/metrics_reports with a .md+.json pair per run + LOG + lock."""
    d = root / ".ai-state" / "metrics_reports"
    d.mkdir(parents=True)
    (d / "METRICS_LOG.md").write_text("log index\n")
    (d / "METRICS_LOG.lock").write_text("")
    for ts in timestamps:
        (d / f"METRICS_REPORT_{ts}.md").write_text("md\n")
        (d / f"METRICS_REPORT_{ts}.json").write_text("{}\n")
    return d


def _make_sentinel(root: Path, timestamps: list[str]) -> Path:
    d = root / ".ai-state" / "sentinel_reports"
    d.mkdir(parents=True)
    (d / "SENTINEL_LOG.md").write_text("log index\n")
    for ts in timestamps:
        (d / f"SENTINEL_REPORT_{ts}.md").write_text("md\n")
    return d


def test_keeps_newest_n_prunes_older(tmp_path: Path) -> None:
    mod = _load_module()
    d = _make_sentinel(tmp_path, _TIMESTAMPS)  # 5 runs
    result = mod.prune_all(tmp_path, keep=2, dry_run=False)
    remaining = sorted(p.name for p in d.glob("SENTINEL_REPORT_*"))
    # Only the two newest survive.
    assert remaining == [
        "SENTINEL_REPORT_2026-04-01_00-00-00.md",
        "SENTINEL_REPORT_2026-05-01_00-00-00.md",
    ]
    assert result["total_pruned"] == 3


def test_preserves_log_and_lock(tmp_path: Path) -> None:
    mod = _load_module()
    d = _make_metrics(tmp_path, _TIMESTAMPS)
    mod.prune_all(tmp_path, keep=0, dry_run=False)  # aggressive: prune every run
    # The index and lock are structurally exempt — never pruned.
    assert (d / "METRICS_LOG.md").exists()
    assert (d / "METRICS_LOG.lock").exists()
    assert not list(d.glob("METRICS_REPORT_*"))


def test_metrics_pair_pruned_together(tmp_path: Path) -> None:
    mod = _load_module()
    d = _make_metrics(tmp_path, _TIMESTAMPS)
    mod.prune_all(tmp_path, keep=1, dry_run=False)
    # The single surviving run keeps both its .md and .json.
    survivors = sorted(p.name for p in d.glob("METRICS_REPORT_*"))
    assert survivors == [
        "METRICS_REPORT_2026-05-01_00-00-00.json",
        "METRICS_REPORT_2026-05-01_00-00-00.md",
    ]


def test_dry_run_deletes_nothing(tmp_path: Path) -> None:
    mod = _load_module()
    d = _make_sentinel(tmp_path, _TIMESTAMPS)
    result = mod.prune_all(tmp_path, keep=1, dry_run=True)
    # Reported as would-prune, but nothing left the disk.
    assert result["total_pruned"] == 4
    assert len(list(d.glob("SENTINEL_REPORT_*"))) == 5


def test_absent_family_is_noop(tmp_path: Path) -> None:
    mod = _load_module()
    # No .ai-state at all — must not raise, must report families absent.
    result = mod.prune_all(tmp_path, keep=10, dry_run=False)
    assert result["total_pruned"] == 0
    assert all(not fam["present"] for fam in result["families"])


def test_fewer_than_keep_prunes_nothing(tmp_path: Path) -> None:
    mod = _load_module()
    d = _make_sentinel(tmp_path, _TIMESTAMPS[:3])  # 3 runs, keep 10
    result = mod.prune_all(tmp_path, keep=10, dry_run=False)
    assert result["total_pruned"] == 0
    assert len(list(d.glob("SENTINEL_REPORT_*"))) == 3


def test_bites_canary(tmp_path: Path) -> None:
    """Gate-liveness proof: with keep=N and N+2 runs, exactly the 2 oldest runs
    are deleted from disk — the script demonstrably *prunes*, not just passes."""
    mod = _load_module()
    keep = 3
    d = _make_sentinel(tmp_path, _TIMESTAMPS)  # 5 runs, keep 3 -> prune 2 oldest
    before = {p.name for p in d.glob("SENTINEL_REPORT_*")}
    mod.prune_all(tmp_path, keep=keep, dry_run=False)
    after = {p.name for p in d.glob("SENTINEL_REPORT_*")}
    deleted = before - after
    assert deleted == {
        "SENTINEL_REPORT_2026-01-01_00-00-00.md",
        "SENTINEL_REPORT_2026-02-01_00-00-00.md",
    }
    assert len(after) == keep
