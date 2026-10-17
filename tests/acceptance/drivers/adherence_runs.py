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
test (a committed copy of this repository), and committing a file in it.

Unbound until a binding step names the designed surface (each raises with the
assumption it stands for): the stand-in launcher itself (it must pass each arm's proof
and report every launch with its arm, task and attempt), the option that declares the
stop count, continuing and closing a run, a stopped run constructed in the runner's own
format, the dry run's per-task launch order, and every reading of what this change adds
to a results file (the error tails, the stop, the declared stop settings, the allowance
method, the lineage, the worst-case lean failures and the earlier-runs listing). Where
the results directory sits is bound: a run writes into `<checkout>/.ai-state/eval_ledger/
adherence/`, beside every earlier run of the checkout.
"""

from __future__ import annotations

import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from tests.acceptance.drivers import adherence_eval
from tests.acceptance.drivers.adherence_eval import (
    RunRequest,
    _git,
    checkout_under_test,
    install_fake_claude,
    run_adherence_eval,
)
from tests.acceptance.drivers.kernel_sandbox import UnboundDriverError

RESULTS_SUBDIR = Path(".ai-state") / "eval_ledger" / "adherence"
ROLE = "researcher"  # a role with a full kit: 24 planned tasks by default
DEFAULT_STOP_COUNT = 3
PLANTED_SECRET = "sk-ant-oat01-acceptance-planted-session-secret-7f3a9c"

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
    launches: tuple[LaunchedSession, ...]

    def launches_in(self, arm: str) -> list[LaunchedSession]:
        return [launch for launch in self.launches if launch.arm == arm]

    def launched_tasks(self) -> set[str]:
        return {launch.task_id for launch in self.launches}


INCOMPLETE_EXIT = 1  # the console entry's exit status for an incomplete run


def results_dir(checkout: Path) -> Path:
    return checkout / RESULTS_SUBDIR


def new_checkout(workspace: Path) -> Path:
    """A clean, committed copy of this repository for a run to measure."""
    return checkout_under_test(workspace)


def commit_in_checkout(checkout: Path, relpath: str, message: str) -> None:
    _git(checkout, "add", "--", relpath)
    _git(checkout, "commit", "-q", "-m", message)


def change_in_checkout(checkout: Path, relpath: str) -> None:
    """Change a tracked file of the checkout and commit the change."""
    target = checkout / relpath
    target.write_text(target.read_text(encoding="utf-8") + "\n# changed\n", encoding="utf-8")
    commit_in_checkout(checkout, relpath, f"change {relpath}")


# -- Runs with the stand-in launcher: unbound ------------------------------------------------


def run_with_stand_in(
    workspace: Path, checkout: Path, plan: Plan, script: Script, *, run_id_hint: str = ""
) -> StandInRun:
    """Run the adherence eval on `checkout` through its console entry, every session a stand-in.

    The results file goes into the checkout's results directory.
    """
    raise UnboundDriverError(
        "a stand-in session launcher the console entry runs instead of a paying `claude`:"
        " it passes each arm's proof, ends each session as the scenario scripts it, and"
        " reports every launch with its arm, its task and its attempt"
    )


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


def harness_transcript_dir_name(cwd: str) -> str:
    """The name Claude Code gives the transcript directory of a session started in `cwd`.

    Provisional oracle, until a transcript directory the harness wrote for such a working
    directory is recorded: every character other than an ASCII letter or digit becomes a
    dash, as the harness was seen to map slashes, dots and every other non-alphanumeric.
    """
    return "".join(ch if ch.isascii() and ch.isalnum() else "-" for ch in cwd)


def run_report(workspace: Path, results_path: Path) -> str:
    from tests.acceptance.drivers.adherence_scoring import render

    rendering = render(results_path, workspace)
    assert rendering.exit_code == 0, f"the report failed: {rendering.stderr[-2000:]}"
    return rendering.text


def head_commit(root: Path) -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=True
    ).stdout.strip()
