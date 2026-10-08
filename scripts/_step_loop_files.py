"""The file and transcript adapters of the step-loop driver.

* **Writers**: each is atomic (a temporary file renamed over the target; one append for the
  ledger) and idempotent per request, so a `record` cut off part-way completes when the same
  call runs again; each says whether it wrote, and none rewrites a file whose content would not
  change. Git and the command runner live in `_step_loop_io.py`.
* **Transcripts**: the reading is `hooks/_agent_transcript.py`'s; here it becomes end evidence for
  the gate, the fidelity warnings, the search for an agent that started on a request, and the
  `agent_stop` row (read through the handoff gate's session reader, a declared consumer of the
  observation log).
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import sys
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks"))
from _agent_transcript import (  # noqa: E402 (after sys.path injection)
    CONFIG_DIR_VARIABLE,
    Final,
    Read,
    TranscriptReading,
    locate,
    locate_session,
    read_transcript,
    request_count,
)
from _handoff_inputs import read_existing  # noqa: E402
from _handoff_readiness import WAL_AGENT_STOP, session_wal_rows  # noqa: E402
from _loop_fields import REQUEST_ID_RE, AnyAttempt, render_attempts_line  # noqa: E402
from _step_loop_gate import EndEvidence  # noqa: E402
from _step_loop_render import AgentCall, parse_request_id  # noqa: E402
from _step_loop_state import SNAPSHOT_STEM, SNAPSHOT_SUFFIX  # noqa: E402
from _step_schema import Counts, NoRun, checklist_step_id, parse_result_line  # noqa: E402
from compose_handoff import MID_PHASE_PREFIX, SECTION_HEADINGS, write_handoff  # noqa: E402
from iteration_ledger import IterationRecord, append_record, read_ledger  # noqa: E402

STEP_LABEL = "Step "
PROMPT_STEM, PROMPT_SUFFIX = "PROMPT", ".md"
ITERATION_PATCH_STEM, PATCH_SUFFIX = "ITERATION", ".patch"
WORKER_STEM, WORKER_SUFFIX, WORKER_FILE_VERSION = "WORKER", ".json", 1
STARTED_SUFFIX = ".started"
META_UNREADABLE, REQUEST_FIDELITY = "meta-unreadable", "request-fidelity"
DEFAULT_FILE_MODE, MODE_MASK = 0o644, 0o777
_RESULT_PREFIX, _BLOCK_HEADING_PREFIX, _COMMAND_PREFIX = "Result:", "## ", "Command:"
_PENDING_RE = re.compile(r"(?:^|\s)pending=(?P<count>[0-9]+)(?:\s|$)")
_FENCES, _CHILD_INDENT = ("```", "~~~"), "  "
_TRANSCRIPT_GLOBS = (
    "projects/*/*/subagents/agent-*.jsonl",
    "projects/*/*/subagents/workflows/*/agent-*.jsonl",
)
_NEXT_ACTION, _NEXT_SECTION = SECTION_HEADINGS[2], SECTION_HEADINGS[3]


# --- The atomic primitive ---------------------------------------------------------------


def write_atomic(path: Path, text: str) -> bool:
    """Replace `path` with `text` in one rename; False, and no write, when it holds it already."""
    data = text.encode("utf-8", "surrogateescape")
    with contextlib.suppress(FileNotFoundError):
        if path.read_bytes() == data:
            return False
    handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(data)
        os.chmod(temporary, path.stat().st_mode & MODE_MASK if path.exists() else DEFAULT_FILE_MODE)
        os.replace(temporary, path)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temporary)
        raise
    return True


# --- The Attempts: line -----------------------------------------------------------------


def set_attempts_line(wip_path: Path, step_id: str, attempt: AnyAttempt | None) -> bool:
    """Make `WIP.md` say `attempt` for the step (`None` removes its line); True when it wrote."""
    return write_atomic(wip_path, with_attempts_line(wip_path.read_text("utf-8"), step_id, attempt))


def with_attempts_line(wip_text: str, step_id: str, attempt: AnyAttempt | None) -> str:
    """The WIP text with exactly one `Attempts:` line for the step, or none for `None`.

    An existing line (outside code fences) is replaced in place, keeping its indent, and any
    stale duplicate dropped; a new one goes under the step's checklist line, else at the end.
    """
    lines, label = wip_text.split("\n"), STEP_LABEL + step_id
    fenced, own_line = _fenced_flags(lines), _own_attempts_re(step_id)
    own = [i for i, line in enumerate(lines) if not fenced[i] and own_line.match(line)]
    if attempt is None:
        return "\n".join(line for i, line in enumerate(lines) if i not in own)
    rendered = render_attempts_line(step_id, attempt)
    if own:
        lines[own[0]] = _indent(lines[own[0]]) + rendered
        return "\n".join(line for i, line in enumerate(lines) if i == own[0] or i not in own)
    anchor = next(
        (i for i, line in enumerate(lines) if not fenced[i] and checklist_step_id(line) == label),
        None,
    )
    if anchor is None:  # no checklist line: the end of the file, before its final newline
        at = len(lines) - 1 if lines[-1] == "" else len(lines)
        return "\n".join([*lines[:at], rendered, *lines[at:]])
    child = _indent(lines[anchor]) + _CHILD_INDENT + rendered
    return "\n".join([*lines[: anchor + 1], child, *lines[anchor + 1 :]])


def _indent(line: str) -> str:
    return line[: len(line) - len(line.lstrip())]


def _own_attempts_re(step_id: str) -> re.Pattern[str]:
    return re.compile(
        r"^\s*[-*+]\s+\*{0,2}Attempts\*{0,2}\s*:\s*\*{0,2}\s*"
        rf"Step\s+{re.escape(step_id)}\s+count="
    )


def _fenced_flags(lines: Sequence[str]) -> list[bool]:
    """Per line: inside a code fence (the fence lines count), where an `Attempts:` declares nothing."""
    inside, flags = False, []
    for line in lines:
        is_fence = line.lstrip().startswith(_FENCES)
        inside = inside != is_fence
        flags.append(inside or is_fence)
    return flags


# --- The results, the prompt, the snapshot, the ledger, the handoff, the worker's end -----


def gate_heading(step_id: str, request: str) -> str:
    return f"{_BLOCK_HEADING_PREFIX}{STEP_LABEL}{step_id} — step-loop gate, {request}"


def write_gate_block(results_path: Path, step_id: str, request: str, body: Sequence[str]) -> bool:
    """Write the request's gate block, replacing an earlier one of the same request.

    The block must end on its deciding `Result:` line (the reconciler reads the latest) and
    must not hold a heading of its own, which would end it early on the next write.
    """
    if not body or not body[-1].startswith(_RESULT_PREFIX):
        raise ValueError("a gate block ends on its deciding Result: line")
    if any(line.startswith(_BLOCK_HEADING_PREFIX) for line in body):
        raise ValueError("a gate block holds no heading of its own")
    current = results_path.read_text("utf-8") if results_path.exists() else ""
    block = [gate_heading(step_id, request), "", *body]
    return write_atomic(results_path, _with_block(current, block))


def _with_block(text: str, block: list[str]) -> str:
    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines) if line == block[0]), None)
    if start is None:
        before, after = lines, []
    else:
        end = next(
            (i for i in range(start + 1, len(lines)) if lines[i].startswith(_BLOCK_HEADING_PREFIX)),
            len(lines),
        )
        before, after = lines[:start], lines[end:]
    spaced_before = [*before, ""] if before and before[-1] != "" else before
    spaced_after = ["", *after] if after else []
    return "\n".join([*spaced_before, *block, *spaced_after]) + "\n"


def latest_reading(results_path: Path, step_id: str) -> tuple[str, ...]:
    """The step's latest gate block as lines to show: the check's command, then each `Result:`
    line restated. The latest block is the last in the file, so the scaffold's baseline block,
    written first, reads until a gate block follows it; empty when the step has none."""
    lines = results_path.read_text("utf-8").splitlines() if results_path.is_file() else []
    prefix = gate_heading(step_id, "")
    start = next((i for i in reversed(range(len(lines))) if lines[i].startswith(prefix)), None)
    if start is None:
        return ()
    end = next(
        (i for i in range(start + 1, len(lines)) if lines[i].startswith(_BLOCK_HEADING_PREFIX)),
        len(lines),
    )
    block = lines[start + 1 : end]
    commands = [line for line in block if line.startswith(_COMMAND_PREFIX)]
    results = [restate_result(line) for line in block if line.startswith(_RESULT_PREFIX)]
    return (*commands[-1:], *results)  # the check's command is the gate's last


def restate_result(line: str) -> str:
    """A `Result:` line as `<p> passed, <f> failed`, the goal's pending tests counted as failed."""
    parsed = parse_result_line(line)
    if isinstance(parsed, Counts):
        pended = _PENDING_RE.search(line)
        failed = parsed.failed + parsed.errors + (int(pended["count"]) if pended else 0)
        return f"{parsed.passed} passed, {failed} failed"
    return f"no run: {parsed.rationale}" if isinstance(parsed, NoRun) else "unreadable result"


def write_prompt(task_dir: Path, request: str, text: str) -> Path:
    """`PROMPT_<request>.md`, flat beside the task documents."""
    return _write_request_file(task_dir, PROMPT_STEM, request, PROMPT_SUFFIX, text)


def write_tree_snapshot(task_dir: Path, request: str, patch_text: str) -> Path:
    """`TREE_SNAPSHOT_<request>.patch`: what lay outside the commit when a tree was disturbed."""
    return _write_request_file(task_dir, SNAPSHOT_STEM, request, SNAPSHOT_SUFFIX, patch_text)


def snapshot_requests(task_dir: Path) -> tuple[str, ...]:
    """The request ids that have a `TREE_SNAPSHOT_<request>.patch` beside the task documents.

    The files keep the loop stopped until a person deletes them, so the next call reads them
    from the task directory, not from anything the previous call kept.
    """
    stem, suffix = f"{SNAPSHOT_STEM}_", SNAPSHOT_SUFFIX
    names = (path.name for path in task_dir.glob(f"{stem}*{suffix}") if path.is_file())
    found = (name[len(stem) : -len(suffix)] for name in names)
    return tuple(sorted(request for request in found if REQUEST_ID_RE.fullmatch(request)))


def write_iteration_patch(task_dir: Path, request: str, patch_text: str) -> Path:
    """`ITERATION_<request>.patch`, written before the restore; the first write stands, since a
    rerun computes its patch from the restored tree and would erase the only record."""
    return _write_request_file(
        task_dir, ITERATION_PATCH_STEM, request, PATCH_SUFFIX, patch_text, keep=True
    )


def iteration_patches(task_dir: Path, step_id: str) -> tuple[str, ...]:
    """The names of the step's `ITERATION_<request>.patch` files beside the task documents."""
    stem, suffix = f"{ITERATION_PATCH_STEM}_", PATCH_SUFFIX
    names = sorted(path.name for path in task_dir.glob(f"{stem}*{suffix}") if path.is_file())
    keys = ((name, parse_request_id(name[len(stem) : -len(suffix)])) for name in names)
    return tuple(name for name, key in keys if key is not None and key.step == step_id)


def _write_request_file(
    task_dir: Path, stem: str, request: str, suffix: str, text: str, keep: bool = False
) -> Path:
    if not REQUEST_ID_RE.fullmatch(request):
        raise ValueError(f"not a request id: {request!r}")
    path = task_dir / f"{stem}_{request}{suffix}"
    if not (keep and path.exists()):
        write_atomic(path, text)
    return path


def append_ledger_record(task_dir: Path, record: IterationRecord) -> bool:
    """Append the record unless its request is already recorded; True when it appended."""
    if record.request is None:
        raise ValueError("a driver record names its request")
    if record.request in read_ledger(task_dir).requests:
        return False
    append_record(task_dir, record)
    return True


def write_stop_handoff(
    slug: str,
    repo_root: Path,
    next_action: str,
    cause: str | None = None,
    base_ref: str | None = None,
) -> bool:
    """Compose `HANDOFF.md` with `next_action` as section 2 and write it only if section 2 moved.

    A stop's boundary is `mid-phase:<cause>`: the composer must name one once every step reads
    verified, and the cause (unlike a request id) repeats. Without one the composer picks its
    own. The readiness gate is overridden on purpose: a stop leaves the step's files uncommitted.
    `base_ref` is the pipeline's own fork point, so the composed reconciler rows read the same
    ground truth the driver gated on.
    """
    boundary = None if cause is None else f"{MID_PHASE_PREFIX}{cause}"
    composed = write_handoff(
        slug,
        repo_root,
        boundary=boundary,
        force=True,
        base_ref=base_ref,
        next_action=next_action,
        dry_run=True,
    )
    path: Path = composed["path"]
    existing = read_existing(path)
    if existing is not None and _next_action_of(existing) == _next_action_of(composed["text"]):
        return False
    return write_atomic(path, composed["text"])


def _next_action_of(handoff_text: str) -> str | None:
    start = handoff_text.find(f"## {_NEXT_ACTION}")
    end = handoff_text.find(f"## {_NEXT_SECTION}", start)
    return handoff_text[start:end].strip() if start >= 0 and end > start else None


@dataclass(frozen=True)
class NoWorkerResult:
    detail: str  # what the worker file shows where an ended worker should be


@dataclass(frozen=True)
class WorkerEnd:
    """An ended headless worker; a field its result object did not report is `None`."""

    session_id: str
    subtype: str
    final_text: str | None
    cost_usd: float | None
    denials: int
    num_turns: int | None
    max_turns: int


def worker_result_path(task_dir: Path, request: str) -> Path:
    """The file a headless worker's end is written to."""
    return task_dir / f"{WORKER_STEM}_{request}{WORKER_SUFFIX}"


def worker_marker_path(task_dir: Path, request: str) -> Path:
    """The marker written before a worker is launched, so a launch is never repeated blind."""
    return task_dir / f"{WORKER_STEM}_{request}{STARTED_SUFFIX}"


def write_worker_end(
    task_dir: Path,
    request: str,
    *,
    argv: Sequence[str],
    exit_code: int,
    max_turns: int,
    max_budget_usd: float,
    stdout_tail: str,
    result: dict[str, object] | None,
) -> Path:
    """The exited process's end, in its result file; `result` is the object it printed."""
    document = {
        "v": WORKER_FILE_VERSION,
        "argv": list(argv),
        "exit": exit_code,
        "max_turns": max_turns,
        "max_budget_usd": max_budget_usd,
        "stdout_tail": stdout_tail,
        "result": result,
    }
    text = json.dumps(document, indent=2) + "\n"
    return _write_request_file(task_dir, WORKER_STEM, request, WORKER_SUFFIX, text)


def read_worker_end(task_dir: Path, request: str) -> NoWorkerResult | WorkerEnd | None:
    """Parse the file once: `None` is no file (relayed).

    Short of a usable result is `NoWorkerResult`.
    """
    path = worker_result_path(task_dir, request)
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:  # unreadable bytes and broken JSON are both ValueErrors
        return NoWorkerResult(f"the worker file cannot be read: {exc}")
    if not isinstance(document, dict) or document.get("v") != WORKER_FILE_VERSION:
        return NoWorkerResult("the worker file is not a version-1 worker document")
    result = _typed(document, "result", dict) or {}
    session_id, subtype = _typed(result, "session_id", str), _typed(result, "subtype", str)
    max_turns = _typed(document, "max_turns", int)
    if not session_id or not subtype or max_turns is None:
        return NoWorkerResult(f"exit {document.get('exit')} left no usable result; see {path.name}")
    cost = _typed(result, "total_cost_usd", (int, float))
    return WorkerEnd(
        session_id=session_id,
        subtype=subtype,
        final_text=_typed(result, "result", str),
        cost_usd=float(cost) if cost is not None and 0 <= cost < float("inf") else None,
        denials=len(_typed(result, "permission_denials", list) or ()),
        num_turns=_typed(result, "num_turns", int),
        max_turns=max_turns,
    )


def _typed(source: dict, key: str, kind: type | tuple[type, ...]) -> Any:
    value = source.get(key)
    return value if isinstance(value, kind) and not isinstance(value, bool) else None


# --- The agent's transcript ---------------------------------------------------------------


def read_agent(
    agent_id: str,
    *,
    session_id: str | None = None,
    transcript_path: str | None = None,
    config: Path | None = None,
    cwd: Path | None = None,
) -> tuple[Path | None, TranscriptReading]:
    """(where the agent's transcript is, or None; what it reads as). With a `cwd`, an id no
    subagent carries is looked up as a top-level session's id (`locate_session`)."""
    path = locate(agent_id, session_id=session_id, transcript_path=transcript_path, config=config)
    if path is None and cwd is not None:
        path = locate_session(agent_id, cwd, config)
    return path, read_transcript(path)


def end_evidence(
    reading: TranscriptReading, max_turns: int | None, agent_stopped: bool
) -> EndEvidence:
    """What the gate needs to tell an ended agent from a running one; nothing of an unreadable file."""
    if not isinstance(reading, Read):
        return EndEvidence(None, None, max_turns, agent_stopped)
    final = reading.last_turn.text if isinstance(reading.last_turn, Final) else None
    return EndEvidence(final, request_count(reading), max_turns, agent_stopped)


def names_request(reading: TranscriptReading, request: str) -> bool:
    """The agent's first user message carries `Spawn request: <request>` (hooks may prepend text)."""
    if not isinstance(reading, Read):
        return False
    pattern = rf"Spawn request: {re.escape(request)}(?![a-z0-9-])"
    return re.search(pattern, reading.first_user_text) is not None


def meta_warnings(transcript: Path | None, call: AgentCall) -> tuple[str, ...]:
    """The `.meta.json` beside a transcript against the call the request asked for."""
    if transcript is None:
        return ()
    try:
        meta = json.loads(transcript.with_suffix(".meta.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return (META_UNREADABLE,)
    if not isinstance(meta, dict):
        return (META_UNREADABLE,)
    asked = {"agentType": call.subagent_type, "model": call.model}
    return tuple(
        f"{REQUEST_FIDELITY}: {key} is {meta.get(key)!r}, the request asked for {value!r}"
        for key, value in asked.items()
        if meta.get(key) != value
    )


def agent_stopped(repo_root: Path, agent_id: str) -> bool:
    """The observation log holds an `agent_stop` row for the agent (in the newest session)."""
    return any(
        row.get("event_type") == WAL_AGENT_STOP and row.get("agent_id") == agent_id
        for row in session_wal_rows(repo_root)
    )


def find_request_transcript(request: str, since: float, config: Path | None = None) -> Path | None:
    """The newest transcript written at or after `since` (the prompt's write time, epoch
    seconds) whose first user message names the request: proof an agent started on it."""
    root = config or Path(os.environ.get(CONFIG_DIR_VARIABLE) or Path.home() / ".claude")
    found = (path for pattern in _TRANSCRIPT_GLOBS for path in root.glob(pattern))
    stamped = ((_mtime(path), path) for path in found)
    recent = sorted(((t, p) for t, p in stamped if t >= since), reverse=True)
    return next((p for _, p in recent if names_request(read_transcript(p), request)), None)


def _mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return float("-inf")
