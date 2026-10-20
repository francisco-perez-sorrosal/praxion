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
  the request and that `end_source` reads as ended: the predicate `record` accepts an agent by.
  The transcript must be a clean `Read`; a line that does not parse makes it `NotHeld`, where
  `record` would salvage the lines that do. The command to run is built by the driver's own
  `Invocation`, never retyped.

The observation log is read from `work_root`'s parent: `.ai-work/` sits at the repository root.
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
    transcripts = _load_transcripts(subagents_dir)
    repo_root = work_root.parent
    return tuple((o, _judge(o, transcripts, repo_root, invocation)) for o in outstanding)


def outstanding_requests(work_root: Path) -> tuple[Outstanding, ...]:
    """The requests every task under `work_root` issued and the ledger does not record, oldest
    issued first, ties by task slug."""
    try:
        tasks = sorted(path for path in work_root.iterdir() if path.is_dir())
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
    try:
        return (task / f"{PROMPT_STEM}_{request}{PROMPT_SUFFIX}").stat().st_mtime
    except OSError:
        return NEVER_ISSUED


# --- The transcripts of the session --------------------------------------------------------


def _load_transcripts(subagents_dir: Path) -> tuple[_Transcript, ...]:
    paths = sorted({path for glob in _TRANSCRIPT_GLOBS for path in subagents_dir.glob(glob)})
    loaded = (_load(path) for path in paths)
    return tuple(t for t in loaded if _AGENT_ID_RE.fullmatch(t.agent_id))


def _load(path: Path) -> _Transcript:
    agent_id = path.stem[len(_TRANSCRIPT_PREFIX) :]
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return _Transcript(agent_id, Unreadable(lines_ok=0, last_ok=False), "")
    return _Transcript(agent_id, parse_transcript(text), text)


# --- The verdict -----------------------------------------------------------------------------


def _judge(
    outstanding: Outstanding,
    transcripts: Sequence[_Transcript],
    repo_root: Path,
    invocation: Invocation,
) -> Verdict:
    """Held when any transcript tied to the request shows its agent ended; else the reason."""
    max_turns = declared_max_turns(_agent_type(outstanding.request))
    verdicts = [
        _judge_transcript(outstanding, t, max_turns, repo_root, invocation) for t in transcripts
    ]
    related = [verdict for verdict in verdicts if verdict is not None]
    held = next((verdict for verdict in related if isinstance(verdict, Held)), None)
    if held is not None:
        return held
    reasons = {verdict.reason for verdict in related if isinstance(verdict, NotHeld)}
    reason = next((r for r in _REASON_PRECEDENCE if r in reasons), "no-transcript-in-session")
    return NotHeld(reason)


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
        return NotHeld("unreadable") if _mentions(transcript.text, request) else None
    if not names_request(reading, request):
        return None
    if not isinstance(reading, Read) or reading.malformed:
        return NotHeld("unreadable")
    evidence = end_evidence(reading, max_turns, False)
    if end_source(evidence) is None:  # the observation log is read only for an agent still silent
        evidence = end_evidence(reading, max_turns, agent_stopped(repo_root, transcript.agent_id))
    if end_source(evidence) is None:
        return NotHeld("running")
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


def _mentions(text: str, request: str) -> bool:
    return re.search(rf"Spawn request: {re.escape(request)}(?![a-z0-9-])", text) is not None
