"""Conduct a floor run or a paired run of a move: the refusals before any launch, then the sessions.

A run is first refused or prepared. Every refusal below raises :class:`RunRefusedError` naming what it
refuses, and nothing has been launched or written when it does: the kit the move needs, a stopped
run of the move that is neither continued nor closed, the arms (their declaration, relocation,
host reach and pinned settings, all inside ``arms.build``), the task count, and, for a paired
run, the floor citation and the governed checks that floor run showed can fail.

A prepared run declares its settings (the pinned ones, the stop rule, the allowance method) in a
results file written before the first launch, then runs each task's sessions in the order drawn
for it, one headless main session each. After each session it proves the arm's take from the
session's own record, grades the governed checks on the end state, folds the result into the
infrastructure stop and rewrites the results file whole. No session is launched to prove an arm.

A run ends ``Finished``, ``Stopped`` by the infrastructure stop, ``SpendRefused`` (a launch the
cap refused records no session), or ``Interrupted``; the file is final either way.

Two entries of every arm's identity are the runner's own: the digest of the arm's whole copy
(``TREE_ENTRY``) and of the kit's task list (``TASKS_ENTRY``). The results file holds no other
record of either, and a floor run is citable only by a paired run that would measure the same
(``floor_identity``), so a changed checkout or kit shows as a difference of identity.

Edges: ``launcher`` runs one session (a stand-in in unit tests) and ``clock`` reads the time.
"""

from __future__ import annotations

import hashlib
import shutil
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import assert_never

from praxion_evals.adherence.infra_stop import Continue, StopRule
from praxion_evals.adherence.lineage import Finished, Interrupted, PartRef, SpendRefused
from praxion_evals.adherence.model import (
    OWN_DISCORDANCE_EXACT,
    DeclaredSettings,
    Errored,
    Failed,
    Passed,
)
from praxion_evals.adherence.moves import (
    arms,
    checks_git,
    kit_git,
    launch,
    lineage,
    results,
    session_record,
    stop,
    take,
    trigger,
    verdict,
)
from praxion_evals.adherence.moves.lineage import (
    ChangeDigest,
    CheckCounts,
    CitedFloor,
    FloorIdentity,
    FloorPart,
    MoveEnding,
    MoveIdentity,
    Stopped,
    StoredRun,
)
from praxion_evals.adherence.moves.model import (
    ARMS_OF,
    MOVE_ARMS,
    CheckTrigger,
    FinalState,
    FixtureKind,
    Grade,
    MoveArm,
    MoveDeclaration,
    NothingToGrade,
    OnlyKind,
    Pinned,
    RunKind,
)
from praxion_evals.adherence.moves.results import (
    FloorRun,
    MoveRun,
    MoveRunCommon,
    MoveSession,
    PairedRun,
)
from praxion_evals.adherence.moves.session_record import Parsed, ToolUse
from praxion_evals.adherence.moves.tasks import MoveTask, TaskListError, target_with_slack
from praxion_evals.adherence.moves.verdict import MovePair, MoveVerdict, Side
from praxion_evals.adherence.results import new_run_id
from praxion_evals.adherence.run_identity import RESULTS_DIR
from praxion_evals.adherence.session_launch import DEFAULT_TAIL_CHARS, Attempt
from praxion_evals.adherence.session_loop import launch_order
from praxion_evals.adherence.tasks import DEFAULT_TARGET
from praxion_evals.live.materialize import digest_entries, make_writable, tree_entries
from praxion_evals.live.spend import SpendLedger

DEFAULT_FLOOR_TASKS = 8  # the floor run's declared handful of tasks
FLOOR_MINIMUM = 6
REFUSED_LAUNCH = "launch_refused"  # a session the spend cap refused: nothing started
WORKSPACE_PREFIX = "praxion-evals-moves-"
GIT_DIR = ".git/"
TREE_ENTRY = "(whole tree)"
TASKS_ENTRY = "(task list)"
EMPTY_DIGEST = hashlib.sha256(b"").hexdigest()  # what a removal leaves at its path
CONFIDENCE = verdict.CONFIDENCE

Launcher = Callable[..., tuple[SpendLedger, Attempt]]
Clock = Callable[[], datetime]


class RunRefusedError(ValueError):
    """A run refused before any launch; the message names what it refuses."""


@dataclass(frozen=True)
class Kit:
    """What a move needs of its task kit: the candidate tasks, the fixture, the end-state grader."""

    tasks: Callable[[MoveDeclaration, int], tuple[MoveTask, ...]]
    candidates: Callable[[], tuple[MoveTask, ...]]
    build_fixture: Callable[[MoveDeclaration, MoveTask, Path], Path]
    grade: Callable[..., Grade | NothingToGrade]


KITS: Mapping[str, Kit] = {
    "git-conventions": Kit(
        kit_git.tasks, kit_git.candidates, kit_git.build_fixture, checks_git.grade
    )
}


@dataclass(frozen=True)
class RunPlan:
    """What the operator asked of one run, fixed for its whole length."""

    declaration: MoveDeclaration
    kind: RunKind
    checkout: Path
    moves_dir: Path
    seed: int
    stop_rule: StopRule
    harness_version: str
    margin_pp: float
    session_budget_usd: float
    run_cap_usd: float
    ambient: Mapping[str, str]
    model: str
    effort: str
    max_tasks: int | None = None
    floor_run: str | None = None  # a run id of the floor lineage a paired run cites
    continues: str | None = None  # the stopped run this one picks up; see ``continuing``
    supplied_options: tuple[str, ...] = ()  # the options the operator named beside ``continues``
    target_pairs: int = DEFAULT_TARGET
    session_token_file: Path | None = None
    keep_sandbox: bool = False
    tail_chars: int = DEFAULT_TAIL_CHARS


@dataclass(frozen=True)
class Conducted:
    path: Path
    run: MoveRun


@dataclass(frozen=True)
class Scored:
    checks: Mapping[str, CheckTrigger]


@dataclass(frozen=True)
class Unscored:
    reason: str


@dataclass(frozen=True)
class _Prepared:
    kit: Kit
    arm_set: arms.ArmSet
    tasks: tuple[MoveTask, ...]
    base: MoveRunCommon  # the run before its first session
    cited: CitedFloor | None
    launch: launch.MoveLaunch
    planned: tuple[MoveTask, ...]  # the whole plan; ``tasks`` are those this run launches
    prior: tuple[MoveSession, ...] = ()  # the sessions the lineage's earlier parts launched


@dataclass(frozen=True)
class _State:
    """What each session replaces."""

    sessions: tuple[MoveSession, ...] = ()
    ledger: SpendLedger = SpendLedger(cap_usd=1.0)
    fold: stop.MoveFold = stop.MoveFold()
    stopped: stop.MoveStopReason | None = None
    refused_tasks: tuple[str, ...] = ()  # tasks whose launch the cap refused

    @property
    def halted(self) -> bool:
        return self.stopped is not None or bool(self.refused_tasks)


# ---------------------------------------------------------------------------
# The run
# ---------------------------------------------------------------------------


def conduct(
    plan: RunPlan,
    *,
    launcher: Launcher = launch.launch_session,
    clock: Clock = lambda: datetime.now(UTC),
) -> Conducted:
    """Prepare and run ``plan``; raises :class:`RunRefusedError` before anything is launched or written."""
    workspace = Path(tempfile.mkdtemp(prefix=WORKSPACE_PREFIX)).resolve()
    try:
        prepared = _prepare(plan, workspace, clock())
        return _run(plan, prepared, launcher)
    finally:
        if plan.keep_sandbox:
            print(f"sandbox kept: {workspace}")
        else:
            make_writable(workspace)  # an arm's copy is read-only
            shutil.rmtree(workspace, ignore_errors=True)


def _run(plan: RunPlan, prepared: _Prepared, launcher: Launcher) -> Conducted:
    state = _State(ledger=SpendLedger(cap_usd=plan.run_cap_usd))
    path = _checkpoint(plan, prepared, state, Interrupted())  # declared before the first launch
    interrupted = False
    try:
        for task in prepared.tasks:
            for arm in _order(plan, task):
                if state.halted:
                    break
                state = _session(plan, prepared, launcher, state, task, arm)
                path = _checkpoint(plan, prepared, state, Interrupted())
    except KeyboardInterrupt:
        interrupted = True
    ending = _ending(state, interrupted)
    path = _checkpoint(plan, prepared, state, ending)
    return Conducted(path, results.load(path))


def _order(plan: RunPlan, task: MoveTask) -> tuple[MoveArm, ...]:
    return launch_order(plan.seed, task.task_id) if plan.kind == "paired" else ("floor",)


def _ending(state: _State, interrupted: bool) -> MoveEnding:
    if interrupted:
        return Interrupted()
    if state.stopped is not None:
        return Stopped(state.stopped)
    if state.refused_tasks:
        return SpendRefused(state.refused_tasks)
    return Finished()


# ---------------------------------------------------------------------------
# One session
# ---------------------------------------------------------------------------


def _session(
    plan: RunPlan,
    prepared: _Prepared,
    launcher: Launcher,
    state: _State,
    task: MoveTask,
    arm: MoveArm,
) -> _State:
    declaration, kit = plan.declaration, prepared.kit
    ledger, attempt = launcher(
        prepared.launch,
        state.ledger,
        task,
        arm,
        prepared.arm_set.arms[arm].copy,
        lambda where: kit.build_fixture(declaration, task, where),
        lambda finished: _assess(plan, kit, task, arm, finished),
    )
    result = attempt.result
    if isinstance(result, Errored) and result.kind == REFUSED_LAUNCH:
        return replace(state, ledger=ledger, refused_tasks=(*state.refused_tasks, task.task_id))
    error = result if isinstance(result, Errored) else None
    fold, decision = stop.step(plan.stop_rule, state.fold, task.task_id, arm, error)
    recorded = _recorded(task, arm, fold.seen[-1].session.attempt, attempt)
    return replace(
        state,
        ledger=ledger,
        fold=fold,
        stopped=None if isinstance(decision, Continue) else decision.reason,
        sessions=(*state.sessions, recorded),
    )


def _assess(
    plan: RunPlan, kit: Kit, task: MoveTask, arm: MoveArm, finished: launch.Finished
) -> Scored | Unscored:
    """Prove the arm took from the session's own record, then grade each governed check."""
    declaration = plan.declaration
    if finished.record is None:
        return Unscored("the session left no record, so its arm cannot be proven")
    proof = take.prove(declaration, arm, finished.record, plan.checkout)
    if not proof.scored:
        return Unscored(proof.reason or "")
    events = session_record.parse(finished.record)
    commands = (
        [e.command for e in events.events if isinstance(e, ToolUse) and e.command]
        if isinstance(events, Parsed)
        else []
    )
    graded = {}
    for record in trigger.triggers(declaration, events):
        grade = kit.grade(declaration, record.check, finished.repo, task.named_files, commands)
        graded[record.check] = replace(record, final=_final_state(grade))
    return Scored(graded)


def _final_state(grade: Grade | NothingToGrade) -> FinalState:
    match grade:
        case NothingToGrade():
            return grade
        case Grade(failed_parts=parts):
            return Failed(", ".join(parts)) if parts else Passed()
        case _:
            assert_never(grade)


def _recorded(task: MoveTask, arm: MoveArm, attempt_number: int, attempt: Attempt) -> MoveSession:
    result = attempt.result
    match result:
        case Scored(checks=checks):
            status, reason, held = "scored", None, checks
        case Unscored(reason=reason):
            status, held = "refused", {}
        case Errored(kind=kind, detail=detail):
            status, reason, held = "errored", f"{kind}: {detail}", {}
        case _:
            assert_never(result)
    return MoveSession(
        f"{task.task_id}.{arm}.{attempt_number}",
        task.task_id,
        arm,
        attempt_number,
        status,
        reason,
        held,
        attempt.started_at,
        attempt.charged_usd,
        attempt.duration_ms,
    )


# ---------------------------------------------------------------------------
# The results file
# ---------------------------------------------------------------------------


def _checkpoint(plan: RunPlan, prepared: _Prepared, state: _State, ending: MoveEnding) -> Path:
    common = replace(
        prepared.base,
        sessions=state.sessions,
        first_launch_at=state.sessions[0].started_at if state.sessions else None,
        ending=ending,
    )
    if plan.kind == "floor":
        return results.write(plan.moves_dir, FloorRun(common))
    assert prepared.cited is not None  # a paired run is prepared only with its citation
    flip, verdicts = _standing(_verdict(plan, prepared, state.sessions))
    return results.write(plan.moves_dir, PairedRun(common, prepared.cited.lineage, flip, verdicts))


def _verdict(plan: RunPlan, prepared: _Prepared, sessions: tuple[MoveSession, ...]):
    """The lineage's reading so far: the earlier parts' sessions, then this part's."""
    return verdict.move_verdict(
        measurement(
            plan.declaration,
            plan.margin_pp,
            plan.target_pairs,
            prepared.planned,
            (*prepared.prior, *sessions),
        )
    )


def measurement(
    declaration: MoveDeclaration,
    margin_pp: float,
    target_pairs: int,
    tasks: Sequence[MoveTask],
    sessions: Sequence[MoveSession],
    floor: Sequence[MoveSession] = (),
) -> verdict.Measurement:
    """What a paired run measured, from its sessions alone; ``floor`` holds the cited floor's."""
    kinds: dict[str, FixtureKind] = {t.task_id: t.fixture_kind for t in tasks}
    latest = {(s.task_id, s.arm): s for s in sessions}  # a later record replaces an earlier
    pairs = tuple(
        MovePair(
            task_id,
            kinds[task_id],
            _side(latest.get((task_id, "full"))),
            _side(latest.get((task_id, "lean"))),
        )
        for task_id in dict.fromkeys(s.task_id for s in sessions)
    )
    scope = declaration.fixture_scope
    return verdict.Measurement(
        checks=tuple(c.name for c in declaration.checks.checks),
        margin_pp=margin_pp,
        target_pairs=target_pairs,
        kind_restriction=scope.kind if isinstance(scope, OnlyKind) else None,
        pairs=pairs,
        floor=tuple(_side(s) for s in floor),
    )


def _side(session: MoveSession | None) -> Side | None:
    """A scored session as the verdict reads it; any other (refused, errored, absent) is none."""
    if session is None or session.status != "scored":
        return None
    return Side(
        final={n: t.final for n, t in session.checks.items() if t.final is not None},
        history={n: t.history for n, t in session.checks.items() if t.history is not None},
        arrivals={n: t.arrivals for n, t in session.checks.items()},
    )


def _standing(measured: MoveVerdict) -> tuple[results.FlipLabel, dict[str, str]]:
    """Clearing needs the target's worth of pairs; before that no verdict is stated."""
    if measured.cleared is None:
        return "underpowered", {}
    return ("clear" if measured.cleared else "not clear"), dict(measured.check_verdicts)


# ---------------------------------------------------------------------------
# Before any launch
# ---------------------------------------------------------------------------


def planned_tasks(
    kind: RunKind, drawn: tuple[MoveTask, ...], max_tasks: int | None
) -> tuple[MoveTask, ...]:
    """The tasks a run launches: a prefix of the draw, which stays balanced across fixture kinds.

    A floor run takes the declared handful (never fewer than the minimum); ``max_tasks`` caps both.
    """
    if max_tasks is not None and max_tasks < 1:
        raise RunRefusedError(f"a run launches at least one task, got max-tasks {max_tasks}")
    count = min(DEFAULT_FLOOR_TASKS if kind == "floor" else len(drawn), max_tasks or len(drawn))
    if kind == "floor" and count < FLOOR_MINIMUM:
        raise RunRefusedError(f"a floor run holds at least {FLOOR_MINIMUM} tasks, got {count}")
    return drawn[:count]


def _prepare(plan: RunPlan, workspace: Path, declared: datetime) -> _Prepared:
    declaration = plan.declaration
    kit = KITS.get(declaration.move.value)
    if kit is None:
        raise RunRefusedError(
            f"the {declaration.move.value} move has no task kit, so no run of it exists"
        )
    if plan.continues is None:
        _require_no_pending_stop(plan)
        parts, continued_by = (), None
    else:
        parts, continued_by = read_lineage(plan.moves_dir, plan.continues)
    built = arms.build(
        declaration, plan.checkout, workspace / "arms", model=plan.model, effort=plan.effort
    )
    if isinstance(built, arms.ArmRefusal):
        raise RunRefusedError(f"arms: {built.reason}")
    try:
        drawn = kit.tasks(declaration, plan.seed)
    except TaskListError as error:
        raise RunRefusedError(f"tasks: {error}") from error
    tasks = (
        drawn[: len(parts[-1].common.planned_tasks)]
        if parts
        else planned_tasks(plan.kind, drawn, plan.max_tasks)
    )
    identity = _identity(declaration, plan.checkout, built, kit)
    if parts:
        _refuse_continuation(plan, parts, continued_by, identity, built.pinned, tasks)
    cited = _cite(plan, identity, built.pinned) if plan.kind == "paired" else None
    launched = _unfinished(plan, tasks, parts)
    base = _base(plan, built.pinned, identity, (tasks, launched), declared, parts)
    moves = launch.MoveLaunch(
        workspace,
        built.pinned,
        plan.session_budget_usd,
        plan.ambient,
        plan.session_token_file,
        plan.keep_sandbox,
        plan.tail_chars,
    )
    prior = tuple(s for part in parts for s in part.common.sessions)
    return _Prepared(kit, built, launched, base, cited, moves, tasks, prior)


def _require_no_pending_stop(plan: RunPlan) -> None:
    stored = [
        StoredRun(
            PartRef(
                r.common.run_id, plan.moves_dir / f"{r.common.run_id}.json", r.common.continues
            ),
            r.common.move.value,
            r.common.ending,
        )
        for r in results.read_directory(plan.moves_dir)[0]
    ]
    pending = lineage.pending_stop(stored, plan.declaration.move.value)
    if pending is not None:
        raise RunRefusedError(
            f"run {pending.run_id} of {plan.declaration.move.value} stopped and is neither"
            " continued nor closed; continue it or close it with a reason first"
        )


# ---------------------------------------------------------------------------
# Continuing a stopped run
# ---------------------------------------------------------------------------


def read_lineage(moves_dir: Path, run_id: str) -> tuple[tuple[MoveRun, ...], str | None]:
    """The parts of ``run_id``'s lineage up to it, oldest first, and the run that continues it
    (``None`` when it is the latest part). A run no readable results file holds is refused."""
    for group in results.lineage_groups(results.read_directory(moves_dir)[0], moves_dir):
        ids = [part.common.run_id for part in group]
        if run_id in ids:
            at = ids.index(run_id)
            return group[: at + 1], ids[at + 1] if at + 1 < len(ids) else None
    raise RunRefusedError(f"no readable move run {run_id} in {moves_dir}")


def continuing(plan: RunPlan, run_id: str, supplied: Sequence[str]) -> RunPlan:
    """``plan`` as the continuation of the stopped run ``run_id``: it declares what the run
    declared, so the run's kind, seed, stop rule, margin, target, model, effort and cited floor
    stand in place of the plan's own. What would make it measure something else is refused when
    it is prepared."""
    parts, _ = read_lineage(plan.moves_dir, run_id)
    common, tip = parts[0].common, parts[-1]
    return replace(
        plan,
        kind=tip.run_kind,
        seed=common.seed,
        stop_rule=common.settings.stop_rule or plan.stop_rule,
        margin_pp=common.settings.margin_pp,
        target_pairs=common.settings.required_pairs,
        model=next(iter(common.pinned.values())).model,
        effort=next(iter(common.pinned.values())).effort,
        floor_run=tip.cited_floor[-1] if isinstance(tip, PairedRun) else None,
        max_tasks=None,
        continues=run_id,
        supplied_options=tuple(supplied),
    )


def _refuse_continuation(
    plan: RunPlan,
    parts: Sequence[MoveRun],
    continued_by: str | None,
    identity: MoveIdentity,
    pinned: Pinned,
    tasks: Sequence[MoveTask],
) -> None:
    tip = parts[-1].common
    read = lineage.ReadTip(tip.run_id, tip.ending, tip.identity, continued_by)
    changed = (*_plan_changes(tip, tasks), *_pinned_changes(tip, pinned))
    refusals = lineage.continuation_refusals(read, identity, plan.supplied_options, changed)
    if refusals:
        raise RunRefusedError(
            f"run {tip.run_id} cannot be continued:" + "".join(f"\n  {line}" for line in refusals)
        )


def _plan_changes(tip: MoveRunCommon, tasks: Sequence[MoveTask]) -> tuple[str, ...]:
    if not tip.planned_tasks:
        return ("the run does not record its planned tasks",)
    drawn = tuple(t.task_id for t in tasks)
    return () if drawn == tip.planned_tasks else ("the tasks drawn differ from the ones planned",)


def _pinned_changes(tip: MoveRunCommon, pinned: Pinned) -> tuple[str, ...]:
    differing = {name for then in tip.pinned.values() for name in then.differences(pinned)}
    return tuple(f"the pinned {name} differs" for name in sorted(differing))


def _unfinished(
    plan: RunPlan, tasks: tuple[MoveTask, ...], parts: Sequence[MoveRun]
) -> tuple[MoveTask, ...]:
    """The planned tasks this run launches: all of a fresh run's, a continuation's unfinished."""
    if not parts:
        return tasks
    held = [
        (
            [
                lineage.Launch(s.task_id, s.arm, s.attempt, _error_kind(s))
                for s in part.common.sessions
            ],
            part.common.ending,
        )
        for part in parts
    ]
    again = lineage.relaunch_tasks([t.task_id for t in tasks], ARMS_OF[plan.kind], held)
    return tuple(t for t in tasks if t.task_id in again)


def _error_kind(session: MoveSession) -> str | None:
    """The error kind of an errored session, from the ``kind: detail`` reason ``_recorded`` wrote."""
    return (
        session.reason.partition(":")[0] if session.status == "errored" and session.reason else None
    )


def interim(run: MoveRun) -> dict[str, str]:
    """Per governed check, where the run stood: a paired run's verdict words, a floor run's
    final-state failures among the sessions scored."""
    if isinstance(run, PairedRun):
        return dict(run.verdicts)
    return {
        check: f"{counts.failed} of {counts.scored} scored sessions failed"
        for check, counts in _counts(run).items()
    }


def _identity(
    declaration: MoveDeclaration, checkout: Path, built: arms.ArmSet, kit: Kit
) -> MoveIdentity:
    """The moved rule's text and every arm's changes, with the runner's two whole-run digests."""
    pool = hashlib.sha256(
        "\n".join(sorted(f"{t.task_id}\t{t.wording}" for t in kit.candidates())).encode()
    ).hexdigest()
    return MoveIdentity(
        moved_rule_text=(checkout / declaration.moved_rule.value).read_text(encoding="utf-8"),
        arms={
            arm: (
                *(ChangeDigest(c.path, c.sha256 or EMPTY_DIGEST) for c in built.arms[arm].changes),
                ChangeDigest(TREE_ENTRY, _copy_digest(built.arms[arm].copy)),
                ChangeDigest(TASKS_ENTRY, pool),
            )
            for arm in MOVE_ARMS
        },
    )


def _copy_digest(copy: Path) -> str:
    """The digest of what an arm's session can read of its copy: the repository's own history and
    the results directory are left out, since a run's own results file (and git's bookkeeping) land
    in the checkout between one run and the next without changing what a session is shown."""
    entries = {
        path: entry
        for path, entry in tree_entries(copy).items()
        if not path.startswith((GIT_DIR, RESULTS_DIR))
    }
    return digest_entries(entries)


def floor_identity(
    declaration: MoveDeclaration, identity: MoveIdentity, pinned: Pinned
) -> FloorIdentity:
    """What a floor run was measured on, read from its identity and pinned settings alone."""
    held = {c.path: c.sha256 for c in identity.arms.get("floor", ())}
    return FloorIdentity(
        tree=held.get(TREE_ENTRY, ""),
        tasks=((TASKS_ENTRY, held.get(TASKS_ENTRY, "")),),
        checks=tuple((c.name, c.section) for c in declaration.checks.checks),
        model=pinned.model,
        effort=pinned.effort,
        settings=(
            ("commit_attribution", pinned.commit_attribution),
            ("user_instructions", pinned.user_instructions),
        ),
    )


def _cite(plan: RunPlan, identity: MoveIdentity, pinned: Pinned) -> CitedFloor:
    """The floor lineage this paired run cites, or a refusal naming why it may not."""
    declaration = plan.declaration
    floors = {
        r.common.run_id: FloorPart(
            PartRef(
                r.common.run_id, plan.moves_dir / f"{r.common.run_id}.json", r.common.continues
            ),
            floor_identity(declaration, r.common.identity, r.common.pinned["floor"]),
            r.common.ending,
            _counts(r),
        )
        for r in results.read_directory(plan.moves_dir)[0]
        if isinstance(r, FloorRun) and r.common.move == declaration.move
    }
    now = floor_identity(declaration, identity, pinned)
    cited = lineage.cite(floors, plan.floor_run, now, [c.name for c in declaration.checks.checks])
    if isinstance(cited, CitedFloor):
        return cited
    raise RunRefusedError(lineage.refusal_text(cited))


def _counts(run: FloorRun) -> dict[str, CheckCounts]:
    """Per governed check, the final-state failures among the floor sessions that graded it; one
    that left nothing to grade is neither a failure nor graded, so it cannot make a floor citable."""
    finals = [s.checks for s in run.common.sessions if s.status == "scored"]
    names = {name for checks in finals for name in checks}
    return {
        name: CheckCounts(
            sum(isinstance(c[name].final, Failed) for c in finals if name in c),
            sum(isinstance(c[name].final, Passed | Failed) for c in finals if name in c),
        )
        for name in names
    }


def _base(
    plan: RunPlan,
    pinned: Pinned,
    identity: MoveIdentity,
    tasks: tuple[tuple[MoveTask, ...], tuple[MoveTask, ...]],
    declared: datetime,
    parts: Sequence[MoveRun] = (),
) -> MoveRunCommon:
    """The run before its first session; ``tasks`` are the whole plan and those this run launches."""
    declaration = plan.declaration
    arms_run = ARMS_OF[plan.kind]
    planned, launched = tasks
    return MoveRunCommon(
        run_id=new_run_id(declared),
        move=declaration.move,
        identity=identity,
        settings=_settings(plan),
        pinned=dict.fromkeys(arms_run, pinned),
        declared_at=declared.isoformat(),
        first_launch_at=None,
        seed=plan.seed,
        launch_orders=(
            {t.task_id: launch_order(plan.seed, t.task_id) for t in launched}
            if plan.kind == "paired"
            else {}
        ),
        sessions=(),
        continues=plan.continues,
        ending=Interrupted(),
        harness_version=plan.harness_version,
        earlier=results.earlier_runs(
            plan.moves_dir,
            declaration.move,
            identity,
            exclude=[part.common.run_id for part in parts],
        ),
        planned_tasks=tuple(t.task_id for t in planned),
    )


def _settings(plan: RunPlan) -> DeclaredSettings:
    """Declared before the first launch: no calibration run, so the allowance is the run's own."""
    return DeclaredSettings(
        margin_pp=plan.margin_pp,
        method="tango-score",
        confidence=CONFIDENCE,
        sidedness="one-sided",
        required_pairs=plan.target_pairs,
        pair_slack=target_with_slack(plan.target_pairs) - plan.target_pairs,
        retry_policy=verdict.MOVE_RETRY_POLICY,
        allowance_source=None,
        allowances={},
        stop_rule=plan.stop_rule,
        allowance_method=OWN_DISCORDANCE_EXACT if plan.kind == "paired" else None,
    )
