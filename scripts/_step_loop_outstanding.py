"""The outstanding-request probe: which request has an agent of this session that has ended and
whose return `record` has not taken back.

A reader only: it writes no file, runs no git and starts no process. It answers one question for
a guard that must not hold a live agent, so it shares the driver's own evidence instead of
keeping a second reading:

* **Outstanding**: a `WIP.md` `Attempts:` line whose `request=` the task's `ITERATION_LEDGER.jsonl`
  does not record (`parse_attempts` and `read_ledger`, the driver's readers). A task whose
  `WIP.md` or ledger cannot be read yields no request: a guard that cannot look lets the stop
  through.
* **Held**: an agent transcript of this session (`subagents_dir`) that `names_request` ties to
  the request, whose prompt also carries the `Task slug:` line of the request's own task (request
  ids restart in every task), and that `end_source` reads as ended: the predicate `record` accepts
  an agent by, tightened. The transcript must be a clean `Read`; a line that does not parse makes
  it `NotHeld`, where `record` would salvage the lines that do. When several transcripts of the
  session are tied to one request and any of them is running, the request is `NotHeld`. The
  command to run is built by the driver's own `Invocation`, never retyped. A task directory whose
  name is not a slug is skipped, so a `Held` never carries one.

The observation log is read from `work_root`'s parent, and that is the root `record` reads: it
takes `.ai-work/` at the top level of the checkout, which is where the Stop guard looks for
`work_root` (its walk-up stops at the first ancestor holding a `.git` entry). A caller whose
`work_root` is not at its checkout's root breaks that equality. Transcripts older than the oldest
outstanding request's prompt file, and files whose names are not agent ids, are never read.
Stdlib-only and 3.9-safe at runtime.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Union

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks"))
from _agent_transcript import (  # noqa: E402 (after sys.path injection)
    Read,
    TranscriptReading,
    Unreadable,
    parse_transcript,
)
from _loop_fields import OutstandingAttempt, parse_attempts  # noqa: E402
from _step_loop_files import (  # noqa: E402
    PROMPT_STEM,
    PROMPT_SUFFIX,
    STEP_LABEL,
    agent_stopped,
    end_evidence,
    names_request,
)
from _step_loop_gate import Marker, end_source, parse_marker  # noqa: E402
from _step_loop_record import declared_max_turns  # noqa: E402
from _step_loop_render import Invocation, parse_request_id  # noqa: E402
from iteration_ledger import read_ledger  # noqa: E402

WIP_FILE = "WIP.md"
REVIEWER_AGENT, WORKER_AGENT = "praxion:verifier", "praxion:implementer"
NEVER_ISSUED = float("-inf")  # a request whose prompt file is gone sorts as the oldest
# The shape `_goal_scaffold._SLUG_RE` accepts for a task slug, bounded: the Stop guard prints the
# slug into a command the model runs, so a directory name outside it is no task.
_SLUG_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")
# The ids `hooks/_agent_transcript.locate` accepts: any other file is one `record` cannot find.
_AGENT_ID_RE = re.compile(r"[A-Za-z0-9_-]+")
_TRANSCRIPT_PREFIX, _TRANSCRIPT_GLOBS = "agent-", ("agent-*.jsonl", "workflows/*/agent-*.jsonl")

NotHeldReason = Literal["no-transcript-in-session", "running", "unreadable"]
_REASON_PRECEDENCE: tuple[NotHeldReason, ...] = ("unreadable", "running")


@dataclass(frozen=True)
class Outstanding:
    """A request the loop issued whose return is not recorded; `issued_at` is the mtime of its
    prompt file (epoch seconds), and `step` the bare step id."""

    slug: str
    step: str
    request: str
    issued_at: float


@dataclass(frozen=True)
class Held:
    """An outstanding request whose agent has ended: `command` records it."""

    outstanding: Outstanding
    agent_id: str
    marker: Marker
    command: str


@dataclass(frozen=True)
class NotHeld:
    """An outstanding request no stop should wait on, and why."""

    reason: NotHeldReason


Verdict = Union[Held, NotHeld]  # noqa: UP007 -- runtime value, 3.9 floor
RUNNING = NotHeld("running")


@dataclass(frozen=True)
class _Transcript:
    agent_id: str
    reading: TranscriptReading
    text: str


# --- The questions -----------------------------------------------------------------------


def ended_unrecorded(
    work_root: Path, subagents_dir: Path, invocation: Invocation
) -> tuple[Held, ...]:
    """The outstanding requests whose agent of this session has ended, oldest issued first."""
    judged = judge_outstanding(work_root, subagents_dir, invocation)
    return tuple(verdict for _, verdict in judged if isinstance(verdict, Held))


def judge_outstanding(
    work_root: Path, subagents_dir: Path, invocation: Invocation
) -> tuple[tuple[Outstanding, Verdict], ...]:
    """Every outstanding request with its verdict; no transcript is read without a request."""
    outstanding = outstanding_requests(work_root)
    if not outstanding:
        return ()
    transcripts = _load_transcripts(subagents_dir, min(o.issued_at for o in outstanding))
    repo_root = work_root.parent
    return tuple((o, _judge(o, transcripts, repo_root, invocation)) for o in outstanding)


def outstanding_requests(work_root: Path) -> tuple[Outstanding, ...]:
    """The requests every task under `work_root` issued and the ledger does not record, oldest
    issued first, ties by task slug."""
    try:
        tasks = sorted(
            path for path in work_root.iterdir() if _SLUG_RE.fullmatch(path.name) and path.is_dir()
        )
    except OSError:
        return ()
    found = [request for task in tasks for request in _outstanding_of(task)]
    return tuple(sorted(found, key=lambda o: (o.issued_at, o.slug, o.step, o.request)))


def _outstanding_of(task: Path) -> Iterator[Outstanding]:
    try:
        wip_text = (task / WIP_FILE).read_text(encoding="utf-8")
        ledger = read_ledger(task)
    except (OSError, UnicodeDecodeError):
        return
    if ledger.findings:  # a record the reader skipped may be the one that settles a request
        return
    for label, attempt in parse_attempts(wip_text, ledger.requests).counts.items():
        if isinstance(attempt, OutstandingAttempt):
            step = label[len(STEP_LABEL) :]
            yield Outstanding(task.name, step, attempt.request, _issued_at(task, attempt.request))


def _issued_at(task: Path, request: str) -> float:
    return _mtime(task / f"{PROMPT_STEM}_{request}{PROMPT_SUFFIX}")


def _mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return NEVER_ISSUED


# --- The transcripts of the session --------------------------------------------------------


def _load_transcripts(subagents_dir: Path, since: float) -> tuple[_Transcript, ...]:
    """The session's transcripts written at or after `since` under an agent id, each read once."""
    paths = sorted({path for glob in _TRANSCRIPT_GLOBS for path in subagents_dir.glob(glob)})
    candidates = [path for path in paths if _AGENT_ID_RE.fullmatch(_agent_id_of(path))]
    return tuple(_load(path) for path in candidates if _mtime(path) >= since)


def _agent_id_of(path: Path) -> str:
    return path.stem[len(_TRANSCRIPT_PREFIX) :]


def _load(path: Path) -> _Transcript:
    agent_id = _agent_id_of(path)
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return _Transcript(agent_id, Unreadable(lines_ok=0, last_ok=False), "")
    reading = parse_transcript(text)
    return _Transcript(agent_id, reading, text if isinstance(reading, Unreadable) else "")


# --- The verdict -----------------------------------------------------------------------------


def _judge(
    outstanding: Outstanding,
    transcripts: Sequence[_Transcript],
    repo_root: Path,
    invocation: Invocation,
) -> Verdict:
    """Held when a transcript tied to the request shows its agent ended and no other agent tied
    to it is running; else the reason."""
    max_turns = declared_max_turns(_agent_type(outstanding.request))
    verdicts = [
        _judge_transcript(outstanding, t, max_turns, repo_root, invocation) for t in transcripts
    ]
    related = [verdict for verdict in verdicts if verdict is not None]
    held = next((verdict for verdict in related if isinstance(verdict, Held)), None)
    if held is not None:  # a reissued request has two agents; one ending says nothing of the other
        return RUNNING if len(related) > 1 and RUNNING in related else held
    reasons: set[NotHeldReason] = {v.reason for v in related if isinstance(v, NotHeld)}
    for reason in _REASON_PRECEDENCE:
        if reason in reasons:
            return NotHeld(reason)
    return NotHeld("no-transcript-in-session")


def _judge_transcript(
    outstanding: Outstanding,
    transcript: _Transcript,
    max_turns: int | None,
    repo_root: Path,
    invocation: Invocation,
) -> Verdict | None:
    """One transcript's verdict on the request, `None` when it is not about it."""
    reading, request = transcript.reading, outstanding.request
    if isinstance(reading, Unreadable):  # it cannot be tied to a request; its bytes can mention one
        return NotHeld("unreadable") if _mentions(transcript.text, outstanding) else None
    if not (names_request(reading, request) and _names_task(reading, outstanding.slug)):
        return None
    if not isinstance(reading, Read) or reading.malformed:
        return NotHeld("unreadable")
    evidence = end_evidence(reading, max_turns, False)
    if end_source(evidence) is None:  # the observation log is read only for an agent still silent
        evidence = end_evidence(reading, max_turns, agent_stopped(repo_root, transcript.agent_id))
    if end_source(evidence) is None:
        return RUNNING
    marker = parse_marker(evidence.final_text)
    command = invocation.command(
        "record",
        outstanding.slug,
        "--request",
        request,
        "--agent-id",
        transcript.agent_id,
        "--marker",
        marker,
    )
    return Held(outstanding, transcript.agent_id, marker, command)


def _agent_type(request: str) -> str:
    """The agent definition a request starts: a review is the verifier's, any other the implementer's."""
    key = parse_request_id(request)
    return REVIEWER_AGENT if key is not None and key.kind == "review" else WORKER_AGENT


def _names_task(reading: TranscriptReading, slug: str) -> bool:
    """The agent's first user message carries the `Task slug:` line of the request's own task."""
    return (
        isinstance(reading, Read) and _task_line(slug).search(reading.first_user_text) is not None
    )


def _mentions(text: str, outstanding: Outstanding) -> bool:
    """Raw transcript bytes name the request and its task: all an unparseable file can say."""
    request = rf"Spawn request: {re.escape(outstanding.request)}(?![a-z0-9-])"
    return (
        re.search(request, text) is not None
        and _task_line(outstanding.slug).search(text) is not None
    )


def _task_line(slug: str) -> re.Pattern[str]:
    return re.compile(rf"Task slug: {re.escape(slug)}(?![A-Za-z0-9_-])")
