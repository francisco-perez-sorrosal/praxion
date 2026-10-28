"""The move half of the ``praxion-evals-adherence`` entry: the options of a move, its dry run and its run.

The entry hands over every command line that names ``--move``, with the move already parsed into
a :class:`MoveSubject`; this module parses the rest of the move's options once and acts on them.
``--run floor|paired`` conducts the run through :mod:`~praxion_evals.adherence.moves.runner` and
prints where its results file went. Billing and caps are the role path's, option for option:
``--session-oauth-token-file`` bills the sessions to a subscription instead of the API key,
``--max-total-usd`` caps the run and ``--session-budget-usd`` caps each session (the
``--max-budget-usd`` it hands the harness).
``--dry-run`` prices the floor run and the paired run together, printing one line per session, one
per task, the totals and a calibration line (a move has no calibration run, so it is always
``sessions=0``), and launches and writes nothing. Tokens of a line contain no spaces:

    session <floor|paired> <task_id> <fixture> <managed|unmanaged> <wording_variant> <arm>
    task <floor|paired> <task_id> sessions=<n>
    total floor=<n> paired=<n> all=<n>
    calibration sessions=0

Exit codes follow the entry: 0 complete, 1 incomplete (the run stopped, a launch was refused for
spend or it was interrupted; its results file is written), 2 usage (a refusal names what it
refuses).

``report_text`` renders a results file that lives in ``moves/``; the entry routes ``--report`` there.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from praxion_evals.adherence.infra_stop import (
    COUNTING_KINDS,
    DEFAULT_STOP_COUNT,
    MIN_STOP_COUNT,
    StopRule,
)
from praxion_evals.adherence.lineage import Finished
from praxion_evals.adherence.moves import declaration as declarations
from praxion_evals.adherence.moves import report, results, runner
from praxion_evals.adherence.moves.model import ARMS_OF, MoveDeclaration, MoveName, RunKind
from praxion_evals.adherence.moves.tasks import MoveTask
from praxion_evals.adherence.session_launch import DEFAULT_TAIL_CHARS
from praxion_evals.adherence.session_loop import (
    OUTPUT_DIR,
    launch_order,
    query_claude_version,
)
from praxion_evals.live.report import CREDENTIAL_KEYS
from praxion_evals.live.spend import RUNNER_SPEND_CAP_USD

PROG = "praxion-evals-adherence"
EXIT_COMPLETE = 0
EXIT_INCOMPLETE = 1
EXIT_USAGE = 2
# The role entry's defaults, so a move run draws the same orders and bills and pins the same as a
# role run; ``test_moves_cli`` pins each to its twin there.
DEFAULT_SEED = 7
DEFAULT_MARGIN_PP = 10.0
DEFAULT_SESSION_BUDGET_USD = 3.0
DEFAULT_MODEL = "opus"
DEFAULT_EFFORT = "medium"
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
    run_cap_usd: float
    session_budget_usd: float
    session_oauth_token_file: Path | None


def move_subject(text: str) -> MoveSubject:
    """An option value naming a move; a name no move can have is a usage error."""
    try:
        return MoveSubject(MoveName(text))
    except ValueError as error:
        raise argparse.ArgumentTypeError(str(error)) from error


def main(subject: MoveSubject, argv: Sequence[str] | None = None) -> int:
    options = _parse(argv)
    try:
        checkout = _checkout(options.checkout)
        declared = _declaration(subject, options, checkout)
        if options.dry_run:
            print("\n".join(dry_run_lines(options, declared)))
            return EXIT_COMPLETE
        conducted = runner.conduct(_plan(options, declared, checkout))
    except (ValueError, OSError) as error:
        print(f"{PROG}: {error}", file=sys.stderr)
        return EXIT_USAGE
    ending = conducted.run.common.ending
    print(f"{conducted.run.run_kind} run {conducted.run.common.run_id} ended {_word(ending)}")
    print(f"results: {conducted.path}")
    return EXIT_COMPLETE if isinstance(ending, Finished) else EXIT_INCOMPLETE


def _word(ending: object) -> str:
    return type(ending).__name__.lower()


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
        args.run_cap_usd,
        args.session_budget_usd,
        args.session_oauth_token_file,
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
    add(
        "--max-total-usd",
        dest="run_cap_usd",
        type=_above_zero,
        default=RUNNER_SPEND_CAP_USD,
        help="what the run may spend",
    )
    add(
        "--session-budget-usd",
        type=_above_zero,
        default=DEFAULT_SESSION_BUDGET_USD,
        help="what one session may spend",
    )
    add(
        "--session-oauth-token-file",
        type=Path,
        help="a `claude setup-token` file: sessions bill its subscription, never the API key",
    )
    return parser


def _at_least(minimum: int) -> Callable[[str], int]:
    def parse(raw: str) -> int:
        value = int(raw)
        if value < minimum:
            raise argparse.ArgumentTypeError(f"must be at least {minimum}, got {raw}")
        return value

    return parse


def _above_zero(raw: str) -> float:
    value = float(raw)
    if value <= 0:
        raise argparse.ArgumentTypeError(f"must be above 0.0, got {raw}")
    return value


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


# --- --run: what one run is told, once, before it launches ---


def _plan(options: MoveOptions, declared: MoveDeclaration, checkout: Path) -> runner.RunPlan:
    assert options.run is not None  # _parse leaves no run kind only on a dry run
    if not any(os.environ.get(key) for key in CREDENTIAL_KEYS):
        raise ValueError(
            f"no credential in the environment; set one of {', '.join(CREDENTIAL_KEYS)}"
        )
    return runner.RunPlan(
        declaration=declared,
        kind=options.run,
        checkout=checkout,
        moves_dir=checkout / OUTPUT_DIR / results.MOVES_DIR_NAME,
        seed=options.seed,
        stop_rule=StopRule.parse(options.stop_count, COUNTING_KINDS, DEFAULT_TAIL_CHARS),
        harness_version=query_claude_version(),
        margin_pp=DEFAULT_MARGIN_PP,
        session_budget_usd=options.session_budget_usd,
        run_cap_usd=options.run_cap_usd,
        ambient=dict(os.environ),
        model=DEFAULT_MODEL,
        effort=DEFAULT_EFFORT,
        max_tasks=options.max_tasks,
        floor_run=_run_id(options.floor_run),
        session_token_file=options.session_oauth_token_file,
    )


def _run_id(cited: str | None) -> str | None:
    """The run a ``--floor-run`` names: a results file is named by its run id."""
    return None if cited is None else Path(cited).name.removesuffix(".json")


# --- --report: a results file that lives in moves/ ---


def is_move_results(path: Path) -> bool:
    """A results file is a move's by the directory it lives in, the one place a move writes."""
    return path.resolve().parent.name == results.MOVES_DIR_NAME


def report_text(path: Path) -> str:
    """The report of the move results file ``path``, headed by the move it measures.

    The governed checks, the tasks' fixture kinds and the fixture restriction are the kit's own
    declaration for the move; a paired run's floor figures come from the floor parts it cites,
    read from beside it.
    """
    run = results.load(path)
    common = run.common
    declared = declarations.kit(common.move.value)
    tasks = runner.KITS[common.move.value].tasks(declared, common.seed)
    match run:
        case results.FloorRun():
            pairs, floor = (), common.sessions
        case results.PairedRun():
            pairs, floor = common.sessions, _floor_sessions(path.parent, run.cited_floor)
    measured = runner.measurement(
        declared,
        common.settings.margin_pp,
        common.settings.required_pairs,
        tasks,
        pairs,
        floor,
    )
    heading = f"Move {common.move.value}: {run.run_kind} run {common.run_id}"
    return f"{heading}\n\n{report.render(measured)}"


def _floor_sessions(directory: Path, cited: Sequence[str]) -> list[results.MoveSession]:
    return [s for part in cited for s in results.load(directory / f"{part}.json").common.sessions]


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
