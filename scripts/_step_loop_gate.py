"""The pure gate of the step-loop driver: what a test run showed, who owns its failures
and how an agent's attempt ended.

Pure: pytest output text, plan fields and transcript facts in; counts, `Result:` lines and
stop reasons out.

Normative reading of pytest output -- the short summary printed by the default `-rfE`:

    FAILED <node id> - <reason>
    ERROR <node id> - <reason>
    ===== 2 failed, 5 passed, 1 skipped, 1 error in 0.34s =====

The last line holding a duration (`in 0.34s`) and a count (or `no tests ran`) is the count
line; `-q` drops the `=` rules and reads the same. Output with no such line is no run:
`NoRun`, never a guessed pass. A node line names its id up to the first ` - ` outside square
brackets. Node lines never count as the count line. A failure the count line reports but
no node line names stays a failure, and a named failure is never discounted: counts fall to
the named non-pending nodes at the least.

A run's verdict is `GateRun.red`, not a `Check:` alone: the check grammar has no `error`
key, so a run red only by errors still meets `pass>=2 fail=0`; the caller must AND the two.
`classify_run` reads one run's whole output: a derived scope of several invocations is
merged into one run by the caller, never concatenated raw.

Normative ownership of a failed node -- a `Read-only:` entry owns every node it is a
prefix of, at a path, `::` or `[` boundary (`a.py::f` owns `a.py::f[x]` but not
`a.py::fg`). The longest owning entry decides. A node counts as pending only when every
entry tied for longest belongs to another step that is not done; any other failure is
a failure, so a tie with the step's own entry stays a failure.

Normative reading of an agent's final text -- its last non-blank line carries one
terminal marker (`[COMPLETE]`, `[BLOCKED]`, `[CONFLICT]` or `[PARTIAL]`) at its start or
its end, past any `*`, `_` or backtick emphasis. Two different markers there, or a marker
elsewhere in the text, read as no marker.

`Ownership.step`, `done_steps` and the map keys share one id form; `step` must be a key of
the map (a step with no entries maps to `()`).
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Literal, Union

from _step_schema import RED, Counts, NoRun

BY_STEP_LOOP = "by=step-loop"
NO_SUMMARY_RATIONALE = "the output holds no pytest summary line"

Marker = Literal["complete", "blocked", "conflict", "partial", "none"]
StopReason = Literal["completed", "turn-cap", "blocked", "conflict", "partial", "no-marker"]
EndSource = Literal["marker", "turn-cap", "final-text", "agent-stop"]
Nodes = tuple[str, ...]
RunCounts = Union[Counts, NoRun]  # noqa: UP007 -- runtime value, 3.9 floor

_SUMMARY_DURATION_RE = re.compile(r"\bin \d+(?:\.\d+)?s\b")
_COUNT_RE = re.compile(r"\b(\d+) (passed|failed|skipped|errors?)\b")
_NO_TESTS_RE = re.compile(r"\bno tests ran\b")
_NODE_LINE_RE = re.compile(r"^(?P<kind>FAILED|ERROR) (?P<rest>\S.*)$")
_REASON_SEPARATOR = " - "
_NODE_BOUNDARIES = ("::", "[")
_PATH_BOUNDARY = "/"

_MARKERS: Mapping[str, Marker] = {
    "[COMPLETE]": "complete",
    "[BLOCKED]": "blocked",
    "[CONFLICT]": "conflict",
    "[PARTIAL]": "partial",
}
_MARKER_RE = re.compile("|".join(re.escape(token) for token in _MARKERS))
_EMPHASIS = "*_` \t"
_STOP_BY_MARKER: Mapping[str, StopReason] = {
    "blocked": "blocked",
    "conflict": "conflict",
    "partial": "partial",
    "complete": "completed",
}


# --- Reading a pytest run ---


@dataclass(frozen=True)
class PytestSummary:
    """The count line and the node ids the short summary named, each id once."""

    counts: Counts
    failed_ids: tuple[str, ...]
    error_ids: tuple[str, ...]


def parse_pytest_summary(output: str) -> PytestSummary | None:
    """The run `output` shows, or None when it holds no count line (no run)."""
    lines = output.splitlines()
    counts = _read_count_line(lines)
    if counts is None:
        return None
    return PytestSummary(counts, _node_ids(lines, "FAILED"), _node_ids(lines, "ERROR"))


def _read_count_line(lines: list[str]) -> Counts | None:
    for line in reversed(lines):
        if _NODE_LINE_RE.match(line) or not _SUMMARY_DURATION_RE.search(line):
            continue
        tallies: dict[str, int] = {}
        for number, word in _COUNT_RE.findall(line):
            key = "errors" if word.startswith("error") else word
            tallies[key] = int(number)
        if tallies or _NO_TESTS_RE.search(line):
            return Counts(
                passed=tallies.get("passed", 0),
                failed=tallies.get("failed", 0),
                skipped=tallies.get("skipped", 0),
                errors=tallies.get("errors", 0),
            )
    return None


def _node_ids(lines: list[str], kind: str) -> tuple[str, ...]:
    named = (_NODE_LINE_RE.match(line) for line in lines)
    ids = (_cut_reason(match["rest"]) for match in named if match and match["kind"] == kind)
    return tuple(dict.fromkeys(ids))


def _cut_reason(rest: str) -> str:
    """The node id at the start of `rest`: cut at the first ` - ` outside square brackets."""
    depth = 0
    for index, char in enumerate(rest):
        if char == "[":
            depth += 1
        elif char == "]":
            depth = max(depth - 1, 0)
        elif depth == 0 and rest.startswith(_REASON_SEPARATOR, index):
            return rest[:index]
    return rest


# --- Who owns a failed node ---


def entry_owns(entry: str, node_id: str) -> bool:
    """Whether `entry` is a prefix of `node_id` at a path, `::` or `[` boundary (`/` only
    for a bare path entry: inside a node id a slash can only follow `[`)."""
    if not node_id.startswith(entry):
        return False
    rest = node_id[len(entry) :]
    boundaries = _NODE_BOUNDARIES if "::" in entry else (_PATH_BOUNDARY, *_NODE_BOUNDARIES)
    return rest == "" or entry.endswith(_PATH_BOUNDARY) or rest.startswith(boundaries)


@dataclass(frozen=True)
class Ownership:
    """Which step holds each outer-loop test: `step` is the one being gated,
    `read_only_by_step` maps every plan step to its `Read-only:` entries, and
    `done_steps` are the steps already complete."""

    step: str
    read_only_by_step: Mapping[str, tuple[str, ...]]
    done_steps: frozenset[str]

    def __post_init__(self) -> None:
        if self.step not in self.read_only_by_step:
            raise ValueError(f"step {self.step!r} is not a key of the Read-only map")

    def is_pending(self, node_id: str) -> bool:
        """True when only other steps that are not done own `node_id` (longest entry wins)."""
        claims = [
            (len(entry), owner)
            for owner, entries in self.read_only_by_step.items()
            for entry in entries
            if entry_owns(entry, node_id)
        ]
        if not claims:
            return False
        longest = max(length for length, _ in claims)
        owners = {owner for length, owner in claims if length == longest}
        return all(owner != self.step and owner not in self.done_steps for owner in owners)


# --- One run, classified; its Result: line; the order of two ---


@dataclass(frozen=True)
class GateRun:
    """A test run the driver executed itself: the command and what it showed.

    `counts` hold only the failures that belong to the step; those a later step owns are
    `pending_ids`, the rest `failed_ids`. A run that showed no summary has no ids."""

    command: str
    counts: RunCounts
    failed_ids: tuple[str, ...] = ()
    pending_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if isinstance(self.counts, NoRun) and (self.failed_ids or self.pending_ids):
            raise ValueError("a run that showed no summary cannot name failed nodes")

    @property
    def pending(self) -> int:
        return len(self.pending_ids)

    @property
    def red(self) -> bool:
        """No run is not green: only counts with a pass and no failure or error are."""
        return isinstance(self.counts, NoRun) or self.counts.status == RED


def classify_run(command: str, output: str, ownership: Ownership) -> GateRun:
    """Read `output` into a `GateRun`, moving later steps' failures from fail to pending."""
    summary = parse_pytest_summary(output)
    if summary is None:
        return GateRun(command, NoRun(NO_SUMMARY_RATIONALE))
    failed, pending_failed = _split_pending(summary.failed_ids, ownership)
    errored, pending_errored = _split_pending(summary.error_ids, ownership)
    counts = replace(
        summary.counts,
        failed=max(summary.counts.failed - len(pending_failed), len(failed)),
        errors=max(summary.counts.errors - len(pending_errored), len(errored)),
    )
    pending = tuple(dict.fromkeys(pending_failed + pending_errored))
    return GateRun(command, counts, failed + errored, pending)


def _split_pending(ids: Nodes, ownership: Ownership) -> tuple[Nodes, Nodes]:
    pending = tuple(node for node in ids if ownership.is_pending(node))
    return tuple(node for node in ids if node not in pending), pending


def render_result_line(run: GateRun) -> str:
    """The `Result:` line the reconciler reads; a run with counts says it is the driver's."""
    counts = run.counts
    if isinstance(counts, NoRun):
        return f"Result: none — {' '.join(counts.rationale.split())}"
    tokens = [f"pass={counts.passed}", f"fail={counts.failed}", f"skip={counts.skipped}"]
    if counts.errors:
        tokens.append(f"error={counts.errors}")
    return " ".join(["Result:", *tokens, f"pending={run.pending}", BY_STEP_LOOP])


def gate_result_lines(scope: GateRun | None, check: GateRun) -> tuple[str, ...]:
    """The `Result:` lines of the derived-scope run and the `Check:` run, deciding line last.

    The reconciler judges a step by its latest line, so the line that decides goes last:
    the red one if either run is red (the check's own when both are), otherwise the
    check's. A step with no derived scope has only the check's line.
    """
    scope_decides = scope is not None and scope.red and not check.red
    runs = (check, scope) if scope_decides else (scope, check)
    return tuple(render_result_line(run) for run in runs if run is not None)


# --- How an attempt ended ---


def parse_marker(final_text: str | None) -> Marker:
    """The terminal marker on the last non-blank line of `final_text`, or `none`."""
    lines = [line.strip(_EMPHASIS) for line in (final_text or "").splitlines() if line.strip()]
    if not lines:
        return "none"
    last = lines[-1]
    anchored = {
        _MARKERS[match[0]]
        for match in _MARKER_RE.finditer(last)
        if match.start() == 0 or match.end() == len(last)
    }
    return next(iter(anchored)) if len(anchored) == 1 else "none"


def reached_turn_cap(requests: int | None, max_turns: int | None) -> bool:
    """The agent made at least as many API requests as its declared cap (unknown: no)."""
    return requests is not None and max_turns is not None and 0 < max_turns <= requests


@dataclass(frozen=True)
class EndEvidence:
    """What the driver can see of an agent's end: the text of its last well-formed request
    when that is text only (None while it calls a tool, or unreadable), its distinct API
    requests (None when unreadable) and whether the log holds an `agent_stop` row for it."""

    final_text: str | None
    requests: int | None
    max_turns: int | None
    agent_stopped: bool = False


def end_source(evidence: EndEvidence) -> EndSource | None:
    """Which evidence shows the agent has ended, or None while it may still be editing.

    A last request of text only ends an agent, with a marker or without one: an agent that
    calls no tool has stopped.
    """
    if parse_marker(evidence.final_text) != "none":
        return "marker"
    if reached_turn_cap(evidence.requests, evidence.max_turns):
        return "turn-cap"
    if evidence.final_text is not None:
        return "final-text"
    return "agent-stop" if evidence.agent_stopped else None


def derive_stop_reason(marker: Marker, requests: int | None, max_turns: int | None) -> StopReason:
    """Why an ended attempt stopped: its marker first, then the cap, else no marker."""
    if marker != "none":
        return _STOP_BY_MARKER[marker]
    return "turn-cap" if reached_turn_cap(requests, max_turns) else "no-marker"


@dataclass(frozen=True)
class MarkerReading:
    """The marker that counts, and whether the orchestrator's relay contradicted it."""

    marker: Marker
    disagrees: bool


def resolve_marker(transcript: Marker | None, relayed: Marker) -> MarkerReading:
    """The transcript's marker wins over the relayed one; None means it was unreadable."""
    if transcript is None:
        return MarkerReading(relayed, False)
    return MarkerReading(transcript, transcript != relayed)
