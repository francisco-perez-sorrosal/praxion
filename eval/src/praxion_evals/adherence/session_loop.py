"""The paid run: its context, its state and the session loop the console entry hands over to.

``cli`` parses argv, answers ``--report`` and ``--dry-run`` and declares the run's
settings; everything after that costs money and lives here. A run declares its
settings in a provisional results file, builds and proves each named arm of each role,
runs the role's tasks (arms interleaved, a fresh scratch repository per session) under
the run-level spend ledger, grades each session and rewrites the results file after
every one. Nothing in this module reads argv or prints a usage error: a refusal before
the first launch is a ``ValueError`` the console entry reports.

One session's launch (sandbox, ``claude``, settlement, grading) lives in ``session_launch``.

After every task session (a retry is the arm's next session) the run folds the record into
the infrastructure stop (``infra_stop.step``); once it answers ``Stop`` nothing more is
launched, no session, retry or proof, and the run ends ``InfraStopped`` with every session it
recorded. The stop reads only an errored session's kind and evidence, never a graded outcome.

Exit codes of a run: 0 it is complete; 1 it is incomplete (a refused launch, an arm that
could not be built or proven, a session that ended in error, a stop, an operator interrupt;
the results are written). The results file records how the run ended (``run_ending.finalized``);
a later part of a stopped run starts from its ``run_ending.Continuation``.
Judge calls are metered by the judge's own account, not by the ledger, which covers the
``claude`` sessions only.
"""

from __future__ import annotations

import os
import random
import shutil
import subprocess
import tempfile
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any, assert_never

from praxion_evals.adherence import arms, grade, report, results, run_index, tasks
from praxion_evals.adherence.catalog import check_catalog
from praxion_evals.adherence.checks_common import GoldenVerdicts, judge_golden_cases
from praxion_evals.adherence.infra_stop import (
    DEFAULT_STOP_COUNT,
    Continue,
    FoldState,
    Stop,
    StopReason,
    step,
)
from praxion_evals.adherence.lineage import (
    MeasuredIdentity,
    current_identity,
    diff,
    measured_identity,
)
from praxion_evals.adherence.model import (
    Arm,
    ArmBuild,
    CheckErrored,
    DeclaredSettings,
    Errored,
    Failed,
    NotBuilt,
    Passed,
    Role,
    SessionEvidence,
    SessionRecord,
    Standard,
    TaskSpec,
    outcome_to_json,
)
from praxion_evals.adherence.run_ending import Continuation, finalized
from praxion_evals.adherence.session_launch import (
    DEFAULT_TAIL_CHARS,
    REAL_HOME,
    Launch,
    attempt,
    injection_of,
    task_session,
)
from praxion_evals.harness.judge_client import JudgeClient, select_judge_client
from praxion_evals.live.materialize import (
    Materialization,
    install_user_scope,
    make_writable,
    materialize_path,
)
from praxion_evals.live.report import CREDENTIAL_KEYS
from praxion_evals.live.session import (
    CLAUDE_BINARY,
    SandboxPaths,
    SessionRun,
    build_env,
    session_error,
    with_session_token,
)
from praxion_evals.live.spend import SpendLedger

EXIT_COMPLETE, EXIT_INCOMPLETE = 0, 1
OUTPUT_DIR = Path(".ai-state/eval_ledger/adherence")
SANDBOX_PREFIX = "praxion-evals-adherence-"
PROBE_TIMEOUT_S = 15
HTTP_OK = 200

LAUNCH_ARMS: tuple[Arm, Arm] = ("full", "lean")
CALIBRATION_ORDER: tuple[Arm, Arm] = ("full", "lean")  # its slots, in the order they run

# Infrastructure errors a second try may not repeat. Never an isolation breach (the sandbox
# leaked), a refused launch (the cap is spent) or an evaluation exception (the grader failed,
# not the session); a budget stop is left alone because it would stop again at the same budget.
RETRYABLE_ERRORS = frozenset({"timeout", "exit_nonzero", "no_result_event", "envelope_unparseable"})
RETRY_POLICY = (
    "one retry per session, only after a timeout, a non-zero exit, a missing result or an "
    "unparseable stream; never after an isolation breach, a refused launch or an evaluation "
    "exception; the retry is recorded as a later session and replaces the error in its pair"
)


# --- the run's configuration and checkout ---


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
    max_tasks: int | None = None  # a cap on the tasks per role, below the target plus slack
    # A `claude setup-token` file: sessions authenticate with it and never see the API key,
    # which the runner's own process keeps for the judge. None: sessions inherit the key.
    session_oauth_token_file: Path | None = None
    # The infrastructure stop, declared with the other settings (see `infra_stop.StopRule`).
    stop_count: int = DEFAULT_STOP_COUNT
    tail_chars: int = DEFAULT_TAIL_CHARS
    # Close the stopped run with this id, saying why; a close launches nothing.
    close: str | None = None
    reason: str | None = None
    # Continue the stopped run with this id: a later part of it, launching its unfinished tasks.
    continue_run: str | None = None
    # Rebuild the run index of the results directory; launches nothing.
    reindex: bool = False


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
    """What each step replaces: the results so far, the spend, the C6 page probe and the
    infrastructure stop's fold over the task sessions."""

    results: results.RunResults
    ledger: SpendLedger
    page_fetchable: bool | None = None  # None: not probed yet
    fold: FoldState = FoldState()
    stop: StopReason | None = None  # set once by the fold; nothing is launched after it


def session_env(config: RunConfig, root: Path, ambient: Mapping[str, str]) -> dict[str, str]:
    """A session's environment: the sandbox allowlist, and the token file's token in place of
    the API key when the run names one (the runner's own process keeps the key for the judge)."""
    env = build_env(root, ambient)
    if config.session_oauth_token_file is None:
        return env
    token = config.session_oauth_token_file.read_text(encoding="utf-8")
    return with_session_token(env, token)


def _launch_of(context: Context) -> Launch:
    config = context.config
    return Launch(
        run_root=context.run_root,
        checkout_commit=context.checkout.commit,
        page_url=context.page_url,
        judge=context.judge,
        seed=config.seed,
        model=config.model,
        effort=config.effort,
        session_budget_usd=config.session_budget_usd,
        keep_sandbox=config.keep_sandbox,
        env_for=lambda root: session_env(config, root, os.environ),
        tail_chars=config.tail_chars,
    )


def begin(
    config: RunConfig,
    checkout: Checkout,
    planned: Mapping[Role, list[TaskSpec]],
    declare: Callable[[RunConfig, Checkout, Mapping[Role, list[TaskSpec]]], DeclaredSettings],
    continuation: Continuation | None = None,
) -> tuple[Context, RunState]:
    """Check the credential, declare the settings, write the provisional results file.

    ``planned`` is what this run launches; a ``continuation`` is a later part of a stopped run,
    which launches again only the tasks no earlier part finished and records the whole plan.
    """
    if not any(os.environ.get(key) for key in CREDENTIAL_KEYS):
        raise ValueError(
            f"no credential in the environment; set one of {', '.join(CREDENTIAL_KEYS)}"
        )
    settings = declare(config, checkout, planned)
    judge = _open_judge(config)
    version = query_claude_version()
    started = datetime.now(UTC)
    run_id = results.new_run_id(started)
    output = config.output or _default_output(run_id)
    results.refuse_existing(output, config.overwrite)
    provisional = _provisional(
        config, checkout, planned, settings, run_id, version, started, output, continuation
    )
    results.write_atomic(output, provisional)
    context = Context(
        config=config,
        checkout=checkout,
        planned=planned,
        judge=judge,
        output=output,
        run_root=Path(tempfile.mkdtemp(prefix=SANDBOX_PREFIX)).resolve(),
        page_url=page_url_of(config, checkout, continuation),
        needs_page=any(injection_of(t) for role_tasks in planned.values() for t in role_tasks),
    )
    return context, RunState(provisional, SpendLedger(cap_usd=config.run_cap_usd))


def page_url_of(config: RunConfig, checkout: Checkout, continuation: Continuation | None) -> str:
    """The address of the C6 page: the one named, else the one the run's first part probed, else
    the page at the checkout's commit (a continuation measures the page its first part measured)."""
    base = config.fixture_pages_base_url
    if base is not None:
        return f"{base.rstrip('/')}/{PurePosixPath(tasks.PAGE_PATH).name}"
    if continuation is not None and continuation.page_url is not None:
        return continuation.page_url
    return tasks.fixture_page_url(checkout.commit)


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
    return _default_results_dir() / f"{run_id}.json"


def _default_results_dir() -> Path:
    return Path(_git(Path.cwd(), "rev-parse", "--show-toplevel").strip()) / OUTPUT_DIR


def results_dir(config: RunConfig) -> Path:
    """The directory holding the runs a run is listed beside: where its results file goes."""
    return config.output.parent if config.output else _default_results_dir()


def _provisional(
    config: RunConfig,
    checkout: Checkout,
    planned: Mapping[Role, list[TaskSpec]],
    settings: DeclaredSettings,
    run_id: str,
    version: str,
    started: datetime,
    output: Path,
    continuation: Continuation | None = None,
) -> results.RunResults:
    """The results file as first written: every setting declared, no session yet."""
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
        "identity": current_identity(checkout.path, config.roles),
        **(continuation.extra(run_id) if continuation else {}),
    }
    run = results.RunInfo(run_id, config.model, version, False, (), {}, extra)
    catalog = {
        role: tuple(results.catalog_entry(check) for check in check_catalog(role))
        for role in config.roles
    }
    provisional = results.RunResults(run, settings, started.isoformat(), catalog, {}, (), None)
    return _with_earlier_runs(provisional, output, checkout.path)


def _with_earlier_runs(
    provisional: results.RunResults, output: Path, repo: Path
) -> results.RunResults:
    """The provisional file with the runs beside it listed by what they measured."""
    this = measured_identity(provisional, repo)
    listing = results.earlier_runs(
        output.parent,
        tuple(provisional.catalog),
        _identity_differences(this, repo),
        replaced=_loaded_run_id(output),  # a file this run overwrites is no longer evidence
    )
    run = replace(
        provisional.run,
        earlier_runs=listing.for_older_readers(),
        extra={**provisional.run.extra, **results.earlier_to_json(listing)},
    )
    return replace(provisional, run=run)


def _identity_differences(this: MeasuredIdentity, repo: Path) -> results.Differences:
    """How an earlier run's role identity (its definition and kernel) differs from this run's.

    An identity that cannot be derived is a difference, so that run is listed apart, not lost.
    A run that recorded none has only the identity its commit held, which is an inference (the
    commit may not be what ran), so it is never a draw: it is listed apart, saying what its
    commit held.
    """

    def differences(earlier: results.RunResults, role: str) -> tuple[str, ...]:
        try:
            theirs = measured_identity(earlier, repo).roles[role]
        except (ValueError, KeyError) as error:
            return (f"identity cannot be derived ({error})",)
        found = diff(replace(this, roles={**this.roles, role: theirs}), this)
        if "identity" in earlier.run.extra:
            return found
        held = "; ".join(found) or "the same definition and kernel as this run"
        return (f"recorded no identity; its commit held {held}",)

    return differences


def _loaded_run_id(path: Path) -> str | None:
    try:
        return results.load(path).run.id
    except (OSError, ValueError):
        return None


# --- the paid run: conducting it ---


def conduct(context: Context, state: RunState) -> int:
    interrupted = False
    try:
        if context.config.judge_golden:
            state = _judge_golden(context, state)
        for role, role_tasks in context.planned.items():
            if state.stop is not None:
                break
            state = _measure_role(context, state, role, role_tasks)
    except KeyboardInterrupt:
        interrupted, state = True, _as_checkpointed(context)
    finally:
        _clean_up(context)
    final = _finalize(context, state, interrupted)
    print(f"wrote {context.output}")
    print(report.render(final), end="")
    return EXIT_COMPLETE if final.run.complete else EXIT_INCOMPLETE


def _as_checkpointed(context: Context) -> RunState:
    """The run as its last checkpoint recorded it. An interrupt unwinds through the steps that
    hold the newer state, but every session is checkpointed as it ends, so the file is the
    truth; the spend is the last settled one (a session in flight is not charged)."""
    on_disk = results.load(context.output)
    spent = on_disk.run.extra.get("spend", {}).get("spent_usd", 0.0)
    ledger = SpendLedger(cap_usd=context.config.run_cap_usd, spent_usd=spent)
    return RunState(on_disk, ledger)


def _clean_up(context: Context) -> None:
    if context.config.keep_sandbox:
        print(f"sandbox kept: {context.run_root}")
        return
    make_writable(context.run_root)  # a plugin copy inside it is read-only
    shutil.rmtree(context.run_root, ignore_errors=True)


def _finalize(context: Context, state: RunState, interrupted: bool) -> results.RunResults:
    ended = finalized(state.results, state.stop, interrupted, datetime.now(UTC))
    ended = replace(ended, standing=run_index.standing_ending_at(context.output.parent, ended))
    final = _checkpoint(context, replace(state, results=ended)).results
    run_index.write_index(context.output.parent)  # the file the index names is final now
    return final


def _judge_golden(context: Context, state: RunState) -> RunState:
    assert context.judge is not None  # parse_config refuses --judge-golden with --no-judge
    named = [check for role in context.config.roles for check in check_catalog(role)]
    record = golden_record(judge_golden_cases(context.judge, named))
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
        if state.stop is not None:
            return state
        state = _record_launch_order(context, state, role, task)
        for slot, copy_arm in _slots(config, runnable, task):
            if state.stop is not None:
                return state
            build = builds[(copy_arm, tasks.turn_cap_of(task))]
            state = _session_with_retry(context, state, task, slot, build)
    return state


def launch_order(seed: int, task_id: str) -> tuple[Arm, Arm]:
    """Which arm a task launches first, drawn from the run's seed and the task alone.

    Drawing per task spreads both orders over the list, so a drift in the account over the run
    falls on both arms alike; the seed and task fix it, so a rerun or a continuation repeats it.
    """
    first, second = random.Random(f"{seed}:{task_id}").sample(LAUNCH_ARMS, 2)
    return first, second


def ordered_arms(arms_named: Sequence[Arm], seed: int, task_id: str) -> list[Arm]:
    """The named arms in the task's launch order."""
    return [arm for arm in launch_order(seed, task_id) if arm in arms_named]


def _record_launch_order(context: Context, state: RunState, role: Role, task: TaskSpec) -> RunState:
    """Write the task's launch order into the results before its first session starts, so a
    continuation reads the order the stopped run used rather than drawing it again."""
    order = planned_order(context.config, task.task_id)
    recorded = state.results.run.extra.get("launch_order", {})
    per_role = {**recorded.get(role, {}), task.task_id: list(order)}
    state = _update_extra(state, launch_order={**recorded, role: per_role})
    return _checkpoint(context, state)


def planned_order(config: RunConfig, task_id: str) -> tuple[Arm, Arm]:
    """The order a task's slots run in: the calibration's fixed one, else the seed's draw."""
    return CALIBRATION_ORDER if config.calibration else launch_order(config.seed, task_id)


def _slots(config: RunConfig, runnable: Sequence[Arm], task: TaskSpec) -> list[tuple[Arm, Arm]]:
    """(the arm a session is recorded under, the arm whose copy it runs), in launch order.

    A calibration run records its second run of the full copy in the lean slot, so the
    ordinary pairing and verdict code reads it as a pair; it keeps that fixed order.
    """
    if config.calibration:
        return [("full", "full"), ("lean", "full")] if "full" in runnable else []
    return [(arm, arm) for arm in ordered_arms(runnable, config.seed, task.task_id)]


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
        ledger, done = attempt(
            _launch_of(context), state.ledger, proof_task, build, copy_home, None, _observe
        )
        state = _note_resolved_model(replace(state, ledger=ledger), done.model)
        match done.result:
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


# --- one session, with its one retry, each folded into the stop ---


def _session_with_retry(
    context: Context, state: RunState, task: TaskSpec, slot: Arm, build: ArmBuild
) -> RunState:
    state = _task_session(context, state, task, slot, build)
    if state.stop is not None:  # the run stopped on this session: no retry either
        return state
    last = state.results.sessions[-1].status
    if not (isinstance(last, Errored) and last.kind in RETRYABLE_ERRORS):
        return state
    retry = {"role": task.role, "arm": slot, "task_id": task.task_id, "after": last.kind}
    state = _update_extra(state, retries=[*state.results.run.extra["retries"], retry])
    return _task_session(context, state, task, slot, build)


def _task_session(
    context: Context, state: RunState, task: TaskSpec, slot: Arm, build: ArmBuild
) -> RunState:
    ledger, record, model = task_session(
        _launch_of(context), state.ledger, task, slot, build, state.page_fetchable
    )
    status = record.status
    if isinstance(status, Errored) and status.kind == "launch_refused":
        state = _add_refusal(state, f"{task.role} {slot} {task.task_id}: {status.detail}")
    state = replace(
        state,
        ledger=ledger,
        results=replace(state.results, sessions=(*state.results.sessions, record)),
    )
    return _checkpoint(context, _fold_stop(_note_resolved_model(state, model), record))


def _note_resolved_model(state: RunState, model: str | None) -> RunState:
    """Record the model a session's init event reported, once: the first session to report one."""
    identity = state.results.run.extra["identity"]
    if model is None or identity["model"] is not None:
        return state
    return _update_extra(state, identity={**identity, "model": model})


def _fold_stop(state: RunState, record: SessionRecord) -> RunState:
    """Fold one recorded task session into the infrastructure stop under the declared rule."""
    rule = state.results.settings.stop_rule
    assert rule is not None  # a run declares its stop rule before its first launch
    fold, decision = step(rule, state.fold, record)
    match decision:
        case Stop(reason=reason):
            return replace(state, fold=fold, stop=reason)
        case Continue():
            return replace(state, fold=fold)
        case _:
            assert_never(decision)


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
