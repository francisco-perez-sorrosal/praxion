"""Tests for the decision-record gate judging a commit from a PreToolUse Bash payload.

Every case builds a throwaway git repository under ``tmp_path`` and feeds ``main`` a real payload
on stdin with ``PRAXION_COMMIT_PAYLOAD=1``, the way ``hooks/commit_gate.sh`` does. The hook fires
before any command of the Bash call runs, so the same-call cases leave the repository in the state
the hook would see: the file on disk, the ``git add`` not yet run. A file the same call creates or
rewrites is therefore not modelled: it is not on disk when the hook fires.
"""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import check_decision_records as cli  # noqa: E402
from test_check_decision_records import (  # noqa: E402
    DRAFT,
    GOOD_DRAFT,
    GOOD_NUMBERED,
    NUMBERED,
    commit_all,
    git,
    make_repo,
    put,
    record,
    stale_local_main_clone,
)

SECOND_NUMBERED = ".ai-state/decisions/008-adopt-duckdb.md"
COMMIT = 'git commit -m "add a record"'
HEREDOC_COMMIT = "git commit -m \"$(cat <<'EOF'\nadd a record\nEOF\n)\""
NO_CATEGORY_DRAFT = record(category=None)


@pytest.fixture
def feature(tmp_path: Path) -> Path:
    repo = make_repo(tmp_path)
    git(repo, "checkout", "-q", "-b", "feature")
    return repo


def payload(repo: Path, command: str) -> str:
    return json.dumps({"tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(repo)})


def judge(raw: str, monkeypatch, capsys) -> tuple[int, str, str]:
    monkeypatch.setenv("PRAXION_COMMIT_PAYLOAD", "1")
    monkeypatch.setattr(sys, "stdin", io.StringIO(raw))
    code = cli.main([])
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def judge_commit(repo: Path, command: str, monkeypatch, capsys) -> tuple[int, str, str]:
    return judge(payload(repo, command), monkeypatch, capsys)


def stage(repo: Path, rel: str, text: str) -> None:
    put(repo, rel, text)
    git(repo, "add", rel)


# -- Clean commits print nothing ----------------------------------------------------------


def test_a_staged_conforming_draft_commits_in_silence(feature, monkeypatch, capsys):
    stage(feature, DRAFT, GOOD_DRAFT)
    assert judge_commit(feature, COMMIT, monkeypatch, capsys) == (0, "", "")


def test_a_commit_that_stages_no_record_commits_in_silence(feature, monkeypatch, capsys):
    stage(feature, "docs/notes.md", "no frontmatter\n")
    assert judge_commit(feature, COMMIT, monkeypatch, capsys) == (0, "", "")


@pytest.mark.parametrize("branch", ["main", "master"])
def test_a_promotion_on_the_default_branch_commits_in_silence(
    tmp_path, monkeypatch, capsys, branch
):
    repo = make_repo(tmp_path, branch=branch)
    stage(repo, NUMBERED, GOOD_NUMBERED)
    assert judge_commit(repo, COMMIT, monkeypatch, capsys) == (0, "", "")


def test_a_merge_bringing_in_a_numbered_record_the_default_branch_holds_commits_in_silence(
    tmp_path, monkeypatch, capsys
):
    repo = make_repo(tmp_path)
    git(repo, "checkout", "-q", "-b", "feature")
    git(repo, "checkout", "-q", "main")
    put(repo, NUMBERED, GOOD_NUMBERED)
    commit_all(repo, "promoted on main")
    git(repo, "checkout", "-q", "feature")
    put(repo, "feature.txt", "work\n")
    commit_all(repo, "feature work")
    git(repo, "merge", "--no-commit", "--no-ff", "-q", "main")
    assert (repo / NUMBERED).exists()
    assert judge_commit(repo, "git commit --no-edit", monkeypatch, capsys) == (0, "", "")


@pytest.mark.parametrize("default", ["main", "master"])
def test_a_merge_of_the_remote_default_while_the_local_default_lags_commits_in_silence(
    tmp_path, monkeypatch, capsys, default
):
    clone = stale_local_main_clone(tmp_path, default)
    git(clone, "merge", "--no-commit", "--no-ff", "-q", f"origin/{default}")
    assert (clone / NUMBERED).exists()
    assert judge_commit(clone, "git commit --no-edit", monkeypatch, capsys) == (0, "", "")


def test_a_numbered_record_no_default_branch_holds_is_refused_beside_a_remote(
    tmp_path, monkeypatch, capsys
):
    clone = stale_local_main_clone(tmp_path)
    stage(clone, SECOND_NUMBERED, record("dec-008"))
    code, _, err = judge_commit(clone, COMMIT, monkeypatch, capsys)
    assert code == 1
    assert SECOND_NUMBERED in err


# -- A command that is no commit ----------------------------------------------------------


@pytest.mark.parametrize(
    "command",
    [
        "git status",
        "git log --grep commit",
        "echo 'git commit'",
        "git add -A",
        "ls && git diff",
        "git commit-graph write",
        "git -c user.name=x log commit",
        "git diff --stat commit",
    ],
)
def test_a_command_that_is_not_a_git_commit_exits_silently_even_over_a_bad_stage(
    feature, monkeypatch, capsys, command
):
    stage(feature, NUMBERED, GOOD_NUMBERED)
    assert judge_commit(feature, command, monkeypatch, capsys) == (0, "", "")


@pytest.mark.parametrize("raw", ["{}", '{"tool_input": {}}', '{"tool_input": "git commit"}', "[]"])
def test_a_payload_naming_no_command_exits_silently(raw, monkeypatch, capsys):
    assert judge(raw, monkeypatch, capsys) == (0, "", "")


# -- Refused commits ----------------------------------------------------------------------


def test_a_staged_numbered_record_on_a_feature_branch_is_refused(feature, monkeypatch, capsys):
    stage(feature, NUMBERED, GOOD_NUMBERED)
    code, out, err = judge_commit(feature, COMMIT, monkeypatch, capsys)
    assert (code, out) == (1, "")
    assert "Commit refused" in err
    assert NUMBERED in err


def test_each_offending_path_is_named_once(feature, monkeypatch, capsys):
    stage(feature, NUMBERED, GOOD_NUMBERED)
    stage(feature, SECOND_NUMBERED, record("dec-008"))
    _, _, err = judge_commit(feature, COMMIT, monkeypatch, capsys)
    assert err.count(NUMBERED) == 1
    assert err.count(SECOND_NUMBERED) == 1


def test_a_draft_with_no_category_is_refused(feature, monkeypatch, capsys):
    stage(feature, DRAFT, NO_CATEGORY_DRAFT)
    code, _, err = judge_commit(feature, COMMIT, monkeypatch, capsys)
    assert code == 1
    assert DRAFT in err


def test_a_commit_whose_message_is_a_heredoc_is_judged(feature, monkeypatch, capsys):
    stage(feature, NUMBERED, GOOD_NUMBERED)
    assert judge_commit(feature, HEREDOC_COMMIT, monkeypatch, capsys)[0] == 1


@pytest.mark.parametrize(
    "command",
    [
        f"git add . && {COMMIT}",
        f"cd . && {COMMIT}",
        f"FOO=1 {COMMIT}",
        f"git add -A; {COMMIT}",
        f"true || {COMMIT}",
    ],
)
def test_a_commit_anywhere_in_a_compound_command_is_judged(feature, monkeypatch, capsys, command):
    stage(feature, NUMBERED, GOOD_NUMBERED)
    assert judge_commit(feature, command, monkeypatch, capsys)[0] == 1


@pytest.mark.parametrize(
    "command",
    [
        'git -c user.name=x commit -m "m"',
        'git -c "user.name=A B" commit -m "m"',
        'git -C . commit -m "m"',
        'git --git-dir .git commit -m "m"',
        'git --git-dir=.git --work-tree=. commit -m "m"',
        'git --no-pager commit -m "m"',
        '(git commit -m "m")',
        'if ! git commit -m "m"; then echo failed; fi',
        'command git commit -m "m"',
        'time git commit -m "m"',
        'nohup git commit -m "m"',
        '/usr/bin/git commit -m "m"',
        'FOO=1 BAR="a" git -c x.y=z commit -m "m"',
    ],
)
def test_a_commit_spelled_with_global_options_or_a_wrapper_is_judged(
    feature, monkeypatch, capsys, command
):
    stage(feature, NUMBERED, GOOD_NUMBERED)
    code, _, err = judge_commit(feature, command, monkeypatch, capsys)
    assert code == 1
    assert NUMBERED in err


# -- The stale-index trap: what the same call will stage ----------------------------------


def test_an_untracked_record_a_same_call_add_all_will_stage_is_refused(
    feature, monkeypatch, capsys
):
    put(feature, NUMBERED, GOOD_NUMBERED)
    code, _, err = judge_commit(feature, f"git add -A && {COMMIT}", monkeypatch, capsys)
    assert code == 1
    assert NUMBERED in err


def test_an_untracked_record_a_same_call_add_of_its_path_will_stage_is_refused(
    feature, monkeypatch, capsys
):
    put(feature, NUMBERED, GOOD_NUMBERED)
    code, _, err = judge_commit(feature, f"git add {NUMBERED} && {COMMIT}", monkeypatch, capsys)
    assert code == 1
    assert NUMBERED in err


def test_an_untracked_record_no_add_stages_is_not_judged(feature, monkeypatch, capsys):
    put(feature, NUMBERED, GOOD_NUMBERED)
    assert judge_commit(feature, COMMIT, monkeypatch, capsys) == (0, "", "")


def test_a_record_a_same_call_add_stages_over_a_conforming_index_blob_is_refused(
    feature, monkeypatch, capsys
):
    stage(feature, DRAFT, GOOD_DRAFT)
    put(feature, DRAFT, NO_CATEGORY_DRAFT)
    code, _, err = judge_commit(feature, f"git add {DRAFT} && {COMMIT}", monkeypatch, capsys)
    assert code == 1
    assert DRAFT in err


def test_a_conforming_working_tree_a_same_call_add_stages_over_a_bad_index_blob_is_clean(
    feature, monkeypatch, capsys
):
    stage(feature, DRAFT, NO_CATEGORY_DRAFT)
    put(feature, DRAFT, GOOD_DRAFT)
    command = f"git add {DRAFT} && {COMMIT}"
    assert judge_commit(feature, command, monkeypatch, capsys) == (0, "", "")


def test_a_working_tree_edit_nothing_stages_leaves_the_index_blob_as_the_judged_text(
    feature, monkeypatch, capsys
):
    stage(feature, DRAFT, GOOD_DRAFT)
    put(feature, DRAFT, NO_CATEGORY_DRAFT)
    assert judge_commit(feature, COMMIT, monkeypatch, capsys) == (0, "", "")


def test_a_commit_all_judges_the_tracked_working_tree_edit(feature, monkeypatch, capsys):
    put(feature, DRAFT, GOOD_DRAFT)
    commit_all(feature, "a good draft")
    put(feature, DRAFT, NO_CATEGORY_DRAFT)
    code, _, err = judge_commit(feature, 'git commit -am "edit"', monkeypatch, capsys)
    assert code == 1
    assert DRAFT in err


# -- Declared limits ----------------------------------------------------------------------


def test_a_commit_naming_a_pathspec_is_still_judged_by_the_staged_set(feature, monkeypatch, capsys):
    # `git commit -- <paths>` records those paths' working-tree text and ignores the rest of the
    # index; the gate does not read the pathspec, so another path's staged blob decides.
    stage(feature, NUMBERED, GOOD_NUMBERED)
    put(feature, "docs/notes.md", "notes\n")
    code, _, err = judge_commit(feature, "git commit -m m -- docs/notes.md", monkeypatch, capsys)
    assert code == 1
    assert NUMBERED in err


def test_an_add_update_does_not_bring_a_tracked_edit_into_the_judged_set(
    feature, monkeypatch, capsys
):
    # `git add -u` stages tracked edits, but names no pathspec, so the scope adds nothing for it.
    put(feature, DRAFT, GOOD_DRAFT)
    commit_all(feature, "a good draft")
    put(feature, DRAFT, NO_CATEGORY_DRAFT)
    command = f"git add -u && {COMMIT}"
    assert judge_commit(feature, command, monkeypatch, capsys) == (0, "", "")


# -- Doubts pass --------------------------------------------------------------------------


def test_an_unreadable_payload_passes_with_a_note(monkeypatch, capsys):
    code, out, err = judge("not json at all", monkeypatch, capsys)
    assert (code, out) == (0, "")
    assert err == "check_decision_records: the hook payload is unreadable; passing.\n"


def test_a_payload_naming_a_directory_that_is_no_repository_passes_with_a_note(
    tmp_path, monkeypatch, capsys
):
    elsewhere = tmp_path / "plain"
    elsewhere.mkdir()
    code, out, err = judge_commit(elsewhere, COMMIT, monkeypatch, capsys)
    assert (code, out) == (0, "")
    assert err == "check_decision_records: the commit scope is unavailable; passing.\n"


def test_a_repository_inside_a_plugin_cache_passes_with_a_note(tmp_path, monkeypatch, capsys):
    parent = tmp_path / "home" / "plugins" / "cache"
    parent.mkdir(parents=True)
    cached = make_repo(parent, name="praxion")
    stage(cached, NUMBERED, GOOD_NUMBERED)
    code, out, err = judge_commit(cached, COMMIT, monkeypatch, capsys)
    assert (code, out) == (0, "")
    assert "plugin-cache root" in err


def test_a_blob_the_gate_cannot_read_passes_with_a_note(feature, monkeypatch, capsys):
    stage(feature, NUMBERED, GOOD_NUMBERED)
    monkeypatch.setattr(cli, "_index_text", _unreadable)
    code, _, err = judge_commit(feature, COMMIT, monkeypatch, capsys)
    assert code == 0
    assert "cannot read" in err
    assert "passing" in err


def _unreadable(root: Path, rel: str) -> str:
    raise cli.InputError(f"cannot read the staged blob of {rel}")


# -- Modes stay apart ---------------------------------------------------------------------


def test_a_path_argument_keeps_the_path_mode_under_the_payload_signal(feature, monkeypatch, capsys):
    put(feature, NUMBERED, GOOD_NUMBERED)
    monkeypatch.setenv("PRAXION_COMMIT_PAYLOAD", "1")
    monkeypatch.setattr(sys, "stdin", io.StringIO(payload(feature, "git status")))
    code = cli.main(["--repo-root", str(feature), NUMBERED])
    assert (code, capsys.readouterr().out.startswith(NUMBERED)) == (1, True)


def test_the_staged_flag_keeps_the_staged_mode_under_the_payload_signal(
    feature, monkeypatch, capsys
):
    stage(feature, NUMBERED, GOOD_NUMBERED)
    monkeypatch.setenv("PRAXION_COMMIT_PAYLOAD", "1")
    monkeypatch.setattr(sys, "stdin", io.StringIO(payload(feature, "git status")))
    code = cli.main(["--repo-root", str(feature), "--staged"])
    assert (code, capsys.readouterr().out.startswith(NUMBERED)) == (1, True)


def test_without_the_payload_signal_no_argument_is_still_an_error(monkeypatch):
    monkeypatch.delenv("PRAXION_COMMIT_PAYLOAD", raising=False)
    with pytest.raises(SystemExit) as raised:
        cli.main([])
    assert raised.value.code == 2


# -- The process-level fact ---------------------------------------------------------------


def run_script(repo: Path, command: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PRAXION_COMMIT_PAYLOAD": "1"}
    return subprocess.run(
        [sys.executable, str(SCRIPT_DIR / "check_decision_records.py")],
        input=payload(repo, command),
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def test_the_script_run_as_a_process_refuses_and_passes_a_commit(feature):
    stage(feature, NUMBERED, GOOD_NUMBERED)
    refused = run_script(feature, COMMIT)
    assert (refused.returncode, refused.stdout) == (1, "")
    assert NUMBERED in refused.stderr
    git(feature, "reset", "-q")
    clean = run_script(feature, COMMIT)
    assert (clean.returncode, clean.stdout, clean.stderr) == (0, "", "")
