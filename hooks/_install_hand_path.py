"""The hand path's instructions step: bring `~/.claude/CLAUDE.md` to the installed version.

`install.sh code --complete-install` calls this as its last step, in the person's own
terminal: `python3 <root>/hooks/_install_hand_path.py --root <root>`. `HOME` comes from the
environment, the answers from standard input, the conversation (the offer, the questions,
the values about to be written) goes to standard error, and standard output carries exactly
one outcome line. The exit status is the outcome's (`exit_status`): 0, 1 or 3.

It composes what the update path already owns, with no second copy: the five-state
classifier and the hand-path plan of `_install_refresh`, and the read-back and the atomic
writer of `_install_update`. What it adds is the conversation, and the words of the outcome.

Answers are never put in argv or the environment, never persisted outside the render, never
logged, and never reach standard output. A failure line carries the kind of failure and the
role of the path, never an exception message: a message could hold a personal value.

Stdlib only and importable on Python 3.9 (stock macOS `python3`), like the hook it sits beside.
"""

from __future__ import annotations

import argparse
import contextlib
import os
import posixpath
import sys
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path
from typing import TextIO

# `render_claude_md` lives in scripts/, beside this directory's parent.
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).parent))
from _install_refresh import (  # noqa: E402 (after sys.path injection)
    STATUS_DONE,
    STATUS_LEFT_BEHIND,
    AskForValues,
    AskReason,
    CachedRender,
    CarryForward,
    Current,
    Failed,
    FailureKind,
    HandPathOutcome,
    HandPathPlan,
    InstructionsState,
    LeaveAlone,
    LeaveAloneReason,
    LeftAlone,
    MissingCachedRender,
    NoAnswer,
    Readback,
    SetUp,
    Skipped,
    SkipPoint,
    Unreadable,
    cache_version_dir,
    classify_instructions,
    exit_status,
    plan_hand_path_instructions,
    unreachable,
)
from _install_update import (  # noqa: E402 (after sys.path injection)
    _CLAUDE_MD_SUBPATH,
    _default_values,
    read_back,
    snapshot_instructions,
    write_instructions,
)

INSTRUCTIONS = "~/.claude/CLAUDE.md"

# The personal values, in the order they are asked, with the label each prompt carries.
_VALUE_LABELS = (("USERNAME", "Username"), ("EMAIL", "Email"), ("GITHUB_URL", "GitHub URL"))

_ACCEPT_OFFER = frozenset({"", "1"})
_SKIP_OFFER = "2"
_CONFIRM_YES = frozenset({"", "y"})
_CONFIRM_NO = "n"


class InputEndedError(Exception):
    """The input ended before the person answered: no answer, never consent."""


class StepFailedError(Exception):
    """A phase of the step failed; `kind` is all the report may say of it."""

    def __init__(self, kind: FailureKind) -> None:
        super().__init__(kind.value)
        self.kind = kind


# -- The entry ------------------------------------------------------------------------------------


def main(
    argv: Sequence[str],
    environ: Mapping[str, str],
    stdin: TextIO,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    """Run the step, print its one outcome line, and return the outcome's exit status."""
    arguments = _parse_arguments(argv)
    root = os.path.abspath(arguments.root)  # lexical: a dev-linked hooks/ must not move the root
    if arguments.check:
        return _check_status(_home_of(environ), root)
    try:
        outcome, carried_from = run_instructions_step(_home_of(environ), root, stdin, stderr)
    except Exception:  # the line has a kind and no message, so nothing here can leak a value
        outcome, carried_from = Failed(FailureKind.UNEXPECTED), None
    stdout.write(outcome_line(outcome, root, carried_from) + "\n")
    stdout.flush()
    return exit_status(outcome)


def _check_status(home: Path, root: str) -> int:
    """`STATUS_LEFT_BEHIND` when the instructions read from another version's render, else `STATUS_DONE`.

    Judged from the state alone, with no read-back: a version removed from the cache
    cannot be read back, and that is behind too. A failure to look says nothing.
    """
    try:
        state, is_cache_version = _gather(home, root)
    except OSError:
        return STATUS_DONE
    behind = is_cache_version and (
        isinstance(state, MissingCachedRender)
        or (isinstance(state, CachedRender) and state.version_dir != root)
    )
    return STATUS_LEFT_BEHIND if behind else STATUS_DONE


def _parse_arguments(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Bring ~/.claude/CLAUDE.md to this plugin version."
    )
    parser.add_argument("--root", required=True, help="the plugin root this command runs from")
    parser.add_argument(
        "--check",
        action="store_true",
        help="change and print nothing; exit 3 when the instructions are behind this version",
    )
    return parser.parse_args(argv)


def _home_of(environ: Mapping[str, str]) -> Path:
    """The home directory, never a relative one: an empty HOME would write into the working directory."""
    home = environ["HOME"]
    if not os.path.isabs(home):
        raise ValueError("HOME is not an absolute path")
    return Path(home)


# -- The step -------------------------------------------------------------------------------------


def run_instructions_step(
    home: Path, root: str, stdin: TextIO, stderr: TextIO
) -> tuple[HandPathOutcome, str | None]:
    """Gather, decide, converse and write; the outcome, and the version whose values were carried.

    A failure becomes `Failed(kind)` by the phase that raised it; an exception that is
    neither a filesystem error nor the input ending is left for `main` to name unexpected.
    """
    try:
        state, plan = _decide(home, root)
        earlier = posixpath.basename(state.version_dir) if isinstance(plan, CarryForward) else None
        return _carry_out(plan, earlier, home, root, stdin, stderr), earlier
    except InputEndedError:
        return NoAnswer(), None
    except StepFailedError as failure:
        return Failed(failure.kind), None


def _decide(home: Path, root: str) -> tuple[InstructionsState, HandPathPlan]:
    """What the instructions hold and what to do about them: reads, and changes nothing."""
    with _phase(FailureKind.READING):
        state, is_cache_version = _gather(home, root)
        readback = _read_back_when_needed(state, root, is_cache_version)
        return state, plan_hand_path_instructions(state, readback, is_cache_version, root)


def _gather(home: Path, root: str) -> tuple[InstructionsState, bool]:
    """What the instructions entry is, and whether `root` is a cache version directory."""
    link_dir = str(home / _CLAUDE_MD_SUBPATH.parent)
    state = classify_instructions(snapshot_instructions(home / _CLAUDE_MD_SUBPATH), link_dir)
    return state, cache_version_dir(root, link_dir) == root


def _read_back_when_needed(state: InstructionsState, root: str, is_cache_version: bool) -> Readback:
    """The plan reads the read-back only for a cache render run from a cache version."""
    if is_cache_version and isinstance(state, CachedRender):
        return read_back(state, Path(root))
    return Unreadable()


def _carry_out(
    plan: HandPathPlan,
    earlier: str | None,
    home: Path,
    root: str,
    stdin: TextIO,
    stderr: TextIO,
) -> HandPathOutcome:
    if isinstance(plan, Current):
        return plan
    if isinstance(plan, LeaveAlone):
        return LeftAlone(plan.why)
    if isinstance(plan, CarryForward):
        why = (
            f"{INSTRUCTIONS} was rendered from version {earlier}; this renders it again "
            "from this version's template, keeping your values."
        )
        if not ask_offer(why, stdin, stderr):
            return Skipped(SkipPoint.OFFER)
        return _write(home, root, dict(plan.values))
    if isinstance(plan, AskForValues):
        if not ask_offer(_WHY_ASKING[plan.why], stdin, stderr):
            return Skipped(SkipPoint.OFFER)
        values = ask_values(_default_values(), stdin, stderr)
        if not confirm_values(values, stdin, stderr):
            return Skipped(SkipPoint.CONFIRM)
        return _write(home, root, values)
    return unreachable(plan)


_WHY_ASKING = {
    AskReason.UNREADABLE: (
        f"{INSTRUCTIONS} links a render that cannot be read back, so your values cannot be "
        "carried over; this sets it up again from this version, asking for them."
    ),
    AskReason.MISSING: (
        f"{INSTRUCTIONS} is missing, or links a render that is gone; this sets it up from "
        "this version, asking for your values."
    ),
}


def _write(home: Path, root: str, values: dict[str, str]) -> SetUp:
    with _phase(FailureKind.WRITING):
        write_instructions(home, Path(root), values)
    return SetUp()


@contextlib.contextmanager
def _phase(kind: FailureKind) -> Iterator[None]:
    """A filesystem error inside is `kind`'s failure, or permission when the system said so."""
    try:
        yield
    except PermissionError as error:
        raise StepFailedError(FailureKind.PERMISSION) from error
    except OSError as error:
        raise StepFailedError(kind) from error


# -- The conversation: each function takes its streams -------------------------------------------


def ask_offer(why: str, stdin: TextIO, stderr: TextIO) -> bool:
    """Offer the change with one line saying why; True to bring the instructions up to date."""
    stderr.write(f"\n{why}\n  [1] Bring {INSTRUCTIONS} to this version\n  [2] Skip instructions\n")
    while True:
        choice = _answer("Choice [1]: ", stdin, stderr)
        if choice in _ACCEPT_OFFER:
            return True
        if choice == _SKIP_OFFER:
            return False
        stderr.write("Please answer 1 or 2.\n")


def ask_values(defaults: Mapping[str, str], stdin: TextIO, stderr: TextIO) -> dict[str, str]:
    """Ask for each personal value; Enter takes the value shown in brackets."""
    stderr.write("\nYour details for the instructions. Enter keeps the value in brackets.\n")
    values = {}
    for key, label in _VALUE_LABELS:
        values[key] = _answer(f"{label} [{defaults[key]}]: ", stdin, stderr) or defaults[key]
    return values


def confirm_values(values: Mapping[str, str], stdin: TextIO, stderr: TextIO) -> bool:
    """Show what will be written and ask: Enter or `y` confirms, `n` declines, else ask again."""
    shown = "".join(f"  {label}: {values[key]}\n" for key, label in _VALUE_LABELS)
    stderr.write(f"\nThe values to write:\n{shown}")
    while True:
        answer = _answer(f"Write these to {INSTRUCTIONS}? [Y/n]: ", stdin, stderr).lower()
        if answer in _CONFIRM_YES:
            return True
        if answer == _CONFIRM_NO:
            return False
        stderr.write("Please answer y or n.\n")


def _answer(prompt: str, stdin: TextIO, stderr: TextIO) -> str:
    """One stripped line; the prompt waits on the same line. Raises `InputEndedError` at the end."""
    stderr.write(prompt)
    stderr.flush()
    line = stdin.readline()
    if not line:
        stderr.write("\n")
        raise InputEndedError
    return line.strip()


# -- The outcome line -----------------------------------------------------------------------------

_LEFT_ALONE_WHY = {
    LeaveAloneReason.OWN_FILE: "your own regular file",
    LeaveAloneReason.OUTSIDE_CACHE: (
        "a link outside the plugin cache that its own `install.sh code` sets up"
    ),
}

# What a failure says of itself: its kind, and the role of the path, never a message.
_FAILURE_DETAIL = {
    FailureKind.READING: "could not read the earlier render or the template",
    FailureKind.WRITING: "could not write the new render or the link",
    FailureKind.PERMISSION: "permission denied",
    FailureKind.UNEXPECTED: "unexpected error",
}


def outcome_line(outcome: HandPathOutcome, root: str, carried_from: str | None) -> str:
    """The one line the outcome prints: it names the instructions and how to finish them."""
    return f"{INSTRUCTIONS} {_say(outcome, root, carried_from)}"


def _say(outcome: HandPathOutcome, root: str, carried_from: str | None) -> str:
    if isinstance(outcome, SetUp):
        source = (
            f"from version {carried_from}'s values" if carried_from else "with the values given"
        )
        return f"set up ({source})"
    if isinstance(outcome, Current):
        return "current"
    if isinstance(outcome, LeftAlone):
        return f"left alone: {_why_left_alone(outcome.why, root)}"
    if isinstance(outcome, Skipped):
        return (
            "skipped (run this command again, `install.sh code --complete-install`, "
            "and accept the instructions step)"
        )
    if isinstance(outcome, NoAnswer):
        return "not set up: no answer (run the command again in your terminal)"
    if isinstance(outcome, Failed):
        return (
            f"could not be set up ({_FAILURE_DETAIL[outcome.kind]}; "
            "run `/praxion-complete-install` again)"
        )
    return unreachable(outcome)


def _why_left_alone(why: LeaveAloneReason, root: str) -> str:
    if why is LeaveAloneReason.CHECKOUT:
        return f'this command runs from a checkout (run "{root}/install.sh" code there)'
    return _LEFT_ALONE_WHY[why]


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:], os.environ, sys.stdin, sys.stdout, sys.stderr))
