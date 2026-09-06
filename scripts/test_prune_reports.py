"""Tests for prune_reports.py -- retain-last-N report pruning.

Import strategy: deferred via importlib.util so collection never requires the
script on sys.path (mirrors the sibling detector tests).
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

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


def _inventory(directory: Path) -> dict[str, str]:
    """Name -> content for every file directly under `directory`."""
    return {p.name: p.read_text() for p in sorted(directory.iterdir()) if p.is_file()}


def _run_cli(mod: Any, capsys: pytest.CaptureFixture[str], argv: list[str]) -> tuple[int, str]:
    """Parse CLI args and run, returning (exit_code, captured_stdout).

    Goes through `_parse_args` (the argparse layer), not `prune_all` directly,
    so a not-yet-implemented `--family` flag fails here with argparse's own
    "unrecognized arguments" error -- the correct signature for the flag's
    absence, not a collection error.
    """
    args = mod._parse_args(argv)
    code = mod._run(args)
    return code, capsys.readouterr().out


def test_sibling_series_in_one_directory_have_independent_retention(tmp_path: Path) -> None:
    """Two report series sharing a directory must not evict each other.

    `.ai-state/metrics_reports/` legitimately hosts two deliberately-distinct
    namespaces: the code-health `METRICS_REPORT_*` triple and the self-healing
    `SELF_HEALING_REPORT_*` triple. Grouping on a bare `_REPORT_` token pooled
    them, so each self-healing run silently consumed a metrics retention slot.
    Every prior fixture put one prefix per directory, which is exactly why no
    test could see it — the bug deleted real committed reports twice before a
    fixture existed that could fail on it.
    """
    mod = _load_module()
    d = _make_metrics(tmp_path, _TIMESTAMPS)  # 5 METRICS runs
    # One self-healing run, timestamped mid-series so a pooled sort interleaves it.
    (d / "SELF_HEALING_REPORT_2026-03-15_00-00-00.md").write_text("md\n")
    (d / "SELF_HEALING_REPORT_2026-03-15_00-00-00.json").write_text("{}\n")

    mod.prune_all(tmp_path, keep=5, dry_run=False)

    # All 5 metrics runs survive: the self-healing run must not have taken a slot.
    assert len(list(d.glob("METRICS_REPORT_*.md"))) == 5
    # And the self-healing run survives on its own budget, not as a metrics leftover.
    assert (d / "SELF_HEALING_REPORT_2026-03-15_00-00-00.md").exists()
    assert (d / "SELF_HEALING_REPORT_2026-03-15_00-00-00.json").exists()


def test_canary_pooled_retention_would_evict_a_sibling_series(tmp_path: Path) -> None:
    """Proof the guard above bites: under a pooled marker, a metrics run dies.

    Reconstructs the historical defect directly rather than trusting the fixed
    code — `_report_runs` is called with the bare `_REPORT_` marker the buggy
    version used, and the oldest metrics run lands in the prune set.
    """
    mod = _load_module()
    d = _make_metrics(tmp_path, _TIMESTAMPS)  # 5 METRICS runs
    (d / "SELF_HEALING_REPORT_2026-03-15_00-00-00.md").write_text("md\n")

    # The historical grouping: any file *containing* `_REPORT_`, keyed by timestamp.
    pooled: set[str] = {
        ts
        for p in d.iterdir()
        if p.is_file() and "_REPORT_" in p.name and (ts := mod._timestamp_of(p.name))
    }
    scoped = mod._report_runs(d, "METRICS")

    assert len(pooled) == 6, "pooled grouping must see both series as one"
    assert len(scoped) == 5, "prefixed grouping must see only its own series"
    # With keep=5 the pooled set overflows by exactly one — the oldest metrics run,
    # which is the file the live defect deleted twice.
    assert sorted(pooled, reverse=True)[5:] == ["2026-01-01_00-00-00"]
    assert "2026-01-01_00-00-00" in scoped, "prefixed grouping keeps it inside budget"


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


def test_family_filter_prunes_only_named_family(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """--family scopes pruning to exactly the named family. Every other
    family -- including a sibling series sharing the same directory -- is
    left byte-identical to its pre-run state."""
    mod = _load_module()
    metrics_dir = _make_metrics(tmp_path, _TIMESTAMPS)  # 5 METRICS runs
    (metrics_dir / "SELF_HEALING_REPORT_2026-03-15_00-00-00.md").write_text("md\n")
    sentinel_dir = _make_sentinel(tmp_path, _TIMESTAMPS)  # 5 SENTINEL runs
    before_metrics_dir = _inventory(metrics_dir)

    code, _ = _run_cli(
        mod,
        capsys,
        [
            "--repo-root",
            str(tmp_path),
            "--keep",
            "1",
            "--family",
            ".ai-state/sentinel_reports:SENTINEL",
        ],
    )

    assert code == 0
    # The named family was pruned down to its keep budget.
    assert sorted(p.name for p in sentinel_dir.glob("SENTINEL_REPORT_*")) == [
        "SENTINEL_REPORT_2026-05-01_00-00-00.md",
    ]
    # Every file in the untouched sibling directory -- both the METRICS
    # series and the SELF_HEALING series it shares the directory with --
    # is byte-identical to before the run.
    assert _inventory(metrics_dir) == before_metrics_dir


def test_family_filter_may_repeat(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """--family may be passed multiple times to prune several named
    families in one invocation; a family never named stays untouched."""
    mod = _load_module()
    metrics_dir = _make_metrics(tmp_path, _TIMESTAMPS)  # 5 METRICS runs
    (metrics_dir / "SELF_HEALING_REPORT_2026-03-01_00-00-00.md").write_text("md\n")
    (metrics_dir / "SELF_HEALING_REPORT_2026-04-01_00-00-00.md").write_text("md\n")
    sentinel_dir = _make_sentinel(tmp_path, _TIMESTAMPS)  # 5 SENTINEL runs, never named

    code, _ = _run_cli(
        mod,
        capsys,
        [
            "--repo-root",
            str(tmp_path),
            "--keep",
            "1",
            "--family",
            ".ai-state/metrics_reports:METRICS",
            "--family",
            ".ai-state/metrics_reports:SELF_HEALING",
        ],
    )

    assert code == 0
    assert len(list(metrics_dir.glob("METRICS_REPORT_*.md"))) == 1
    assert len(list(metrics_dir.glob("SELF_HEALING_REPORT_*"))) == 1
    assert len(list(sentinel_dir.glob("SENTINEL_REPORT_*"))) == 5


def test_rejects_unknown_family_label(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """An unrecognized --family value is refused with a non-zero exit --
    never silently pruning nothing -- and the error names every known
    family label so the caller can self-correct."""
    mod = _load_module()
    known_labels = [f"{rel}:{prefix}" for rel, prefix in mod._REPORT_FAMILIES]

    with pytest.raises(SystemExit) as exc_info:
        mod._parse_args(["--repo-root", str(tmp_path), "--family", "bogus/dir:NOPE"])

    assert exc_info.value.code != 0
    stderr = capsys.readouterr().err
    assert "bogus/dir:NOPE" in stderr
    for label in known_labels:
        assert label in stderr


def test_absent_family_flag_prunes_all_families(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Omitting --family preserves today's behavior: every family is
    considered, unchanged from the pre-flag CLI contract."""
    mod = _load_module()
    metrics_dir = _make_metrics(tmp_path, _TIMESTAMPS)
    sentinel_dir = _make_sentinel(tmp_path, _TIMESTAMPS)

    code, _ = _run_cli(mod, capsys, ["--repo-root", str(tmp_path), "--keep", "1"])

    assert code == 0
    assert len(list(metrics_dir.glob("METRICS_REPORT_*.md"))) == 1
    assert len(list(sentinel_dir.glob("SENTINEL_REPORT_*"))) == 1


def test_family_filter_composes_with_dry_run(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """--family + --dry-run previews the scoped family's prune without
    deleting anything, in either the named family or any other."""
    mod = _load_module()
    sentinel_dir = _make_sentinel(tmp_path, _TIMESTAMPS)  # 5 runs
    metrics_dir = _make_metrics(tmp_path, _TIMESTAMPS)  # untouched sibling family

    code, _ = _run_cli(
        mod,
        capsys,
        [
            "--repo-root",
            str(tmp_path),
            "--keep",
            "1",
            "--dry-run",
            "--family",
            ".ai-state/sentinel_reports:SENTINEL",
        ],
    )

    assert code == 0
    assert len(list(sentinel_dir.glob("SENTINEL_REPORT_*"))) == 5
    # Untouched sibling family: 5 runs x (.md + .json) = 10 files, unchanged.
    assert len(list(metrics_dir.glob("METRICS_REPORT_*"))) == 10


def test_family_filter_composes_with_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """--family + --json reports a prune count scoped to the named family
    only; the sibling family's files stay on disk untouched."""
    mod = _load_module()
    sentinel_dir = _make_sentinel(tmp_path, _TIMESTAMPS)  # 5 runs, keep 1 -> 4 pruned
    metrics_dir = _make_metrics(tmp_path, _TIMESTAMPS)  # untouched sibling family

    code, out = _run_cli(
        mod,
        capsys,
        [
            "--repo-root",
            str(tmp_path),
            "--keep",
            "1",
            "--json",
            "--family",
            ".ai-state/sentinel_reports:SENTINEL",
        ],
    )

    assert code == 0
    result = json.loads(out)
    # If the filter were ignored, metrics (4) would inflate this total too.
    assert result["total_pruned"] == 4
    assert len(list(sentinel_dir.glob("SENTINEL_REPORT_*"))) == 1
    # Untouched sibling family: 5 runs x (.md + .json) = 10 files, unchanged.
    assert len(list(metrics_dir.glob("METRICS_REPORT_*"))) == 10
