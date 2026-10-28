"""The generic task list of a move: distinct tasks, enough of them, free of the rule they measure.

A kit supplies candidate tasks (its fixtures and wordings); this module draws the list a run
takes from them and refuses a list that would not measure the move. The unit of analysis is a
distinct task, so no two tasks share both fixture and wording; a list holds at least the
declared target plus slack, so a run that drops a few tasks still reaches its target; no
wording states a governed rule line or invokes a slash command, so a task never hands the rule
to the session it measures; and each fixture kind the declaration admits holds at least a third
of the list, so pooling across kinds does not let one kind stand for both.

Pure: the draw is a function of the candidates and the seed, and nothing here touches a file.
"""

from __future__ import annotations

import math
import random
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from itertools import zip_longest
from types import MappingProxyType
from typing import get_args

from praxion_evals.adherence.model import _non_empty, _require
from praxion_evals.adherence.moves.model import (
    BothKinds,
    FixtureKind,
    MoveDeclaration,
    admits,
)
from praxion_evals.adherence.session_loop import launch_order
from praxion_evals.adherence.tasks import DEFAULT_TARGET, SLACK_DIVISOR, SLACK_FLOOR

FIXTURE_KINDS: tuple[FixtureKind, ...] = get_args(FixtureKind)
MIN_KIND_SHARE_DIVISOR = 3  # each admitted fixture kind holds at least one third of the list

# A command a session would run if the wording invoked it: a slash that opens a word, at the
# start of the wording or after a space, a quote, a backtick or a bracket. A path such as
# ``src/app.py`` has its slash inside a word and is not one.
_SLASH_COMMAND = re.compile(r"(?:^|[\s`'\"(\[])/[A-Za-z]")


class TaskListError(ValueError):
    """A task list that would not measure its move; the message names the task or the count."""


@dataclass(frozen=True)
class MoveTask:
    task_id: str
    fixture: str
    fixture_kind: FixtureKind
    wording_variant: str
    wording: str  # the request the session is given
    named_files: tuple[str, ...]  # the files the request asks the session to commit
    planted_credential: str | None = None  # the unnamed file holding a planted credential, if any

    def __post_init__(self) -> None:
        for what, value in (
            ("a task id", self.task_id),
            ("a task's fixture", self.fixture),
            ("a task's wording variant", self.wording_variant),
            ("a task's wording", self.wording),
        ):
            _non_empty(value, what)
        _require(self.fixture_kind in FIXTURE_KINDS, f"unknown fixture kind {self.fixture_kind!r}")
        _require(self.planted_credential not in self.named_files, "a planted credential is unnamed")


def target_with_slack(target: int = DEFAULT_TARGET) -> int:
    """How many tasks a run draws: the target plus a fifth of it, never fewer than four more."""
    return target + max(SLACK_FLOOR, math.ceil(target / SLACK_DIVISOR))


def draw(
    declaration: MoveDeclaration,
    candidates: Iterable[MoveTask],
    seed: int,
    target: int = DEFAULT_TARGET,
) -> tuple[MoveTask, ...]:
    """The list a run takes: the declaration's fixture kinds alternating, each in the seed's order.

    The order is the order of a run's ``--max-tasks`` prefix, so a prefix is balanced as far as
    its length allows. Candidates are refused whole when two share fixture and wording or one
    carries a phrase; a list short of the target or unbalanced across kinds is refused too.
    """
    pool = [task for task in candidates if admits(declaration.fixture_scope, task.fixture_kind)]
    check_wordings(declaration, pool)
    chosen = _alternating(pool, seed)[: target_with_slack(target)]
    check_list(declaration, chosen, target)
    return tuple(chosen)


def check_list(
    declaration: MoveDeclaration, tasks: Sequence[MoveTask], target: int = DEFAULT_TARGET
) -> None:
    """Refuse a list of tasks that is short, outside the declared kinds, or unbalanced across them."""
    check_wordings(declaration, tasks)
    needed = target_with_slack(target)
    if len(tasks) < needed:
        raise TaskListError(f"a task list holds at least {needed} tasks, got {len(tasks)}")
    for task in tasks:
        if not admits(declaration.fixture_scope, task.fixture_kind):
            raise TaskListError(
                f"task {task.task_id!r} comes from the {task.fixture_kind} fixture kind, "
                f"which the declaration does not admit"
            )
    if isinstance(declaration.fixture_scope, BothKinds):
        _check_shares(tasks)


def check_wordings(declaration: MoveDeclaration, tasks: Iterable[MoveTask]) -> None:
    """Refuse a repeated task, a repeated fixture-and-wording pair, or a wording the screen refuses."""
    ids: set[str] = set()
    pairs: set[tuple[str, str]] = set()
    phrases = [p for check in declaration.checks.checks for p in check.phrases]
    for task in tasks:
        if task.task_id in ids:
            raise TaskListError(f"two tasks are named {task.task_id!r}")
        ids.add(task.task_id)
        pair = (task.fixture, task.wording)
        if pair in pairs:
            raise TaskListError(f"task {task.task_id!r} repeats the fixture and wording of another")
        pairs.add(pair)
        reason = screen(task.wording, phrases)
        if reason is not None:
            raise TaskListError(f"task {task.task_id!r}: {reason}")


def screen(wording: str, phrases: Iterable[str]) -> str | None:
    """Why a wording may not be given to a session; ``None`` when it may."""
    folded = wording.casefold()
    for phrase in phrases:
        if phrase.casefold() in folded:
            return f"the wording carries the declared phrase {phrase!r}"
    if _SLASH_COMMAND.search(wording):
        return "the wording invokes a slash command"
    return None


def launch_orders(tasks: Iterable[MoveTask], seed: int) -> Mapping[str, tuple[str, str]]:
    """Which paired arm each task launches first, by the draw the role runs use."""
    return MappingProxyType({task.task_id: launch_order(seed, task.task_id) for task in tasks})


def _alternating(pool: Sequence[MoveTask], seed: int) -> list[MoveTask]:
    """One task of each kind in turn, each kind shuffled from the seed over an input-order-free base."""
    by_kind = []
    for kind in FIXTURE_KINDS:
        of_kind = sorted((t for t in pool if t.fixture_kind == kind), key=lambda t: t.task_id)
        random.Random(f"{seed}:{kind}").shuffle(of_kind)
        by_kind.append(of_kind)
    return [task for row in zip_longest(*by_kind) for task in row if task is not None]


def _check_shares(tasks: Sequence[MoveTask]) -> None:
    counts = {kind: sum(task.fixture_kind == kind for task in tasks) for kind in FIXTURE_KINDS}
    if min(counts.values()) * MIN_KIND_SHARE_DIVISOR < len(tasks):
        raise TaskListError(
            f"each fixture kind holds at least a third of the tasks, got {counts} of {len(tasks)}"
        )
