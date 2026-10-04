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
# `--worktree` prints one report plus how the recording mode was found.
WORKTREE_JSON_KEYS = REPORT_KEYS | {"mode_source", "notes"}


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


def _bring_in(main: Path, name: str, *, record: tuple[int, ...] = ()) -> Path:
    """A worktree that commits, records `record` and is merged into main: one merge brings it in."""
    worktree = _add_worktree(main, name, commit=True)
    if record:
        _record(worktree, *record)
    _merge_into_main(main, name)
    return worktree


def _write_settings(main: Path, filename: str, content: object) -> None:
    directory = main / ".claude"
    directory.mkdir(exist_ok=True)
    text = content if isinstance(content, str) else json.dumps(content)
    (directory / filename).write_text(text)


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
    assert set(report) == WORKTREE_JSON_KEYS
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


def test_merged_picks_the_worktrees_this_merge_brings_in_that_hold_a_log(main: Path) -> None:
    merged = _add_worktree(main, "merged-wt", commit=True)
    _record(merged, 5)
    _add_worktree(main, "never-recorded", commit=True)
    _add_worktree(main, "unmerged-wt", commit=True)
    _record(main.parent / "unmerged-wt", 6)
    _git(main, "merge", "-q", "--no-edit", "merged-wt", "never-recorded")  # one octopus merge

    result = _run("--merged", "--json", "--repo-root", str(main), cwd=main)

    envelope = json.loads(result.stdout)
    assert result.returncode == 0, result.stderr
    assert set(envelope) == {"schema", "main", "mode", "mode_source", "notes", "worktrees", "error"}
    assert (envelope["main"], envelope["mode"], envelope["error"]) == (str(main), "standard", None)
    assert [w["worktree"] for w in envelope["worktrees"]] == [str(merged)]
    assert all(set(w) == REPORT_KEYS for w in envelope["worktrees"])
    assert _held(main) == [5]


def test_merged_never_copies_a_worktree_with_no_commit_of_its_own(main: Path) -> None:
    idle = _add_worktree(main, "idle-wt")
    _record(idle, 1)
    _bring_in(main, "other-wt")  # a merge, so ORIG_HEAD names the state before it

    result = _run("--merged", "--repo-root", str(main), cwd=main)

    assert (result.returncode, result.stdout) == (0, "")
    assert not reader.log_path(main / ".ai-state").exists()


def test_merged_never_copies_a_worktree_an_earlier_merge_already_brought_in(main: Path) -> None:
    worktree = _bring_in(main, "first-wt", record=(1,))
    _bring_in(main, "second-wt")  # now ORIG_HEAD already holds first-wt's commit
    _record(worktree, 2)

    result = _run("--merged", "--repo-root", str(main), cwd=main)

    assert (result.returncode, result.stdout) == (0, "")
    assert not reader.log_path(main / ".ai-state").exists()


def test_before_names_the_revision_the_merge_started_from(main: Path) -> None:
    before = _git(main, "rev-parse", "HEAD")
    _bring_in(main, "pipeline-wt", record=(1,))
    _bring_in(main, "later-wt")

    default = _run("--merged", "--repo-root", str(main), cwd=main)
    explicit = _run("--merged", "--before", before, "--repo-root", str(main), cwd=main)

    assert default.stdout == ""
    assert explicit.stdout == "merge-in pipeline-wt: copied 1, already held 0, malformed 0\n"


def test_merged_is_silent_when_nothing_happened(main: Path) -> None:
    _bring_in(main, "bare-wt")  # a merge with no log anywhere
    quiet_repository = _run("--merged", "--repo-root", str(main), cwd=main)
    worktree = _bring_in(main, "pipeline-wt", record=(1,))
    first = _run("--merged", "--repo-root", str(main), cwd=main)
    again = _run("--merged", "--repo-root", str(main), cwd=main)
    off = _run("--merged", "--repo-root", str(main), cwd=main, mode="off")

    assert worktree.is_dir()
    assert (quiet_repository.returncode, quiet_repository.stdout) == (0, "")
    assert first.stdout == "merge-in pipeline-wt: copied 1, already held 0, malformed 0\n"
    assert [(r.returncode, r.stdout) for r in (again, off)] == [(0, ""), (0, "")]


def test_merged_exits_one_when_any_worktree_it_brought_in_could_not_be_merged(main: Path) -> None:
    healthy = _add_worktree(main, "healthy-wt", commit=True)
    broken = _add_worktree(main, "broken-wt", commit=True)
    _record(healthy, 1)
    _record(broken, 2)
    retention.archive_path(reader.log_path(broken / ".ai-state"), 1).mkdir()
    _merge_into_main(main, "healthy-wt")
    _merge_into_main(main, "broken-wt")
    before = _git(main, "rev-parse", "HEAD~2")

    result = _run("--merged", "--before", before, "--json", "--repo-root", str(main), cwd=main)

    outcomes = {w["worktree"]: w["outcome"] for w in json.loads(result.stdout)["worktrees"]}
    assert result.returncode == 1
    assert outcomes == {str(healthy): "merged", str(broken): "degraded"}
    assert _held(main) == [1, 2]


def test_an_unresolvable_before_is_an_input_error_when_a_worktree_holds_a_log(
    main: Path,
) -> None:
    _bring_in(main, "pipeline-wt", record=(1,))

    result = _run("--merged", "--before", "no-such-rev", "--repo-root", str(main), cwd=main)

    assert result.returncode == 2
    assert "cannot resolve no-such-rev" in result.stderr
    assert result.stdout == ""


def test_the_default_boundary_is_orig_head_and_a_repository_without_one_is_an_input_error(
    main: Path,
) -> None:
    worktree = _add_worktree(main, "pipeline-wt", commit=True)
    _record(worktree, 1)
    _git(main, "merge", "-q", "--ff-only", "pipeline-wt")
    (main / ".git" / "ORIG_HEAD").unlink(missing_ok=True)

    result = _run("--merged", "--repo-root", str(main), cwd=main)

    assert result.returncode == 2
    assert "cannot resolve ORIG_HEAD" in result.stderr


def test_before_belongs_to_merged(main: Path) -> None:
    worktree = _add_worktree(main, "pipeline-wt")

    result = _run(
        "--worktree", str(worktree), "--before", "HEAD", "--repo-root", str(main), cwd=main
    )

    assert result.returncode == 2


# -- a worktree that cannot be read ------------------------------------------------------------


@pytest.mark.skipif(os.geteuid() == 0, reason="root reads any directory")
def test_an_unreadable_worktree_log_directory_degrades_that_worktree_and_the_others_still_merge(
    main: Path,
) -> None:
    unreadable = _add_worktree(main, "unreadable-wt", commit=True)
    readable = _add_worktree(main, "readable-wt", commit=True)
    _record(unreadable, 1)
    _record(readable, 2)
    _merge_into_main(main, "unreadable-wt")
    _merge_into_main(main, "readable-wt")
    before = _git(main, "rev-parse", "HEAD~2")
    (unreadable / ".ai-state").chmod(0o000)
    try:
        result = _run("--merged", "--before", before, "--json", "--repo-root", str(main), cwd=main)
        worktree_result = _run(
            "--worktree", str(unreadable), "--json", "--repo-root", str(main), cwd=main
        )
    finally:
        (unreadable / ".ai-state").chmod(0o755)

    reports = {w["worktree"]: w for w in json.loads(result.stdout)["worktrees"]}
    assert result.returncode == 1
    assert (reports[str(unreadable)]["outcome"], reports[str(readable)]["outcome"]) == (
        "degraded",
        "merged",
    )
    assert str(unreadable / ".ai-state") in reports[str(unreadable)]["reason"]
    assert _held(main) == [2]
    assert (worktree_result.returncode, json.loads(worktree_result.stdout)["outcome"]) == (
        1,
        "degraded",
    )


def test_a_row_with_an_escaped_lone_surrogate_never_aborts_the_run(main: Path) -> None:
    worktree = _add_worktree(main, "surrogate-wt", commit=True)
    (worktree / ".ai-state").mkdir()
    reader.log_path(worktree / ".ai-state").write_text(
        '{"event_type": "agent_start", "n": 1, "text": "half \\ud83d pair"}\n', encoding="utf-8"
    )
    _merge_into_main(main, "surrogate-wt")
    before = _git(main, "rev-parse", "HEAD~1")

    result = _run("--merged", "--before", before, "--repo-root", str(main), cwd=main)

    assert result.returncode == 0, result.stderr
    assert "copied 1" in result.stdout
    assert "Traceback" not in result.stderr


# -- the recording mode as the project sets it -------------------------------------------------


def test_the_process_environment_decides_the_mode_when_it_defines_one(main: Path) -> None:
    _write_settings(main, "settings.json", {"env": {"PRAXION_DISABLE_OBSERVABILITY": "1"}})
    worktree = _add_worktree(main, "pipeline-wt")
    _record(worktree, 1)

    result = _run("--worktree", str(worktree), "--json", "--repo-root", str(main), cwd=main)

    report = json.loads(result.stdout)
    assert (report["mode"], report["mode_source"], report["notes"]) == ("standard", "process", [])
    assert report["copied"] == 1


def test_a_project_that_set_the_mode_off_in_its_settings_copies_nothing(main: Path) -> None:
    _write_settings(main, "settings.json", {"env": {"PRAXION_DISABLE_OBSERVABILITY": "1"}})
    worktree = _add_worktree(main, "pipeline-wt")
    _record(worktree, 1)

    result = _run(
        "--worktree", str(worktree), "--json", "--repo-root", str(main), cwd=main, mode=None
    )

    report = json.loads(result.stdout)
    assert (report["mode"], report["mode_source"]) == ("off", ".claude/settings.json")
    assert (report["outcome"], report["copied"]) == ("recording-off", 0)
    assert not reader.log_path(main / ".ai-state").exists()


def test_the_local_settings_override_the_shared_ones_key_by_key(main: Path) -> None:
    _write_settings(main, "settings.json", {"env": {"PRAXION_OBSERVATION_LOG": "full"}})
    _write_settings(main, "settings.local.json", {"env": {"PRAXION_OBSERVATION_LOG": "off"}})
    _bring_in(main, "pipeline-wt", record=(1,))

    result = _run("--merged", "--json", "--repo-root", str(main), cwd=main, mode=None)

    envelope = json.loads(result.stdout)
    assert (envelope["mode"], envelope["mode_source"]) == ("off", ".claude/settings.local.json")
    assert envelope["worktrees"] == []  # recording is off: nothing worth saying
    assert not reader.log_path(main / ".ai-state").exists()


def test_a_key_only_the_shared_settings_define_still_applies(main: Path) -> None:
    _write_settings(main, "settings.json", {"env": {"PRAXION_OBSERVATION_LOG": "full"}})
    _write_settings(main, "settings.local.json", {"env": {"SOMETHING_ELSE": "1"}})
    worktree = _add_worktree(main, "pipeline-wt")

    report = json.loads(
        _run(
            "--worktree", str(worktree), "--json", "--repo-root", str(main), cwd=main, mode=None
        ).stdout
    )

    assert (report["mode"], report["mode_source"]) == ("full", ".claude/settings.json")


def test_without_a_mode_anywhere_the_mode_is_the_default(main: Path) -> None:
    worktree = _add_worktree(main, "pipeline-wt")

    report = json.loads(
        _run(
            "--worktree", str(worktree), "--json", "--repo-root", str(main), cwd=main, mode=None
        ).stdout
    )

    assert (report["mode"], report["mode_source"], report["notes"]) == ("standard", "default", [])


@pytest.mark.parametrize(
    "content",
    ["{not json", "[1, 2]", '{"env": "nope"}'],
    ids=["invalid-json", "not-an-object", "env-not-an-object"],
)
def test_a_settings_file_that_cannot_be_used_is_skipped_and_named(main: Path, content: str) -> None:
    _write_settings(main, "settings.json", content)
    worktree = _add_worktree(main, "pipeline-wt")
    _record(worktree, 1)

    result = _run(
        "--worktree", str(worktree), "--json", "--repo-root", str(main), cwd=main, mode=None
    )

    report = json.loads(result.stdout)
    assert result.returncode == 0, result.stderr
    assert (report["mode"], report["mode_source"], report["copied"]) == ("standard", "default", 1)
    assert len(report["notes"]) == 1
    assert ".claude/settings.json" in report["notes"][0]


def test_the_human_form_names_a_settings_file_that_could_not_be_used(main: Path) -> None:
    _write_settings(main, "settings.json", "{not json")
    worktree = _add_worktree(main, "pipeline-wt")

    result = _run("--worktree", str(worktree), "--repo-root", str(main), cwd=main, mode=None)

    assert result.returncode == 0
    assert ".claude/settings.json" in result.stderr


# -- the command text names where the script is ------------------------------------------------

COMMAND = Path(__file__).resolve().parent.parent / "commands" / "merge-worktree.md"


def _step_9_5() -> str:
    text = COMMAND.read_text()
    return text[text.index("9.5.") : text.index("\n10.")]


def test_step_nine_five_looks_for_the_script_in_the_plugin_then_on_path_then_the_checkout() -> None:
    step = _step_9_5()

    positions = [
        step.index("$CLAUDE_PLUGIN_ROOT/scripts/merge_worktree_log.py"),
        step.index("command -v merge_worktree_log.py"),
        step.index("scripts/merge_worktree_log.py", step.index("command -v")),
    ]
    assert positions == sorted(positions)


def test_step_nine_five_treats_a_missing_script_as_neither_success_nor_an_input_error() -> None:
    step = _step_9_5()

    none_exists = step.index("When **none** of the three exists")
    not_installed = step.index("not installed", none_exists)
    keep = step.index("do **not** remove the worktree", not_installed)
    assert none_exists < not_installed < keep, (
        "the missing-tool clause must follow the three lookups, in order"
    )
    assert "loses the rows" in step[keep:] or "losing the rows" in step[keep:]


def test_step_nine_five_never_runs_a_project_relative_script_unlooked_for() -> None:
    assert "python3 scripts/merge_worktree_log.py" not in _step_9_5()


def test_merged_says_nothing_about_an_unusable_settings_file_when_nothing_happened(
    main: Path,
) -> None:
    _write_settings(main, "settings.json", "{not json")
    _bring_in(main, "bare-wt")  # a merge with no log anywhere

    result = _run("--merged", "--repo-root", str(main), cwd=main, mode=None)

    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")
