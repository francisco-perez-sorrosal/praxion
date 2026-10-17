"""One paid session: reserve its budget, sandbox it, start it, settle it, read it, grade it.

``session_loop`` conducts the run and owns its state; this module is the half that
launches a single ``claude`` session. It reads nothing of the run but what ``Launch``
carries and returns what a session produced (a ledger and a record), so it never imports
the run's context or state back.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from praxion_evals.adherence import grade, tasks
from praxion_evals.adherence.catalog import check_catalog
from praxion_evals.adherence.infra_stop import EvidenceTail
from praxion_evals.adherence.model import (
    Arm,
    ArmBuild,
    EarlyStop,
    Errored,
    SessionEvidence,
    SessionRecord,
    SessionSetup,
    SessionStatus,
    Standard,
    TaskSpec,
)
from praxion_evals.harness.judge_client import JudgeClient
from praxion_evals.live.materialize import install_user_scope
from praxion_evals.live.report import CREDENTIAL_KEYS
from praxion_evals.live.results import Errored as LiveErrored
from praxion_evals.live.session import (
    SandboxPaths,
    SessionRun,
    SessionSpec,
    parse_stream,
    run_session,
)
from praxion_evals.live.spend import SpendLedger

MS_PER_S = 1000
REAL_HOME = Path.home()  # read once, here: the isolation scan takes it in as an input
# What an errored session keeps of each output stream when the run declares no other bound
# (the run's declared bound, `RunConfig.tail_chars`, reaches `Launch.tail_chars`).
DEFAULT_TAIL_CHARS = 2000
# A session that never started, or whose output is lost, has no output to keep.
NO_OUTPUT = EvidenceTail("", "")


@dataclass(frozen=True)
class Launch:
    """What a session launch reads of the run; fixed for the whole run."""

    run_root: Path
    checkout_commit: str
    page_url: str
    judge: JudgeClient | None
    seed: int
    model: str
    effort: str
    session_budget_usd: float
    keep_sandbox: bool
    env_for: Callable[[Path], Mapping[str, str]]  # a session's environment, given its sandbox root
    tail_chars: int = DEFAULT_TAIL_CHARS  # what an errored session keeps of each output stream


# --- one task session ---


def task_session(
    launch: Launch,
    ledger: SpendLedger,
    task: TaskSpec,
    slot: Arm,
    build: ArmBuild,
    page_fetchable: bool | None,
) -> tuple[SpendLedger, SessionRecord]:
    setup = SessionSetup(
        arm=slot,
        checkout_commit=launch.checkout_commit,
        role=task.role,
        task_id=task.task_id,
        template_id=task.template_id,
        seed=launch.seed,
    )
    page_url = launch.page_url if injection_of(task) and page_fetchable else None

    def populate(root: Path) -> None:
        install_user_scope(build.copy_root, root)

    ledger, done = attempt(
        launch,
        ledger,
        task,
        build,
        populate,
        page_url,
        lambda evidence: _grade(launch.judge, evidence, task, setup),
    )
    status: SessionStatus = done.result
    if isinstance(status, Errored):
        status = replace(status, setup=setup)
    record = SessionRecord(setup, status, done.charged_usd, done.duration_ms, done.started_at)
    print(
        f"{task.role} {slot} {task.task_id}: {type(status).__name__}", file=sys.stderr, flush=True
    )
    return ledger, record


def _grade(
    judge: JudgeClient | None, evidence: SessionEvidence, task: TaskSpec, setup: SessionSetup
) -> SessionStatus:
    """C3 is named only for a task that planted a gap or a conflict: without one it passes vacuously."""
    names = [
        check.name
        for check in check_catalog(task.role)
        if not (check.name == "C3" and isinstance(task.variant, EarlyStop))
    ]
    return grade.grade(evidence, names, judge, setup, real_home=REAL_HOME)


def injection_of(task: TaskSpec) -> tasks.Injection | None:
    return task.variant.injection if isinstance(task.variant, Standard) else None


# --- one launch: reserve, sandbox, start, settle, read, assess ---


@dataclass(frozen=True)
class Attempt[R]:
    """One session's assessment, or the error that kept it from having one.

    ``charged_usd`` is what the ledger took: the reported cost, or the full budget when the
    session reported none. An errored result carries the tails of the session's output.
    """

    result: R | Errored
    charged_usd: float
    duration_ms: int
    started_at: str


def attempt[R](
    launch: Launch,
    ledger: SpendLedger,
    task: TaskSpec,
    build: ArmBuild,
    populate: Callable[[Path], None],
    page_url: str | None,
    assess: Callable[[SessionEvidence], R],
) -> tuple[SpendLedger, Attempt[R]]:
    """Run one session in a fresh sandbox and scratch repository, assess it, and clean up.

    The budget is reserved first and a refusal starts nothing. A session that never started
    settles at nothing; one whose process may have started and spent settles at the full
    budget when its outcome is lost. The sandbox outlives the assessment because a check
    may run a script against the scratch repository.
    """
    budget = launch.session_budget_usd
    started_at, began = datetime.now(UTC).isoformat(), time.monotonic()

    def finish(result: R | Errored, charged: float, tails: EvidenceTail = NO_OUTPUT) -> Attempt[R]:
        if isinstance(result, Errored):
            result = replace(result, tails=tails)
        return Attempt(result, charged, int((time.monotonic() - began) * MS_PER_S), started_at)

    reserved = ledger.reserve(budget)
    if isinstance(reserved, LiveErrored):
        return ledger, finish(Errored("launch_refused", reserved.detail), 0.0)
    root = _new_sandbox_root(launch, task)
    try:
        try:
            spec, commit = _prepare(launch, task, build, populate, page_url, root)
        except Exception as error:  # nothing was started, so nothing was spent
            return reserved.settle(budget, 0.0), finish(_crash(error), 0.0)
        try:
            env = launch.env_for(root)
            run = run_session(spec, env)
        except Exception as error:  # the process may have run and spent: charge the budget
            return reserved.settle(budget, None), finish(_crash(error), budget)
        settled, charged = _settle(reserved, budget, run)
        tails = _tails_of(run, env, launch.tail_chars)
        try:
            evidence = _evidence(launch, task, build, page_url, root, run, commit)
            return settled, finish(assess(evidence), charged, tails)
        except Exception as error:  # one unreadable session must not discard the paid run
            return settled, finish(_crash(error), charged, tails)
    finally:
        if not launch.keep_sandbox:
            shutil.rmtree(root, ignore_errors=True)


def _crash(error: Exception) -> Errored:
    return Errored("evaluation_exception", f"{type(error).__name__}: {error}")


def _new_sandbox_root(launch: Launch, task: TaskSpec) -> Path:
    parent = launch.run_root / task.role / "sessions"
    parent.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix="s-", dir=parent))


def _prepare(
    launch: Launch,
    task: TaskSpec,
    build: ArmBuild,
    populate: Callable[[Path], None],
    page_url: str | None,
    root: Path,
) -> tuple[SessionSpec, str]:
    """Populate the sandbox and build the scratch repository; nothing is launched yet.

    Returns the session to launch and the fixture commit the scratch repository starts from.
    """
    sandbox = SandboxPaths(root)
    populate(root)
    commit = tasks.build_scratch_repo(task, tasks.scratch_dir(sandbox), page_url)
    spec = tasks.session_spec(
        task,
        build,
        sandbox,
        model=launch.model,
        effort=launch.effort,
        max_budget_usd=launch.session_budget_usd,
    )
    return spec, commit


def _settle(ledger: SpendLedger, budget: float, run: SessionRun) -> tuple[SpendLedger, float]:
    """Settle the reservation at the reported cost, or at the full budget when none was reported."""
    final = parse_stream(run.stdout).final_result
    cost = None if final is None else final.total_cost_usd
    return ledger.settle(budget, cost), budget if cost is None else cost


def _tails_of(run: SessionRun, env: Mapping[str, str], bound: int) -> EvidenceTail:
    """The end of the session's error output and of its result text, with the credentials
    the session was given (and any API key shape) redacted before the bound clips them."""
    final = parse_stream(run.stdout).final_result
    result_text = final.result_text if final and final.result_text else ""
    secrets = [env[key] for key in CREDENTIAL_KEYS if key in env]
    return EvidenceTail.capture(run.stderr, result_text, bound, secrets)


def _evidence(
    launch: Launch,
    task: TaskSpec,
    build: ArmBuild,
    page_url: str | None,
    root: Path,
    run: SessionRun,
    commit: str,
) -> SessionEvidence:
    return grade.evidence_from_recording(
        role=task.role,
        envelope=run.stdout,
        repo_root=tasks.scratch_dir(SandboxPaths(root)),
        fixture_commit=commit,
        sandbox=root,
        plugin_copy=build.copy_root,
        slug=task.slug,
        exit_code=run.exit_code,
        timed_out=run.timed_out,
        judging=launch.judge is not None,
        # The lean arm of an adopted role is owed its kernel; its delivery markers are read from
        # the role's transcript under the sandbox's config dir, since a sandbox's observation log
        # is never written and the parent stream never carries a subagent's hook output.
        kernel_expected=build.arm == "lean" and grade.kernel_adopted(build.copy_root, task.role),
        config_dir=SandboxPaths(root).config_dir,
        **_task_facts(task, page_url is not None),
    )


def _task_facts(task: TaskSpec, page_available: bool) -> dict[str, Any]:
    """The task's own flags for the grader; ``page_available`` is the C6 probe's answer."""
    injection = injection_of(task)
    return {
        "forced_stop": isinstance(task.variant, EarlyStop),
        "turn_cap": tasks.turn_cap_of(task),
        "fetchable_page": injection is not None and page_available,
        "planted_instruction": injection.instruction if injection else None,
        "planted_effect": injection.effect_path if injection else None,
    }
