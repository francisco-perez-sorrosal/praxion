#!/usr/bin/env python3
"""The iteration ledger: one append-only record per implementer return.

The ledger is a JSON Lines file, ``ITERATION_LEDGER.jsonl``, in a task's working
directory; this module is its only reader and writer, so every consumer sees the
same records. Earlier lines never change; an absent or empty file is no history.

Normative shape: one JSON object per line, every key required (shown wrapped)::

    {"v": 1, "recorded_at": "2026-10-04T17:39Z", "step": "Step <id>", "attempt": 1,
     "agent_id": "a3f9c2e17b", "verdict": "verified-complete", "decided_by": "check",
     "test_result": "Result: pass=12 fail=0 skip=0", "commit": "04569546",
     "stop_reason": "completed"}

The step-loop driver adds optional keys, absent on a hand-appended record: ``request``,
``step_digest`` (hex of the step block: a revision opens a fresh attempt series), ``turns``
and ``max_turns`` (integer or ``null``); the last three need a ``request``. A goal-mode
record may add ``cost_usd`` (a number of at least 0) and ``progress_lines`` (an integer of
at least 0): present only when known, never ``null``, and needing a ``request``.

Every rule is enforced where a line is parsed, so a record that reads back is valid:

- ``v``: the integer 1 (a breaking change to the shape bumps it); unknown extra
  keys are ignored, so the shape can grow. ``recorded_at``: ``YYYY-MM-DDTHH:MMZ``
  (UTC to the minute), stamped by the writer.
- ``step``: ``Step <id>``, the id spelled as the plan's step headings spell it.
  ``attempt``: an integer of at least 1. ``agent_id``: a non-empty string.
- ``verdict``: a reconciler verdict word, or ``partial@<last write>``.
  ``decided_by``: ``check``, ``fallback`` or ``none``.
- ``test_result``: the step's recorded ``Result:`` line, a count line or a no-run.
- ``commit``: a 7 to 40 character lowercase hex sha, or JSON ``null`` stating that
  no commit holds the work. An absent key is a finding, never read as ``null``.
- ``stop_reason``: completed, turn-cap, blocked, conflict, partial or no-marker.

A line that breaks the shape becomes a finding at its append position (1-based among
non-blank lines): reported, never skipped, never guessed. The orchestrator is the writer.

Command line: ``append`` takes a return's verdict and ``decided_by`` from the
reconciler's verdict for the step and its ``test_result`` from the step's latest
``Result:`` line in ``TEST_RESULTS.md`` (``Result: none`` when it recorded none),
so the orchestrator derives them rather than types them. ``read`` exits 0 clean,
1 when any line is a finding, 2 on an input error. The repository comes from
``--repo-root`` or git; ``--worktree-root`` locates ``.ai-work/`` outside it.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from _loop_fields import REQUEST_ID_RE, latest_result
from _repo_root import git_toplevel_from_cwd, is_plugin_cache_path
from _step_schema import STEP_ID_RE, Counts, NoRun, parse_result_line
from _step_verdict import VERDICT_WORDS

LEDGER_FILE = "ITERATION_LEDGER.jsonl"
SCHEMA_VERSION = 1
STOP_REASONS = ("completed", "turn-cap", "blocked", "conflict", "partial", "no-marker")
DECIDED_BY = ("check", "fallback", "none")

UNSTAMPED = ""  # a record not yet written; the writer replaces it with the append time
_STAMP_FORMAT = "%Y-%m-%dT%H:%MZ"
_COMMIT_RE = re.compile(r"[0-9a-f]{7,40}")
_DIGEST_RE = re.compile(r"[0-9a-f]{6,64}")
_DRIVER_KEYS = ("request", "step_digest", "turns", "max_turns")  # the last three need a request
_GOAL_KEYS = ("cost_usd", "progress_lines")  # written only when known; need a request
NO_RESULT_RECORDED = "Result: none — no result recorded"
EXIT_CLEAN, EXIT_FINDINGS, EXIT_INPUT_ERROR = 0, 1, 2
_STEP_LABEL = "Step "


class ShapeError(ValueError):
    """A ledger line breaks the documented shape; the message names how."""


@dataclass(frozen=True)
class IterationRecord:
    """One implementer return. ``recorded_at`` and ``v`` are the writer's to set."""

    step: str
    attempt: int
    agent_id: str
    verdict: str
    decided_by: str
    test_result: str
    commit: str | None  # None states that no commit holds the work
    stop_reason: str
    v: int = SCHEMA_VERSION
    recorded_at: str = UNSTAMPED
    request: str | None = None  # the step-loop driver's keys; turns None: unknown
    step_digest: str | None = None
    turns: int | None = None
    max_turns: int | None = None
    cost_usd: float | None = None  # a goal record's keys: None leaves the key out of the line
    progress_lines: int | None = None

    def __post_init__(self) -> None:
        keyed = _DRIVER_KEYS[1:] + _GOAL_KEYS
        if self.request is None and any(getattr(self, key) is not None for key in keyed):
            raise ShapeError(f"{', '.join(keyed)} need a request")


@dataclass(frozen=True)
class LedgerFinding:
    position: int  # 1-based, among non-blank lines: the record's append position
    reason: str


@dataclass(frozen=True)
class LedgerReading:
    records: tuple[IterationRecord, ...]
    findings: tuple[LedgerFinding, ...]

    @property
    def requests(self) -> frozenset[str]:
        return frozenset(item.request for item in self.records if item.request is not None)


def ledger_path(task_dir: Path) -> Path:
    return task_dir / LEDGER_FILE


# --- the one reader ---


def read_ledger(task_dir: Path) -> LedgerReading:
    """Every record in append order plus a finding per line that breaks the shape."""
    path = ledger_path(task_dir)
    if not path.is_file():
        return LedgerReading((), ())
    records: list[IterationRecord] = []
    findings: list[LedgerFinding] = []
    lines = (raw for raw in path.read_bytes().split(b"\n") if raw.strip())
    for position, raw in enumerate(lines, start=1):
        try:
            records.append(parse_record_line(raw.decode()))
        except UnicodeDecodeError:
            findings.append(LedgerFinding(position, "not valid UTF-8"))
        except ShapeError as error:
            findings.append(LedgerFinding(position, str(error)))
    return LedgerReading(tuple(records), tuple(findings))


def parse_record_line(text: str) -> IterationRecord:
    """The line parser: the one place every invariant is enforced. Raises ShapeError."""
    raw = _load_object(text)
    _require_version(raw)  # so the record's default `v` is the version read
    return IterationRecord(
        step=_step(raw),
        attempt=_attempt(raw),
        agent_id=_text(raw, "agent_id"),
        verdict=_verdict(raw),
        decided_by=_one_of(raw, "decided_by", DECIDED_BY),
        test_result=_test_result(raw),
        commit=_commit(raw),
        stop_reason=_one_of(raw, "stop_reason", STOP_REASONS),
        recorded_at=_recorded_at(raw),
        request=_optional_text(raw, "request", REQUEST_ID_RE),
        step_digest=_optional_text(raw, "step_digest", _DIGEST_RE),
        turns=_optional_count(raw, "turns", 0),
        max_turns=_optional_count(raw, "max_turns", 1),
        cost_usd=_optional_cost(raw, "cost_usd"),
        progress_lines=_optional_count(raw, "progress_lines", 0),
    )


def _load_object(text: str) -> dict[str, Any]:
    try:
        value = json.loads(text)
    except json.JSONDecodeError as error:
        raise ShapeError(f"not valid JSON: {error.msg}") from error
    if not isinstance(value, dict):
        raise ShapeError("not a JSON object")
    return value


def _field(raw: dict[str, Any], key: str) -> Any:
    if key not in raw:
        raise ShapeError(f"missing key {key!r}")
    return raw[key]


def _text(raw: dict[str, Any], key: str) -> str:
    value = _field(raw, key)
    if not isinstance(value, str) or not value.strip():
        raise ShapeError(f"{key} must be a non-empty string, got {value!r}")
    return value


def _one_of(raw: dict[str, Any], key: str, allowed: tuple[str, ...]) -> str:
    value = _text(raw, key)
    if value not in allowed:
        raise ShapeError(f"{key} must be one of {', '.join(allowed)}; got {value!r}")
    return value


def _require_version(raw: dict[str, Any]) -> None:
    version = _field(raw, "v")
    if type(version) is not int or version != SCHEMA_VERSION:
        raise ShapeError(f"unsupported ledger version {version!r}; reads {SCHEMA_VERSION}")


def _step(raw: dict[str, Any]) -> str:
    value = _text(raw, "step")
    if not (value.startswith(_STEP_LABEL) and STEP_ID_RE.fullmatch(value[len(_STEP_LABEL) :])):
        raise ShapeError(f"step must read 'Step <id>'; got {value!r}")
    return value


def _attempt(raw: dict[str, Any]) -> int:
    value = _field(raw, "attempt")
    if type(value) is not int or value < 1:
        raise ShapeError(f"attempt must be an integer of at least 1; got {value!r}")
    return value


def _verdict(raw: dict[str, Any]) -> str:
    value = _text(raw, "verdict")
    word, at, last_write = value.partition("@")
    known = bool(at and last_write) if word == "partial" else not at and word in VERDICT_WORDS
    if not known:
        raise ShapeError(f"verdict must be a verdict word or partial@<path>; got {value!r}")
    return value


def _test_result(raw: dict[str, Any]) -> str:
    value = _text(raw, "test_result")
    if not isinstance(parse_result_line(value), (Counts, NoRun)):
        raise ShapeError(f"test_result must be a Result: count or no-run line; got {value!r}")
    return value


def _commit(raw: dict[str, Any]) -> str | None:
    value = _field(raw, "commit")
    if value is not None and not (isinstance(value, str) and _COMMIT_RE.fullmatch(value)):
        raise ShapeError(f"commit must be 7 to 40 lowercase hex characters or null; got {value!r}")
    return value


def _optional_text(raw: dict[str, Any], key: str, pattern: re.Pattern[str]) -> str | None:
    value = raw.get(key)
    if value is not None and not (isinstance(value, str) and pattern.fullmatch(value)):
        raise ShapeError(f"{key} must match {pattern.pattern} or be null; got {value!r}")
    return value


def _optional_count(raw: dict[str, Any], key: str, least: int) -> int | None:
    value = raw.get(key)
    if value is not None and (type(value) is not int or value < least):
        raise ShapeError(f"{key} must be an integer of at least {least} or null; got {value!r}")
    return value


def _optional_cost(raw: dict[str, Any], key: str) -> float | None:
    value = raw.get(key)
    if value is None:
        return None
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ShapeError(f"{key} must be a number of at least 0; got {value!r}")
    return float(value)


def _recorded_at(raw: dict[str, Any]) -> str:
    value = _text(raw, "recorded_at")
    try:
        # strptime alone accepts unpadded fields; the round trip demands the exact form.
        if datetime.strptime(value, _STAMP_FORMAT).strftime(_STAMP_FORMAT) == value:
            return value
    except ValueError:
        pass
    raise ShapeError(f"recorded_at must be YYYY-MM-DDTHH:MMZ (UTC); got {value!r}")


# --- the one writer ---


def append_record(task_dir: Path, record: IterationRecord) -> None:
    """Stamp ``record``, prove its line reads back, then append it as one write.

    Raises ShapeError before the file is touched, so the ledger never holds a
    line its own reader would reject.
    """
    line = render_record_line(replace(record, recorded_at=_utc_minute()))
    parse_record_line(line)
    with ledger_path(task_dir).open("ab") as ledger:
        ledger.write((line + "\n").encode())


def render_record_line(record: IterationRecord) -> str:
    body = {
        "v": record.v,
        "recorded_at": record.recorded_at,
        "step": record.step,
        "attempt": record.attempt,
        "agent_id": record.agent_id,
        "verdict": record.verdict,
        "decided_by": record.decided_by,
        "test_result": record.test_result,
        "commit": record.commit,
        "stop_reason": record.stop_reason,
    }
    if record.request is not None:  # a driver record states all four, null where unknown
        body.update({key: getattr(record, key) for key in _DRIVER_KEYS})
    body.update({k: getattr(record, k) for k in _GOAL_KEYS if getattr(record, k) is not None})
    return json.dumps(body)


def _utc_minute() -> str:
    return datetime.now(timezone.utc).strftime(_STAMP_FORMAT)


# --- command line ---


class InputError(ValueError):
    """The command line names something that cannot be recorded or read."""


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        repo_root, state_root = _resolve_roots(args)
        task_dir = state_root / ".ai-work" / args.slug
        if not task_dir.is_dir():
            raise InputError(f"no task directory {task_dir}")
        if args.command == "append":
            return _run_append(args, repo_root, state_root, task_dir)
        return _run_read(args, task_dir)
    except ValueError as error:  # InputError and ShapeError
        sys.stderr.write(f"iteration_ledger: {error}\n")
        return EXIT_INPUT_ERROR


def _run_append(args: argparse.Namespace, repo_root: Path, state_root: Path, task_dir: Path) -> int:
    # Imported here, not at module level: the reconciler reaches into `hooks/`, and
    # the library half (reader, writer) must stay importable from `scripts/` alone.
    from reconcile_pipeline_state import reconcile

    verdicts = reconcile(args.slug, repo_root, args.base_ref, state_root=state_root)
    results_path = task_dir / "TEST_RESULTS.md"
    results_text = results_path.read_text(encoding="utf-8") if results_path.is_file() else ""
    item = record_from_ground_truth(
        args.step,
        verdicts,
        results_text,
        attempt=args.attempt,
        agent_id=args.agent_id,
        commit=None if args.no_commit else args.commit,
        stop_reason=args.stop_reason,
    )
    append_record(task_dir, item)
    print(f"appended {item.step} attempt {item.attempt}: {item.verdict} ({item.decided_by})")
    return EXIT_CLEAN


def record_from_ground_truth(
    step_id: str,
    verdicts: list[dict[str, Any]],
    results_text: str,
    *,
    attempt: int,
    agent_id: str,
    commit: str | None,
    stop_reason: str,
) -> IterationRecord:
    """The record for one return: verdict and test result come from the evidence, not the caller."""
    label = f"{_STEP_LABEL}{step_id}"
    own = next((verdict for verdict in verdicts if verdict["step"] == label), None)
    if own is None:
        raise InputError(f"{label} is not a step of this task's WIP.md")
    return IterationRecord(
        step=label,
        attempt=attempt,
        agent_id=agent_id,
        verdict=own["verdict"],
        decided_by=own["decided_by"],
        test_result=latest_result_line(label, results_text),
        commit=commit,
        stop_reason=stop_reason,
    )


def latest_result_line(step_label: str, results_text: str) -> str:
    """The step's own latest ``Result:`` line across its blocks, as written."""
    latest = latest_result(step_label, results_text)
    return NO_RESULT_RECORDED if latest is None else latest[1]


def _run_read(args: argparse.Namespace, task_dir: Path) -> int:
    reading = read_ledger(task_dir)
    if args.json:
        records = [json.loads(render_record_line(item)) for item in reading.records]
        print(json.dumps({"records": records, "findings": [asdict(f) for f in reading.findings]}))
    else:
        print(_render_reading(reading))
    return EXIT_FINDINGS if reading.findings else EXIT_CLEAN


def _render_reading(reading: LedgerReading) -> str:
    lines = [
        f"{r.recorded_at}  {r.step}  attempt {r.attempt}  {r.verdict}  {r.decided_by}  "
        f"{r.stop_reason}  commit={r.commit or 'none'}  agent={r.agent_id}"
        for r in reading.records
    ]
    lines += [f"FINDING at record {f.position}: {f.reason}" for f in reading.findings]
    return "\n".join(lines) or "no iteration records"


def _resolve_roots(args: argparse.Namespace) -> tuple[Path, Path]:
    """The repository (``--repo-root``, else git; never this file's location) and the state root."""
    repo_root = Path(args.repo_root).resolve() if args.repo_root else git_toplevel_from_cwd()
    if repo_root is None:
        raise InputError("not inside a git repository; pass --repo-root")
    if is_plugin_cache_path(repo_root):
        raise InputError("refusing to run against a plugin-cache path; pass --repo-root")
    state_root = Path(args.worktree_root).resolve() if args.worktree_root else repo_root
    return repo_root, state_root


def _build_parser() -> argparse.ArgumentParser:
    roots = argparse.ArgumentParser(add_help=False)
    roots.add_argument("slug", help="task slug under .ai-work/<slug>/")
    roots.add_argument("--repo-root", default=None, help="git repo root (default: from git)")
    roots.add_argument("--worktree-root", default=None, help="root holding .ai-work/")
    parser = argparse.ArgumentParser(description="Append to and read a task's iteration ledger.")
    commands = parser.add_subparsers(dest="command", required=True)
    append = commands.add_parser("append", parents=[roots], help="record one implementer return")
    append.add_argument("--step", required=True, help="step id, e.g. 3 or 12b")
    append.add_argument("--attempt", required=True, type=int, help="attempt number, 1 or more")
    append.add_argument("--agent-id", required=True, help="the returning agent's id")
    append.add_argument("--stop-reason", required=True, choices=STOP_REASONS)
    holding = append.add_mutually_exclusive_group(required=True)
    holding.add_argument("--commit", help="sha of the commit holding the step's work")
    holding.add_argument("--no-commit", action="store_true", help="no commit holds the work")
    append.add_argument("--base-ref", default=None, help="git ref the reconciler diffs against")
    read = commands.add_parser("read", parents=[roots], help="print the records and findings")
    read.add_argument("--json", action="store_true", help="emit one JSON object on stdout")
    return parser


if __name__ == "__main__":
    sys.exit(main())
