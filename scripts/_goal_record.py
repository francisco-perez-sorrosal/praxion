"""A goal iteration's return: judged by progress, then kept, left as a patch, or stopped on.

The first half is the judgement, pure: counts, paths and line counts arrive by value, and nothing
there opens a file, reads a repository or starts a process, so the same evidence always gives the
same answer. The second half (`record_goal`) is the shell: it gathers the evidence, acts on the
answer and writes the ledger record. It reuses every phase of `record` for an ordinary step and
replaces only the commit decision.

Judged in this order, the first that applies deciding:

1. A changed path under the protected set: `Protected`, whatever else holds.
2. A red gate: `Unkept`.
3. A regression against the reference reading (more failures or fewer passes): `Unkept`.
4. No path of the step's `Files:` differs from the last commit: `Unkept`.
5. The progress record gained no line: `Unkept`.
6. Otherwise: `Progressing`.

Acted on as follows:

* `Progressing`: the step's `Files:` are committed by explicit path with the request's trailer
  (outer-loop and `Read-only:` paths never), and the step is ticked when its check is met.
* `Unkept`: nothing is committed; the whole tree's diff is saved as `ITERATION_<request>.patch`
  and the `Files:` return to the last commit, so the next iteration starts from the last kept
  unit. A gate that was not red gains a refusal line saying why, so it is never verified.
* `Protected`: nothing is committed or restored; the tree is saved as
  `TREE_SNAPSHOT_<request>.patch` and a refusal line names the paths, which stops the loop for
  a person (the same stop a disturbed commit makes).

A worker that left a `WORKER_<request>.json` has exited: it is never waited for, only its
transcript is, for the flush. Its file gives the turn bound, the cost and, for the three
`error_*` subtypes, the stop reason. Every effect is keyed by the request, so a call cut off
part-way completes when run again: a HEAD commit with the trailer means `Progressing`, an
`ITERATION_<request>.patch` means `Unkept`, and a gate block already written is reused.

Runs on the bare `python3` the scripts are invoked with, so no `X | Y` at runtime.
"""

from __future__ import annotations

import fnmatch
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, NamedTuple, Union, cast

import _step_loop_record as ordinary
from _plan_steps import PlanStep
from _step_loop_action import Spawn
from _step_loop_files import (
    ITERATION_PATCH_STEM,
    PATCH_SUFFIX,
    STEP_LABEL,
    NoWorkerResult,
    WorkerEnd,
    append_ledger_record,
    gate_heading,
    names_request,
    read_worker_end,
    write_iteration_patch,
    write_tree_snapshot,
)
from _step_loop_gate import Marker
from _step_loop_io import paths_differing_from_head, restore_paths, tree_patch
from _step_loop_record_gate import (
    RESULTS_FILE,
    Gate,
    TaskView,
    add_refusal,
    read_verdict,
    recorded_gate,
    run_gate,
)
from _step_loop_render import SpawnRequest, spawn_request
from _step_loop_settle import Warnings, edit_warnings, settle_replan, tick_step
from _step_loop_state import VERIFIED, series_work, step_cap
from _step_schema import Counts, parse_result_line
from iteration_ledger import IterationRecord

if TYPE_CHECKING:
    from pathlib import Path

DEFAULT_PROTECTED = (
    "tests/acceptance/**",
    "tests/e2e/**",
    "CLAUDE.md",
    "rules/**",
    "agents/**",
    "skills/**",
    ".claude/**",
)
PROGRESS_HEADING = "## Progress record"
NODE_SEPARATOR = "::"

_DIRECTORY_SUFFIXES = ("/**", "/*", "/")
_GLOB_CHARACTERS = frozenset("*?[")
_PENDING_TOKEN_RE = re.compile(r"(?:^|\s)pending=(?P<count>[0-9]+)(?:\s|$)")
_SECTION_END_RE = re.compile(r"^#{1,2}[ \t]")


# --- The reading of a check run, and the reference it is compared with ---


@dataclass(frozen=True)
class Reading:
    """What a check run showed: the tests that passed and those that failed, pended or errored."""

    passes: int
    failures: int

    def __post_init__(self) -> None:
        if self.passes < 0 or self.failures < 0:
            raise ValueError("a reading cannot count fewer than none")

    def regressed_from(self, reference: Reading) -> bool:
        """Worse than `reference` on either count; equal counts are not worse."""
        return self.failures > reference.failures or self.passes < reference.passes


def reading_from_result(line: str) -> Reading | None:
    """A `Result:` line's counts as a reading; None for a line that is not a count line.

    A goal's own failing tests are `pending` on the line, so they count as failures here."""
    counts = parse_result_line(line)
    if not isinstance(counts, Counts):
        return None
    pending = _PENDING_TOKEN_RE.search(line)
    pended = int(pending["count"]) if pending else 0
    return Reading(counts.passed, counts.failed + pended + counts.errors)


def progress_line_count(wip_text: str) -> int:
    """The non-blank lines under `## Progress record`, up to the next heading; 0 without one."""
    count, inside = 0, False
    for line in wip_text.splitlines():
        if line.rstrip() == PROGRESS_HEADING:
            inside = True
        elif inside and _SECTION_END_RE.match(line):
            break
        elif inside and line.strip():
            count += 1
    return count


# --- The protected set ---


def protected_set(read_only: Iterable[str]) -> tuple[str, ...]:
    """The default set plus a step's `Read-only:` entries, each once, in order."""
    return tuple(dict.fromkeys((*DEFAULT_PROTECTED, *read_only)))


def is_protected(path: str, protected: Iterable[str]) -> bool:
    """Whether `path` is an entry itself, under an entry that names a directory, or matches a glob.

    A path matches an entry from its start, so `CLAUDE.md` is the root file only."""
    return any(_covers(entry, path) for entry in protected)


def changed_protected(changed: Iterable[str], protected: Iterable[str]) -> tuple[str, ...]:
    """The changed paths that are under the protected set, in the order given."""
    entries = tuple(protected)
    return tuple(path for path in changed if is_protected(path, entries))


def _covers(entry: str, path: str) -> bool:
    base = _entry_base(entry)
    return path == base or path.startswith(f"{base}/") or _glob_covers(entry, path)


def _entry_base(entry: str) -> str:
    """The path an entry names: a test node id protects its whole file."""
    base = entry.partition(NODE_SEPARATOR)[0].removeprefix("./")
    for suffix in _DIRECTORY_SUFFIXES:
        if base.endswith(suffix):
            return base.removesuffix(suffix)
    return base


def _glob_covers(entry: str, path: str) -> bool:
    return not _GLOB_CHARACTERS.isdisjoint(entry) and fnmatch.fnmatchcase(path, entry)


# --- The judgement ---


@dataclass(frozen=True)
class Progressing:
    """The iteration is kept: it commits."""


@dataclass(frozen=True)
class Unkept:
    """The iteration is not kept, for `reason`: it commits nothing."""

    reason: str


@dataclass(frozen=True)
class Protected:
    """The iteration changed `paths` under the protected set: a person decides."""

    paths: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.paths:
            raise ValueError("a protected change names at least one path")


Judgement = Union[Progressing, Unkept, Protected]  # noqa: UP007 -- runtime value, 3.9 floor

RED_GATE = "the gate is red"
NO_FILE_CHANGED = "no path in Files: differs from the last commit"
NO_PROGRESS_LINE = "the progress record gained no line"


@dataclass(frozen=True)
class Evidence:
    """Everything the judgement reads about one iteration.

    `changed_files` are the step's `Files:` paths that differ from the last commit;
    `protected_changes` are the changed paths under the protected set; the progress counts are
    the lines of the progress record before the iteration and now."""

    red: bool
    reading: Reading
    reference: Reading
    changed_files: tuple[str, ...]
    progress_before: int
    progress_now: int
    protected_changes: tuple[str, ...] = ()


def judge(evidence: Evidence) -> Judgement:
    """Decide one iteration from `evidence`, by the order in this module's docstring."""
    if evidence.protected_changes:
        return Protected(evidence.protected_changes)
    if evidence.red:
        return Unkept(RED_GATE)
    if evidence.reading.regressed_from(evidence.reference):
        return Unkept(_regression_reason(evidence.reading, evidence.reference))
    if not evidence.changed_files:
        return Unkept(NO_FILE_CHANGED)
    if evidence.progress_now <= evidence.progress_before:
        return Unkept(NO_PROGRESS_LINE)
    return Progressing()


def _regression_reason(reading: Reading, reference: Reading) -> str:
    return (
        f"the check regressed: {reading.passes} passing and {reading.failures} failing, "
        f"against {reference.passes} passing and {reference.failures} failing"
    )


# --- The recorder: the shell around the judgement ---

BASELINE_REQUEST = "baseline"  # the label of the scaffold's reading, in a gate block's heading
NO_MARKER, TURN_CAP = "no-marker", "turn-cap"
PATCH_KEPT = "the iteration is already kept as a patch"
_STOP_OF_SUBTYPE = {
    "error_max_turns": TURN_CAP,
    "error_max_budget_usd": NO_MARKER,
    "error_during_execution": NO_MARKER,
}


class Settled(NamedTuple):
    """What acting on the judgement left: the gate (refused or not), the commit and the word."""

    gate: Gate
    committing: ordinary.Committing
    judgement: Judgement


def record_goal(task: TaskView, spawn: Spawn, agent_id: str, relayed: str) -> ordinary.Taken:
    """Take back a goal iteration's return for the pending `spawn`: judge it by progress, keep or
    leave its work, and append the one ledger record (cost and progress count included)."""
    step, key = spawn.step, spawn.key
    asked = spawn_request(task.slug, step, key, step_cap(step), str(task.dir))
    ending = take_end(task, asked, agent_id, relayed)
    gate = run_gate(task, step, key.id)
    progress = progress_line_count((task.dir / ordinary.WIP_FILE).read_text(encoding="utf-8"))
    settled = settle_iteration(task, step, asked, gate, progress)
    verdict = read_verdict(task, step.id, key.id, settled.gate)
    sha, failure = settled.committing
    if sha is not None and failure is None and verdict["verdict"] == VERIFIED:
        tick_step(task.dir / ordinary.WIP_FILE, step.id)
    record = IterationRecord(
        step=STEP_LABEL + step.id,
        attempt=key.attempt,
        agent_id=agent_id,
        verdict=verdict["verdict"],
        decided_by=verdict["decided_by"],
        test_result=settled.gate.deciding,
        commit=sha,
        stop_reason=ending.stop_reason,
        request=key.id,
        step_digest=step.digest,
        turns=ending.seen.turns,
        max_turns=ending.max_turns,
        cost_usd=ending.worker.cost_usd if ending.worker else None,
        progress_lines=progress,
    )
    append_ledger_record(task.dir, record)
    ended = replace(task.inputs, records=(*task.inputs.records, record))
    settle_replan(task.dir / ordinary.WIP_FILE, ended, step, key.id)
    said = f"appended {record.step} attempt {record.attempt}: {record.verdict}"
    said += f" ({record.decided_by}); {describe(settled.judgement, ending.worker)}"
    warnings = ending.warnings + edit_warnings(task, step, key.id)
    return ordinary.Taken(ordinary.recorded_object(record, ending.marker, said), step.id, warnings)


def describe(judgement: Judgement, worker: WorkerEnd | None) -> str:
    """The judgement in words for the call's summary, naming how an `error_*` worker ended."""
    if isinstance(judgement, Progressing):
        said = "kept as progress"
    elif isinstance(judgement, Protected):
        said = f"stopped on a protected change: {', '.join(judgement.paths)}"
    else:
        said = f"not kept: {judgement.reason}"
    return said if worker is None else f"{said}; the worker ended {worker.subtype}"


# --- The worker's end ---


class Ending(NamedTuple):
    """How the iteration's agent ended: its transcript, its worker file when it had one, the
    marker that counts, why it stopped, its turn bound and the warnings the reading gave."""

    seen: ordinary.Sighting
    worker: WorkerEnd | None
    marker: str
    stop_reason: str
    max_turns: int | None
    warnings: Warnings


def take_end(task: TaskView, asked: SpawnRequest, agent_id: str, relayed: str) -> Ending:
    """Wait for the end as an ordinary return does, unless a worker file shows the process has
    exited. A worker that ended on an error without a marker stopped for the error's reason."""
    request = asked.key.id
    found = read_worker_end(task.dir, request)
    worker = exited_worker(found, request, agent_id)
    max_turns = (
        worker.max_turns if worker else ordinary.declared_max_turns(asked.agent_call.subagent_type)
    )
    if found is None:
        seen = ordinary.await_end(task.repo, request, agent_id, max_turns)
    else:
        seen = await_exited(task, request, agent_id, max_turns)
    marker, stop_reason, warnings = ordinary.read_return(
        seen, cast(Marker, relayed), asked, max_turns
    )
    if worker is not None and marker == "none":  # a real marker still wins: it may be a stop
        stop_reason = _STOP_OF_SUBTYPE.get(worker.subtype, stop_reason)
    return Ending(seen, worker, marker, stop_reason, max_turns, warnings)


def exited_worker(
    found: NoWorkerResult | WorkerEnd | None, request: str, agent_id: str
) -> WorkerEnd | None:
    """The worker's result when its file holds one. A file that shows none (exit 1, killed) still
    means the process has exited, so the end is not waited for, but the turn bound, the cost and
    the stop reason are the relay's: the transcript and the subagent's declared bound decide.
    A file written for another session is refused."""
    if not isinstance(found, WorkerEnd):
        return None
    if found.session_id != agent_id:
        raise ordinary.RecordRefusedError(
            "agent-not-for-request",
            f"record failed because the worker file of {request} is for session"
            f" {found.session_id}, not {agent_id}. To fix: relay the session id the run reported.",
        )
    return found


def await_exited(
    task: TaskView,
    request: str,
    agent_id: str,
    max_turns: int | None,
    clock: Callable[[], float] = ordinary.time.monotonic,
    sleep: Callable[[float], None] = ordinary.time.sleep,
) -> ordinary.Sighting:
    """The exited worker's transcript once it names the request: its end is known from the file,
    so only the flush is waited for, within the bounded end wait."""
    deadline = clock() + ordinary.end_wait_seconds()
    seen = ordinary.sight(task.repo, agent_id, max_turns)
    while not names_request(seen.reading, request) and clock() < deadline:
        sleep(ordinary.POLL_SECONDS)
        seen = ordinary.sight(task.repo, agent_id, max_turns)
    if seen.path is None:
        raise ordinary.RecordRefusedError(
            "agent-not-found",
            f"record failed because no transcript of session {agent_id} was found. To fix: pass"
            " the session id the run reported, under the config directory the harness uses.",
        )
    if not names_request(seen.reading, request):
        raise ordinary.RecordRefusedError(
            "agent-not-for-request",
            f"record failed because session {agent_id} was not started on {request}. To fix:"
            " relay the session id of the run made for this request.",
        )
    return seen


# --- Acting on the judgement ---


def settle_iteration(
    task: TaskView, step: PlanStep, asked: SpawnRequest, gate: Gate, progress: int
) -> Settled:
    """Judge the iteration (or recognise it as already settled) and carry out the answer."""
    request = asked.key.id
    judgement = settled_before(task, request) or judge(gather_evidence(task, step, gate, progress))
    if isinstance(judgement, Progressing):
        committing = ordinary.commit_attempt(task, step, asked, gate.deciding)
        if committing.failure is not None:
            gate = add_refusal(task, step.id, request, gate, committing.failure)
        return Settled(gate, committing, judgement)
    if isinstance(judgement, Protected):
        why = f"the iteration changed protected paths: {', '.join(judgement.paths)}"
        gate = add_refusal(task, step.id, request, gate, why)
        write_tree_snapshot(task.dir, request, f"# {why}\n{tree_patch(task.repo)}")
    else:
        gate = leave_as_patch(task, step, request, gate, judgement.reason)
    return Settled(gate, ordinary.Committing(None, None), judgement)


def settled_before(task: TaskView, request: str) -> Judgement | None:
    """The judgement an earlier, cut-off call already acted on: a commit with the request's
    trailer is `Progressing`, a patch named by the request is `Unkept`. Judging again would
    read the tree those effects changed."""
    if ordinary.head_commit_for(task.repo, request) is not None:
        return Progressing()
    if iteration_patch(task, request).exists():
        return Unkept(PATCH_KEPT)
    return None


def leave_as_patch(task: TaskView, step: PlanStep, request: str, gate: Gate, why: str) -> Gate:
    """Keep the whole tree's diff as the request's patch, then return the step's `Files:` to the
    last commit. A gate that was not red says why the work was not kept."""
    if not gate.red:
        gate = add_refusal(task, step.id, request, gate, why)
    if not iteration_patch(task, request).exists():
        write_iteration_patch(task.dir, request, tree_patch(task.repo))
    restore_paths(task.repo, step.files)
    return gate


def iteration_patch(task: TaskView, request: str) -> Path:
    return task.dir / f"{ITERATION_PATCH_STEM}_{request}{PATCH_SUFFIX}"


# --- The evidence, gathered ---


def gather_evidence(task: TaskView, step: PlanStep, gate: Gate, progress: int) -> Evidence:
    """Everything `judge` reads, from the gate, the tree, the ledger and the results file."""
    reading = reading_from_result(gate.deciding) or Reading(0, 0)
    everything = paths_differing_from_head(task.repo, ["."])
    return Evidence(
        red=gate.red,
        reading=reading,
        reference=reference_reading(task, step) or reading,  # no reference: nothing regresses
        changed_files=paths_differing_from_head(task.repo, step.files),
        progress_before=progress_before(task, step),
        progress_now=progress,
        protected_changes=changed_protected(everything, protected_set(step.read_only)),
    )


def reference_reading(task: TaskView, step: PlanStep) -> Reading | None:
    """The check's reading to hold the iteration to: the latest committed iteration's of the
    series whose line is a count line (a commit refused after the fact leaves one that is not),
    else the scaffold's baseline."""
    for record in reversed(series_work(task.inputs, step)):
        reading = reading_from_result(record.test_result) if record.commit is not None else None
        if reading is not None:
            return reading
    baseline = recorded_gate(task.dir / RESULTS_FILE, gate_heading(step.id, BASELINE_REQUEST))
    return reading_from_result(baseline.deciding) if baseline else None


def progress_before(task: TaskView, step: PlanStep) -> int:
    """The progress record's line count after the series' latest iteration; 0 before the first."""
    work = series_work(task.inputs, step)
    return (work[-1].progress_lines or 0) if work else 0
