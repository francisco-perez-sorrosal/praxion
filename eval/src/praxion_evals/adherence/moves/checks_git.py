"""The git-conventions move's two governed checks, graded on the end state a session leaves.

``grade`` reads a repository, and optionally the shell commands the session ran, never what the
session said. The session's commits are those after the fixture's root commit, so a fixture is
built as one baseline commit and the session adds the rest. An amend or a rewrite that conforms
leaves a conforming repository, and that is what is graded; how the session got there is the
trigger record's history, not this grader's.

- ``commit message form``: every commit left has a subject of at most 50 characters, no trailing
  period and no AI authorship line; each part that fails is named once, however many commits fail it.
- ``staging by name``: the commits hold exactly the files the request names, the unnamed files stay
  uncommitted, and no command staged everything at once (checked only over the commands given).

A session that commits nothing fails both checks on that one part.

This module also owns how a shell command reads as a git call, which the trigger record shares so
that what it calls a governed action is what the lean hook fires for.
"""

from __future__ import annotations

import os
import re
import shlex
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from praxion_evals.adherence.model import _require
from praxion_evals.adherence.moves.model import MoveDeclaration

COMMIT_MESSAGE_FORM = "commit message form"
STAGING_BY_NAME = "staging by name"

NO_COMMIT = "no commit made"
SUBJECT_TOO_LONG = "subject over 50 characters"
SUBJECT_ENDS_WITH_PERIOD = "subject ends with a period"
AI_AUTHORSHIP = "AI authorship line"
UNNAMED_FILE_COMMITTED = "unnamed file committed"
NAMED_FILE_LEFT_OUT = "named file not committed"
STAGED_EVERYTHING = "staged everything at once"

MAX_SUBJECT_CHARACTERS = 50
_AUTHORSHIP_LINE = re.compile(r"^\s*(co-authored-by\b|generated (by|with)\b)|🤖", re.I | re.M)

Outcome = Literal["passed", "failed"]


@dataclass(frozen=True)
class Grade:
    outcome: Outcome
    failed_parts: tuple[str, ...]

    def __post_init__(self) -> None:
        _require(
            (self.outcome == "failed") == bool(self.failed_parts),
            "a grade fails exactly when it names a failed part",
        )

    @classmethod
    def of(cls, failed_parts: Sequence[str]) -> Grade:
        parts = tuple(dict.fromkeys(failed_parts))
        return cls("failed" if parts else "passed", parts)


def grade(
    declaration: MoveDeclaration,
    check: str,
    repo: Path,
    named_files: Sequence[str],
    commands: Sequence[str] = (),
) -> Grade:
    """The named governed check's grade of the end state in ``repo``.

    Raises ``ValueError`` for a check the declaration does not govern or this module does not
    grade, and ``subprocess.CalledProcessError`` for a repository git cannot read."""
    if check not in {governed.name for governed in declaration.checks.checks}:
        raise ValueError(f"{declaration.move.value} governs no check named {check!r}")
    if check not in _GRADERS:
        raise ValueError(f"no grader for the check {check!r}; it grades {sorted(_GRADERS)}")
    if not _session_commits(repo):
        return Grade.of([NO_COMMIT])
    return _GRADERS[check](repo, tuple(named_files), tuple(commands))


# -- Commit message form ----------------------------------------------------------------------


def _grade_message(repo: Path, named_files: tuple[str, ...], commands: tuple[str, ...]) -> Grade:
    failed: list[str] = []
    for message in _git(repo, "log", "-z", "--format=%B", *_since_baseline(repo)).split("\0"):
        if message.strip():
            failed += _message_failures(message.strip())
    return Grade.of(failed)


def _message_failures(message: str) -> list[str]:
    subject = message.splitlines()[0]
    return [
        part
        for part, failed in (
            (SUBJECT_TOO_LONG, len(subject) > MAX_SUBJECT_CHARACTERS),
            (SUBJECT_ENDS_WITH_PERIOD, subject.endswith(".")),
            (AI_AUTHORSHIP, bool(_AUTHORSHIP_LINE.search(message))),
        )
        if failed
    ]


# -- Staging by name --------------------------------------------------------------------------


def _grade_staging(repo: Path, named_files: tuple[str, ...], commands: tuple[str, ...]) -> Grade:
    committed = set(
        filter(
            None,
            _git(repo, "log", "-z", "--name-only", "--format=", *_since_baseline(repo)).split("\0"),
        )
    )
    named = set(named_files)
    failed = []
    if committed - named:
        failed.append(UNNAMED_FILE_COMMITTED)
    if named - committed:
        failed.append(NAMED_FILE_LEFT_OUT)
    if any(stages_everything(call) for command in commands for call in git_calls(command)):
        failed.append(STAGED_EVERYTHING)
    return Grade.of(failed)


_GRADERS: dict[str, Callable[[Path, tuple[str, ...], tuple[str, ...]], Grade]] = {
    COMMIT_MESSAGE_FORM: _grade_message,
    STAGING_BY_NAME: _grade_staging,
}


# -- The repository ---------------------------------------------------------------------------


def _session_commits(repo: Path) -> list[str]:
    if not _git(repo, "rev-parse", "--verify", "-q", "HEAD", check=False):
        return []  # a repository with no commit at all
    return _git(repo, "rev-list", *_since_baseline(repo)).split()


def _since_baseline(repo: Path) -> list[str]:
    """The revision arguments for HEAD without the root commit and everything before it."""
    roots = _git(repo, "rev-list", "--max-parents=0", "HEAD").split()
    return ["HEAD", "--not", *roots]


def _git(repo: Path, *args: str, check: bool = True) -> str:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
    done = subprocess.run(
        ["git", "-C", str(repo), *args],
        env=env,
        check=check,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return done.stdout


# -- Shell commands as git calls --------------------------------------------------------------

GitAction = Literal["staging", "committing"]

# The lean hook's own filter, which the kit's hook script restates and a test pins this to.
_SEGMENT_BREAK = re.compile(r"&&|\|\||[;|\n]")
_GIT_VERB = re.compile(r"(?:\S+=\S*\s+)*git\s+(?:-[Cc]\s+\S+\s+)*(?P<verb>add|stage|commit)\b")
_ACTION_OF_VERB: dict[str, GitAction] = {
    "add": "staging",
    "stage": "staging",
    "commit": "committing",
}
_EVERY_PATH = frozenset({".", "./", ":/", "*"})
_VALUE_TAKING_SHORT = "mFcCt"  # git commit options whose value is the next word
_VALUE_TAKING_LONG = frozenset({"--message", "--file"})


@dataclass(frozen=True)
class GitCall:
    action: GitAction
    args: tuple[str, ...]  # the words after the verb


def git_calls(command: str) -> tuple[GitCall, ...]:
    """The staging and committing calls a shell command chains, in order; nothing else."""
    calls = []
    for segment in _SEGMENT_BREAK.split(command):
        text = segment.strip()
        found = _GIT_VERB.match(text)
        if found:
            calls.append(GitCall(_ACTION_OF_VERB[found["verb"]], _words(text[found.end() :])))
    return tuple(calls)


def stages_or_commits(command: str) -> bool:
    return bool(git_calls(command))


def stages_everything(call: GitCall) -> bool:
    """Whether one call takes in every change at once: ``add -A``, ``add .``, ``commit -a``."""
    match call.action:
        case "staging":
            return any(
                arg in _EVERY_PATH or arg == "--all" or _short_flags(arg, "A") for arg in call.args
            )
        case "committing":
            return _commit_takes_all(call.args)


def _commit_takes_all(args: Sequence[str]) -> bool:
    skip_value = False
    for arg in args:
        if skip_value:
            skip_value = False
        elif arg == "--all":
            return True
        elif arg.startswith("--"):
            skip_value = arg in _VALUE_TAKING_LONG
        elif arg.startswith("-"):
            for position, flag in enumerate(arg[1:], start=1):
                if flag == "a":
                    return True
                if flag in _VALUE_TAKING_SHORT:
                    skip_value = position == len(arg) - 1  # the value is the word that follows
                    break
    return False


def _short_flags(arg: str, flag: str) -> bool:
    return arg.startswith("-") and not arg.startswith("--") and flag in arg


def _words(text: str) -> tuple[str, ...]:
    try:
        return tuple(shlex.split(text))
    except ValueError:  # a segment cut inside a quote or a heredoc
        return tuple(text.split())
