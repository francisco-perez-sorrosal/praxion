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
from pathlib import Path

from praxion_evals.adherence import arms, report, results, session_loop, tasks, verdict
from praxion_evals.adherence.infra_stop import (
    COUNTING_KINDS,
    DEFAULT_STOP_COUNT,
    MIN_STOP_COUNT,
    StopRule,
)
from praxion_evals.adherence.model import (
    ARMS,
    ROLES,
    Arm,
    ArmBuild,
    DeclaredSettings,
    Role,
    TaskSpec,
    allowance_key,
)
from praxion_evals.adherence.session_loop import (
    DEFAULT_TAIL_CHARS,
    EXIT_COMPLETE,
    OUTPUT_DIR,
    RETRY_POLICY,
    SANDBOX_PREFIX,
    Checkout,
    RunConfig,
    ordered_arms,
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


def main(argv: Sequence[str] | None = None) -> int:
    config = parse_config(argv)
    try:
        if config.report is not None:
            print(report.render(results.load(config.report)), end="")
            return EXIT_COMPLETE
        checkout = resolve_checkout(config)
        if config.output is not None:
            results.refuse_existing(config.output, config.overwrite)
        planned = plan_tasks(config)
        if config.dry_run:
            return _print_dry_run(config, checkout, planned)
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
    if args["report"] is None and not args["roles"]:
        parser.error("name at least one --role, or --report FILE")
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
    noise.add_argument("--calibration", action="store_true", help="run the full arm against itself")
    noise.add_argument("--calibration-run", type=Path, help="a calibration file: allowance source")
    add("--judge-golden", action="store_true")
    add("--report", type=Path, help="render a results file; launch nothing")
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


def declared_settings(
    config: RunConfig,
    allowance_source: str | None = None,
    allowances: Mapping[str, int] | None = None,
) -> DeclaredSettings:
    return DeclaredSettings(
        margin_pp=config.margin_pp,
        method="tango-score",
        confidence=config.confidence,
        sidedness="one-sided",
        required_pairs=config.required_pairs,
        pair_slack=config.pair_slack,
        retry_policy=RETRY_POLICY,
        allowance_source=allowance_source,
        allowances=allowances or {},
        stop_rule=StopRule.parse(config.stop_count, COUNTING_KINDS, config.tail_chars),
    )


def calibrated_allowances(
    path: Path, config: RunConfig, planned: Mapping[Role, Sequence[TaskSpec]], commit: str
) -> tuple[str, dict[str, int]]:
    """The run id and each role's mechanical-check noise allowances from a calibration run.

    An allowance is an absolute count of discordant pairs measured on one checkout, one
    seed, one pair target and one task list of one role, so the file is refused when any
    of those differs from this run's or it lacks pairs of a named role; a check shared by
    several roles keeps one allowance per role, never the widest of them.
    """
    calibration = results.load(path)
    if not calibration.run.extra.get("calibration"):
        raise ValueError(f"{path} is not a calibration run")
    mismatch = _calibration_mismatch(calibration, config, planned, commit)
    if mismatch is not None:
        raise ValueError(f"the calibration run {calibration.run.id} {mismatch}")
    allowances: dict[str, int] = {}
    for role in config.roles:
        pairs = results.pairs_of(calibration, role)
        mechanical = {e.name for e in calibration.catalog.get(role, ()) if e.kind == "mechanical"}
        measured = verdict.allowances_from_calibration(pairs, config.confidence)
        for name, allowance in measured.items():
            if name in mechanical:
                allowances[allowance_key(name, role)] = allowance
    return calibration.run.id, allowances


def _calibration_mismatch(
    calibration: results.RunResults,
    config: RunConfig,
    planned: Mapping[Role, Sequence[TaskSpec]],
    commit: str,
) -> str | None:
    """Why the calibration's allowances do not carry to this run, or ``None`` when they do."""
    extra = calibration.run.extra
    measured = (extra.get("checkout") or {}).get("commit")
    if measured != commit:
        return f"measured checkout {measured}, not {commit}: an allowance does not carry across checkouts"
    if extra.get("seed") != config.seed:
        return f"measured seed {extra.get('seed')}, not {config.seed}: an allowance holds for one task draw"
    target = calibration.settings.required_pairs
    if target != config.required_pairs:
        return (
            f"declared a pair target of {target}, not {config.required_pairs}: an allowance "
            "is a count at the calibration's size"
        )
    for role in config.roles:
        if not results.pairs_of(calibration, role):
            return f"has no pairs of {role}"
        theirs = list((extra.get("tasks") or {}).get(role, ()))
        ours = [task.task_id for task in planned.get(role, ())]
        if theirs != ours:
            return _task_list_mismatch(role, theirs, ours)
    return None


def _task_list_mismatch(role: Role, theirs: Sequence[str], ours: Sequence[str]) -> str:
    if len(theirs) != len(ours):
        return f"measured the {role} on {len(theirs)} tasks, not the {len(ours)} planned"
    return f"measured the {role} on other tasks than the {len(ours)} planned (another kit or cap)"


def _declare(
    config: RunConfig, checkout: Checkout, planned: Mapping[Role, Sequence[TaskSpec]]
) -> DeclaredSettings:
    """The settings a paid run declares, with the noise allowances of its calibration run if any."""
    source, allowances = None, {}
    if config.calibration_run is not None:
        source, allowances = calibrated_allowances(
            config.calibration_run, config, planned, checkout.commit
        )
    return declared_settings(config, source, allowances)


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
