"""The move half of the ``praxion-evals-adherence`` entry: the options of a move and its dry run.

The entry hands over every command line that names ``--move``, with the move already parsed into
a :class:`MoveSubject`; this module parses the rest of the move's options once and acts on them.
``--dry-run`` prices the floor run and the paired run together, printing one line per session, one
per task, the totals and a calibration line (a move has no calibration run, so it is always
``sessions=0``), and launches and writes nothing. Tokens of a line contain no spaces:

    session <floor|paired> <task_id> <fixture> <managed|unmanaged> <wording_variant> <arm>
    task <floor|paired> <task_id> sessions=<n>
    total floor=<n> paired=<n> all=<n>
    calibration sessions=0

Exit codes follow the entry: 0 complete, 2 usage (a refusal names what it refuses).
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from praxion_evals.adherence.infra_stop import DEFAULT_STOP_COUNT, MIN_STOP_COUNT
from praxion_evals.adherence.moves import declaration as declarations
from praxion_evals.adherence.moves import runner
from praxion_evals.adherence.moves.model import ARMS_OF, MoveDeclaration, MoveName, RunKind
from praxion_evals.adherence.moves.tasks import MoveTask
from praxion_evals.adherence.session_loop import launch_order

PROG = "praxion-evals-adherence"
EXIT_COMPLETE = 0
EXIT_USAGE = 2
DEFAULT_SEED = 7  # the role entry's default, so one seed draws the same launch orders in both
RUN_KINDS: tuple[RunKind, ...] = ("floor", "paired")
ARMS_PER_TASK = {kind: len(ARMS_OF[kind]) for kind in RUN_KINDS}


@dataclass(frozen=True)
class MoveSubject:
    """What the entry measures when it measures a move, never a role."""

    move: MoveName


@dataclass(frozen=True)
class MoveOptions:
    """The options of a move run, after the entry's own checks; a dry run names no run kind."""

    checkout: Path | None
    run: RunKind | None
    floor_run: str | None
    declaration: Path | None
    max_tasks: int | None
    stop_count: int
    seed: int
    dry_run: bool


def move_subject(text: str) -> MoveSubject:
    """An option value naming a move; a name no move can have is a usage error."""
    try:
        return MoveSubject(MoveName(text))
    except ValueError as error:
        raise argparse.ArgumentTypeError(str(error)) from error


def main(subject: MoveSubject, argv: Sequence[str] | None = None) -> int:
    options = _parse(argv)
    try:
        if not options.dry_run:
            raise ValueError(
                "a move run is launched with --run floor|paired, which is not wired yet"
            )
        checkout = _checkout(options.checkout)
        lines = dry_run_lines(options, _declaration(subject, options, checkout))
    except (ValueError, OSError) as error:
        print(f"{PROG}: {error}", file=sys.stderr)
        return EXIT_USAGE
    print("\n".join(lines))
    return EXIT_COMPLETE


# --- argv, parsed once ---


def _parse(argv: Sequence[str] | None) -> MoveOptions:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.dry_run and (args.run or args.floor_run):
        parser.error("--dry-run prices both runs; it takes no --run or --floor-run")
    if not args.dry_run and args.run is None:
        parser.error("name the run: --run floor|paired, or --dry-run to price both")
    if args.floor_run and args.run != "paired":
        parser.error("--floor-run names the floor run a paired run cites; it needs --run paired")
    return MoveOptions(
        args.checkout,
        args.run,
        args.floor_run,
        args.declaration,
        args.max_tasks,
        args.stop_count,
        args.seed,
        args.dry_run,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=PROG, description="Measure whether a move keeps a session on process."
    )
    add = parser.add_argument
    add("checkout", nargs="?", type=Path, help="default: this repository's root")
    add("--move", type=move_subject, required=True, help="the move to measure")
    add(
        "--run", choices=RUN_KINDS, help="floor: no line of the rule anywhere; paired: full vs lean"
    )
    add("--floor-run", help="the floor run (a results file or run id) a paired run cites")
    add("--declaration", type=Path, help="a declaration file in place of the kit's own")
    add("--max-tasks", type=_at_least(1), help="cap the tasks of each run below its default")
    add("--stop-count", type=_at_least(MIN_STOP_COUNT), default=DEFAULT_STOP_COUNT)
    add("--seed", type=int, default=DEFAULT_SEED)
    add("--dry-run", action="store_true", help="print the sessions of both runs; launch nothing")
    return parser


def _at_least(minimum: int) -> Callable[[str], int]:
    def parse(raw: str) -> int:
        value = int(raw)
        if value < minimum:
            raise argparse.ArgumentTypeError(f"must be at least {minimum}, got {raw}")
        return value

    return parse


# --- what the run reads, before anything launches ---


def _checkout(given: Path | None) -> Path:
    if given is not None:
        return given.resolve()
    done = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=False
    )
    if done.returncode != 0:
        raise ValueError("no checkout named and the working directory is not in a git checkout")
    return Path(done.stdout.strip())


def _declaration(subject: MoveSubject, options: MoveOptions, checkout: Path) -> MoveDeclaration:
    name = subject.move.value
    if options.declaration is None:
        return declarations.kit(name, checkout)
    declared = declarations.load(options.declaration, checkout)
    if declared.move != subject.move:
        raise ValueError(
            f"{options.declaration} declares the move {declared.move.value}, not {name}"
        )
    return declared


# --- --dry-run: the sessions both runs would launch ---


def dry_run_lines(options: MoveOptions, declaration: MoveDeclaration) -> list[str]:
    """Every session of the floor run, then of the paired run, with the counts; pure."""
    kit = runner.KITS.get(declaration.move.value)
    if kit is None:
        raise ValueError(
            f"the {declaration.move.value} move has no task kit, so no run of it exists"
        )
    drawn = kit.tasks(declaration, options.seed)
    planned = {kind: runner.planned_tasks(kind, drawn, options.max_tasks) for kind in RUN_KINDS}
    lines = [
        line
        for kind in RUN_KINDS
        for task in planned[kind]
        for line in _task_lines(kind, task, options.seed)
    ]
    sessions = {kind: ARMS_PER_TASK[kind] * len(planned[kind]) for kind in RUN_KINDS}
    total = (
        f"total floor={sessions['floor']} paired={sessions['paired']} all={sum(sessions.values())}"
    )
    return [*lines, total, "calibration sessions=0"]


def _task_lines(kind: RunKind, task: MoveTask, seed: int) -> list[str]:
    arms = launch_order(seed, task.task_id) if kind == "paired" else ARMS_OF[kind]
    sessions = [
        f"session {kind} {task.task_id} {task.fixture} {task.fixture_kind} "
        f"{task.wording_variant} {arm}"
        for arm in arms
    ]
    return [f"task {kind} {task.task_id} sessions={len(sessions)}", *sessions]
