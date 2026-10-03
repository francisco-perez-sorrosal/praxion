"""Tests for merge_worktree_log.py -- the one command that copies a worktree's log into the main log.

The merge itself is tested in `hooks/test_observation_log_merge_in.py`; these pin what the
command adds: the argument and exit-code contract, the JSON shapes, and which worktrees
`--merged` picks. Every scenario runs the CLI as a subprocess over a real repository with
real linked worktrees, the way `/merge-worktree` and the post-merge hook run it.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from hooks._observation_log import reader, retention

SCRIPT = Path(__file__).resolve().parent / "merge_worktree_log.py"
REPORT_KEYS = {
    "schema",
    "main",
    "worktree",
    "mode",
    "outcome",
    "copied",
    "skipped",
    "malformed",
    "unreadable",
    "reason",
}


def _git(cwd: Path, *args: str) -> str:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    result = subprocess.run(
        ["git", "-C", str(cwd), "-c", "user.name=t", "-c", "user.email=t@t", *args],
        capture_output=True,
        text=True,
        check=True,
        env=env,
    )
    return result.stdout.strip()


def _new_repository(root: Path) -> Path:
    root.mkdir(parents=True)
    _git(root, "init", "-q", "-b", "main")
    _git(root, "commit", "-q", "--allow-empty", "-m", "initial")
    return root.resolve()


def _add_worktree(main: Path, name: str, *, commit: bool = False) -> Path:
    location = main.parent / name
    _git(main, "worktree", "add", "-q", "-b", name, str(location))
    if commit:
        _git(location, "commit", "-q", "--allow-empty", "-m", f"work in {name}")
    return location.resolve()


def _merge_into_main(main: Path, branch: str) -> None:
    _git(main, "merge", "-q", "--no-ff", "--no-edit", branch)


def _record(checkout: Path, *numbers: int) -> None:
    """Append one row per number to the checkout's active log."""
    state = checkout / ".ai-state"
    state.mkdir(exist_ok=True)
    lines = [
        json.dumps({"event_type": "agent_start", "timestamp": f"2026-10-0{n}T00:00:00Z", "n": n})
        for n in numbers
    ]
    with reader.log_path(state).open("a", encoding="utf-8") as log:
        log.write("".join(line + "\n" for line in lines))


def _held(checkout: Path) -> list[int]:
    return sorted(row["n"] for row in reader.read_rows(checkout / ".ai-state", archives=True))


def _run(*args: str, cwd: Path, mode: str | None = "standard"):
    env = {k: v for k, v in os.environ.items() if not k.startswith(("CLAUDE", "PRAXION_", "GIT_"))}
    if mode is not None:
        env["PRAXION_OBSERVATION_LOG"] = mode
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args], capture_output=True, text=True, cwd=cwd, env=env
    )


@pytest.fixture
def main(tmp_path: Path) -> Path:
    return _new_repository(tmp_path / "project")


# -- the argument and exit-code contract -------------------------------------------------------


@pytest.mark.parametrize("arguments", [[], ["--merged", "--worktree", "somewhere"]])
def test_naming_neither_or_both_modes_is_an_input_error(main: Path, arguments: list[str]) -> None:
    result = _run(*arguments, "--repo-root", str(main), cwd=main)

    assert result.returncode == 2
    assert result.stdout == ""


def test_a_directory_that_is_not_a_repository_is_an_input_error(tmp_path: Path) -> None:
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()

    result = _run("--merged", "--json", "--repo-root", str(elsewhere), cwd=tmp_path)

    assert result.returncode == 2
    assert json.loads(result.stdout)["error"], result.stdout


@pytest.mark.parametrize("target", ["main", "stranger"])
def test_a_path_that_is_no_linked_worktree_of_the_repository_is_an_input_error(
    main: Path, tmp_path: Path, target: str
) -> None:
    stranger = _new_repository(tmp_path / "stranger-repo")
    chosen = main if target == "main" else stranger

    result = _run("--worktree", str(chosen), "--repo-root", str(main), cwd=main)

    assert result.returncode == 2
    assert "not a worktree of this repository" in result.stderr


def test_a_plugin_cache_root_is_refused(tmp_path: Path) -> None:
    cached = _new_repository(tmp_path / "plugins" / "cache" / "owner" / "praxion" / "1.0.0")

    result = _run("--merged", "--repo-root", str(cached), cwd=tmp_path)

    assert result.returncode == 2
    assert "plugin-cache" in result.stderr


def test_the_repository_root_defaults_to_the_one_the_working_directory_is_in(main: Path) -> None:
    worktree = _add_worktree(main, "pipeline-wt")
    _record(worktree, 1)

    result = _run("--worktree", str(worktree), "--json", cwd=main)

    assert (result.returncode, json.loads(result.stdout)["copied"]) == (0, 1)


def test_the_repository_root_may_name_a_linked_worktree(main: Path) -> None:
    worktree = _add_worktree(main, "pipeline-wt")
    _record(worktree, 1)

    result = _run("--worktree", str(worktree), "--json", "--repo-root", str(worktree), cwd=main)

    assert json.loads(result.stdout)["main"] == str(main)
    assert _held(main) == [1]


# -- one worktree ------------------------------------------------------------------------------


def test_the_json_report_for_one_worktree_has_the_documented_shape(main: Path) -> None:
    worktree = _add_worktree(main, "pipeline-wt")
    _record(main, 1)
    _record(worktree, 1, 2, 3)

    result = _run("--worktree", str(worktree), "--json", "--repo-root", str(main), cwd=main)

    report = json.loads(result.stdout)
    assert result.returncode == 0, result.stderr
    assert set(report) == REPORT_KEYS
    assert (report["schema"], report["main"], report["worktree"]) == (1, str(main), str(worktree))
    assert (report["mode"], report["outcome"]) == ("standard", "merged")
    assert (report["copied"], report["skipped"], report["malformed"]) == (2, 1, 0)
    assert (report["unreadable"], report["reason"]) == ([], None)
    assert _held(main) == [1, 2, 3]


def test_the_human_form_names_the_worktree_and_its_counts(main: Path) -> None:
    worktree = _add_worktree(main, "pipeline-wt")
    _record(main, 1)
    _record(worktree, 1, 2)

    result = _run("--worktree", str(worktree), "--repo-root", str(main), cwd=main)

    assert result.stdout == "merge-in pipeline-wt: copied 1, already held 1, malformed 0\n"


def test_a_worktree_with_no_log_exits_zero_and_says_so(main: Path) -> None:
    worktree = _add_worktree(main, "pipeline-wt")

    result = _run("--worktree", str(worktree), "--repo-root", str(main), cwd=main)

    assert (result.returncode, result.stdout) == (0, "merge-in pipeline-wt: no log to merge\n")


def test_under_the_off_mode_the_command_says_recording_is_off_and_copies_nothing(
    main: Path,
) -> None:
    worktree = _add_worktree(main, "pipeline-wt")
    _record(worktree, 1)

    result = _run("--worktree", str(worktree), "--repo-root", str(main), cwd=main, mode="off")

    assert result.returncode == 0
    assert result.stdout == "merge-in pipeline-wt: recording is off (mode off); nothing merged\n"
    assert not reader.log_path(main / ".ai-state").exists()


def test_an_unreadable_segment_exits_one_with_the_reason_and_the_rows_that_could_be_copied(
    main: Path,
) -> None:
    worktree = _add_worktree(main, "pipeline-wt")
    _record(worktree, 1)
    archive = retention.archive_path(reader.log_path(worktree / ".ai-state"), 1)
    archive.mkdir()

    result = _run("--worktree", str(worktree), "--json", "--repo-root", str(main), cwd=main)

    report = json.loads(result.stdout)
    assert result.returncode == 1
    assert (report["outcome"], report["copied"]) == ("degraded", 1)
    assert report["unreadable"] == [str(archive)]
    assert str(archive) in report["reason"]


def test_the_human_form_prints_the_reason_on_its_own_line_when_degraded(main: Path) -> None:
    worktree = _add_worktree(main, "pipeline-wt")
    _record(worktree, 1)
    retention.archive_path(reader.log_path(worktree / ".ai-state"), 1).mkdir()

    result = _run("--worktree", str(worktree), "--repo-root", str(main), cwd=main)

    first, second = result.stdout.splitlines()
    assert first == "merge-in pipeline-wt: copied 1, already held 0, malformed 0"
    assert second.startswith("reason: ")


# -- every contained worktree ------------------------------------------------------------------


def test_merged_picks_the_worktrees_the_main_head_contains_and_that_hold_a_log(
    main: Path,
) -> None:
    merged = _add_worktree(main, "merged-wt", commit=True)
    _add_worktree(main, "unmerged-wt", commit=True)
    _add_worktree(main, "never-recorded")
    for name in ("merged-wt", "unmerged-wt"):
        _record(main.parent / name, 5)
    _merge_into_main(main, "merged-wt")

    result = _run("--merged", "--json", "--repo-root", str(main), cwd=main)

    envelope = json.loads(result.stdout)
    assert result.returncode == 0, result.stderr
    assert set(envelope) == {"schema", "main", "mode", "worktrees", "error"}
    assert (envelope["main"], envelope["mode"], envelope["error"]) == (str(main), "standard", None)
    assert [w["worktree"] for w in envelope["worktrees"]] == [str(merged)]
    assert all(set(w) == REPORT_KEYS for w in envelope["worktrees"])
    assert _held(main) == [5]


def test_merged_is_silent_when_nothing_happened(main: Path) -> None:
    quiet_repository = _run("--merged", "--repo-root", str(main), cwd=main)
    worktree = _add_worktree(main, "pipeline-wt")
    _record(worktree, 1)
    first = _run("--merged", "--repo-root", str(main), cwd=main)
    again = _run("--merged", "--repo-root", str(main), cwd=main)
    off = _run("--merged", "--repo-root", str(main), cwd=main, mode="off")

    assert (quiet_repository.returncode, quiet_repository.stdout) == (0, "")
    assert first.stdout == "merge-in pipeline-wt: copied 1, already held 0, malformed 0\n"
    assert [(r.returncode, r.stdout) for r in (again, off)] == [(0, ""), (0, "")]


def test_merged_exits_one_when_any_contained_worktree_could_not_be_merged(main: Path) -> None:
    healthy = _add_worktree(main, "healthy-wt")
    broken = _add_worktree(main, "broken-wt")
    _record(healthy, 1)
    _record(broken, 2)
    retention.archive_path(reader.log_path(broken / ".ai-state"), 1).mkdir()

    result = _run("--merged", "--json", "--repo-root", str(main), cwd=main)

    outcomes = {w["worktree"]: w["outcome"] for w in json.loads(result.stdout)["worktrees"]}
    assert result.returncode == 1
    assert outcomes == {str(healthy): "merged", str(broken): "degraded"}
    assert _held(main) == [1, 2]
