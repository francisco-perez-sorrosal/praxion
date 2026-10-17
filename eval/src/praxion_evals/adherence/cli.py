"""``praxion-evals-adherence``: the adherence eval's opt-in console entry.

Every session costs money, so this entry is the only way to reach the eval and no
other module imports it. argv is parsed once into a frozen ``RunConfig``; then
``--report FILE`` renders a results file, ``--dry-run`` prints the sessions a paid
run would launch (through the same ``session_spec``/``build_argv``/``build_env``
path) and writes nothing, and a paid run is handed to
:mod:`~praxion_evals.adherence.session_loop` with the settings it declares.

Exit codes: 0 the run is complete; 1 it is incomplete (a refused launch, an arm that
could not be built or proven, a session that ended in error; the results are
written); 2 usage.

A fresh run of a role is refused, before anything launches, while a run of that role stopped
and was neither continued nor closed; ``--close RUN --reason TEXT`` is how an operator who
will not continue it says so. ``--continue RUN`` starts a later part of the stopped run: it
declares what the run declared and launches again only the tasks no part finished, and it is
refused before anything launches, naming every reason, unless the run stopped continuably and
every option given beside it restates what the run declared.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from praxion_evals.adherence import arms, report, results, session_loop, tasks
from praxion_evals.adherence.infra_stop import (
    COUNTING_KINDS,
    DEFAULT_STOP_COUNT,
    MIN_STOP_COUNT,
    StopRule,
)
from praxion_evals.adherence.lineage import (
    Lineage,
    ReadTip,
    Tip,
    UnreadableTip,
    close,
    continuation_refusals,
    ending_to_json,
    measured_identity,
    pending_stop,
    relaunch_tasks,
)
from praxion_evals.adherence.model import (
    ARMS,
    OWN_DISCORDANCE_EXACT,
    ROLES,
    Arm,
    ArmBuild,
    DeclaredSettings,
    Role,
    TaskSpec,
)
from praxion_evals.adherence.run_ending import Continuation
from praxion_evals.adherence.run_identity import (
    MeasuredIdentity,
    role_identity,
    tree_digest,
    working_tree,
)
from praxion_evals.adherence.session_loop import (
    DEFAULT_TAIL_CHARS,
    EXIT_COMPLETE,
    OUTPUT_DIR,
    RETRY_POLICY,
    SANDBOX_PREFIX,
    Checkout,
    Context,
    RunConfig,
    RunState,
    ordered_arms,
    planned_order,
    resolve_checkout,
    session_env,
)
from praxion_evals.live.session import SandboxPaths, SessionSpec, build_argv
from praxion_evals.live.spend import RUNNER_SPEND_CAP_USD

PROG = "praxion-evals-adherence"
EXIT_USAGE = 2
DEFAULT_SEED = 7
DEFAULT_MARGIN_PP = 10.0
DEFAULT_CONFIDENCE = 0.95
DEFAULT_SESSION_BUDGET_USD = 3.0
DEFAULT_MODEL = "opus"  # the live runner's defaults
DEFAULT_EFFORT = "medium"
CALIBRATION_RUN_NOTE = (
    "a calibration file sets no allowance (each run sizes its own from its discordant pairs)"
)


def main(argv: Sequence[str] | None = None) -> int:
    config = parse_config(argv)
    if config.calibration_run is not None:
        print(f"{PROG}: --calibration-run: {CALIBRATION_RUN_NOTE}", file=sys.stderr)
    try:
        if config.report is not None:
            print(report.render(results.load(config.report)), end="")
            return EXIT_COMPLETE
        checkout = resolve_checkout(config)
        if config.close is not None:
            return _close_run(config, checkout, config.close, config.reason or "")
        if config.output is not None:
            results.refuse_existing(config.output, config.overwrite)
        if config.continue_run is not None:
            context, state = _begin_continuation(config, checkout, given_options(argv))
        else:
            planned = plan_tasks(config)
            if config.dry_run:
                return _print_dry_run(config, checkout, planned)
            _refuse_beside_stopped_run(config)
            context, state = session_loop.begin(config, checkout, planned, _declare)
    except (ValueError, OSError) as error:  # everything before the first launch is a usage error
        print(f"{PROG}: {error}", file=sys.stderr)
        return EXIT_USAGE
    return session_loop.conduct(context, state)


# --- argv, parsed once ---


def parse_config(argv: Sequence[str] | None) -> RunConfig:
    parser = _parser()
    args = vars(parser.parse_args(argv))
    if args["calibration"] and set(args["arms"] or ["full"]) != {"full"}:
        parser.error("a calibration run measures the full arm against itself; use --arm full")
    named = {"full"} if args["calibration"] else set(args["arms"] or ARMS)
    if not (args["roles"] or args["report"] or args["close"] or args["continue_run"]):
        parser.error("name at least one --role, --report FILE, --close RUN or --continue RUN")
    if args["continue_run"] and (args["report"] or args["close"] or args["dry_run"]):
        parser.error(
            "--continue RUN launches the stopped run's unfinished tasks;"
            " it takes no --report, --close or --dry-run"
        )
    if (args["close"] is None) != (args["reason"] is None):
        parser.error(
            "--close RUN and --reason TEXT go together: a stopped run is closed with a reason"
        )
    if args["judge_golden"] and not args["judging"]:
        parser.error("--judge-golden needs a judge; drop --no-judge")
    args["roles"] = tuple(dict.fromkeys(args["roles"] or ()))
    args["arms"] = tuple(arm for arm in ("full", "lean") if arm in named)
    if args["pair_slack"] is None:
        args["pair_slack"] = default_slack(args["required_pairs"])
    config = RunConfig(**args)
    try:
        declared_settings(config)  # the settings' own ranges are the options' ranges
    except ValueError as error:
        parser.error(str(error))
    return config


def default_slack(required_pairs: int) -> int:
    """Tasks above the target that absorb the ones a run drops: a fifth of it, at least four."""
    return max(tasks.SLACK_FLOOR, math.ceil(required_pairs / tasks.SLACK_DIVISOR))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=PROG,
        description="Measure whether a Praxion role keeps its process without the inherited "
        "context layer (spends API money; see eval/EVAL_PLAN.md).",
    )
    add = parser.add_argument
    add("checkout", nargs="?", type=Path, help="default: this repository's root")
    add("--role", dest="roles", action="append", choices=ROLES, help="repeatable")
    add("--arm", dest="arms", action="append", choices=ARMS, help="repeatable; default both")
    add("--output", type=Path, help=f"default: <repo>/{OUTPUT_DIR}/<run-id>.json")
    add("--seed", type=int, default=DEFAULT_SEED)
    add(
        "--max-total-usd",
        dest="run_cap_usd",
        type=_number(float, 0.0, above=True),
        default=RUNNER_SPEND_CAP_USD,
    )
    add(
        "--session-budget-usd",
        type=_number(float, 0.0, above=True),
        default=DEFAULT_SESSION_BUDGET_USD,
    )
    add("--margin-pp", type=float, default=DEFAULT_MARGIN_PP)
    add("--required-pairs", type=_number(int, 1), default=tasks.DEFAULT_TARGET)
    add("--pair-slack", type=_number(int, 0), default=None)
    add(
        "--max-tasks",
        type=_number(int, 1),
        help="cap the tasks per role below the target plus slack; the target is unchanged, "
        "so a run capped under its target is underpowered by construction (a smoke run)",
    )
    add("--confidence", type=float, default=DEFAULT_CONFIDENCE)
    add("--no-judge", dest="judging", action="store_false")
    add("--model", default=DEFAULT_MODEL)
    add("--effort", default=DEFAULT_EFFORT)
    add("--keep-sandbox", action="store_true")
    add(
        "--session-oauth-token-file",
        type=Path,
        help="a `claude setup-token` file: sessions bill its subscription, the judge keeps the API key",
    )
    add(
        "--stop-count",
        type=int,
        default=DEFAULT_STOP_COUNT,
        help="stop the run after this many identical infrastructure failures of one arm in a "
        f"row; at least {MIN_STOP_COUNT}, so one task's session and its retry cannot stop it",
    )
    add(
        "--tail-chars",
        type=_number(int, 1),
        default=DEFAULT_TAIL_CHARS,
        help="the end of an errored session's output kept as its evidence, per stream",
    )
    add("--dry-run", action="store_true")
    add("--overwrite", action="store_true")
    noise = parser.add_mutually_exclusive_group()
    noise.add_argument(
        "--calibration",
        action="store_true",
        help="run the full arm against itself, a diagnostic of the slot order",
    )
    noise.add_argument(
        "--calibration-run",
        type=Path,
        help=f"accepted for old command lines; {CALIBRATION_RUN_NOTE}",
    )
    add("--judge-golden", action="store_true")
    add("--report", type=Path, help="render a results file; launch nothing")
    add("--close", metavar="RUN", help="give up on the stopped run RUN, saying why; launch nothing")
    add("--reason", help="why --close gives up on the run")
    add(
        "--continue",
        dest="continue_run",
        metavar="RUN",
        help="launch again the unfinished tasks of the stopped run RUN, as it declared them",
    )
    add("--fixture-pages-base-url", help="the directory URL that serves the fixture page")
    return parser


def _number[N: (int, float)](
    kind: type[N], minimum: N, *, above: bool = False
) -> Callable[[str], N]:
    """An option value of ``kind`` that is at least ``minimum`` (``above``: strictly more)."""

    def parse(raw: str) -> N:
        value = kind(raw)
        if value < minimum or (above and value == minimum):
            bound = f"above {minimum}" if above else f"at least {minimum}"
            raise argparse.ArgumentTypeError(f"must be {bound}, got {raw}")
        return value

    return parse


# --- what the run declares and plans, before anything launches ---


def declared_settings(config: RunConfig) -> DeclaredSettings:
    """The settings every new run declares: its own discordant count sizes each mechanical
    allowance, so no allowance is declared and no calibration file supplies one."""
    return DeclaredSettings(
        margin_pp=config.margin_pp,
        method="tango-score",
        confidence=config.confidence,
        sidedness="one-sided",
        required_pairs=config.required_pairs,
        pair_slack=config.pair_slack,
        retry_policy=RETRY_POLICY,
        allowance_source=None,
        allowances={},
        allowance_method=OWN_DISCORDANCE_EXACT,
        stop_rule=StopRule.parse(config.stop_count, COUNTING_KINDS, config.tail_chars),
    )


def _declare(
    config: RunConfig, checkout: Checkout, planned: Mapping[Role, Sequence[TaskSpec]]
) -> DeclaredSettings:
    """The settings a paid run declares; the session loop hands every run's context to its declarer."""
    return declared_settings(config)


def plan_tasks(config: RunConfig) -> dict[Role, list[TaskSpec]]:
    """Target plus slack for a full-set role, smoke tasks otherwise, capped by ``--max-tasks``.

    Never more than exist. The cap leaves the declared target alone, so a run capped under
    its target cannot reach it and is reported underpowered.
    """
    plan = {}
    for role in config.roles:
        wanted = config.required_pairs + config.pair_slack
        wanted = wanted if role in tasks.FULL_SET_ROLES else tasks.SMOKE_TASKS
        if config.max_tasks is not None:
            wanted = min(wanted, config.max_tasks)
        count = min(wanted, tasks.producible_task_count(role, config.seed))
        plan[role] = tasks.generate(role, config.seed, count)
    return plan


# --- a stopped run is continued or closed, never left beside a fresh one ---


def _refuse_beside_stopped_run(config: RunConfig) -> None:
    """A fresh run of a role cannot start while a run of it stopped and was neither continued
    nor closed: a new draw beside it would leave the stopped run to be forgotten."""
    directory = session_loop.results_dir(config)
    for role in config.roles:
        if (stopped := pending_stop(directory, role)) is not None:
            raise ValueError(
                f"run {stopped.run_id} of {role} stopped and was neither continued nor closed;"
                f" continue it (--continue {stopped.run_id}) or close it"
                f" (--close {stopped.run_id} --reason TEXT) before starting a fresh run"
            )


def _close_run(config: RunConfig, checkout: Checkout, run_id: str, reason: str) -> int:
    """Write the closed ending into the stopped run's own results file."""
    tip, path, _ = _read_part(session_loop.results_dir(config), run_id, checkout.path)
    ending = close(tip, reason, datetime.now(UTC))
    recorded = tip.results
    extra = {**recorded.run.extra, "ending": ending_to_json(ending)}
    results.write_atomic(path, replace(recorded, run=replace(recorded.run, extra=extra)))
    print(f"closed run {run_id}: {reason}")
    return EXIT_COMPLETE


def _read_part(
    directory: Path, run_id: str, repo: Path
) -> tuple[ReadTip, Path, tuple[results.RunResults, ...]]:
    """The run ``run_id`` as the part of its lineage it is: read, its file, and the parts of the
    lineage up to it, oldest first. A missing run, a fork and a gap are refused."""
    lineage = Lineage.parse(directory, run_id)
    ids = [part.run_id for part in lineage.parts]
    at = ids.index(run_id)
    parts = tuple(results.load(part.path) for part in lineage.parts[: at + 1])
    continued_by = ids[at + 1] if at + 1 < len(ids) else None
    tip = ReadTip(parts[-1], measured_identity(parts[-1], repo), continued_by)
    return tip, lineage.parts[at].path, parts


# --- --continue RUN: a later part of a stopped run ---


def _begin_continuation(
    config: RunConfig, checkout: Checkout, given: Mapping[str, str]
) -> tuple[Context, RunState]:
    """Start a later part of the stopped run ``config.continue_run``, or refuse naming why.

    The part declares what the run's first part declared and launches again, whole in every arm
    and in the seed's order, only the tasks no part finished; it builds and proves its arms like
    any run. Nothing launches before every refusal is ruled out.
    """
    run_id, repo = config.continue_run, checkout.path
    assert run_id is not None  # main hands over only a config that names the run to continue
    tip, parts = _read_tip(session_loop.results_dir(config), run_id, repo)
    if isinstance(tip, UnreadableTip):
        raise _refused(run_id, continuation_refusals(tip, identity_now(config, {}, repo), ()))
    declared = recorded_config(config, parts[0])
    planned = _replanned(declared, parts[0])
    changed = _changed_options(given, config, declared, parts[0])
    if refusals := continuation_refusals(tip, identity_now(declared, planned, repo), changed):
        raise _refused(run_id, refusals)
    again = {role: relaunch_tasks(tip.results, role, parts[:-1]) for role in planned}
    launched: dict[Role, list[TaskSpec]] = {
        role: [task for task in specs if task.task_id in again[role]]
        for role, specs in planned.items()
        if again[role]
    }
    settings = parts[0].settings

    def first_part_settings(*_: object) -> DeclaredSettings:
        return settings

    continuation = Continuation.of(parts)
    return session_loop.begin(declared, checkout, launched, first_part_settings, continuation)


def _refused(run_id: str, refusals: Sequence[str]) -> ValueError:
    return ValueError(f"run {run_id} cannot be continued:" + "".join(f"\n  {r}" for r in refusals))


def _read_tip(
    directory: Path, run_id: str, repo: Path
) -> tuple[Tip, tuple[results.RunResults, ...]]:
    """The run to continue and the parts of its lineage up to it; no parts when its results file
    cannot be read."""
    named = directory / f"{run_id}.json"
    try:
        if named.exists():
            results.load(named)
    except (OSError, ValueError, KeyError, TypeError) as error:
        return UnreadableTip(named, f"{type(error).__name__}: {error}"), ()
    tip, _, parts = _read_part(directory, run_id, repo)
    return tip, parts


def recorded_config(config: RunConfig, first: results.RunResults) -> RunConfig:
    """``config`` with every declaration the run's first part recorded in place of its own."""
    extra, settings = first.run.extra, first.settings
    rule = settings.stop_rule
    stop = {} if rule is None else {"stop_count": rule.count, "tail_chars": rule.tail_chars}
    try:
        return replace(
            config,
            roles=tuple(extra["roles"]),
            arms=tuple(extra["arms"]),
            seed=extra["seed"],
            margin_pp=settings.margin_pp,
            required_pairs=settings.required_pairs,
            pair_slack=settings.pair_slack,
            confidence=settings.confidence,
            judging=extra["judging"],
            model=first.run.model,
            effort=extra["effort"],
            calibration=extra["calibration"],
            judge_golden=first.golden_bad_case_verdicts is not None,
            max_tasks=None,  # the planned tasks are recorded; the cap that chose them is not
            **stop,
        )
    except KeyError as missing:
        raise ValueError(f"run {first.run.id} does not record {missing}") from missing


def _replanned(declared: RunConfig, first: results.RunResults) -> dict[Role, list[TaskSpec]]:
    """The run's planned tasks as the generator builds them now from the recorded seed and
    count; the identity check compares their ids with the recorded ones."""
    recorded = first.run.extra["tasks"]
    return {
        role: tasks.generate(role, declared.seed, len(recorded.get(role, ())))
        for role in declared.roles
    }


def _changed_options(
    given: Mapping[str, str], config: RunConfig, declared: RunConfig, first: results.RunResults
) -> tuple[str, ...]:
    """The options named beside ``--continue`` that would change what the run declared.

    An option that restates a recorded declaration, or sets what a run does not declare (the
    spend cap, the session budget, where the results go), changes nothing. No run records its
    ``--max-tasks`` cap, only the tasks it planned, so the cap changes the run when it would plan
    other tasks.
    """
    changed = [
        option
        for dest, option in given.items()
        if dest != "max_tasks" and getattr(config, dest) != getattr(declared, dest)
    ]
    if "max_tasks" in given:
        capped = plan_tasks(replace(declared, max_tasks=config.max_tasks))
        if {role: [t.task_id for t in specs] for role, specs in capped.items()} != dict(
            first.run.extra["tasks"]
        ):
            changed.append(given["max_tasks"])
    return tuple(changed)


def identity_now(
    config: RunConfig, planned: Mapping[Role, Sequence[TaskSpec]], repo: Path
) -> MeasuredIdentity:
    """What a run of ``config`` planning ``planned`` would be measured on in ``repo`` now. The
    resolved model is unknown until a session reports one."""
    read = working_tree(repo)
    return MeasuredIdentity(
        tree=tree_digest(repo),
        model=None,
        seed=config.seed,
        tasks={role: tuple(task.task_id for task in specs) for role, specs in planned.items()},
        launch_orders={
            role: {task.task_id: planned_order(config, task.task_id) for task in specs}
            for role, specs in planned.items()
        },
        declared=declared_settings(config),
        roles={role: role_identity(read, role) for role in config.roles},
    )


def given_options(argv: Sequence[str] | None) -> dict[str, str]:
    """Each option ``argv`` names, by the run setting it sets, and how it is spelled; an option
    left at its default is not among them."""
    parser = _parser()
    actions = parser._actions  # argparse lists its actions only privately
    for action in actions:
        action.default = argparse.SUPPRESS  # an option argv does not name is left out
    named = vars(parser.parse_args(argv))
    spelling = {action.dest: (action.option_strings or [action.dest])[0] for action in actions}
    return {dest: spelling[dest] for dest in named}


# --- --dry-run: the sessions a paid run would launch ---


def _print_dry_run(
    config: RunConfig, checkout: Checkout, planned: Mapping[Role, list[TaskSpec]]
) -> int:
    run_root = Path(tempfile.gettempdir()) / f"{SANDBOX_PREFIX}<run>"
    for role, role_tasks in planned.items():
        print(f"{role}: {len(role_tasks)} tasks (target {config.required_pairs})", file=sys.stderr)
        for index, task in enumerate(role_tasks):
            for arm in ordered_arms(config.arms, config.seed, task.task_id):
                sandbox = SandboxPaths(run_root / role / f"{index:03d}-{arm}")
                spec = _planned_spec(config, checkout, run_root, task, arm, sandbox)
                env_names = sorted(session_env(config, sandbox.root, os.environ))
                line = {"role": role, "arm": arm, "task_id": task.task_id}
                print(json.dumps({**line, "argv": build_argv(spec), "env_names": env_names}))
    return EXIT_COMPLETE


def _planned_spec(
    config: RunConfig,
    checkout: Checkout,
    run_root: Path,
    task: TaskSpec,
    arm: Arm,
    sandbox: SandboxPaths,
) -> SessionSpec:
    """The spec a real run builds, with the plugin copy it would make named, not made.

    The role's tool line is read from the checkout's own definition, which every copy carries
    unchanged.
    """
    cap = tasks.turn_cap_of(task)
    patched = (arms.definition_path(task.role),) if arm == "lean" or cap else ()
    stand_in = ArmBuild(task.role, arm, checkout.path, cap, "dry-run", patched)
    spec = tasks.session_spec(
        task,
        stand_in,
        sandbox,
        model=config.model,
        effort=config.effort,
        max_budget_usd=config.session_budget_usd,
    )
    copy = run_root / task.role / f"{arm}-copy{cap or ''}"
    return replace(spec, plugin_dir=copy, add_dir=copy)


if __name__ == "__main__":
    sys.exit(main())
