"""Tests for merge_driver_observations.py's graceful-degradation contract and
its dispatch onto the committed observations_summary.jsonl merge.

Run: ``python3 scripts/test_merge_driver_observations.py`` or ``pytest``.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import merge_driver_observations as mdo  # noqa: E402


def _summary_row(session_id: str, started_at: str, ended_at: str) -> str:
    return json.dumps({"session_id": session_id, "started_at": started_at, "ended_at": ended_at})


def test_main_exits_cleanly_when_ours_path_absent(tmp_path, capsys):
    """git never invokes this driver on the raw WAL once it leaves tracking
    (merge drivers apply only to tracked, conflicted paths). Still, a caller
    pointing it at a fresh-clone-shaped absent path must fail loud-but-clean
    -- exit 1 with a message on stderr, never a traceback."""
    ours = tmp_path / "observations.jsonl"  # never created
    theirs = tmp_path / "observations.jsonl.theirs"
    theirs.write_text("", encoding="utf-8")
    ancestor = tmp_path / "observations.jsonl.base"
    ancestor.write_text("", encoding="utf-8")

    # main() reads argv directly, the way git invokes a merge driver.
    original_argv = sys.argv
    try:
        sys.argv = [
            "merge_driver_observations.py",
            str(ancestor),
            str(ours),
            str(theirs),
        ]
        exit_code = mdo.main()
    finally:
        sys.argv = original_argv

    err = capsys.readouterr().err
    assert exit_code == 1
    assert "Cannot read input files" in err


def _run_driver(ancestor: Path, ours: Path, theirs: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT_DIR / "merge_driver_observations.py"),
            str(ancestor),
            str(ours),
            str(theirs),
        ],
        capture_output=True,
        text=True,
    )


def test_two_branches_appending_distinct_sessions_union_with_no_conflict_markers(tmp_path):
    """Each branch appended a session the other never saw -- the merge must
    keep both, and the output must never contain conflict-marker text."""
    ancestor = tmp_path / "base.jsonl"
    ancestor.write_text("", encoding="utf-8")
    ours = tmp_path / "ours.jsonl"
    ours.write_text(_summary_row("s1", "2026-01-01T00:00:00Z", "2026-01-01T00:05:00Z") + "\n")
    theirs = tmp_path / "theirs.jsonl"
    theirs.write_text(_summary_row("s2", "2026-01-02T00:00:00Z", "2026-01-02T00:05:00Z") + "\n")

    result = _run_driver(ancestor, ours, theirs)

    assert result.returncode == 0, result.stderr
    merged_text = ours.read_text(encoding="utf-8")
    assert "<<<<<<<" not in merged_text
    rows = [json.loads(line) for line in merged_text.strip().splitlines()]
    assert sorted(r["session_id"] for r in rows) == ["s1", "s2"]


def test_same_session_id_updated_on_both_sides_later_ended_at_wins(tmp_path):
    """Both branches Stop-wrote a rollup for the same session; the fresher
    (later `ended_at`) rollup must be the one that survives, as a single row."""
    ancestor = tmp_path / "base.jsonl"
    ancestor.write_text(_summary_row("s1", "2026-01-01T00:00:00Z", "2026-01-01T00:05:00Z") + "\n")
    ours = tmp_path / "ours.jsonl"
    ours.write_text(_summary_row("s1", "2026-01-01T00:00:00Z", "2026-01-01T00:05:00Z") + "\n")
    theirs = tmp_path / "theirs.jsonl"
    theirs.write_text(_summary_row("s1", "2026-01-01T00:00:00Z", "2026-01-01T00:10:00Z") + "\n")

    result = _run_driver(ancestor, ours, theirs)

    assert result.returncode == 0, result.stderr
    rows = [json.loads(line) for line in ours.read_text(encoding="utf-8").strip().splitlines()]
    assert len(rows) == 1
    assert rows[0]["ended_at"] == "2026-01-01T00:10:00Z"


def test_output_ordering_is_stable_by_started_at_then_session_id(tmp_path):
    ancestor = tmp_path / "base.jsonl"
    ancestor.write_text("", encoding="utf-8")
    ours = tmp_path / "ours.jsonl"
    ours.write_text(
        _summary_row("sZ", "2026-01-01T00:00:00Z", "2026-01-01T00:05:00Z")
        + "\n"
        + _summary_row("sA", "2026-01-02T00:00:00Z", "2026-01-02T00:05:00Z")
        + "\n"
    )
    theirs = tmp_path / "theirs.jsonl"
    theirs.write_text(_summary_row("sB", "2026-01-01T00:00:00Z", "2026-01-01T00:06:00Z") + "\n")

    result = _run_driver(ancestor, ours, theirs)

    assert result.returncode == 0, result.stderr
    rows = [json.loads(line) for line in ours.read_text(encoding="utf-8").strip().splitlines()]
    # started_at ties (sZ, sB) break by session_id; sA's later started_at sorts last.
    assert [r["session_id"] for r in rows] == ["sB", "sZ", "sA"]


def test_end_to_end_via_subprocess_with_three_temp_files_exits_zero(tmp_path):
    """The exact invocation shape git uses: `%O %A %B` as three positional
    paths, result written to %A (ours), exit 0."""
    ancestor = tmp_path / "ancestor.jsonl"
    ancestor.write_text(_summary_row("s1", "2026-01-01T00:00:00Z", "2026-01-01T00:05:00Z") + "\n")
    ours = tmp_path / "ours.jsonl"
    ours.write_text(_summary_row("s1", "2026-01-01T00:00:00Z", "2026-01-01T00:05:00Z") + "\n")
    theirs = tmp_path / "theirs.jsonl"
    theirs.write_text(
        _summary_row("s1", "2026-01-01T00:00:00Z", "2026-01-01T00:05:00Z")
        + "\n"
        + _summary_row("s2", "2026-01-03T00:00:00Z", "2026-01-03T00:05:00Z")
        + "\n"
    )

    result = _run_driver(ancestor, ours, theirs)

    assert result.returncode == 0, result.stderr
    rows = [json.loads(line) for line in ours.read_text(encoding="utf-8").strip().splitlines()]
    assert sorted(r["session_id"] for r in rows) == ["s1", "s2"]


def test_real_git_merge_of_two_branches_resolves_without_conflict(tmp_path):
    """A real `git merge` through a registered `.gitattributes` + driver --
    the fixture the two unit-level tests above stand in for, proven once end
    to end against actual git plumbing."""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.t"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True)
    subprocess.run(
        [
            "git",
            "config",
            "merge.observations-jsonl.driver",
            f"{sys.executable} {SCRIPT_DIR / 'merge_driver_observations.py'} %O %A %B",
        ],
        cwd=repo,
        check=True,
    )
    (repo / ".gitattributes").write_text(
        ".ai-state/observations_summary.jsonl merge=observations-jsonl\n"
    )
    ai_state = repo / ".ai-state"
    ai_state.mkdir()
    summary = ai_state / "observations_summary.jsonl"
    summary.write_text(_summary_row("s1", "2026-01-01T00:00:00Z", "2026-01-01T00:05:00Z") + "\n")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "seed"], cwd=repo, check=True)

    subprocess.run(["git", "checkout", "-q", "-b", "feature"], cwd=repo, check=True)
    summary.write_text(_summary_row("s2", "2026-01-02T00:00:00Z", "2026-01-02T00:05:00Z") + "\n")
    subprocess.run(["git", "commit", "-q", "-am", "feature: add s2"], cwd=repo, check=True)

    subprocess.run(["git", "checkout", "-q", "main"], cwd=repo, check=True)
    summary.write_text(
        _summary_row("s1", "2026-01-01T00:00:00Z", "2026-01-01T00:05:00Z")
        + "\n"
        + _summary_row("s3", "2026-01-03T00:00:00Z", "2026-01-03T00:05:00Z")
        + "\n"
    )
    subprocess.run(["git", "commit", "-q", "-am", "main: add s3"], cwd=repo, check=True)

    result = subprocess.run(
        ["git", "merge", "-q", "--no-edit", "feature"],
        cwd=repo,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
    merged_text = summary.read_text(encoding="utf-8")
    assert "<<<<<<<" not in merged_text
    rows = [json.loads(line) for line in merged_text.strip().splitlines()]
    assert sorted(r["session_id"] for r in rows) == ["s1", "s2", "s3"]


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
