"""`record` for an agent that returned: take back what it left, judged on ground truth.

The orchestrator relays the request, the agent id and the marker it saw; everything else is
derived here, in phases:

1. **End**: the agent's own transcript, found by its id, must open with the request's
   `Spawn request:` line and show that the agent has ended (a final text, its turn cap, or an
   `agent_stop` row), waiting at most `PRAXION_STEP_LOOP_END_WAIT_SECONDS` for it. Until then
   the call is refused and nothing is written, so the request stays pending.
2. **Return**: the turns (its distinct API requests; unknown when a line did not parse), the
   agent definition's `maxTurns`, the marker (the transcript's wins over the relay) and the
   stop reason.
3. **Gate**: the derived test scope of the declared files that differ from HEAD, and the
   step's `Check:`, run here and never colour-forced; both land in one `TEST_RESULTS.md`
   block ending on the deciding line, and the reconciler reads the verdict as if the request
   were recorded. A red run fails the attempt whatever the check's expectations say: the
   check grammar has no error key, so a run red only by errors would otherwise meet it.
4. **Commit** a verified attempt by explicit path. A commit git refuses, or one that cannot
   finish or would disturb the tree, adds a `Result: none` line saying why, so every reader
   sees the attempt unverified; the last two also stop the loop for a person.
5. **Ledger**: exactly one record per return.

Every phase is keyed by the request, so a call cut off part-way completes when run again: a
gate block for the request reuses its runs, a HEAD commit naming the request reuses its sha,
and a ledger record for the request makes the call a replay that writes nothing.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NamedTuple, Protocol, cast

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks"))
from _agent_transcript import (  # noqa: E402 (after sys.path injection)
    Read,
    TranscriptReading,
    Unreadable,
    parse_transcript,
)
from _git_runner import GitUnavailableError, run_git  # noqa: E402
from _loop_fields import ATTEMPT_CAP, Check, OutstandingAttempt  # noqa: E402
from _plan_steps import PlanStep  # noqa: E402
from _step_loop_action import Spawn, Stop, next_action  # noqa: E402
from _step_loop_files import (  # noqa: E402
    STEP_LABEL,
    agent_stopped,
    append_ledger_record,
    end_evidence,
    gate_heading,
    meta_warnings,
    names_request,
    read_agent,
    write_atomic,
    write_gate_block,
    write_tree_snapshot,
)
from _step_loop_gate import (  # noqa: E402
    GateRun,
    Marker,
    Ownership,
    classify_run,
    derive_stop_reason,
    end_source,
    gate_result_lines,
    parse_marker,
    render_result_line,
    resolve_marker,
)
from _step_loop_io import (  # noqa: E402
    CommandRun,
    CommitInterrupted,
    CommitOutcome,
    CommitRefused,
    Committed,
    GitCommandError,
    NothingToCommit,
    OutsideRepoError,
    ScopeUnresolved,
    commit_paths,
    paths_differing_from_head,
    run_check,
    run_derived_scope,
    split_outer_loop,
)
from _step_loop_render import SpawnRequest, commit_message, spawn_request  # noqa: E402
from _step_loop_state import VERIFIED, LoopInputs, bare_id, is_done, series_states  # noqa: E402
from _step_schema import GREEN, Counts, NoRun, checklist_step_id, parse_result_line  # noqa: E402
from iteration_ledger import IterationRecord  # noqa: E402
from reconcile_pipeline_state import reconcile  # noqa: E402

END_WAIT_VARIABLE = "PRAXION_STEP_LOOP_END_WAIT_SECONDS"
DEFAULT_END_WAIT_SECONDS = 20.0
POLL_SECONDS = 0.5
AGENTS_DIR = Path(__file__).resolve().parent.parent / "agents"
RESULTS_FILE, WIP_FILE, PROMPT_FILE = "TEST_RESULTS.md", "WIP.md", "PROMPT_{}.md"
TRAILER = "Step-Loop-Request: "
DISTURBED_CAUSE = "commit-disturbed-tree"
RED_RUN_VERDICT = "mismatch"  # the reconciler's word for evidence that contradicts the claim
NOTHING_RAN = "the step declares no check and none of its declared files changed"
SCOPE_COMMAND = "resolve_test_scope.py"
_MAX_TURNS_RE = re.compile(r"^maxTurns:\s*(\d+)\s*$", re.MULTILINE)
_MARKER_OF_STOP = {"completed": "complete", **{m: m for m in ("blocked", "conflict", "partial")}}
_HEADING_PREFIX, _RESULT_PREFIX = "## ", "Result:"

Warnings = tuple[tuple[str, str], ...]  # (code, message)


class RecordRefusedError(Exception):
    """A `record` the driver will not take yet: it names its code and wrote nothing."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code, self.message = code, message


class TaskView(Protocol):
    """What `record` reads of the task: where it lives and the loop's inputs, by value."""

    @property
    def slug(self) -> str: ...
    @property
    def repo(self) -> Path: ...
    @property
    def work(self) -> Path: ...
    @property
    def dir(self) -> Path: ...
    @property
    def base_ref(self) -> str: ...
    @property
    def inputs(self) -> LoopInputs: ...


@dataclass(frozen=True)
class Taken:
    """What one `record` took back: the `recorded` object, its warnings, and, when the commit
    disturbed the tree, the evidence that stops the loop for a person."""

    recorded: Mapping[str, Any]
    step: str
    warnings: Warnings = ()
    disturbed: str | None = None


# --- The call --------------------------------------------------------------------------------


def record_return(task: TaskView, request: str, agent_id: str, relayed: str) -> Taken:
    """Take back the agent's return for `request`, or replay the record it already has."""
    done = next((r for r in task.inputs.records if r.request == request), None)
    if done is not None:
        marker = _MARKER_OF_STOP.get(done.stop_reason, "none")
        return Taken(recorded_object(done, marker, None, replayed=True), bare_id(done.step))
    spawn = _pending(task.inputs, request)
    step, key = spawn.step, spawn.key
    if key.kind == "review":  # a review's return is read from its verdict file, never gated
        raise NotImplementedError("recording a light review lands in a later increment")
    asked = spawn_request(task.slug, step, key, ATTEMPT_CAP, str(task.dir))
    max_turns = declared_max_turns(asked.agent_call.subagent_type)
    seen = await_end(task.repo, request, agent_id, max_turns)
    marker, stop_reason, warnings = read_return(seen, cast(Marker, relayed), asked, max_turns)
    gate = run_gate(task, step, request)
    verdict = read_verdict(task, step.id, request, gate)
    committing = Committing(None, None, None)
    if verdict["verdict"] == VERIFIED:
        committing = commit_attempt(task, step, asked, gate.deciding)
        if committing.failure is not None:
            gate = add_refusal(task, step.id, request, gate, committing.failure)
        else:
            tick_step(task.dir / WIP_FILE, step.id)
        verdict = read_verdict(task, step.id, request, gate)
    record = IterationRecord(
        step=STEP_LABEL + step.id,
        attempt=key.attempt,
        agent_id=agent_id,
        verdict=verdict["verdict"],
        decided_by=verdict["decided_by"],
        test_result=gate.deciding,
        commit=committing.sha,
        stop_reason=stop_reason,
        request=request,
        step_digest=step.digest,
        turns=seen.turns,
        max_turns=max_turns,
    )
    append_ledger_record(task.dir, record)
    summary = f"appended {record.step} attempt {record.attempt}: {record.verdict}"
    summary += f" ({record.decided_by})"
    warnings += edit_warnings(task, step, request)
    taken = recorded_object(record, marker, summary)
    return Taken(taken, step.id, warnings, committing.disturbed)


def require_known(inputs: LoopInputs, request: str) -> None:
    """Refuse a request that is neither pending nor recorded, naming the one that is pending."""
    pending = sorted(
        a.request for a in inputs.attempts.values() if isinstance(a, OutstandingAttempt)
    )
    if request in pending or any(record.request == request for record in inputs.records):
        return
    state = f"the pending request is {pending[0]}" if pending else "none is pending"
    raise RecordRefusedError(
        "request-not-pending",
        f"record failed because {request} is neither pending nor recorded ({state})."
        " To fix: record the pending request, or run next to get one.",
    )


def _pending(inputs: LoopInputs, request: str) -> Spawn:
    """The spawn the loop reissues for `request`: it names the step and the request's key."""
    action = next_action(inputs)
    if isinstance(action, Spawn) and action.reissued and action.key.id == request:
        return action
    found = f"stops ({action.cause})" if isinstance(action, Stop) else "does not reissue it"
    raise RecordRefusedError(
        "request-not-pending",
        f"record failed because the loop {found} for {request}. To fix: run status and resolve it.",
    )


def recorded_object(
    record: IterationRecord, marker: str, ledger: str | None, *, replayed: bool = False
) -> dict[str, Any]:
    """The envelope's `recorded` object for a ledger record."""
    return {
        "request": record.request,
        "agent_id": record.agent_id,
        "turns": record.turns,
        "max_turns": record.max_turns,
        "marker": marker,
        "stop_reason": record.stop_reason,
        "gate": {
            "verdict": record.verdict,
            "decided_by": record.decided_by,
            "evidence": record.test_result,
        },
        "review_verdict": None,
        "commit": record.commit,
        "ledger": ledger,
        "replayed": replayed,
    }


def disturbed_stop(inputs: LoopInputs, step_id: str, evidence: str) -> Stop:
    """The stop a disturbed commit leaves, naming the attempts of the step's current series."""
    step = next(s for s in inputs.steps if s.id == step_id)
    series = tuple(r for r in inputs.driver_records(step.id) if r.step_digest == step.digest)
    return Stop(DISTURBED_CAUSE, step.id, evidence, series)


# --- 1. End: the agent's transcript, until it shows the end ---------------------------------


@dataclass(frozen=True)
class Sighting:
    """The agent's transcript as last seen: where it is, what it reads as, whether a line failed
    to parse (its turns are then unknown), its final text, and whether it shows the end."""

    path: Path | None
    reading: TranscriptReading
    unreadable: bool
    final_text: str | None
    ended: bool

    @property
    def turns(self) -> int | None:
        return self.reading.requests if isinstance(self.reading, Read) else None


def await_end(
    repo: Path,
    request: str,
    agent_id: str,
    max_turns: int | None,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> Sighting:
    """The agent's transcript once it shows the end, or a refusal when the wait runs out."""
    deadline = clock() + end_wait_seconds()
    seen = sight(repo, agent_id, max_turns)
    while not seen.ended and clock() < deadline:
        sleep(POLL_SECONDS)
        seen = sight(repo, agent_id, max_turns)
    if seen.path is None:
        raise RecordRefusedError(
            "agent-not-found",
            f"record failed because no transcript of agent {agent_id} was found. To fix: pass"
            " the agentId the Agent tool returned, under the config directory the harness uses.",
        )
    if not names_request(seen.reading, request):
        raise RecordRefusedError(
            "agent-not-for-request",
            f"record failed because agent {agent_id} was not started on {request}. To fix:"
            " relay the agentId of the Agent call made for this request.",
        )
    if not seen.ended:
        raise RecordRefusedError(
            "agent-running",
            f"record failed because agent {agent_id} has not ended; {request} stays pending."
            " To fix: wait for its completion notification, then run the same record again.",
        )
    return seen


def sight(repo: Path, agent_id: str, max_turns: int | None) -> Sighting:
    """The transcript now. A last request of text only ends an agent with or without a marker
    (an agent that calls no tool has stopped), beside the gate's three signs of an end."""
    path, raw = read_agent(agent_id)
    reading = salvaged(path, raw)
    evidence = end_evidence(reading, max_turns, agent_stopped(repo, agent_id))
    unreadable = isinstance(raw, Unreadable) or (isinstance(raw, Read) and raw.malformed)
    ended = evidence.final_text is not None or end_source(evidence) is not None
    return Sighting(path, reading, unreadable, evidence.final_text, ended)


def salvaged(path: Path | None, raw: TranscriptReading) -> TranscriptReading:
    """An unreadable transcript's lines that parse, its turns unknown: enough to tie it to its
    request and, when its final line parsed (no flush cut it off), to read how it ended."""
    if path is None or not isinstance(raw, Unreadable):
        return raw
    text = path.read_text(encoding="utf-8", errors="replace")
    kept = parse_transcript("\n".join(line for line in text.splitlines() if _is_object(line)))
    if not isinstance(kept, Read):
        return raw
    return Read(None, kept.first_user_text, kept.last_turn if raw.last_ok else None, True)


def _is_object(line: str) -> bool:
    try:
        return isinstance(json.loads(line), dict)
    except json.JSONDecodeError:
        return False


def end_wait_seconds() -> float:
    """The bounded wait for an end, from the environment (a value that is not a number: the
    default)."""
    raw = os.environ.get(END_WAIT_VARIABLE, "").strip()
    try:
        return max(float(raw), 0.0) if raw else DEFAULT_END_WAIT_SECONDS
    except ValueError:
        return DEFAULT_END_WAIT_SECONDS


# --- 2. Return: how the attempt ended --------------------------------------------------------


def declared_max_turns(subagent_type: str) -> int | None:
    """The `maxTurns` of the agent definition the request starts (None when it declares none)."""
    path = AGENTS_DIR / f"{subagent_type.split(':')[-1]}.md"
    try:
        front = path.read_text(encoding="utf-8").split("---", 2)[1]
    except (OSError, IndexError):
        return None
    found = _MAX_TURNS_RE.search(front)
    return int(found[1]) if found else None


def read_return(
    seen: Sighting, relayed: Marker, asked: SpawnRequest, max_turns: int | None
) -> tuple[Marker, str, Warnings]:
    """(the marker that counts, the stop reason, the warnings the transcript gives)."""
    shown = None if seen.unreadable else parse_marker(seen.final_text)
    marker = resolve_marker(shown, relayed)
    reason = derive_stop_reason(marker.marker, seen.turns, max_turns)
    warnings: list[tuple[str, str]] = []
    if seen.unreadable:
        warnings.append(("transcript-unreadable", f"a line of {seen.path} did not parse"))
    if marker.disagrees:
        heard = f"the relay said {relayed}, the transcript shows {marker.marker}"
        warnings.append(("marker-disagreement", f"{asked.key.id}: {heard}; the transcript wins"))
    # A missing or unreadable sidecar is not a mismatch, and has no code in the closed set.
    fidelity = (w.split(": ", 1) for w in meta_warnings(seen.path, asked.agent_call) if ": " in w)
    warnings += [(code, message) for code, message in fidelity]
    return marker.marker, reason, tuple(warnings)


# --- 3. Gate: run the scope and the check, write the block, read the verdict ----------------


@dataclass(frozen=True)
class Gate:
    """The gate block's body, deciding `Result:` line last, and whether any run was red."""

    body: tuple[str, ...]
    red: bool

    @property
    def deciding(self) -> str:
        return self.body[-1]


def run_gate(task: TaskView, step: PlanStep, request: str) -> Gate:
    """The request's gate: read back from its block when written, else run and written now."""
    results = task.dir / RESULTS_FILE
    written = recorded_gate(results, gate_heading(step.id, request))
    if written is not None:
        return written
    states = series_states(task.inputs)
    done = frozenset(step_id for step_id, state in states.items() if is_done(state))
    ownership = Ownership(step.id, {s.id: s.read_only for s in task.inputs.steps}, done)
    changed = paths_differing_from_head(task.repo, step.files) if step.files else ()
    scope = scope_run(task.repo, changed, ownership) if changed else None
    check = check_run(task.repo, step, ownership)
    runs = tuple(run for run in (scope, check) if run is not None)
    if not runs:
        runs = (GateRun("", NoRun(NOTHING_RAN)),)
    if check is None:
        lines = tuple(render_result_line(run) for run in runs)
    else:
        lines = gate_result_lines(scope, check)
    body = (*(f"Command: `{run.command}`" for run in runs if run.command), *lines)
    write_gate_block(results, step.id, request, body)
    return Gate(body, any(run.red for run in runs))


def scope_run(repo: Path, changed: Sequence[str], ownership: Ownership) -> GateRun:
    """The derived scope of `changed`, every invocation it lists merged into one run."""
    resolved = run_derived_scope(repo, changed)
    if isinstance(resolved, ScopeUnresolved):
        why = resolved.resolver.problem or f"exit {resolved.resolver.returncode}"
        return GateRun(SCOPE_COMMAND, NoRun(f"the test scope did not resolve ({why})"))
    if not resolved.runs:
        return GateRun(SCOPE_COMMAND, NoRun("the test scope selects no test"))
    return merge_runs(tuple(classified(run, ownership) for run in resolved.runs))


def check_run(repo: Path, step: PlanStep, ownership: Ownership) -> GateRun | None:
    if step.check is None:
        return None
    if not isinstance(step.check, Check):
        return GateRun("Check:", NoRun(f"the Check: line cannot be read: {step.check.reason}"))
    return classified(run_check(repo, step.check.command), ownership, step.check.command)


def classified(run: CommandRun, ownership: Ownership, command: str = "") -> GateRun:
    """One finished command's run as the gate reads it; one that never exited is no run."""
    shown = command or shlex.join(run.argv)
    if run.problem is not None:
        return GateRun(shown, NoRun(f"the run {run.problem}"))
    return classify_run(shown, run.output, ownership)


def merge_runs(runs: Sequence[GateRun]) -> GateRun:
    """One run from several: counts summed and nodes joined, each run having been read on its
    own (one invocation's count line never applies to another's nodes); any no-run is no run."""
    command = " ; ".join(run.command for run in runs)
    absent = [run.counts.rationale for run in runs if isinstance(run.counts, NoRun)]
    if absent or not runs:
        return GateRun(command, NoRun("; ".join(absent) or "nothing ran"))
    counts = [cast(Counts, run.counts) for run in runs]
    total = Counts(
        passed=sum(c.passed for c in counts),
        failed=sum(c.failed for c in counts),
        skipped=sum(c.skipped for c in counts),
        errors=sum(c.errors for c in counts),
    )
    failed = tuple(node for run in runs for node in run.failed_ids)
    pending = tuple(dict.fromkeys(node for run in runs for node in run.pending_ids))
    return GateRun(command, total, failed, pending)


def recorded_gate(results: Path, heading: str) -> Gate | None:
    """The gate block already written for the request, read back, or None."""
    lines = results.read_text(encoding="utf-8").splitlines() if results.is_file() else []
    if heading not in lines:
        return None
    start = lines.index(heading) + 1
    end = next(
        (i for i in range(start, len(lines)) if lines[i].startswith(_HEADING_PREFIX)), len(lines)
    )
    body = tuple(line for line in lines[start:end] if line.strip())
    read = [parse_result_line(line) for line in body if line.startswith(_RESULT_PREFIX)]
    red = any(not (isinstance(one, Counts) and one.status == GREEN) for one in read)
    return Gate(body, red) if read and body[-1].startswith(_RESULT_PREFIX) else None


def read_verdict(task: TaskView, step_id: str, request: str, gate: Gate) -> dict[str, Any]:
    """The reconciler's verdict once the request is recorded; never verified on a red run."""
    verdicts = reconcile(
        task.slug,
        task.repo,
        task.base_ref,
        state_root=task.work,
        assume_recorded=frozenset({request}),
    )
    own = next((v for v in verdicts if bare_id(str(v["step"])) == step_id), None)
    verdict = {"verdict": "unknown", "decided_by": "none", **(own or {})}
    if gate.red and verdict["verdict"] == VERIFIED:
        verdict["verdict"] = RED_RUN_VERDICT
    return verdict


def add_refusal(task: TaskView, step_id: str, request: str, gate: Gate, failure: str) -> Gate:
    """The gate block with a last line saying no commit holds the work, and why."""
    line = render_result_line(GateRun("", NoRun(failure)))
    if gate.deciding == line:
        return gate
    body = (*gate.body, line)
    write_gate_block(task.dir / RESULTS_FILE, step_id, request, body)
    return Gate(body, True)


# --- 4. Commit: by explicit path, once per request -------------------------------------------


class Committing(NamedTuple):
    """The commit's sha (None: none holds the work), why no commit holds it, and the evidence
    of a tree the commit disturbed or may have disturbed (a stop for a person)."""

    sha: str | None
    failure: str | None
    disturbed: str | None


def commit_attempt(
    task: TaskView, step: PlanStep, asked: SpawnRequest, deciding: str
) -> Committing:
    """Commit the step's declared files, unless HEAD already is the request's commit."""
    sha = head_commit_for(task.repo, asked.key.id)
    if sha is not None:
        return Committing(sha, None, None)
    message = commit_message(step, task.slug, asked, deciding)
    read_only = tuple(entry for s in task.inputs.steps for entry in s.read_only)
    try:
        outcome = commit_paths(task.repo, step.files, message, read_only)
    except (GitCommandError, GitUnavailableError, OutsideRepoError) as exc:
        why = f"the step-loop driver could not commit: {_first_line(str(exc))}"
        return Committing(None, why, why + _lock_note(task.repo))
    return judge_commit(task, asked.key.id, outcome)


def judge_commit(task: TaskView, request: str, outcome: CommitOutcome) -> Committing:
    """What each commit outcome means for the attempt (see `Committing`)."""
    if isinstance(outcome, Committed):
        return Committing(outcome.sha, None, None)
    if isinstance(outcome, NothingToCommit):
        return Committing(None, None, None)
    if isinstance(outcome, CommitRefused):
        refused = "the step-loop driver's commit was refused by the repository's hooks"
        return Committing(None, f"{refused}: {_first_line(outcome.detail)}", None)
    if isinstance(outcome, CommitInterrupted):
        saved = write_tree_snapshot(task.dir, request, outcome.after.patch_text())
        why = f"the step-loop driver's commit did not finish: {_first_line(outcome.detail)}"
        return Committing(None, why, f"{why}; the tree is saved in {saved}{_lock_note(task.repo)}")
    saved = write_tree_snapshot(task.dir, request, outcome.before.patch_text())
    why = f"the step-loop driver's commit met files outside its paths: {', '.join(outcome.paths)}"
    return Committing(outcome.sha, why, f"{why}; the earlier state is saved in {saved}")


def head_commit_for(repo: Path, request: str) -> str | None:
    """HEAD's sha when its message carries the request's trailer: the commit already made."""
    shown = run_git(repo, "log", "-1", "--format=%H%n%B")
    if shown.returncode != 0:
        return None
    sha, _, body = shown.stdout.partition("\n")
    return sha.strip() if f"{TRAILER}{request}" in body.splitlines() else None


def _lock_note(repo: Path) -> str:
    found = run_git(repo, "rev-parse", "--git-path", "index.lock")
    lock = repo / found.stdout.strip() if found.returncode == 0 else None
    return f"; {lock} exists: remove it once no git is running" if lock and lock.exists() else ""


def _first_line(text: str) -> str:
    return " ".join((text.strip().splitlines() or ["no detail"])[0].split())


def tick_step(wip_path: Path, step_id: str) -> bool:
    """Tick the step's checklist line in `WIP.md` when it is unticked; True when it wrote."""
    lines = wip_path.read_text(encoding="utf-8").split("\n")
    label = STEP_LABEL + step_id
    at = next(
        (i for i, line in enumerate(lines) if checklist_step_id(line) == label and "[ ]" in line),
        None,
    )
    if at is None:
        return False
    lines[at] = lines[at].replace("[ ]", "[x]", 1)
    return write_atomic(wip_path, "\n".join(lines))


# --- Warnings about the tree -----------------------------------------------------------------


def edit_warnings(task: TaskView, step: PlanStep, request: str) -> Warnings:
    """Files changed since the request's prompt was written that its commit leaves behind:
    outside the step's `Files:`, or outer-loop files, which are never committed. A change
    older than the prompt is the user's own and is not reported."""
    prompt = task.dir / PROMPT_FILE.format(request)
    since = prompt.stat().st_mtime if prompt.exists() else float("-inf")
    changed = [
        path
        for path in paths_differing_from_head(task.repo, ["."])
        if _changed_since(task.repo / path, since)
    ]
    read_only = tuple(entry for s in task.inputs.steps for entry in s.read_only)
    kept, outer = split_outer_loop(changed, read_only, task.repo)
    declared = set(paths_differing_from_head(task.repo, step.files)) if step.files else set()
    stray = [path for path in kept if path not in declared]
    left = "left uncommitted"
    return (
        *(
            ("undeclared-edit", f"{path} changed outside the step's Files:; {left}")
            for path in stray
        ),
        *(("outer-loop-edit", f"{path} is an outer-loop file; {left}") for path in outer),
    )


def _changed_since(path: Path, since: float) -> bool:
    try:
        return path.lstat().st_mtime >= since
    except OSError:  # deleted during the attempt, or unreadable: report it rather than hide it
        return True
