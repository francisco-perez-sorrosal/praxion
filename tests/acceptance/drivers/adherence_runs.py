"""Driver for whole adherence runs: a stand-in launcher, stops, continuations and listings.

A scenario runs the adherence eval the way an operator does, through its console entry,
with every session answered by a stand-in instead of a real, paying `claude`. The
scenario scripts how each session ends, in the specification's terms:

- `ran()`: the session ran to a gradeable end (the run grades it without error);
- `graded_failure()`: the role ran and its checks failed: a behavioural outcome;
- `isolation_breach()`: the session's own startup telemetry shows a plugin from
  outside its sandbox;
- `crashed(text)`: the session exited non-zero, `text` on its error output;
- `error_result(text)`: the session's stream ended in an error result carrying `text`
  (the way a spent credit balance ends a session);
- `unparseable()`: the session printed no parseable result.

A script gives each arm a sequence of endings in that arm's own launch order (a retry
is the next launch of its arm), or names an ending for a task's arm by its position in
the run's planned task order; every other session `ran()`.

Bound here, because the specification or the base commit fixes them: the console
entry and its existing options (`adherence_eval`), `--max-tasks`, `--model`,
`--calibration` and `--calibration-run`, the dry run's JSON lines, a checkout under
test (a committed copy of this repository), committing a file in it, and the stand-in
launcher itself (`stand_in_claude`): it passes each arm's proof, ends each session as the
script says, and reports every launch with its arm, task and attempt.

Unbound until a binding step names the designed surface (each raises with the
assumption it stands for): continuing and closing a run, a stopped run constructed in the
runner's own format, the dry run's per-task launch order, and every reading of what this
change adds to a results file (the error tails, the stop, the declared stop settings, the
allowance method, the lineage, the worst-case lean failures and the earlier-runs
listing). Where the results directory sits is bound: a run writes into
`<checkout>/.ai-state/eval_ledger/adherence/`, beside every earlier run of the checkout.

A run is started from inside the checkout (the console entry names its default results
directory after the repository it is started in), with no judge, no spend cap in the way
of a stand-in that reports no cost, and a fixture-page address nothing answers, so a
scenario stays offline and deterministic.
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from tests.acceptance.drivers import adherence_eval, stand_in_claude
from tests.acceptance.drivers.adherence_eval import (
    DUMMY_CREDENTIAL,
    EVAL_PROJECT,
    EVAL_PYTHON,
    FAKE_CLAUDE_VERSION,
    RunRequest,
    _git,
    _guarded_path,
    _uv,
    adherence_console_entry,
    checkout_under_test,
    eval_env,
    install_fake_claude,
    planned_sessions,
    run_adherence_eval,
)
from tests.acceptance.drivers.kernel_sandbox import UnboundDriverError

RESULTS_SUBDIR = Path(".ai-state") / "eval_ledger" / "adherence"
ROLE = "researcher"  # a role with a full kit: 24 planned tasks by default
DEFAULT_STOP_COUNT = 3
PLANTED_SECRET = "sk-ant-oat01-acceptance-planted-session-secret-7f3a9c"
RUN_TIMEOUT_S = 1800  # 24 tasks in two arms, each session a process of its own
NO_SPEND_CAP_USD = (
    1_000_000  # a stand-in spends nothing; a session that reports no cost is charged its budget
)
UNREACHABLE_PAGES = "http://127.0.0.1:9/"  # nothing answers: the fetched-page probe fails at once

EndingKind = Literal[
    "ran", "graded failure", "isolation breach", "crashed", "error result", "unparseable"
]


@dataclass(frozen=True)
class Ending:
    kind: EndingKind
    error_output: str = ""  # what the session wrote on its error output
    result_text: str = ""  # the text of its final result event


def ran() -> Ending:
    return Ending("ran")


def graded_failure() -> Ending:
    return Ending("graded failure")


def isolation_breach() -> Ending:
    return Ending("isolation breach")


def crashed(text: str) -> Ending:
    return Ending("crashed", error_output=text)


def error_result(text: str, error_output: str = "") -> Ending:
    return Ending("error result", error_output=error_output, result_text=text)


def unparseable() -> Ending:
    return Ending("unparseable")


# Volatile tokens the masking rule hides: an id, a timestamp, a request id, a duration and
# a byte count. Two tails built from one template differ only in these.
CREDIT_TEMPLATE = (
    "API Error: 400 request {request_id} for session {uuid} at {timestamp}:"
    " Your credit balance is too low to access the Anthropic API. Waited {duration}ms,"
    " received {size} bytes."
)
VOLATILE_SETS = (
    {
        "request_id": "req_011CTx9yQe4kz7AbcDefGh12",
        "uuid": "3f2a9c1e-7b4d-4e8f-9a0b-1c2d3e4f5a6b",
        "timestamp": "2026-10-16T09:12:44.123Z",
        "duration": "1834",
        "size": "412",
    },
    {
        "request_id": "req_011CTxB7mWq2r9StuVwXyZ34",
        "uuid": "9e8d7c6b-5a4f-4321-8fed-cba987654321",
        "timestamp": "2026-10-16T09:13:02.981Z",
        "duration": "2207",
        "size": "398",
    },
    {
        "request_id": "req_011CTxC4pLk8s1MnoPqRsT56",
        "uuid": "0a1b2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d",
        "timestamp": "2026-10-16T09:13:30.004Z",
        "duration": "977",
        "size": "1024",
    },
)


def credit_exhausted(variant: int = 0) -> Ending:
    """A spent credit balance: the same error, its volatile tokens taken from `variant`."""
    text = CREDIT_TEMPLATE.format(**VOLATILE_SETS[variant % len(VOLATILE_SETS)])
    return error_result(text, error_output=text)


def connection_refused() -> Ending:
    """An error of the same kind as a spent credit balance, with a genuinely different tail."""
    return error_result(
        "API Error: Connection error: connect ECONNREFUSED 127.0.0.1:443",
        error_output="API Error: Connection error: connect ECONNREFUSED 127.0.0.1:443",
    )


@dataclass(frozen=True)
class Script:
    """How each session of a run ends."""

    by_arm: Mapping[str, Sequence[Ending]] = field(default_factory=dict)
    by_task: Mapping[tuple[int, str], Ending] = field(default_factory=dict)  # (position, arm)
    default: Ending = field(default_factory=ran)


@dataclass(frozen=True)
class Plan:
    """What the operator asks for: a role, a small task list, and the run's declarations."""

    role: str = ROLE
    arms: tuple[str, ...] = ("full", "lean")
    max_tasks: int = 6
    seed: int = adherence_eval.SEED
    stop_count: int | None = None  # None: the declared default
    model: str | None = None
    margin_pp: float | None = None
    calibration: bool = False
    calibration_run: Path | None = None


@dataclass(frozen=True)
class LaunchedSession:
    arm: str
    task_id: str
    attempt: int  # 1 for a task's first session in that arm, 2 for its retry


@dataclass(frozen=True)
class StandInRun:
    exit_code: int
    stdout: str
    stderr: str
    results_path: Path
    launches: tuple[LaunchedSession, ...]  # the task sessions, in launch order
    proofs: tuple[LaunchedSession, ...] = ()  # the arm proofs, which are not task sessions

    def launches_in(self, arm: str) -> list[LaunchedSession]:
        return [launch for launch in self.launches if launch.arm == arm]

    def launched_tasks(self) -> set[str]:
        return {launch.task_id for launch in self.launches}


INCOMPLETE_EXIT = 1  # the console entry's exit status for an incomplete run


def results_dir(checkout: Path) -> Path:
    return checkout / RESULTS_SUBDIR


OMIT_FLAG_LINE = re.compile(r"^omitClaudeMd: true\n", re.MULTILINE)


def new_checkout(workspace: Path) -> Path:
    """A clean, committed copy of this repository for a run to measure.

    A role is measured while it is on trial: its definition does not yet omit the inherited
    instructions, so the full arm is the role as it is and the lean arm adds the switch. A
    role this repository has already switched has no full arm to compare against, and its lean
    arm cannot be built, so the copy puts every such role back on trial in a commit of its own.
    """
    checkout = checkout_under_test(workspace)
    switched = [
        definition
        for definition in sorted((checkout / "agents").glob("*.md"))
        if OMIT_FLAG_LINE.search(definition.read_text(encoding="utf-8"))
    ]
    for definition in switched:
        text = definition.read_text(encoding="utf-8")
        definition.write_text(OMIT_FLAG_LINE.sub("", text, count=1), encoding="utf-8")
    if switched:
        _git(checkout, "add", "--", *(str(d.relative_to(checkout)) for d in switched))
        _git(checkout, "commit", "-q", "-m", "put the switched roles back on trial")
    return checkout


def commit_in_checkout(checkout: Path, relpath: str, message: str) -> None:
    _git(checkout, "add", "--", relpath)
    _git(checkout, "commit", "-q", "-m", message)


def change_in_checkout(checkout: Path, relpath: str) -> None:
    """Change a tracked file of the checkout and commit the change."""
    target = checkout / relpath
    target.write_text(target.read_text(encoding="utf-8") + "\n# changed\n", encoding="utf-8")
    commit_in_checkout(checkout, relpath, f"change {relpath}")


# -- Runs with the stand-in launcher --------------------------------------------------------------


def run_with_stand_in(workspace: Path, checkout: Path, plan: Plan, script: Script) -> StandInRun:
    """Run the adherence eval on `checkout` through its console entry, every session a stand-in.

    The results file goes into the checkout's results directory. The arm of a session is the
    arm of the plugin copy it was handed, so a calibration run's second session of the full
    copy reads as a full session.
    """
    return _run_console(workspace, checkout, plan, script, extra_args=())


def _run_console(
    workspace: Path, checkout: Path, plan: Plan, script: Script, extra_args: Sequence[str]
) -> StandInRun:
    """One console invocation with a fresh stand-in `claude`; the other runs share it."""
    root = _fresh_directory(workspace, "stand-in")
    stand_in = stand_in_claude.install(
        root / "claude",
        version=FAKE_CLAUDE_VERSION,
        role=plan.role,
        tasks=_planned_places(root, checkout, plan),
        by_arm=script.by_arm,
        by_task=script.by_task,
        default=script.default,
    )
    before = set(results_dir(checkout).glob("*.json")) if results_dir(checkout).is_dir() else set()
    done = _console(checkout, stand_in.bin_dir, [*_run_options(plan, checkout), *extra_args])
    launched = stand_in.launches()
    return StandInRun(
        exit_code=done.returncode,
        stdout=done.stdout,
        stderr=done.stderr,
        results_path=_results_path(checkout, before, done.stdout),
        launches=tuple(_launched(r) for r in launched if not r.proof),
        proofs=tuple(_launched(r) for r in launched if r.proof),
    )


def _launched(record: stand_in_claude.LaunchRecord) -> LaunchedSession:
    return LaunchedSession(record.arm, record.task_id, record.attempt)


def _fresh_directory(workspace: Path, stem: str) -> Path:
    """An unused directory name under `workspace`: one workspace may hold several runs."""
    taken = {p.name for p in workspace.iterdir()} if workspace.is_dir() else set()
    name = next(n for n in (f"{stem}-{i}" for i in range(1_000)) if n not in taken)
    root = workspace / name
    root.mkdir(parents=True)
    return root


def _plan_options(plan: Plan, checkout: Path) -> list[str]:
    """The options that fix which sessions a run plans; the dry run takes exactly these."""
    args = [str(checkout), "--role", plan.role, "--seed", str(plan.seed)]
    args += ["--max-tasks", str(plan.max_tasks), "--no-judge"]
    for arm in plan.arms:
        args += ["--arm", arm]
    if plan.calibration:
        args.append("--calibration")
    return args


def _run_options(plan: Plan, checkout: Path) -> list[str]:
    args = _plan_options(plan, checkout)
    args += [
        "--max-total-usd",
        str(NO_SPEND_CAP_USD),
        "--fixture-pages-base-url",
        UNREACHABLE_PAGES,
    ]
    optional = (
        ("--model", plan.model),
        ("--margin-pp", plan.margin_pp),
        ("--calibration-run", plan.calibration_run),
        ("--stop-count", plan.stop_count),
    )
    for flag, value in optional:
        if value is not None:
            args += [flag, str(value)]
    return args


def _planned_places(root: Path, checkout: Path, plan: Plan) -> dict[str, stand_in_claude.TaskPlace]:
    """Each planned task's place in the planned order, by the fingerprint of its scratch repository.

    The dry run says how many tasks a run plans; the task generator then builds the same tasks'
    repositories, because a prompt does not tell tasks apart (a template's variants share one).
    """
    tripwire = adherence_eval.install_tripwire(root)
    done = _console(checkout, tripwire.bin_dir, [*_plan_options(plan, checkout), "--dry-run"])
    assert done.returncode == 0, f"the dry run of the plan failed: {done.stderr[-2000:]}"
    assert not tripwire.starts(), "a dry run started a session"
    planned = list(dict.fromkeys(s.task_id for s in planned_sessions(done.stdout)))
    request = {"role": plan.role, "seed": plan.seed, "count": len(planned)}
    built = adherence_eval.run_in_eval(
        _BUILD_PLANNED_REPOS, {**request, "into": str(root / "scratch")}
    )
    assert [b["task_id"] for b in built] == planned, (
        "the generator and the dry run plan different tasks"
    )
    return {
        stand_in_claude.fingerprint(Path(b["dir"])): stand_in_claude.TaskPlace(b["task_id"], i)
        for i, b in enumerate(built)
    }


_BUILD_PLANNED_REPOS = """
import json, sys
from pathlib import Path
from praxion_evals.adherence import tasks

request = json.load(sys.stdin)
built = []
for i, spec in enumerate(tasks.generate(request["role"], request["seed"], request["count"])):
    dest = Path(request["into"]) / f"{i:03d}"
    tasks.build_scratch_repo(spec, dest, None)
    built.append({"task_id": spec.task_id, "dir": str(dest)})
print(json.dumps(built))
"""


def _console(
    checkout: Path, claude_bin: Path, args: Sequence[str]
) -> subprocess.CompletedProcess[str]:
    """The console entry, started inside `checkout` (its default results directory) as an operator would."""
    entry = adherence_console_entry()
    env = eval_env({"PATH": _guarded_path(claude_bin), "ANTHROPIC_API_KEY": DUMMY_CREDENTIAL})
    command = [_uv(), "run", "--quiet", "--python", EVAL_PYTHON, "--project", str(EVAL_PROJECT)]
    return subprocess.run(
        [*command, entry.name, *args],
        capture_output=True,
        text=True,
        env=env,
        cwd=checkout,
        timeout=RUN_TIMEOUT_S,
        check=False,
    )


WROTE_LINE = re.compile(r"^wrote (?P<path>.+)$", re.MULTILINE)
NO_RESULTS_FILE = "(no results file was written).json"


def _results_path(checkout: Path, before: set[Path], stdout: str) -> Path:
    """The results file the run wrote, or a path that holds none when it wrote nothing."""
    wrote = WROTE_LINE.search(stdout)
    if wrote:
        return Path(wrote["path"])
    appeared = sorted(set(results_dir(checkout).glob("*.json")) - before)
    return appeared[-1] if appeared else results_dir(checkout) / NO_RESULTS_FILE


def continue_run(
    workspace: Path, checkout: Path, stopped: Path, plan: Plan, script: Script | None = None
) -> StandInRun:
    """Ask the console entry to continue the run whose results file is `stopped`."""
    raise UnboundDriverError(
        "the console entry continues a stopped run named by its results file, through the"
        " stand-in launcher"
    )


def close_run(workspace: Path, checkout: Path, stopped: Path, reason: str | None) -> StandInRun:
    """Ask the console entry to close a stopped run, with `reason` (None: no reason given)."""
    raise UnboundDriverError(
        "the console entry closes a stopped run named by its results file, recording the"
        " operator's reason"
    )


def stop_count_refusal(workspace: Path, checkout: Path, stop_count: int) -> StandInRun:
    """A run declared with `stop_count`; the scenario expects a refusal before any launch."""
    return run_with_stand_in(workspace, checkout, Plan(stop_count=stop_count), Script())


# -- A stopped run, constructed: unbound -------------------------------------------------------

TaskShape = Literal[
    "complete pair",
    "both sessions inside the streak",
    "full complete and lean inside the streak",
    "lean of the stopping kind and tail before the streak",
    "lean-only error of another kind",
    "full-only error of another kind",
    "refused launch",
    "never launched",
]

EIGHT_SHAPES: tuple[TaskShape, ...] = (
    "complete pair",
    "lean of the stopping kind and tail before the streak",
    "lean-only error of another kind",
    "full-only error of another kind",
    "full complete and lean inside the streak",
    "both sessions inside the streak",
    "refused launch",
    "never launched",
)
RELAUNCHED_SHAPES = frozenset(
    {
        "both sessions inside the streak",
        "full complete and lean inside the streak",
        "refused launch",
        "never launched",
    }
)
KEPT_LEAN_FAILURE_SHAPES = frozenset(
    {"lean of the stopping kind and tail before the streak", "lean-only error of another kind"}
)

StopVariant = Literal[
    "both arms in the streak",
    "confined to one arm",
    "operator interrupt",
    "complete",
    "already continued",
]


@dataclass(frozen=True)
class PlantedRun:
    path: Path
    run_id: str
    task_ids: tuple[str, ...]  # the planned tasks, in the run's planned order
    shapes: Mapping[str, TaskShape]  # task id -> its shape


def plant_stopped_run(
    workspace: Path,
    checkout: Path,
    plan: Plan,
    shapes: Sequence[TaskShape] = EIGHT_SHAPES,
    *,
    variant: StopVariant = "both arms in the streak",
    recorded_launch_order_swapped: bool = False,
) -> PlantedRun:
    """A results file, in the runner's own format, of a run of `plan` on `checkout`.

    Its planned tasks take `shapes` in planned order; it stopped as `variant` says (a
    streak of one error kind and masked tail; `recorded_launch_order_swapped` records a
    per-task launch order other than the one the run's seed gives).
    """
    raise UnboundDriverError(
        "a stopped run constructed in the runner's own results format: its declarations,"
        " its tree, its planned tasks and launch order, its sessions and its stop"
    )


# -- Readings of a results file: unbound -------------------------------------------------------


@dataclass(frozen=True)
class ErrorTails:
    task_id: str
    arm: str
    error_output: str
    result_text: str


def error_tails(results_path: Path) -> list[ErrorTails]:
    raise UnboundDriverError(
        "an errored session's record keeps the tail of its error output and of its result text"
    )


def declared_tail_bound(results_path: Path) -> int:
    raise UnboundDriverError("the results file declares the tail bound before the first launch")


@dataclass(frozen=True)
class StopReason:
    error_kind: str
    masked_tail: str
    streak: tuple[LaunchedSession, ...]
    other_arm_same: bool  # the other arm ended in the same kind and tail inside the window


def stop_reason(results_path: Path) -> StopReason | None:
    raise UnboundDriverError("the results file records the stop and its reason; None: no stop")


@dataclass(frozen=True)
class StopSettings:
    stop_count: int
    counting_kinds: frozenset[str]
    masking_rule: str
    declared_before_first_launch: bool


def declared_stop_settings(results_path: Path) -> StopSettings:
    raise UnboundDriverError(
        "the results file declares the stop count, its counting kinds and the masking rule"
        " among its settings, before the first launch"
    )


def declared_allowance_method(results_path: Path) -> str:
    raise UnboundDriverError(
        "the results file declares the allowance method among its settings before the first launch"
    )


def allowance_taken_from_calibration(results_path: Path) -> bool:
    raise UnboundDriverError(
        "the results file shows whether any allowance came from a calibration run"
    )


@dataclass(frozen=True)
class LineagePart:
    run_id: str
    stop: str | None  # the stop that ended this part; None for the part that finished


def lineage(results_path: Path) -> list[LineagePart]:
    raise UnboundDriverError("a continued run's results name every part of its lineage in order")


def lean_failure_tasks(results_path: Path, role: str) -> set[str]:
    raise UnboundDriverError(
        "the tasks a continued run counts as lean failures under the worst-case recount"
    )


@dataclass(frozen=True)
class EarlierRun:
    run_ids: tuple[str, ...]  # one id, or every part of a continued lineage
    flip: str  # "clear", "not clear" or "underpowered"
    interim: bool = False  # a closed run, carrying its interim per-check result


@dataclass(frozen=True)
class EarlierRunsListing:
    draws: tuple[EarlierRun, ...]  # same role definition and kernel identity, in order
    apart: Mapping[str, str]  # run id -> how its identity differs ("identity unknown" included)
    calibration: tuple[str, ...]
    skipped_files: tuple[str, ...]  # names of JSON files beside it that are not results files


def earlier_runs(results_path: Path, role: str) -> EarlierRunsListing:
    raise UnboundDriverError(
        "a run's results list its role's earlier runs by measured identity, with calibration"
        " runs and identity differences apart, and name every skipped JSON file"
    )


def earlier_runs_in_report(report: str, role: str) -> EarlierRunsListing:
    raise UnboundDriverError(
        "a report lists its role's earlier runs by measured identity, as the results do"
    )


# -- The dry run's launch order ------------------------------------------------------------------


def dry_run(workspace: Path, checkout: Path, *, seed: int = adherence_eval.SEED) -> str:
    """The dry run's printed sessions for the researcher's planned tasks, both arms."""
    fake = install_fake_claude(workspace)
    request = RunRequest(
        roles=(ROLE,),
        arms=("full", "lean"),
        checkout=checkout,
        output=workspace / "dry" / "adherence.json",
        seed=seed,
        dry_run=True,
    )
    result = run_adherence_eval(request, fake.bin_dir)
    assert result.exit_code == 0, f"the dry run failed: {result.stderr[-2000:]}"
    assert fake.launches() == [], "a dry run started a session"
    return result.stdout


def launch_orders(dry_run_stdout: str) -> dict[str, tuple[str, str]]:
    """Each planned task's arm order, as the dry run prints it: (first arm, second arm)."""
    raise UnboundDriverError("the dry run prints each task's arm launch order")


# -- Transcript directories: the runner's and the catalog's naming --------------------------------


def runner_transcript_dir_name(cwd: str) -> str:
    raise UnboundDriverError(
        "the name the runner gives the transcript directory of a session started in `cwd`"
    )


def catalog_transcript_dir_names(cwd: str) -> dict[str, str]:
    raise UnboundDriverError(
        "the name each catalog row that locates a transcript gives the directory of a session"
        " started in `cwd`, by row"
    )


# Two transcript directories Claude Code 2.1.302 itself named: working directory -> name.
RECORDED_TRANSCRIPT_DIRS = {
    "/private/tmp/claude-501/-Users-fperez-dev-praxion/ad40a83d-c5f0-4541-948c-3fbc6073e3e7"
    "/scratchpad/naming probe_a+b \u00f1": "-private-tmp-claude-501--Users-fperez-dev-praxion"
    "-ad40a83d-c5f0-4541-948c-3fbc6073e3e7-scratchpad-naming-probe-a-b--",
    "/Users/fperez/dev/praxion/.claude/worktrees/lean-spawn-continuation": (
        "-Users-fperez-dev-praxion--claude-worktrees-lean-spawn-continuation"
    ),
}


def lineage_complete_pairs(results_path: Path, role: str) -> int:
    """The complete pairs a continued run's results count for `role` over its whole lineage."""
    raise UnboundDriverError(
        "a continued run's results state the complete pairs of its whole lineage for a role"
    )


def run_report(workspace: Path, results_path: Path) -> str:
    from tests.acceptance.drivers.adherence_scoring import render

    rendering = render(results_path, workspace)
    assert rendering.exit_code == 0, f"the report failed: {rendering.stderr[-2000:]}"
    return rendering.text


def head_commit(root: Path) -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=True
    ).stdout.strip()
