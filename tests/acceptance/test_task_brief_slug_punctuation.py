"""The task-brief reminder reads the slug without its trailing punctuation.

Orchestrators write `Task slug: auth-flow.` as an ordinary sentence. The
punctuation that ends the sentence is not part of the slug: a briefed pipeline
must hear nothing, and an unbriefed one must be pointed at the brief path the
pipeline actually uses, never at `.ai-work/auth-flow./TASK_BRIEF.md`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.acceptance.drivers.task_brief_reminder import (
    ADVISORY_PREFIX,
    new_git_repo,
    run_reminder,
    spawn_payload,
    write_brief,
)

TRAILING_PUNCTUATION = [".", ",", ";", ":", ")", "?", "!"]

SPAWNS = [
    ("Agent", "praxion:systems-architect"),
    ("Agent", "implementation-planner"),
    ("Task", "systems-architect"),
    ("Task", "praxion:implementation-planner"),
]


# -- A briefed pipeline hears nothing ----------------------------------------


@pytest.mark.parametrize("punctuation", TRAILING_PUNCTUATION)
def test_a_briefed_spawn_is_silent_when_punctuation_follows_the_slug(
    tmp_path: Path, punctuation: str
) -> None:
    repo = new_git_repo(tmp_path / "repo")
    write_brief(repo, "auth-flow")

    run = run_reminder(
        spawn_payload(f"Task slug: auth-flow{punctuation} Design the login flow.", repo)
    )

    assert run.exit_code == 0
    assert run.stdout == "", f"a briefed pipeline was warned: {run.stdout}"


@pytest.mark.parametrize(
    "prompt",
    [
        "Task slug: auth-flow.\n\nDesign the login flow.",
        "Task slug: `auth-flow`.\n\nDesign the login flow.",
        "Tier: Standard\nTask slug: auth-flow.",
        "(Task slug: auth-flow) Design the login flow.",
    ],
)
def test_a_briefed_spawn_is_silent_for_sentence_final_and_backticked_slugs(
    tmp_path: Path, prompt: str
) -> None:
    repo = new_git_repo(tmp_path / "repo")
    write_brief(repo, "auth-flow")

    run = run_reminder(spawn_payload(prompt, repo))

    assert run.exit_code == 0
    assert run.stdout == "", f"a briefed pipeline was warned: {run.stdout}"


@pytest.mark.parametrize(("tool_name", "subagent_type"), SPAWNS)
def test_every_reminded_stage_reads_the_slug_without_its_period(
    tmp_path: Path, tool_name: str, subagent_type: str
) -> None:
    repo = new_git_repo(tmp_path / "repo")
    write_brief(repo, "auth-flow")

    run = run_reminder(
        spawn_payload(
            "Task slug: auth-flow.", repo, subagent_type=subagent_type, tool_name=tool_name
        )
    )

    assert run.exit_code == 0
    assert run.stdout == ""


def test_a_slug_of_letters_digits_hyphens_and_underscores_is_read_whole(tmp_path: Path) -> None:
    repo = new_git_repo(tmp_path / "repo")
    write_brief(repo, "auth_flow-2")

    run = run_reminder(spawn_payload("Task slug: auth_flow-2.", repo))

    assert run.exit_code == 0
    assert run.stdout == ""


def test_the_brief_is_found_from_a_subdirectory_of_the_repository(tmp_path: Path) -> None:
    repo = new_git_repo(tmp_path / "repo")
    write_brief(repo, "auth-flow")
    nested = repo / "src" / "app"
    nested.mkdir(parents=True)

    run = run_reminder(spawn_payload("Task slug: auth-flow.", nested))

    assert run.exit_code == 0
    assert run.stdout == ""


# -- A missing brief still warns, naming the right path -----------------------


def _single_advisory_text(run) -> str:
    assert run.exit_code == 0, "the reminder must never block a spawn"
    advisories = run.advisories()
    assert len(advisories) == 1, f"expected exactly one advisory, got {advisories}"
    output = advisories[0]["hookSpecificOutput"]
    assert output["hookEventName"] == "PreToolUse"
    text = output["additionalContext"]
    assert text.startswith(ADVISORY_PREFIX), text
    return text


def test_a_missing_brief_warns_once_naming_the_path_of_a_bare_slug(tmp_path: Path) -> None:
    repo = new_git_repo(tmp_path / "repo")

    run = run_reminder(spawn_payload("Task slug: auth-flow\n\nDesign the login flow.", repo))

    text = _single_advisory_text(run)
    assert ".ai-work/auth-flow/TASK_BRIEF.md" in text, text


@pytest.mark.parametrize("punctuation", TRAILING_PUNCTUATION)
def test_a_missing_brief_warns_once_naming_the_path_without_the_punctuation(
    tmp_path: Path, punctuation: str
) -> None:
    repo = new_git_repo(tmp_path / "repo")

    run = run_reminder(
        spawn_payload(f"Task slug: auth-flow{punctuation} Design the login flow.", repo)
    )

    text = _single_advisory_text(run)
    assert ".ai-work/auth-flow/TASK_BRIEF.md" in text, text
    assert f"auth-flow{punctuation}/" not in text, text


def test_a_missing_brief_for_a_backticked_sentence_final_slug_names_the_bare_slug(
    tmp_path: Path,
) -> None:
    repo = new_git_repo(tmp_path / "repo")

    run = run_reminder(spawn_payload("Task slug: `auth-flow`.\n\nDesign it.", repo))

    text = _single_advisory_text(run)
    assert ".ai-work/auth-flow/TASK_BRIEF.md" in text, text


def test_a_brief_for_a_different_slug_does_not_silence_the_warning(tmp_path: Path) -> None:
    repo = new_git_repo(tmp_path / "repo")
    write_brief(repo, "other-task")

    run = run_reminder(spawn_payload("Task slug: auth-flow.", repo))

    text = _single_advisory_text(run)
    assert ".ai-work/auth-flow/TASK_BRIEF.md" in text, text
