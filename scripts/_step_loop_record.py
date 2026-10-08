"""`record` for an agent that returned: take back what it left, judged on ground truth.

The orchestrator relays the request, the agent id and the marker it saw; everything else is
derived here, in phases:

1. **End**: the agent's own transcript, found by its id, must open with the request's
   `Spawn request:` line and show that the agent has ended (a final text, its turn cap, or an
   `agent_stop` row), waiting at most `PRAXION_STEP_LOOP_END_WAIT_SECONDS` for it. Until then
   the call is refused and nothing is written, so the request stays pending.
2. **Return**: the turns (its distinct API requests; unknown when a line did not parse), the
   agent definition's `maxTurns`, the marker (the transcript's over the relay) and the stop reason.
3. **Gate**: the derived test scope of the declared files that differ from HEAD, and the
   step's `Check:`, run here and never colour-forced; both land in one `TEST_RESULTS.md`
   block ending on the deciding line, and the reconciler reads the verdict as if the request
   were recorded. A red run fails the attempt whatever the check's expectations say: the
   check grammar has no error key, so a run red only by errors would otherwise meet it.
4. **Commit** a verified attempt by explicit path. A commit git refuses, or one that cannot
   finish or would disturb the tree, adds a `Result: none` line saying why, so every reader
   sees the attempt unverified; the last two (and a repository whose commands cannot run) also
   leave a `TREE_SNAPSHOT_<request>.patch`, which keeps the loop stopped for a person until
   they delete it.
5. **Ledger**: exactly one record per return (a light reviewer's skips phases 3 and 4).

Every phase is keyed by the request, so a call cut off part-way completes when run again: a
gate block for the request reuses its runs, a HEAD commit naming the request reuses its sha,
and a ledger record for the request makes the call a replay that writes nothing.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, NamedTuple, cast

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks"))
from _agent_transcript import (  # noqa: E402 (after sys.path injection)
    Read,
    TranscriptReading,
    Unreadable,
    parse_transcript,
    request_count,
)
from _git_runner import GitUnavailableError, run_git  # noqa: E402
from _loop_fields import GoalBudget, OutstandingAttempt  # noqa: E402
from _plan_steps import PlanStep  # noqa: E402
from _step_loop_action import Spawn, Stop, next_action  # noqa: E402
from _step_loop_files import (  # noqa: E402
    STEP_LABEL,
    agent_stopped,
    append_ledger_record,
    end_evidence,
    find_request_transcript,
    meta_warnings,
    names_request,
    read_agent,
    write_tree_snapshot,
)
from _step_loop_gate import (  # noqa: E402
    Marker,
    derive_stop_reason,
    end_source,
    parse_marker,
    resolve_marker,
)
from _step_loop_io import (  # noqa: E402
    HOOK_WORDS_LIMIT,
    CommitInterrupted,
    CommitOutcome,
    CommitRefused,
    Committed,
    GitCommandError,
    NothingToCommit,
    OutsideRepoError,
    commit_paths,
)
from _step_loop_record_gate import TaskView, add_refusal, read_verdict, run_gate  # noqa: E402
from _step_loop_render import SpawnRequest, commit_message, spawn_request  # noqa: E402
from _step_loop_review import file_verdict, review_record  # noqa: E402
from _step_loop_settle import (  # noqa: E402
    PROMPT_FILE,
    Warnings,
    edit_warnings,
    settle_replan,
    tick_step,
    withdraw_line,
)
from _step_loop_state import VERIFIED, LoopInputs, bare_id, series_work, step_cap  # noqa: E402
from iteration_ledger import IterationRecord  # noqa: E402

END_WAIT_VARIABLE = "PRAXION_STEP_LOOP_END_WAIT_SECONDS"
DEFAULT_END_WAIT_SECONDS = 20.0
POLL_SECONDS = 0.5
AGENTS_DIR = Path(__file__).resolve().parent.parent / "agents"
WIP_FILE = "WIP.md"
TRAILER = "Step-Loop-Request: "
_HOOKS_REFUSED = "the gate passed, but the repository's hooks refused the step-loop driver's commit"
_HOOK_FIX = (
    "To fix: make the declared files pass that hook; they stay staged as the attempt left them"
)
_MAX_TURNS_RE = re.compile(r"^maxTurns:\s*(\d+)\s*$", re.MULTILINE)
_MARKER_OF_STOP = {"completed": "complete", **{m: m for m in ("blocked", "conflict", "partial")}}


class RecordRefusedError(Exception):
    """A `record` the driver will not take yet: it names its code and wrote nothing."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code, self.message = code, message


@dataclass(frozen=True)
class Taken:
    """What one `record` took back: the `recorded` object, the step and its warnings."""

    recorded: Mapping[str, Any]
    step: str
    warnings: Warnings = ()


# --- The call --------------------------------------------------------------------------------


def take_back(task: TaskView, request: str, agent_id: str | None, relayed: str | None) -> Taken:
    """The `record` verb: an agent's return, or, with no agent id, a request that never started."""
    if agent_id is None or relayed is None:
        return withdraw_request(task, request)
    return record_return(task, request, agent_id, relayed)


def record_return(task: TaskView, request: str, agent_id: str, relayed: str) -> Taken:
    """Take back the agent's return for `request`, or replay the record it already has."""
    done = next((r for r in task.inputs.records if r.request == request), None)
    if done is not None:
        marker = _MARKER_OF_STOP.get(done.stop_reason, "none")
        step_id = bare_id(done.step)
        settle_replan(task.dir / WIP_FILE, task.inputs, _plan_step(task.inputs, step_id), request)
        return Taken(recorded_object(done, marker, None, replayed=True), step_id)
    spawn = _pending(task.inputs, request)
    step, key = spawn.step, spawn.key
    if key.kind == "review":  # a review's return is read from its verdict file, never gated
        return record_review(task, spawn, agent_id, relayed)
    if isinstance(step.bound, GoalBudget):  # judged by progress, never by verification
        from _goal_record import record_goal

        return record_goal(task, spawn, agent_id, relayed)
    asked = spawn_request(task.slug, step, key, step_cap(step), str(task.dir))
    max_turns = declared_max_turns(asked.agent_call.subagent_type)
    seen = await_end(task.repo, request, agent_id, max_turns)
    marker, stop_reason, warnings = read_return(seen, cast(Marker, relayed), asked, max_turns)
    gate = run_gate(task, step, request)
    verdict = read_verdict(task, step.id, request, gate)
    committing = Committing(None, None)
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
    ended = replace(task.inputs, records=(*task.inputs.records, record))
    settle_replan(task.dir / WIP_FILE, ended, step, request)
    summary = f"appended {record.step} attempt {record.attempt}: {record.verdict}"
    summary += f" ({record.decided_by})"
    warnings += edit_warnings(task, step, request)
    taken = recorded_object(record, marker, summary)
    return Taken(taken, step.id, warnings)


def record_review(task: TaskView, spawn: Spawn, agent_id: str, relayed: str) -> Taken:
    """A light reviewer's return: neither gated nor committed, one ledger record that carries
    the reviewed work's verdict. What the reviewer decided is the verdict word of its file."""
    step, key = spawn.step, spawn.key
    reviewed = next(
        (r for r in reversed(series_work(task.inputs, step)) if r.verdict == VERIFIED), None
    )
    if reviewed is None:
        raise RecordRefusedError(
            "request-not-pending",
            f"record failed because {key.id} reviews no verified work. To fix: run status.",
        )
    asked = spawn_request(task.slug, step, key, step_cap(step), str(task.dir))
    max_turns = declared_max_turns(asked.agent_call.subagent_type)
    seen = await_end(task.repo, key.id, agent_id, max_turns)
    marker, stop_reason, warnings = read_return(seen, cast(Marker, relayed), asked, max_turns)
    record = review_record(reviewed, key.id, agent_id, stop_reason, seen.turns, max_turns)
    append_ledger_record(task.dir, record)
    verdict = file_verdict(task.inputs.reviews.get(step.id))
    summary = (
        f"appended {record.step} attempt {record.attempt}: review {verdict or 'without a verdict'}"
    )
    return Taken(
        recorded_object(record, marker, summary, review_verdict=verdict), step.id, warnings
    )


def withdraw_request(task: TaskView, request: str) -> Taken:
    """Take back a request whose Agent call never started: the `Attempts:` line returns to
    what it was before the write-ahead and the prompt file goes, so the next `next` writes
    both again byte for byte. Refused when a transcript naming the request exists."""
    spawn = _pending(task.inputs, request)
    prompt = task.dir / PROMPT_FILE.format(request)
    since = prompt.stat().st_mtime if prompt.exists() else float("-inf")
    if find_request_transcript(request, since) is not None:
        raise RecordRefusedError(
            "not-started-but-ran",
            f"record failed because an agent was started on {request}. To fix: report its"
            " agentId and marker once it ends, instead of --not-started.",
        )
    outstanding = cast(OutstandingAttempt, task.inputs.attempts[spawn.step.id])
    withdraw_line(task.dir / WIP_FILE, spawn.step.id, outstanding, spawn.key.kind)
    prompt.unlink(missing_ok=True)
    return Taken(withdrawn_object(request), spawn.step.id)


def withdrawn_object(request: str) -> dict[str, Any]:
    """The envelope's `recorded` object for a request that never started."""
    nothing = dict.fromkeys(("agent_id", "turns", "max_turns", "gate", "review_verdict"))
    return {
        **nothing,
        "request": request,
        "marker": "none",
        "stop_reason": "not-started",
        "commit": None,
        "ledger": None,
        "replayed": False,
    }


def _plan_step(inputs: LoopInputs, step_id: str) -> PlanStep:
    return next(step for step in inputs.steps if step.id == step_id)


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
    record: IterationRecord,
    marker: str,
    ledger: str | None,
    *,
    replayed: bool = False,
    review_verdict: str | None = None,
) -> dict[str, Any]:
    """The envelope's `recorded` object for a ledger record; `review_verdict` is the reviewer's
    verdict word (accept, revise or partial), none for any other kind of return."""
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
        "review_verdict": review_verdict,
        "commit": record.commit,
        "ledger": ledger,
        "replayed": replayed,
    }


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
        return request_count(self.reading)


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
    """The transcript now, and whether the gate's evidence shows the agent has ended."""
    path, raw = read_agent(agent_id, cwd=repo)
    reading = salvaged(path, raw)
    evidence = end_evidence(reading, max_turns, agent_stopped(repo, agent_id))
    unreadable = isinstance(raw, Unreadable) or (isinstance(raw, Read) and raw.malformed)
    ended = end_source(evidence) is not None
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


# --- 4. Commit: by explicit path, once per request -------------------------------------------


class Committing(NamedTuple):
    """The commit's sha (None: none holds the work) and why no commit holds it."""

    sha: str | None
    failure: str | None


def commit_attempt(
    task: TaskView, step: PlanStep, asked: SpawnRequest, deciding: str
) -> Committing:
    """Commit the step's declared files, unless HEAD already is the request's commit."""
    sha = head_commit_for(task.repo, asked.key.id)
    if sha is not None:
        return Committing(sha, None)
    message = commit_message(step, task.slug, asked, deciding)
    read_only = tuple(entry for s in task.inputs.steps for entry in s.read_only)
    try:
        outcome = commit_paths(task.repo, step.files, message, read_only)
    except (GitCommandError, GitUnavailableError, OutsideRepoError) as exc:
        why = f"the step-loop driver could not commit: {_first_line(str(exc))}"
        _save_snapshot(task, asked.key.id, "", why)  # the repository could not be read
        return Committing(None, why)
    return judge_commit(task, asked.key.id, outcome)


def judge_commit(task: TaskView, request: str, outcome: CommitOutcome) -> Committing:
    """What each commit outcome means for the attempt (see `Committing`)."""
    if isinstance(outcome, Committed):
        return Committing(outcome.sha, None)
    if isinstance(outcome, NothingToCommit):
        return Committing(None, None)
    if isinstance(outcome, CommitRefused):
        return Committing(None, f"{_HOOKS_REFUSED}: {_one_line(outcome.detail)}. {_HOOK_FIX}")
    if isinstance(outcome, CommitInterrupted):
        why = f"the step-loop driver's commit did not finish: {_first_line(outcome.detail)}"
        _save_snapshot(task, request, outcome.after.patch_text(), why)
        return Committing(None, why)
    why = f"the step-loop driver's commit met files outside its paths: {', '.join(outcome.paths)}"
    _save_snapshot(task, request, outcome.before.patch_text(), why)
    return Committing(outcome.sha, why)


def _save_snapshot(task: TaskView, request: str, patch_text: str, why: str) -> None:
    """Write `TREE_SNAPSHOT_<request>.patch`, headed by why and the lock when one stands.

    The file is the stop: `next` and `status` stop while it exists, until a person deletes it.
    """
    write_tree_snapshot(task.dir, request, f"# {why}{_lock_note(task.repo)}\n{patch_text}")


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


def _one_line(text: str) -> str:
    """The text as one line of at most the hook-words limit (git's own failures run longer)."""
    line = " ".join(text.split()) or "no detail"
    return line if len(line) <= HOOK_WORDS_LIMIT else line[: HOOK_WORDS_LIMIT - 1] + "…"


def _first_line(text: str) -> str:
    return " ".join((text.strip().splitlines() or ["no detail"])[0].split())
