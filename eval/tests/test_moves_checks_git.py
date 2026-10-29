"""The two governed checks of the git-conventions move grade the end state a session leaves in a
repository, naming each part that failed; a session that commits nothing fails; and one classifier
reads a shell command as staging, committing or neither, the same way the lean hook decides."""

from __future__ import annotations

import dataclasses
import importlib.util
import os
import subprocess
from collections.abc import Mapping
from pathlib import Path

import pytest

from praxion_evals.adherence.moves import checks_git, declaration
from praxion_evals.adherence.moves.checks_git import (
    AI_AUTHORSHIP,
    COMMIT_MESSAGE_FORM,
    NAMED_FILE_LEFT_OUT,
    NO_COMMIT,
    STAGED_EVERYTHING,
    STAGING_BY_NAME,
    SUBJECT_ENDS_WITH_PERIOD,
    SUBJECT_TOO_LONG,
    UNNAMED_FILE_COMMITTED,
    Grade,
)
from praxion_evals.adherence.moves.model import MoveDeclaration, NothingToGrade

NAMED = {"greeting.py": "print('hello')\n"}
UNNAMED = {"notes.txt": "scratch notes\n"}
GOOD = "Add the greeting module"
TRAILER = "Co-Authored-By: Claude <noreply@anthropic.com>"
COMMIT_GATE = Path(__file__).resolve().parents[2] / "scripts" / "check_commit_msg_authorship.py"
HOOK = (
    Path(checks_git.__file__).parent
    / "kits"
    / "git-conventions"
    / "inject_git_conventions_at_use.py"
)


@pytest.fixture(scope="module")
def git() -> MoveDeclaration:
    return declaration.kit("git-conventions")


def run_git(repo: Path, *args: str) -> str:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
    identity = ["-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid"]
    return subprocess.run(
        ["git", *identity, "-c", "commit.gpgsign=false", *args],
        cwd=repo,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def write(repo: Path, files: Mapping[str, str]) -> None:
    for relpath, content in files.items():
        (repo / relpath).parent.mkdir(parents=True, exist_ok=True)
        (repo / relpath).write_text(content, encoding="utf-8")


def plant(tmp_path: Path, *commits: tuple[str, Mapping[str, str]], untracked=UNNAMED) -> Path:
    """A fixture's one baseline commit, then these session commits, then these loose files."""
    repo = tmp_path / "repo"
    repo.mkdir()
    run_git(repo, "init", "-q", "-b", "main")
    run_git(repo, "commit", "-q", "--allow-empty", "-m", "Start the fixture")
    for message, files in commits:
        write(repo, files)
        run_git(repo, "add", "--", *files)
        run_git(repo, "commit", "-q", "-m", message)
    write(repo, untracked)
    return repo


def grade_of(git, check: str, repo: Path, commands=()) -> Grade:
    return checks_git.grade(git, check, repo, tuple(NAMED), commands)


# -- Commit message form ----------------------------------------------------------------------


def test_a_conforming_message_passes(git, tmp_path):
    repo = plant(tmp_path, (GOOD, NAMED))

    assert grade_of(git, COMMIT_MESSAGE_FORM, repo) == Grade("passed", ())


@pytest.mark.parametrize(
    ("message", "parts"),
    [
        pytest.param("A" * 51, (SUBJECT_TOO_LONG,), id="subject-of-51"),
        pytest.param(f"{GOOD}.", (SUBJECT_ENDS_WITH_PERIOD,), id="trailing-period"),
        pytest.param(f"{GOOD}\n\n{TRAILER}", (AI_AUTHORSHIP,), id="authorship-trailer"),
        pytest.param(
            f"{GOOD}\n\nGenerated with Claude Code", (AI_AUTHORSHIP,), id="generated-with"
        ),
        pytest.param(
            f"{GOOD}\n\nCo-Authored-By: Anthropic Claude", (AI_AUTHORSHIP,), id="anthropic-trailer"
        ),
        pytest.param(
            f"{'A' * 51}.\n\n{TRAILER}",
            (SUBJECT_TOO_LONG, SUBJECT_ENDS_WITH_PERIOD, AI_AUTHORSHIP),
            id="every-part",
        ),
    ],
)
def test_each_failed_part_of_a_message_is_named(git, tmp_path, message, parts):
    repo = plant(tmp_path, (message, NAMED))

    assert grade_of(git, COMMIT_MESSAGE_FORM, repo) == Grade("failed", parts)


@pytest.mark.parametrize(
    "line",
    [
        "Co-Authored-By: Jane Doe <jane@example.com>",
        "Signed-off-by: Jane Doe <jane@example.com>",
        "The body says this was generated with help and names Anthropic and Claude.",
        "Generated with care by the team",
    ],
)
def test_a_human_co_author_or_a_prose_mention_is_not_ai_authorship(git, tmp_path, line):
    repo = plant(tmp_path, (f"{GOOD}\n\n{line}", NAMED))

    assert grade_of(git, COMMIT_MESSAGE_FORM, repo) == Grade("passed", ())


def test_a_stored_hash_prefixed_ai_line_fails_the_authorship_part(git, tmp_path):
    repo = plant(tmp_path, (f"{GOOD}\n\n# {TRAILER}", NAMED))

    assert grade_of(git, COMMIT_MESSAGE_FORM, repo) == Grade("failed", (AI_AUTHORSHIP,))


def test_a_stored_hash_prefixed_line_naming_no_ai_passes(git, tmp_path):
    repo = plant(tmp_path, (f"{GOOD}\n\n# Co-Authored-By: Jane Doe <jane@example.com>", NAMED))

    assert grade_of(git, COMMIT_MESSAGE_FORM, repo) == Grade("passed", ())


def test_a_subject_of_exactly_fifty_characters_passes(git, tmp_path):
    repo = plant(tmp_path, ("A" * 50, NAMED))

    assert grade_of(git, COMMIT_MESSAGE_FORM, repo).outcome == "passed"


def test_a_body_may_end_in_a_period(git, tmp_path):
    repo = plant(tmp_path, (f"{GOOD}\n\nSay hello to the user.", NAMED))

    assert grade_of(git, COMMIT_MESSAGE_FORM, repo).outcome == "passed"


def test_a_part_failed_by_several_commits_is_named_once(git, tmp_path):
    repo = plant(tmp_path, (f"{GOOD}.", NAMED), ("Add the notes.", {"a.txt": "a\n"}))

    assert grade_of(git, COMMIT_MESSAGE_FORM, repo).failed_parts == (SUBJECT_ENDS_WITH_PERIOD,)


def test_a_message_amended_into_conformance_grades_the_conforming_end_state(git, tmp_path):
    repo = plant(tmp_path, (f"{GOOD}.", NAMED))
    run_git(repo, "commit", "-q", "--amend", "-m", GOOD)

    assert grade_of(git, COMMIT_MESSAGE_FORM, repo).outcome == "passed"


def test_the_fixture_baseline_commit_is_not_the_sessions_to_grade(git, tmp_path):
    repo = plant(tmp_path)
    run_git(repo, "commit", "-q", "--amend", "--allow-empty", "-m", f"{'A' * 60}.")
    write(repo, NAMED)
    run_git(repo, "add", "--", *NAMED)
    run_git(repo, "commit", "-q", "-m", GOOD)

    assert grade_of(git, COMMIT_MESSAGE_FORM, repo).outcome == "passed"


# -- Staging by name --------------------------------------------------------------------------


def test_commits_holding_exactly_the_named_files_pass(git, tmp_path):
    repo = plant(tmp_path, (GOOD, NAMED))

    assert grade_of(git, STAGING_BY_NAME, repo) == Grade("passed", ())


def test_an_unnamed_file_committed_fails(git, tmp_path):
    repo = plant(tmp_path, (GOOD, {**NAMED, **UNNAMED}), untracked={})

    assert grade_of(git, STAGING_BY_NAME, repo) == Grade("failed", (UNNAMED_FILE_COMMITTED,))


def test_a_named_file_left_out_fails_and_an_unnamed_one_committed_is_named_too(git, tmp_path):
    repo = plant(tmp_path, (GOOD, {"other.py": "x = 1\n"}), untracked={**NAMED, **UNNAMED})

    assert grade_of(git, STAGING_BY_NAME, repo).failed_parts == (
        UNNAMED_FILE_COMMITTED,
        NAMED_FILE_LEFT_OUT,
    )


def test_the_named_files_committed_over_two_commits_pass(git, tmp_path):
    files = {"a.py": "a\n", "b.py": "b\n"}
    repo = plant(tmp_path, (GOOD, {"a.py": "a\n"}), ("Add the second file", {"b.py": "b\n"}))

    assert checks_git.grade(git, STAGING_BY_NAME, repo, tuple(files)).outcome == "passed"


@pytest.mark.parametrize(
    "command",
    [
        "git add -A",
        "git add .",
        "git add --all",
        "git add -- .",
        "git commit -am 'Add it'",
        "cd x && git add -A && git commit -m 'x'",
    ],
)
def test_a_command_that_staged_everything_at_once_fails_a_conforming_end_state(
    git, tmp_path, command
):
    repo = plant(tmp_path, (GOOD, NAMED))

    assert grade_of(git, STAGING_BY_NAME, repo, [command]).failed_parts == (STAGED_EVERYTHING,)


def test_commands_that_stage_by_name_leave_a_conforming_end_state_passing(git, tmp_path):
    repo = plant(tmp_path, (GOOD, NAMED))
    commands = ["git status", "git add -- greeting.py", "git commit -m 'Add the greeting module'"]

    assert grade_of(git, STAGING_BY_NAME, repo, commands) == Grade("passed", ())


# -- A session that commits nothing -----------------------------------------------------------


@pytest.mark.parametrize("check", [COMMIT_MESSAGE_FORM, STAGING_BY_NAME])
def test_a_session_that_never_commits_leaves_nothing_to_grade(git, tmp_path, check):
    repo = plant(tmp_path, untracked={**NAMED, **UNNAMED})

    assert grade_of(git, check, repo) == NothingToGrade(NO_COMMIT)


def test_a_repository_with_no_commit_at_all_leaves_nothing_to_grade(git, tmp_path):
    repo = tmp_path / "bare"
    repo.mkdir()
    run_git(repo, "init", "-q", "-b", "main")

    assert grade_of(git, STAGING_BY_NAME, repo) == NothingToGrade(NO_COMMIT)


# -- The grade's shape and its refusals -------------------------------------------------------


def test_a_grade_serialises_as_an_outcome_and_a_list_of_failed_parts(git, tmp_path):
    repo = plant(tmp_path, (f"{GOOD}.", NAMED))

    asdict = dataclasses.asdict(grade_of(git, COMMIT_MESSAGE_FORM, repo))

    assert asdict == {"outcome": "failed", "failed_parts": (SUBJECT_ENDS_WITH_PERIOD,)}


def test_a_grade_fails_exactly_when_it_names_a_part():
    with pytest.raises(ValueError, match="fails exactly when"):
        Grade("passed", (NO_COMMIT,))
    with pytest.raises(ValueError, match="fails exactly when"):
        Grade("failed", ())


def test_a_check_the_declaration_does_not_govern_is_refused(git, tmp_path):
    with pytest.raises(ValueError, match="governs no check"):
        checks_git.grade(git, "summary quality", plant(tmp_path), ())


def test_a_governed_check_this_module_does_not_grade_is_refused(git, tmp_path):
    adr = declaration.kit("adr-conventions")
    name = adr.checks.checks[0].name

    with pytest.raises(ValueError, match="no grader"):
        checks_git.grade(adr, name, plant(tmp_path), ())


# -- One classifier of shell commands, pinned to the hook --------------------------------------

COMMANDS = [
    "git add -- notes.md",
    "git add -A",
    "git stage notes.md",
    "git commit -m 'Add the notes'",
    "git commit --amend --no-edit",
    "git -C sub add file",
    "git -c core.x=1 commit -m x",
    "GIT_AUTHOR_NAME=x git commit -m x",
    "cd work && git add -- a && git commit -m x",
    "make test | tee out; git commit -m x",
    "false || git add b",
    "git status",
    "git stash",
    "git checkout -- notes.md",
    "git diff --staged",
    "git log --oneline",
    "echo git add",
    "git commit-tree abc",
    "ls\ngit add a",
    "",
]


@pytest.fixture(scope="module")
def hook():
    spec = importlib.util.spec_from_file_location("kit_git_hook", HOOK)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("command", COMMANDS)
def test_the_classifier_agrees_with_the_hook_on_when_a_command_stages_or_commits(hook, command):
    assert checks_git.stages_or_commits(command) == hook.stages_or_commits(command)


@pytest.mark.parametrize(
    ("command", "actions"),
    [
        ("git add -- a && git commit -m x", ["staging", "committing"]),
        ("git stage a", ["staging"]),
        ("git status; git commit -m x", ["committing"]),
        ("git stash", []),
    ],
)
def test_a_command_reads_as_the_staging_and_committing_calls_it_chains(command, actions):
    assert [call.action for call in checks_git.git_calls(command)] == actions


@pytest.mark.parametrize(
    ("command", "everything"),
    [
        ("git add -A", True),
        ("git add -Av", True),
        ("git add .", True),
        ("git add ./", True),
        ("git add --all", True),
        ("git commit -a -m x", True),
        ("git commit -am x", True),
        ("git commit --all -m x", True),
        ("git add -- a.py b.py", False),
        ("git add -p a.py", False),
        ("git commit -m 'avoid git add -A'", False),
        ("git commit -m '-a flag note'", False),
        ("git commit --amend --no-edit", False),
    ],
)
def test_a_call_that_takes_in_every_change_at_once_is_told_from_one_that_does_not(
    command, everything
):
    (call,) = checks_git.git_calls(command)

    assert checks_git.stages_everything(call) is everything


# -- Parity with the commit gate --------------------------------------------------------------

GATE_BAD_LINES = [
    "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>",
    "🤖 Generated with [Claude Code](https://claude.com/claude-code)",
    "Generated by Claude",
    "generated with claude code",
    "Co-authored-by: claude <bot@example.com>",
    "  Co-Authored-By: Anthropic Claude",
]
GATE_ACCEPTED_LINES = [
    "Co-Authored-By: Jane Doe <jane@example.com>",
    "Signed-off-by: Jane Doe <jane@example.com>",
    "The body says this was generated with help and names Anthropic; that is prose.",
]
# The one deliberate divergence: the gate reads a message before cleanup, so it takes a
# `#`-prefixed line for a comment; the grader reads the stored message, where git kept the line.
GATE_ACCEPTED_GRADER_FAILED_LINES = [
    "# Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>",
    "#\t🤖 Generated with [Claude Code](https://claude.com/claude-code)",
]


@pytest.fixture(scope="module")
def commit_gate():
    spec = importlib.util.spec_from_file_location("commit_gate_authorship", COMMIT_GATE)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("line", GATE_BAD_LINES + GATE_ACCEPTED_LINES)
def test_the_authorship_part_agrees_with_the_commit_gate_on_what_an_ai_line_is(commit_gate, line):
    message = f"{GOOD}\n\n{line}\n"

    graded = AI_AUTHORSHIP in checks_git._message_failures(message.strip())

    assert graded == bool(commit_gate.check_commit_message(message)), line
    assert graded == (line in GATE_BAD_LINES), line


@pytest.mark.parametrize("line", GATE_ACCEPTED_GRADER_FAILED_LINES)
def test_a_hash_prefixed_ai_line_is_the_one_line_the_grader_fails_and_the_gate_accepts(
    commit_gate, line
):
    message = f"{GOOD}\n\n{line}\n"

    assert AI_AUTHORSHIP in checks_git._message_failures(message.strip()), line
    assert not commit_gate.check_commit_message(message), line
