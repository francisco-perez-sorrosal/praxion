"""``praxion-evals-adherence``: the adherence eval's opt-in console entry.

Every session costs money, so this entry is the only way to reach the eval and no
other module imports it. argv is parsed once into a frozen ``RunConfig``; then
``--report FILE`` renders a results file, ``--dry-run`` prints the sessions a paid
run would launch (through the same ``session_spec``/``build_argv``/``build_env``
path) and writes nothing, and a paid run declares its settings in a provisional
results file, builds and proves each named arm of each role, runs the role's tasks
(arms interleaved, a fresh scratch repository per session) under the run-level spend
ledger, grades each session and rewrites the results file after every one.

Exit codes: 0 the run is complete; 1 it is incomplete (a refused launch, an arm that
could not be built or proven, a session that ended in error; the results are
written); 2 usage. Judge calls are metered by the judge's own account, not by the
ledger, which covers the ``claude`` sessions only.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from praxion_evals.adherence import arms, grade, report, results, tasks, verdict
from praxion_evals.adherence.catalog import check_catalog
from praxion_evals.adherence.checks_common import GoldenVerdicts, judge_golden_cases
from praxion_evals.adherence.model import (
    ARMS,
    ROLES,
    Arm,
    ArmBuild,
    CheckErrored,
    DeclaredSettings,
    EarlyStop,
    Errored,
    Failed,
    NotBuilt,
    Passed,
    Role,
    SessionEvidence,
    SessionRecord,
    SessionSetup,
    SessionStatus,
    Standard,
    TaskSpec,
    outcome_to_json,
)
from praxion_evals.harness.judge_client import JudgeClient, select_judge_client
from praxion_evals.live.materialize import (
    Materialization,
    install_user_scope,
    make_writable,
    materialize_path,
)
from praxion_evals.live.report import CREDENTIAL_KEYS
from praxion_evals.live.results import Errored as LiveErrored
from praxion_evals.live.session import (
    CLAUDE_BINARY,
    SandboxPaths,
    SessionRun,
    SessionSpec,
    build_argv,
    build_env,
    parse_stream,
    run_session,
    session_error,
)
from praxion_evals.live.spend import RUNNER_SPEND_CAP_USD, SpendLedger

PROG = "praxion-evals-adherence"
EXIT_COMPLETE, EXIT_INCOMPLETE, EXIT_USAGE = 0, 1, 2
DEFAULT_SEED = 7
DEFAULT_MARGIN_PP = 10.0
DEFAULT_CONFIDENCE = 0.95
DEFAULT_SESSION_BUDGET_USD = 3.0
DEFAULT_MODEL = "opus"  # the live runner's defaults
DEFAULT_EFFORT = "medium"
OUTPUT_DIR = Path(".ai-state/eval_ledger/adherence")
SANDBOX_PREFIX = "praxion-evals-adherence-"
PROBE_TIMEOUT_S = 15
HTTP_OK = 200
MS_PER_S = 1000
REAL_HOME = Path.home()  # read once, here: the isolation scan takes it in as an input

# Infrastructure errors a second try may not repeat. Never an isolation breach (the sandbox
# leaked), a refused launch (the cap is spent) or an evaluation exception (the grader failed,
# not the session); a budget stop is left alone because it would stop again at the same budget.
RETRYABLE_ERRORS = frozenset({"timeout", "exit_nonzero", "no_result_event", "envelope_unparseable"})
RETRY_POLICY = (
    "one retry per session, only after a timeout, a non-zero exit, a missing result or an "
    "unparseable stream; never after an isolation breach, a refused launch or an evaluation "
    "exception; the retry is recorded as a later session and replaces the error in its pair"
)


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
        context, state = _begin(config, checkout, planned)
    except (ValueError, OSError) as error:  # everything before the first launch is a usage error
        print(f"{PROG}: {error}", file=sys.stderr)
        return EXIT_USAGE
    return _conduct(context, state)


# --- argv, parsed once ---


@dataclass(frozen=True)
class RunConfig:
    checkout: Path | None
    roles: tuple[Role, ...]
    arms: tuple[Arm, ...]
    output: Path | None
    seed: int
    run_cap_usd: float
    session_budget_usd: float
    margin_pp: float
    required_pairs: int
    pair_slack: int
    confidence: float
    judging: bool
    model: str
    effort: str
    keep_sandbox: bool
    dry_run: bool
    overwrite: bool
    calibration: bool
    calibration_run: Path | None
    judge_golden: bool
    report: Path | None
    fixture_pages_base_url: str | None


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
    add("--confidence", type=float, default=DEFAULT_CONFIDENCE)
    add("--no-judge", dest="judging", action="store_false")
    add("--model", default=DEFAULT_MODEL)
    add("--effort", default=DEFAULT_EFFORT)
    add("--keep-sandbox", action="store_true")
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
    )


def calibrated_allowances(
    path: Path, roles: Sequence[Role], confidence: float
) -> tuple[str, dict[str, int]]:
    """The run id and each mechanical check's noise allowance from a same-arm calibration run.

    A check shared by several roles takes the widest allowance any of them showed.
    """
    calibration = results.load(path)
    if not calibration.run.extra.get("calibration"):
        raise ValueError(f"{path} is not a calibration run")
    allowances: dict[str, int] = {}
    for role in roles:
        pairs = results.pairs_of(calibration, role)
        if not pairs:
            raise ValueError(f"the calibration run {calibration.run.id} has no pairs of {role}")
        mechanical = {e.name for e in calibration.catalog.get(role, ()) if e.kind == "mechanical"}
        for name, allowance in verdict.allowances_from_calibration(pairs, confidence).items():
            if name in mechanical:
                allowances[name] = max(allowances.get(name, 0), allowance)
    return calibration.run.id, allowances


def plan_tasks(config: RunConfig) -> dict[Role, list[TaskSpec]]:
    """Target plus slack for a full-set role, smoke tasks otherwise, never more than exist."""
    plan = {}
    for role in config.roles:
        wanted = config.required_pairs + config.pair_slack
        wanted = wanted if role in tasks.FULL_SET_ROLES else tasks.SMOKE_TASKS
        count = min(wanted, tasks.producible_task_count(role, config.seed))
        plan[role] = tasks.generate(role, config.seed, count)
    return plan


@dataclass(frozen=True)
class Checkout:
    path: Path
    commit: str
    dirty: bool


def resolve_checkout(config: RunConfig) -> Checkout:
    path = config.checkout or Path(_git(Path.cwd(), "rev-parse", "--show-toplevel").strip())
    path = path.resolve()
    return Checkout(
        path=path,
        commit=_git(path, "rev-parse", "HEAD").strip(),
        dirty=bool(_git(path, "status", "--porcelain").strip()),
    )


def _git(repo: Path, *args: str) -> str:
    try:
        done = subprocess.run(
            ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as error:
        raise ValueError(f"`git {' '.join(args)}` failed in {repo}: not a git checkout?") from error
    return done.stdout


# --- --dry-run: the sessions a paid run would launch ---


def _print_dry_run(
    config: RunConfig, checkout: Checkout, planned: Mapping[Role, list[TaskSpec]]
) -> int:
    run_root = Path(tempfile.gettempdir()) / f"{SANDBOX_PREFIX}<run>"
    for role, role_tasks in planned.items():
        for index, task in enumerate(role_tasks):
            for arm in config.arms:
                sandbox = SandboxPaths(run_root / role / f"{index:03d}-{arm}")
                spec = _planned_spec(config, checkout, run_root, task, arm, sandbox)
                env_names = sorted(build_env(sandbox.root, os.environ))
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


# --- the paid run: its context, its state, its start ---


@dataclass(frozen=True)
class Context:
    """What stays fixed for the whole run."""

    config: RunConfig
    checkout: Checkout
    planned: Mapping[Role, list[TaskSpec]]
    judge: JudgeClient | None
    output: Path
    run_root: Path
    page_url: str
    needs_page: bool  # some planned task plants an injection in the C6 page


@dataclass(frozen=True)
class RunState:
    """What each step replaces: the results so far, the spend and the C6 page probe."""

    results: results.RunResults
    ledger: SpendLedger
    page_fetchable: bool | None = None  # None: not probed yet


def _begin(
    config: RunConfig, checkout: Checkout, planned: Mapping[Role, list[TaskSpec]]
) -> tuple[Context, RunState]:
    if not any(os.environ.get(key) for key in CREDENTIAL_KEYS):
        raise ValueError(
            f"no credential in the environment; set one of {', '.join(CREDENTIAL_KEYS)}"
        )
    source, allowances = None, {}
    if config.calibration_run is not None:
        source, allowances = calibrated_allowances(
            config.calibration_run, config.roles, config.confidence
        )
    settings = declared_settings(config, source, allowances)
    judge = _open_judge(config)
    version = query_claude_version()
    started = datetime.now(UTC)
    run_id = results.new_run_id(started)
    output = config.output or _default_output(run_id)
    results.refuse_existing(output, config.overwrite)
    provisional = _provisional(
        config, checkout, planned, settings, run_id, version, started, output
    )
    results.write_atomic(output, provisional)
    base = config.fixture_pages_base_url
    context = Context(
        config=config,
        checkout=checkout,
        planned=planned,
        judge=judge,
        output=output,
        run_root=Path(tempfile.mkdtemp(prefix=SANDBOX_PREFIX)).resolve(),
        page_url=tasks.fixture_page_url(checkout.commit)
        if base is None
        else f"{base.rstrip('/')}/{PurePosixPath(tasks.PAGE_PATH).name}",
        needs_page=any(_injection_of(t) for role_tasks in planned.values() for t in role_tasks),
    )
    return context, RunState(provisional, SpendLedger(cap_usd=config.run_cap_usd))


def query_claude_version() -> str:
    done = subprocess.run([CLAUDE_BINARY, "--version"], capture_output=True, text=True, check=False)
    words = done.stdout.split()
    if done.returncode != 0 or not words:
        raise ValueError(f"`{CLAUDE_BINARY} --version` gave no version; is it on PATH?")
    return words[0]


def page_is_fetchable(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=PROBE_TIMEOUT_S) as response:
            return response.status == HTTP_OK
    except Exception:  # any failure means "not fetchable": C6 is withheld, never guessed
        return False


def _open_judge(config: RunConfig) -> JudgeClient | None:
    if not config.judging:
        return None
    try:
        return select_judge_client()
    except (RuntimeError, ImportError) as error:
        raise ValueError(
            f"judging is unavailable ({error}); pass --no-judge to run without"
        ) from error


def _default_output(run_id: str) -> Path:
    repo = Path(_git(Path.cwd(), "rev-parse", "--show-toplevel").strip())
    return repo / OUTPUT_DIR / f"{run_id}.json"


def _provisional(
    config: RunConfig,
    checkout: Checkout,
    planned: Mapping[Role, list[TaskSpec]],
    settings: DeclaredSettings,
    run_id: str,
    version: str,
    started: datetime,
    output: Path,
) -> results.RunResults:
    """The results file as first written: every setting declared, no session yet."""
    replaced = _loaded_run_id(output)  # a file this run overwrites is no longer evidence
    earlier = {
        role: tuple(
            e
            for e in results.earlier_runs(output.parent, role, checkout.commit)
            if e.run_id != replaced
        )
        for role in config.roles
    }
    extra = {
        "started_at": started.isoformat(),
        "effort": config.effort,
        "checkout": {
            "path": str(checkout.path),
            "commit": checkout.commit,
            "dirty": checkout.dirty,
        },
        "seed": config.seed,
        "roles": list(config.roles),
        "arms": list(config.arms),
        "tasks": {role: [t.task_id for t in role_tasks] for role, role_tasks in planned.items()},
        "calibration": config.calibration,
        "judging": config.judging,
        "session_budget_usd": config.session_budget_usd,
        "retries": [],
    }
    run = results.RunInfo(run_id, config.model, version, False, (), earlier, extra)
    catalog = {
        role: tuple(results.catalog_entry(check) for check in check_catalog(role))
        for role in config.roles
    }
    return results.RunResults(run, settings, started.isoformat(), catalog, {}, (), None)


def _loaded_run_id(path: Path) -> str | None:
    try:
        return results.load(path).run.id
    except (OSError, ValueError):
        return None


# --- the paid run: conducting it ---


def _conduct(context: Context, state: RunState) -> int:
    try:
        if context.config.judge_golden:
            state = _judge_golden(context, state)
        for role, role_tasks in context.planned.items():
            state = _measure_role(context, state, role, role_tasks)
    finally:
        _clean_up(context)
    final = _finalize(context, state)
    print(f"wrote {context.output}")
    print(report.render(final), end="")
    return EXIT_COMPLETE if final.run.complete else EXIT_INCOMPLETE


def _clean_up(context: Context) -> None:
    if context.config.keep_sandbox:
        print(f"sandbox kept: {context.run_root}")
        return
    make_writable(context.run_root)  # a plugin copy inside it is read-only
    shutil.rmtree(context.run_root, ignore_errors=True)


def _finalize(context: Context, state: RunState) -> results.RunResults:
    """Complete means: no refused launch, every arm built and proven, no session left in error."""
    latest = {
        (r.setup.role, r.setup.arm, r.setup.task_id): r.status for r in state.results.sessions
    }
    unbuilt = any(
        not a["built"] for per_arm in state.results.arms.values() for a in per_arm.values()
    )
    complete = (
        not state.results.run.refused_launches
        and not unbuilt
        and not any(isinstance(status, Errored) for status in latest.values())
    )
    state = _update_run(state, complete=complete)
    return _checkpoint(
        context, _update_extra(state, finished_at=datetime.now(UTC).isoformat())
    ).results


def _judge_golden(context: Context, state: RunState) -> RunState:
    assert context.judge is not None  # parse_config refuses --judge-golden with --no-judge
    record = golden_record(judge_golden_cases(context.judge))
    return _checkpoint(
        context, replace(state, results=replace(state.results, golden_bad_case_verdicts=record))
    )


def golden_record(cases: Mapping[str, GoldenVerdicts]) -> dict[str, Any]:
    """Both golden verdicts per judged check, and the share of judged cases the judge got wrong.

    A case the judge errored on is recorded but is neither right nor wrong.
    """
    right = [
        isinstance(outcome, expected)
        for golden in cases.values()
        for outcome, expected in ((golden.bad, Failed), (golden.good, Passed))
        if not isinstance(outcome, CheckErrored)
    ]
    return {
        "observed_error": right.count(False) / len(right) if right else None,
        "cases": {
            name: {
                "bad": outcome_to_json(golden.bad),
                "good": outcome_to_json(golden.good),
                "separates": golden.separates,
            }
            for name, golden in cases.items()
        },
    }


# --- one role: copies, proof, tasks ---

Builds = dict[tuple[Arm, int | None], ArmBuild]  # (the arm whose copy, its early-stop cap)


def _measure_role(
    context: Context, state: RunState, role: Role, role_tasks: list[TaskSpec]
) -> RunState:
    config, role_dir = context.config, context.run_root / role
    try:
        original = materialize_path(context.checkout.path, role_dir / "original")
    except Exception as error:  # a checkout that cannot be copied leaves every arm unbuilt
        unbuilt = NotBuilt(f"the checkout could not be copied: {type(error).__name__}: {error}")
        return _record_arms(context, state, role, {}, dict.fromkeys(config.arms, unbuilt))
    copies: dict[Arm, ArmBuild | NotBuilt] = {
        arm: _build_copy(role_dir, original, role, arm) for arm in config.arms
    }
    builds: Builds = {(a, None): c for a, c in copies.items() if isinstance(c, ArmBuild)}
    verdicts: dict[Arm, arms.ArmVerdict] = {
        a: c for a, c in copies.items() if isinstance(c, NotBuilt)
    }
    state, proof = _prove(context, state, role, original, builds, role_tasks[0])
    verdicts.update(proof)
    caps = sorted({cap for t in role_tasks if (cap := tasks.turn_cap_of(t)) is not None})
    proven: list[Arm] = [a for a, v in verdicts.items() if isinstance(v, arms.ArmProven)]
    for arm in proven:
        for cap in caps:  # the early-stop twins of a proven arm; a twin that fails demotes the arm
            twin = _build_copy(role_dir, original, role, arm, cap)
            if isinstance(twin, NotBuilt):
                verdicts[arm] = twin
            else:
                builds[(arm, cap)] = twin
    state = _record_arms(context, state, role, builds, verdicts)
    runnable: list[Arm] = [a for a in config.arms if isinstance(verdicts.get(a), arms.ArmProven)]
    state = _probe_page(context, state, runnable)
    for task in role_tasks:
        for slot, copy_arm in _slots(config, runnable):
            build = builds[(copy_arm, tasks.turn_cap_of(task))]
            state = _session_with_retry(context, state, task, slot, build)
    return state


def _slots(config: RunConfig, runnable: Sequence[Arm]) -> list[tuple[Arm, Arm]]:
    """(the arm a session is recorded under, the arm whose copy it runs), in launch order.

    A calibration run records its second run of the full copy in the lean slot, so the
    ordinary pairing and verdict code reads it as a pair.
    """
    if config.calibration:
        return [("full", "full"), ("lean", "full")] if "full" in runnable else []
    return [(arm, arm) for arm in runnable]


def _build_copy(
    role_dir: Path, original: Materialization, role: Role, arm: Arm, cap: int | None = None
) -> ArmBuild | NotBuilt:
    try:
        return arms.build_arm(
            original, role_dir / (f"{arm}-cap{cap}" if cap else arm), role, arm, turn_cap=cap
        )
    except (arms.ArmCopyError, OSError) as error:
        return NotBuilt(f"the {arm} copy could not be built: {error}")


def _record_arms(
    context: Context,
    state: RunState,
    role: Role,
    builds: Builds,
    verdicts: Mapping[Arm, arms.ArmVerdict],
) -> RunState:
    per_arm: dict[str, Any] = {}
    for arm, outcome in verdicts.items():
        build = builds.get((arm, None))
        if isinstance(outcome, NotBuilt) or build is None:
            per_arm[arm] = {"built": False, "reason": getattr(outcome, "reason", "not built")}
        else:
            proof = {
                "first_request_tokens": outcome.first_request_tokens,
                "cross_checked": outcome.cross_checked,
            }
            per_arm[arm] = {
                "built": True,
                "proof": proof,
                "tree_digest": build.tree_digest,
                "patched": list(build.patched),
            }
    updated = replace(state.results, arms={**state.results.arms, role: per_arm})
    return _checkpoint(context, replace(state, results=updated))


# --- the arm proof ---


def _prove(
    context: Context,
    state: RunState,
    role: Role,
    original: Materialization,
    builds: Builds,
    first_task: TaskSpec,
) -> tuple[RunState, dict[Arm, arms.ArmVerdict]]:
    """One proof session per built arm, all under one planted nonce, then one decision."""
    template = context.run_root / role / "proof-home"
    install_user_scope(original.root, template)
    nonce = arms.plant_proof_marker(SandboxPaths(template))
    proof_task = replace(first_task, variant=Standard(), main_prompt=arms.proof_prompt())

    def copy_home(root: Path) -> None:
        shutil.copytree(template, root, symlinks=True, dirs_exist_ok=True)

    observed: dict[Arm, arms.ProofObservation | None] = {}
    verdicts: dict[Arm, arms.ArmVerdict] = {}
    for (arm, _), build in builds.items():
        ledger, attempt = _attempt(
            context, state.ledger, proof_task, build, copy_home, None, _observe
        )
        state = replace(state, ledger=ledger)
        match attempt.result:
            case Errored(kind="launch_refused", detail=detail):
                state = _add_refusal(state, f"{role} {arm} arm proof: {detail}")
                verdicts[arm] = NotBuilt(f"the proof launch was refused: {detail}")
            case Errored(detail=detail):
                verdicts[arm] = NotBuilt(f"the proof session failed: {detail}")
            case NotBuilt() as unobserved:
                verdicts[arm] = unobserved
            case arms.ProofObservation() as seen:
                observed[arm] = seen
    return state, {**verdicts, **arms.decide_proof(nonce, observed)}


def _observe(evidence: SessionEvidence) -> arms.ProofObservation | NotBuilt:
    """What the proof session's role answered, or why nothing was observed."""
    run = SessionRun("", "", None if evidence.timed_out else evidence.exit_code)
    error = session_error(evidence.envelope, run, evidence.plugin_copy, real_home=REAL_HOME)
    if error is not None:
        return NotBuilt(f"the proof session ended in {error.kind}: {error.detail}")
    if evidence.spawn_id is None:
        return NotBuilt("the role was never spawned in the proof session")
    return arms.ProofObservation(
        answer=evidence.role_return or "",
        first_request_tokens=grade.first_request_tokens(evidence),
    )


def _probe_page(context: Context, state: RunState, runnable: Sequence[Arm]) -> RunState:
    """Probe the C6 page once, after the first arm has proven; any failure is 'not fetchable'."""
    if not (context.needs_page and runnable) or state.page_fetchable is not None:
        return state
    fetchable = page_is_fetchable(context.page_url)
    state = _update_extra(state, c6_page={"url": context.page_url, "fetchable": fetchable})
    return replace(state, page_fetchable=fetchable)


# --- one session, with its one retry ---


def _session_with_retry(
    context: Context, state: RunState, task: TaskSpec, slot: Arm, build: ArmBuild
) -> RunState:
    state = _task_session(context, state, task, slot, build)
    last = state.results.sessions[-1].status
    if not (isinstance(last, Errored) and last.kind in RETRYABLE_ERRORS):
        return state
    retry = {"role": task.role, "arm": slot, "task_id": task.task_id, "after": last.kind}
    state = _update_extra(state, retries=[*state.results.run.extra["retries"], retry])
    return _task_session(context, state, task, slot, build)


def _task_session(
    context: Context, state: RunState, task: TaskSpec, slot: Arm, build: ArmBuild
) -> RunState:
    config = context.config
    setup = SessionSetup(
        arm=slot,
        checkout_commit=context.checkout.commit,
        role=task.role,
        task_id=task.task_id,
        template_id=task.template_id,
        seed=config.seed,
    )
    page_url = context.page_url if _injection_of(task) and state.page_fetchable else None

    def populate(root: Path) -> None:
        install_user_scope(build.copy_root, root)

    ledger, attempt = _attempt(
        context,
        state.ledger,
        task,
        build,
        populate,
        page_url,
        lambda evidence: _grade(context, evidence, task, setup),
    )
    status: SessionStatus = attempt.result
    if isinstance(status, Errored):
        status = replace(status, setup=setup)
        if status.kind == "launch_refused":
            state = _add_refusal(state, f"{task.role} {slot} {task.task_id}: {status.detail}")
    record = SessionRecord(
        setup, status, attempt.charged_usd, attempt.duration_ms, attempt.started_at
    )
    print(
        f"{task.role} {slot} {task.task_id}: {type(status).__name__}", file=sys.stderr, flush=True
    )
    state = replace(
        state,
        ledger=ledger,
        results=replace(state.results, sessions=(*state.results.sessions, record)),
    )
    return _checkpoint(context, state)


def _grade(
    context: Context, evidence: SessionEvidence, task: TaskSpec, setup: SessionSetup
) -> SessionStatus:
    """C3 is named only for a task that planted a gap or a conflict: without one it passes vacuously."""
    names = [
        check.name
        for check in check_catalog(task.role)
        if not (check.name == "C3" and isinstance(task.variant, EarlyStop))
    ]
    return grade.grade(evidence, names, context.judge, setup, real_home=REAL_HOME)


def _injection_of(task: TaskSpec) -> tasks.Injection | None:
    return task.variant.injection if isinstance(task.variant, Standard) else None


# --- one launch: reserve, sandbox, start, settle, read, assess ---


@dataclass(frozen=True)
class Attempt[R]:
    """One session's assessment, or the error that kept it from having one.

    ``charged_usd`` is what the ledger took: the reported cost, or the full budget when the
    session reported none.
    """

    result: R | Errored
    charged_usd: float
    duration_ms: int
    started_at: str


def _attempt[R](
    context: Context,
    ledger: SpendLedger,
    task: TaskSpec,
    build: ArmBuild,
    populate: Callable[[Path], None],
    page_url: str | None,
    assess: Callable[[SessionEvidence], R],
) -> tuple[SpendLedger, Attempt[R]]:
    """Run one session in a fresh sandbox and scratch repository, assess it, and clean up.

    The budget is reserved first and a refusal starts nothing. A session that never started
    settles at nothing. The sandbox outlives the assessment because a check may run a script
    against the scratch repository.
    """
    config, budget = context.config, context.config.session_budget_usd
    started_at, began = datetime.now(UTC).isoformat(), time.monotonic()

    def finish(result: R | Errored, charged: float) -> Attempt[R]:
        return Attempt(result, charged, int((time.monotonic() - began) * MS_PER_S), started_at)

    reserved = ledger.reserve(budget)
    if isinstance(reserved, LiveErrored):
        return ledger, finish(Errored("launch_refused", reserved.detail), 0.0)
    parent = context.run_root / task.role / "sessions"
    parent.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix="s-", dir=parent))
    try:
        sandbox = SandboxPaths(root)
        try:
            populate(root)
            commit = tasks.build_scratch_repo(task, tasks.scratch_dir(sandbox), page_url)
            spec = tasks.session_spec(
                task,
                build,
                sandbox,
                model=config.model,
                effort=config.effort,
                max_budget_usd=budget,
            )
            run = run_session(spec, build_env(root, os.environ))
        except Exception as error:  # nothing was started, so nothing was spent
            crashed = Errored("evaluation_exception", f"{type(error).__name__}: {error}")
            return reserved.settle(budget, 0.0), finish(crashed, 0.0)
        final = parse_stream(run.stdout).final_result
        cost = None if final is None else final.total_cost_usd
        settled, charged = reserved.settle(budget, cost), budget if cost is None else cost
        try:
            evidence = grade.evidence_from_recording(
                role=task.role,
                envelope=run.stdout,
                repo_root=tasks.scratch_dir(sandbox),
                fixture_commit=commit,
                sandbox=root,
                plugin_copy=build.copy_root,
                slug=task.slug,
                exit_code=run.exit_code,
                timed_out=run.timed_out,
                judging=context.judge is not None,
                **_task_facts(task, page_url is not None),
            )
            return settled, finish(assess(evidence), charged)
        except Exception as error:  # one unreadable session must not discard the paid run
            crashed = Errored("evaluation_exception", f"{type(error).__name__}: {error}")
            return settled, finish(crashed, charged)
    finally:
        if not config.keep_sandbox:
            shutil.rmtree(root, ignore_errors=True)


def _task_facts(task: TaskSpec, page_available: bool) -> dict[str, Any]:
    """The task's own flags for the grader; ``page_available`` is the C6 probe's answer."""
    injection = _injection_of(task)
    return {
        "forced_stop": isinstance(task.variant, EarlyStop),
        "fetchable_page": injection is not None and page_available,
        "planted_instruction": injection.instruction if injection else None,
        "planted_effect": injection.effect_path if injection else None,
    }


# --- state updates: each returns a new state; a checkpoint writes the file whole ---


def _update_run(state: RunState, **changes: Any) -> RunState:
    run = replace(state.results.run, **changes)
    return replace(state, results=replace(state.results, run=run))


def _update_extra(state: RunState, **entries: Any) -> RunState:
    return _update_run(state, extra={**state.results.run.extra, **entries})


def _add_refusal(state: RunState, text: str) -> RunState:
    return _update_run(state, refused_launches=(*state.results.run.refused_launches, text))


def _checkpoint(context: Context, state: RunState) -> RunState:
    spend = {"cap_usd": context.config.run_cap_usd, "spent_usd": round(state.ledger.spent_usd, 6)}
    state = _update_extra(state, spend=spend)
    results.write_atomic(context.output, state.results)
    return state


if __name__ == "__main__":
    sys.exit(main())
