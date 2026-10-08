"""Tests for the words a refused commit is reduced to (``scripts/_step_loop_io.py``).

The excerpt function is tested on output text alone; one case runs a real hook in a scratch
repository and reads the refusal back through ``commit_paths``.
"""

from __future__ import annotations

import stat
import sys
import time
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from _git_runner import run_git  # noqa: E402
from _step_loop_io import CommitRefused, commit_paths, hook_words  # noqa: E402

LIMIT = 300
PROMPT_SECONDS = 1.0
LONG_RUN = 50_000
MARKER = "…"
DOTS = "." * 40
MESSAGE = "Add the thing\n\nStep-Loop-Request: abc123\n"
IDENTITY = {"user.name": "Tester", "user.email": "tester@example.invalid"}


def status(name: str, verdict: str, note: str = "") -> str:
    return f"{name}{DOTS}{note}{verdict}"


def passing(count: int, prefix: str = "check") -> list[str]:
    return [status(f"{prefix} {n}", "Passed") for n in range(count)]


def failing(name: str, *messages: str) -> list[str]:
    return [
        status(name, "Failed"),
        f"- hook id: {name}",
        "- exit code: 1",
        "",
        *messages,
        "",
    ]


def positions(text: str, *needles: str) -> list[int]:
    return [text.index(one) for one in needles]


def hook_script(lines: list[str]) -> str:
    echoes = [f"echo '{line}'" for line in lines]
    return "\n".join(["#!/bin/sh", *echoes, "exit 1", ""])


def install_hook(repo: Path, body: str) -> None:
    hook = repo / ".git" / "hooks" / "pre-commit"
    hook.parent.mkdir(exist_ok=True)
    hook.write_text(body)
    hook.chmod(hook.stat().st_mode | stat.S_IXUSR)


def git(repo: Path, *args: str) -> None:
    done = run_git(repo, *args)
    assert done.returncode == 0, done.stderr


@pytest.fixture
def scratch(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    settings = {
        **IDENTITY,
        "commit.gpgsign": "false",
        "core.hooksPath": str(root / ".git" / "hooks"),
    }
    for key, value in settings.items():
        git(root, "config", key, value)
    (root / "a.py").write_text("a = 1\n")
    git(root, "add", "--all")
    git(root, "commit", "-q", "-m", "base")
    (root / "a.py").write_text("a = 2\n")
    return root


def test_one_failing_hook_among_many_is_reduced_to_its_name_and_message() -> None:
    lines = [
        *passing(3),
        status("optional", "Skipped", "(no files to check)"),
        *failing("ruff", "a.py:1:1: F401 unused import", "Found 1 error."),
        *passing(22, "later"),
    ]

    words = hook_words("\n".join(lines))

    assert (
        "\n" in words,
        len(words) <= LIMIT,
        "ruff" in words and "F401 unused import" in words and "Found 1 error." in words,
        "Passed" in words or "Skipped" in words,
        "hook id" in words or "exit code" in words,
    ) == (False, True, True, False, False)


def test_two_failing_hooks_both_appear_in_order() -> None:
    lines = [*failing("first-hook", "first message"), *failing("second-hook", "second message")]

    found = positions(
        hook_words("\n".join(lines)), "first-hook", "first message", "second-hook", "second message"
    )

    assert found == sorted(found)


def test_colour_around_a_status_line_does_not_hide_it() -> None:
    painted = "\x1b[41mruff" + DOTS + "Failed\x1b[m\n- exit code: 1\n\x1b[31mbroken\x1b[m\n"

    assert hook_words(painted) == f"ruff{DOTS}Failed broken"


def test_output_without_a_status_line_yields_its_last_five_non_blank_lines() -> None:
    text = "\n".join(["one", "", "two", "three", "", "four", "five", "six", ""])

    assert hook_words(text) == "two three four five six"


def test_an_over_long_section_is_cut_at_the_limit_with_the_marker() -> None:
    words = hook_words("\n".join(failing("ruff", "x" * 1000)))

    assert (len(words), words.endswith(MARKER)) == (LIMIT, True)


@pytest.mark.parametrize("tail", ["progress", "x Passed", "x Failed"])
def test_a_long_run_of_dots_is_read_promptly(tail: str) -> None:
    started = time.monotonic()
    hook_words("." * LONG_RUN + tail + "\nlast words")

    assert time.monotonic() - started < PROMPT_SECONDS


def test_a_real_hook_refusal_reaches_the_caller_as_the_hooks_own_words(scratch: Path) -> None:
    lines = [*passing(2), *failing("lint", "lint says no"), *passing(22, "later")]
    install_hook(scratch, hook_script(lines))

    outcome = commit_paths(scratch, ["a.py"], MESSAGE)

    assert isinstance(outcome, CommitRefused)
    assert (
        "lint says no" in outcome.detail,
        "Passed" in outcome.detail,
        "\n" in outcome.detail,
    ) == (True, False, False)
