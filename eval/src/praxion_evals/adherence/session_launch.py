"""One paid session: reserve its budget, sandbox it, start it, settle it, read it, grade it.

``session_loop`` conducts the run and owns its state; this module is the half that
launches a single ``claude`` session. It reads nothing of the run but what ``Launch``
carries and returns what a session produced (a ledger and a record), so it never imports
the run's context or state back.
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from praxion_evals.adherence import grade, managed_fixture, tasks
from praxion_evals.adherence.catalog import check_catalog
from praxion_evals.adherence.confinement import (
    Confinement,
    Operator,
    Places,
    ShellRun,
    confinement_breach,
    confinement_for,
)
from praxion_evals.adherence.infra_stop import EvidenceTail, redacted
from praxion_evals.adherence.model import (
    Arm,
    ArmBuild,
    EarlyStop,
    Errored,
    RefusedCommand,
    Role,
    SessionEvidence,
    SessionRecord,
    SessionSetup,
    SessionStatus,
    Standard,
    TaskSpec,
)
from praxion_evals.adherence.transcript import Refusal, refused_commands
from praxion_evals.harness.judge_client import JudgeClient
from praxion_evals.live.materialize import install_user_scope, remove_tree
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
# A refused command is committed text in the results file, so it is bounded like a tail.
REFUSED_COMMAND_CHARS = 300


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
    # a session's environment, given its sandbox root and the directories its programs resolve from first
    env_for: Callable[[Path, Sequence[Path]], Mapping[str, str]]
    tail_chars: int = DEFAULT_TAIL_CHARS  # what an errored session keeps of each output stream
    # the operator inputs a confined kit's sandbox is built around; `ambient` is the same
    # environment the session's `env_for` reads, so the confinement and the PATH agree
    real_home: Path = REAL_HOME
    token_file: Path | None = None
    ambient: Mapping[str, str] = field(default_factory=lambda: os.environ)


# --- one task session ---


def task_session(
    launch: Launch,
    ledger: SpendLedger,
    task: TaskSpec,
    slot: Arm,
    build: ArmBuild,
    page_fetchable: bool | None,
) -> tuple[SpendLedger, SessionRecord, str | None]:
    """The session's ledger and record, and the model its init event reported (None if none)."""
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
        lambda evidence: _grade(launch, evidence, task, setup),
    )
    status: SessionStatus = done.result
    if isinstance(status, Errored):
        status = replace(status, setup=setup)
    record = SessionRecord(
        setup, status, done.charged_usd, done.duration_ms, done.started_at, done.refused_commands
    )
    print(
        f"{task.role} {slot} {task.task_id}: {type(status).__name__}", file=sys.stderr, flush=True
    )
    return ledger, record, done.model


def _grade(
    launch: Launch, evidence: SessionEvidence, task: TaskSpec, setup: SessionSetup
) -> SessionStatus:
    """C3 is named only for a task that planted a gap or a conflict: without one it passes vacuously."""
    names = [
        check.name
        for check in check_catalog(task.role)
        if not (check.name == "C3" and isinstance(task.variant, EarlyStop))
    ]
    return grade.grade(evidence, names, launch.judge, setup, real_home=launch.real_home)


def injection_of(task: TaskSpec) -> tasks.Injection | None:
    return task.variant.injection if isinstance(task.variant, Standard) else None


# --- one launch: reserve, sandbox, start, settle, read, assess ---


@dataclass(frozen=True)
class Attempt[R]:
    """One session's assessment, or the error that kept it from having one.

    ``charged_usd`` is what the ledger took: the reported cost, or the full budget when the
    session reported none. An errored result carries the tails of the session's output.
    ``model`` is the model the session's init event reported; None when it started no process
    or the stream carried none. ``refused_commands`` are the shell commands the harness refused
    the role, redacted and bounded.
    """

    result: R | Errored
    charged_usd: float
    duration_ms: int
    started_at: str
    model: str | None = None
    refused_commands: tuple[RefusedCommand, ...] = ()


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

    def finish(
        result: R | Errored,
        charged: float,
        tails: EvidenceTail = NO_OUTPUT,
        model: str | None = None,
        refused: tuple[RefusedCommand, ...] = (),
    ) -> Attempt[R]:
        if isinstance(result, Errored):
            result = replace(result, tails=tails)
        duration_ms = int((time.monotonic() - began) * MS_PER_S)
        return Attempt(result, charged, duration_ms, started_at, model, refused)

    reserved = ledger.reserve(budget)
    if isinstance(reserved, LiveErrored):
        return ledger, finish(Errored("launch_refused", reserved.detail), 0.0)
    root = new_sandbox_root(launch, task)
    try:
        try:
            spec, commit, confinement = _prepare(launch, task, build, populate, page_url, root)
        except Exception as error:  # nothing was started, so nothing was spent
            return reserved.settle(budget, 0.0), finish(_crash(error), 0.0)
        try:
            env = {
                **launch.env_for(root, [Path(path) for path in _program_order(confinement)]),
                **managed_fixture.switches_for(tasks.scratch_dir(SandboxPaths(root))),
            }
            run = run_session(spec, env)
        except Exception as error:  # the process may have run and spent: charge the budget
            return reserved.settle(budget, None), finish(_crash(error), budget)
        settled, charged = settle(reserved, budget, run)
        tails, model = tails_of(run, env, launch.tail_chars), resolved_model(run)
        result, refused = _assessed(launch, task, build, page_url, root, run, commit, env, assess)
        return settled, finish(result, charged, tails, model, refused)
    finally:
        if not launch.keep_sandbox:
            remove_tree(root)


def _assessed[R](
    launch: Launch,
    task: TaskSpec,
    build: ArmBuild,
    page_url: str | None,
    root: Path,
    run: SessionRun,
    commit: str,
    session_env: Mapping[str, str],
    assess: Callable[[SessionEvidence], R],
) -> tuple[R | Errored, tuple[RefusedCommand, ...]]:
    """What the session's output yields: its assessment (or the error that kept it from having
    one), and the commands the harness refused the role.

    A confined kit's broken confinement replaces the assessment, whatever it was: the session
    ran under other settings than the run declared, so its outcome says nothing of the role.
    The breach is read from the commands as they ran; the record keeps them clipped.
    """
    judged: tuple[RefusedCommand, ...] = ()
    tool_results: Iterable[str] = ()
    shell_runs: tuple[ShellRun, ...] = ()
    try:
        evidence = _evidence(launch, task, build, page_url, root, run, commit)
        judged = redacted_refusals(evidence, session_env)
        tool_results = evidence.envelope.tool_results.values()
        shell_runs = _shell_runs(evidence)
        result: R | Errored = assess(evidence)
    except Exception as error:  # one unreadable session must not discard the paid run
        result = _crash(error)
    secrets = _credentials(session_env)
    broken = confinement_breach(
        task.role,
        judged,
        (redacted(text, secrets) for text in tool_results),
        redacted(run.stderr, secrets),
        started=parse_stream(run.stdout).init is not None,
        shell_runs=(
            ShellRun(redacted(r.command, secrets), redacted(r.output, secrets)) for r in shell_runs
        ),
    )
    return (result if broken is None else Errored("confinement_broken", broken)), clipped(judged)


def _crash(error: Exception) -> Errored:
    return Errored("evaluation_exception", f"{type(error).__name__}: {error}")


def new_sandbox_root(launch: Launch, task: TaskSpec) -> Path:
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
) -> tuple[SessionSpec, str, Confinement | None]:
    """Populate the sandbox and build the scratch repository; nothing is launched yet.

    Returns the session to launch, the fixture commit the scratch repository starts from, and the
    confinement the session starts under (None for a kit that is not confined).
    """
    sandbox = SandboxPaths(root)
    populate(root)
    commit = tasks.build_scratch_repo(task, tasks.scratch_dir(sandbox), page_url)
    # marked after the fixture commit, so the marker is no part of what the session authors
    managed_fixture.mark_managed(tasks.scratch_dir(sandbox))
    confinement = session_confinement(
        task.role,
        build.copy_root,
        launch.run_root,
        home=launch.real_home,
        token_file=launch.token_file,
        ambient=launch.ambient,
    )
    spec = tasks.session_spec(
        task,
        build,
        sandbox,
        model=launch.model,
        effort=launch.effort,
        max_budget_usd=launch.session_budget_usd,
        confinement=confinement,
    )
    return spec, commit, confinement


def session_confinement(
    role: Role,
    plugin_copy: Path,
    run_root: Path,
    *,
    home: Path,
    token_file: Path | None,
    ambient: Mapping[str, str],
) -> Confinement | None:
    """The confinement of a `role` session on this machine; None for a kit that is not confined.

    The one place the runner's interpreter and the ambient PATH are read into the confinement, so
    the dry run shows what a live session gets. A relative PATH entry names no fixed directory, so
    it is left out of the confinement's program order (the session's own PATH is built apart).
    """
    ambient_path = tuple(
        entry for entry in ambient.get("PATH", os.defpath).split(os.pathsep) if os.path.isabs(entry)
    )
    operator = Operator(home, token_file, Path(sys.prefix), Path(sys.base_prefix), ambient_path)
    return confinement_for(role, Places(run_root, plugin_copy), operator)


def _program_order(confinement: Confinement | None) -> tuple[str, ...]:
    return () if confinement is None else confinement.program_order


def settle(ledger: SpendLedger, budget: float, run: SessionRun) -> tuple[SpendLedger, float]:
    """Settle the reservation at the reported cost, or at the full budget when none was reported."""
    final = parse_stream(run.stdout).final_result
    cost = None if final is None else final.total_cost_usd
    return ledger.settle(budget, cost), budget if cost is None else cost


def resolved_model(run: SessionRun) -> str | None:
    init = parse_stream(run.stdout).init
    return None if init is None else init.model


def tails_of(run: SessionRun, env: Mapping[str, str], bound: int) -> EvidenceTail:
    """The end of the session's error output and of its result text, with the credentials
    the session was given (and any API key shape) redacted before the bound clips them."""
    final = parse_stream(run.stdout).final_result
    result_text = final.result_text if final and final.result_text else ""
    return EvidenceTail.capture(run.stderr, result_text, bound, _credentials(env))


def _credentials(env: Mapping[str, str]) -> list[str]:
    return [env[key] for key in CREDENTIAL_KEYS if key in env]


def redacted_refusals(
    evidence: SessionEvidence, env: Mapping[str, str]
) -> tuple[RefusedCommand, ...]:
    """The commands the harness refused the role, whole, with the credentials the session was
    given (and any API key shape) redacted: what the breach reading judges."""
    secrets = _credentials(env)
    return tuple(
        RefusedCommand(_redacted(refusal.command, secrets), refusal.source)
        for refusal in _refusals(evidence)
    )


def _refusals(evidence: SessionEvidence) -> tuple[Refusal, ...]:
    final = evidence.envelope.final_result
    denied = () if final is None else final.denied_commands
    return refused_commands(evidence.envelope, evidence.role_tool_uses, denied)


def clipped(
    refusals: Sequence[RefusedCommand], bound: int = REFUSED_COMMAND_CHARS
) -> tuple[RefusedCommand, ...]:
    """The refusals as the record keeps them: each command bounded, after its redaction."""
    return tuple(RefusedCommand(r.command[:bound], r.source) for r in refusals)


def _redacted(command: str, secrets: list[str]) -> str:
    return EvidenceTail.capture(command, "", len(command), secrets).error_tail


def _shell_runs(evidence: SessionEvidence) -> tuple[ShellRun, ...]:
    """Each shell command the role ran, with the output its tool result carried. A command the
    harness refused never ran, so it is none of them, matched whole before any redaction: the
    breach reading takes these as the commands the grant let through."""
    results = evidence.envelope.tool_results
    refused = {refusal.command for refusal in _refusals(evidence)}
    return tuple(
        ShellRun(use.input["command"], results.get(use.id, ""))
        for use in evidence.role_tool_uses
        if use.name == "Bash"
        and isinstance(use.input.get("command"), str)
        and use.input["command"] not in refused
    )


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
