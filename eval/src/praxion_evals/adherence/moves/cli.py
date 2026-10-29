"""The move half of the ``praxion-evals-adherence`` entry: the options of a move, its dry run and its run.

The entry hands over every command line that names ``--move``, with the move already parsed into
a :class:`MoveSubject`; this module parses the rest of the move's options once and acts on them.
``--run floor|paired`` conducts the run through :mod:`~praxion_evals.adherence.moves.runner` and
prints where its results file went. Billing and caps are the role path's, option for option:
``--session-oauth-token-file`` bills the sessions to a subscription instead of the API key,
``--max-total-usd`` caps the run and ``--session-budget-usd`` caps each session (the
``--max-budget-usd`` it hands the harness).
``--continue RUN`` picks up the stopped run RUN and ``--close RUN --reason TEXT`` gives up on it, each
finding the run by its file in ``moves/``, so the entry routes them here without ``--move``; a
continuation declares what the run declared and launches again only the planned tasks no part
finished. ``--reindex`` rebuilds the index beside the move results files. A fresh run is refused
while a stopped run of its move is neither continued nor closed, and so is a continuation that
would measure something else; either way nothing is launched or written.
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
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

from praxion_evals.adherence.infra_stop import (
    COUNTING_KINDS,
    DEFAULT_STOP_COUNT,
    MIN_STOP_COUNT,
    StopRule,
)
from praxion_evals.adherence.lineage import Finished
from praxion_evals.adherence.moves import declaration as declarations
from praxion_evals.adherence.moves import lineage, report, results, runner
from praxion_evals.adherence.moves.model import ARMS_OF, MoveDeclaration, MoveName, RunKind
from praxion_evals.adherence.moves.tasks import MoveTask
from praxion_evals.adherence.session_launch import DEFAULT_TAIL_CHARS
from praxion_evals.adherence.session_loop import (
    OUTPUT_DIR,
    launch_order,
    query_claude_version,
)
from praxion_evals.live.report import require_credential
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
# Named on the command line but not options of the run a continuation may be refused over.
NOT_AN_OPTION_OF_THE_RUN = frozenset({"checkout", "move", "continue_run"})
ARMS_PER_TASK = {kind: len(ARMS_OF[kind]) for kind in RUN_KINDS}


@dataclass(frozen=True)
class MoveSubject:
    """What the entry measures when it measures a move, never a role."""

    move: MoveName


@dataclass(frozen=True)
class MoveOptions:
    """The options of a move command, after the entry's own checks; a dry run names no run kind,
    and ``--continue``, ``--close`` and ``--reindex`` name no run to start."""

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
    continue_run: str | None
    close_run: str | None
    reason: str | None
    reindex: bool
    given: tuple[str, ...]  # each option the command line named, as spelled there


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
        if options.reindex:
            return reindex(checkout / OUTPUT_DIR)
        if options.close_run is not None:
            return _close(_moves_dir(checkout), options.close_run, options.reason or "")
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


def run_subject(argv: Sequence[str] | None) -> MoveSubject | None:
    """The move of the run ``--continue`` or ``--close`` names when its results file lives in
    ``moves/``, else ``None``: the entry leaves a run elsewhere to the role path."""
    args = _parser().parse_known_args(argv)[0]
    named = args.continue_run or args.close_run
    if named is None:
        return None
    try:
        path = _moves_dir(_checkout(args.checkout)) / f"{named}.json"
        return MoveSubject(results.load(path).common.move) if path.exists() else None
    except (ValueError, OSError):
        return None  # the role path names what is wrong with the command line


def reindex(results_dir: Path) -> int:
    """Rebuild the index beside the move results files under ``results_dir``, if there are any."""
    moves_dir = results_dir / results.MOVES_DIR_NAME
    if moves_dir.is_dir():
        print(f"indexed {moves_dir}: {results.write_index(moves_dir).name}")
    return EXIT_COMPLETE


def _word(ending: object) -> str:
    return type(ending).__name__.lower()


# --- argv, parsed once ---


def _parse(argv: Sequence[str] | None) -> MoveOptions:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.continue_run and (args.close_run or args.run or args.floor_run or args.dry_run):
        parser.error("--continue RUN takes no --run, --floor-run, --close or --dry-run")
    if args.close_run and (args.run or args.floor_run or args.dry_run):
        parser.error("--close RUN takes no --run, --floor-run or --dry-run")
    if (args.close_run is None) != (args.reason is None):
        parser.error("--close RUN and --reason TEXT go together: a run is closed with a reason")
    if args.dry_run and (args.run or args.floor_run):
        parser.error("--dry-run prices both runs; it takes no --run or --floor-run")
    starts_run = not (args.dry_run or args.continue_run or args.close_run or args.reindex)
    if starts_run and args.run is None:
        parser.error("name the run: --run floor|paired, or --dry-run to price both")
    if args.floor_run and args.run != "paired":
        parser.error("--floor-run names the floor run a paired run cites; it needs --run paired")
    return MoveOptions(
        checkout=args.checkout,
        run=args.run,
        floor_run=args.floor_run,
        declaration=args.declaration,
        max_tasks=args.max_tasks,
        stop_count=args.stop_count,
        seed=args.seed,
        dry_run=args.dry_run,
        run_cap_usd=args.run_cap_usd,
        session_budget_usd=args.session_budget_usd,
        session_oauth_token_file=args.session_oauth_token_file,
        continue_run=args.continue_run,
        close_run=args.close_run,
        reason=args.reason,
        reindex=args.reindex,
        given=_given(argv),
    )


def _given(argv: Sequence[str] | None) -> tuple[str, ...]:
    """Each option ``argv`` names beside the move and the run it continues, as spelled there."""
    parser = _parser()
    actions = parser._actions  # argparse lists its actions only privately
    for action in actions:
        action.default = argparse.SUPPRESS  # an option argv does not name is left out
    named = vars(parser.parse_args(argv))
    spelling = {action.dest: (action.option_strings or [action.dest])[0] for action in actions}
    return tuple(spelling[dest] for dest in named if dest not in NOT_AN_OPTION_OF_THE_RUN)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=PROG, description="Measure whether a move keeps a session on process."
    )
    add = parser.add_argument
    add("checkout", nargs="?", type=Path, help="default: this repository's root")
    add("--move", type=move_subject, help="the move to measure")
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
    add("--continue", dest="continue_run", metavar="RUN", help="pick up the stopped run RUN")
    add("--close", dest="close_run", metavar="RUN", help="give up on the stopped run RUN")
    add("--reason", help="why --close gives up on the run")
    add("--reindex", action="store_true", help="rebuild the index of the move results files")
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
    """The plan of a fresh run, or of the continuation ``options`` names, which takes what the
    stopped run declared in place of the kind, seed, stop count and the like given here."""
    plan = _fresh_plan(options, declared, checkout)
    if options.continue_run is None:
        return plan
    return runner.continuing(plan, options.continue_run, options.given)


def _fresh_plan(options: MoveOptions, declared: MoveDeclaration, checkout: Path) -> runner.RunPlan:
    require_credential(os.environ, options.session_oauth_token_file)
    return runner.RunPlan(
        declaration=declared,
        kind=options.run or "floor",  # a continuation's kind is its run's, set by ``continuing``
        checkout=checkout,
        moves_dir=_moves_dir(checkout),
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


def _moves_dir(checkout: Path) -> Path:
    return checkout / OUTPUT_DIR / results.MOVES_DIR_NAME


def _close(moves_dir: Path, run_id: str, reason: str) -> int:
    """Write the closing ending into the stopped run's own results file."""
    parts, continued_by = runner.read_lineage(moves_dir, run_id)
    run = parts[-1]
    tip = lineage.ReadTip(run_id, run.common.ending, run.common.identity, continued_by)
    ending = lineage.close(tip, reason, datetime.now(UTC), runner.interim(run))
    results.write(moves_dir, replace(run, common=replace(run.common, ending=ending)))
    print(f"closed run {run_id}: {reason}")
    return EXIT_COMPLETE


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
    read from beside it. A continued run reports the sessions of its whole lineage.
    """
    run = results.load(path)
    common = run.common
    declared = declarations.kit(common.move.value)
    tasks = runner.KITS[common.move.value].tasks(declared, common.seed)
    held = tuple(
        s
        for part in runner.read_lineage(path.parent, common.run_id)[0]
        for s in part.common.sessions
    )
    match run:
        case results.FloorRun():
            pairs, floor = (), held
        case results.PairedRun():
            pairs, floor = held, _floor_sessions(path.parent, run.cited_floor)
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
