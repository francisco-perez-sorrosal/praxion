"""What reached a main session, when, and what it left, per governed check: the trigger record.

Read from the events ``session_record`` returns, never from the raw record. For each governed
check, every channel the move declares is judged on whether it carried the check's governing text
(the check's phrases, or its section title when it declares none), and when, against the first
governed action of the move:

- before composition: ahead of the call that performed the action;
- before execution: after the call was composed and before its result (a hook's context, or a
  gate's refusal);
- after execution: after the result (a path-matched load a creating write triggered);
- never: the channel delivered nothing carrying the text;
- unknown: the record cannot say (``Unreadable``, or a channel no record witnesses), which is
  never the same as never.

A governed action is a tool call the move's deliveries fire on: a call by the tool a hook or gate
declares (a shell call only when it stages or commits, as the lean hook itself decides), or a
creating ``Write`` matching a path-matched delivery's globs. Every check of the move reads the
same actions, because the declaration names no action per check.

History is what the session did with them. A violating action is one a gate refused, or one the
session itself later rewrote (an amend, or a second write of the same file); the content of a
message is the end-state grader's to judge, not this reader's. ``final`` is the record's own
reading of the last governed action (ran: passed, refused: failed) and is meant to be replaced by
the graded end state; a trigger failure is derived from the two, never stored.

``triggers`` is pure; ``records`` is the same answer in the results file's words.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path
from typing import assert_never, get_args

from praxion_evals.adherence.model import Failed, Passed
from praxion_evals.adherence.moves import session_record
from praxion_evals.adherence.moves.model import (
    Arrival,
    ArrivalTiming,
    Arrived,
    Channel,
    CheckTrigger,
    GateRefusal,
    GovernedCheck,
    History,
    HookContext,
    MoveDeclaration,
    NeverArrived,
    PathMatched,
    Unknown,
)
from praxion_evals.adherence.moves.session_record import (
    Delivery,
    Event,
    Parsed,
    SessionEvents,
    ToolResult,
    ToolUse,
    Unreadable,
)

CREATING_WRITE = "Write"

# The commands the lean hook fires for, and the rewrite that repairs a commit.
_SEGMENT_BREAK = re.compile(r"&&|\|\||[;|\n]")
_STAGING_OR_COMMITTING = re.compile(
    r"(?:\S+=\S*\s+)*git\s+(?:-[Cc]\s+\S+\s+)*(?:add|stage|commit)\b"
)
_AMEND = re.compile(r"git\s+(?:\S+\s+)*commit\b.*--amend\b")
# How the harness words a hook's refusal in the tool result it stands in for.
_GATE_REFUSAL = re.compile(
    r"PreToolUse:\S+ hook error: \[[^\]]*\]:?\s*(?P<reason>.*?)\s*(?:\nThis hook comes from [^\n]*)?\Z",
    re.DOTALL,
)


def arrival_of(event: Event) -> tuple[Channel, str] | None:
    """The channel an event's text reached the session by, with the text; None for an event that
    delivers none. A gate's refusal is a tool result, not a delivery, and is the one result that
    does; its text is the reason the gate gave."""
    match event:
        case Delivery():
            return _channel_of(event), event.text
        case ToolResult() if (reason := _refusal(event)) is not None:
            return "gate_refusal", reason
        case _:
            return None


def _channel_of(delivery: Delivery) -> Channel:
    if delivery.at_session_start:
        return "session_start"
    if delivery.origin == session_record.NESTED_MEMORY:
        return "path_matched"
    return "hook_context"


@dataclass(frozen=True)
class TriggerRecord:
    """A ``CheckTrigger`` in the words of the results file: plain strings, nothing derived."""

    check: str
    arrivals: dict[str, str]  # channel -> timing word, "never" or "unknown"
    final: str | None  # "passed" or "failed"
    history: str | None
    refusals: tuple[str, ...]


def records(declaration: MoveDeclaration, record_path: Path) -> tuple[TriggerRecord, ...]:
    """The trigger record of every governed check over the session recorded at ``record_path``."""
    return tuple(_wire(t) for t in triggers(declaration, session_record.parse(record_path)))


def triggers(declaration: MoveDeclaration, events: SessionEvents) -> tuple[CheckTrigger, ...]:
    """One trigger record per governed check of ``declaration``."""
    checks = declaration.checks.checks
    match events:
        case Unreadable():
            channels = _channels(declaration) or get_args(Channel)
            return tuple(CheckTrigger.unreadable(check.name, channels) for check in checks)
        case Parsed():
            actions = _actions(declaration, events.events)
            return tuple(_trigger(check, declaration, events.events, actions) for check in checks)
        case _:
            assert_never(events)


# -- Governed actions -------------------------------------------------------------------------


@dataclass(frozen=True)
class _Action:
    used_at: int  # where the call was composed
    result_at: int | None  # where its result came back; None for a call the record never answers
    command: str | None
    file_path: str | None
    refusal: str | None  # the gate's reason; None for a call that ran

    @property
    def ran(self) -> bool:
        return self.refusal is None

    def amended_by(self, later: _Action) -> bool:
        if later.command is not None:
            return bool(_AMEND.search(later.command))
        return later.file_path is not None and later.file_path == self.file_path


def _actions(declaration: MoveDeclaration, events: Sequence[Event]) -> tuple[_Action, ...]:
    results = {
        event.tool_use_id: (at, event)
        for at, event in reversed(list(enumerate(events)))
        if isinstance(event, ToolResult)
    }  # reversed, so a call answered twice keeps its first answer
    actions = []
    for at, event in enumerate(events):
        if isinstance(event, ToolUse) and _is_governed(declaration, event):
            result_at, result = results.get(event.id, (None, None))
            actions.append(_Action(at, result_at, event.command, event.file_path, _refusal(result)))
    return tuple(actions)


def _is_governed(declaration: MoveDeclaration, use: ToolUse) -> bool:
    for delivery in declaration.deliveries:
        match delivery:
            case HookContext(matcher=matcher) | GateRefusal(matcher=matcher):
                if re.fullmatch(matcher, use.name) and _is_staging_if_shell(use):
                    return True
            case PathMatched(globs=globs):
                if use.name == CREATING_WRITE and _matches_any(use.file_path, globs):
                    return True
            case _:
                continue
    return False


def _is_staging_if_shell(use: ToolUse) -> bool:
    if use.command is None:
        return True
    segments = (segment.strip() for segment in _SEGMENT_BREAK.split(use.command))
    return any(_STAGING_OR_COMMITTING.match(segment) for segment in segments)


def _matches_any(file_path: str | None, globs: Sequence[str]) -> bool:
    return file_path is not None and any(
        fnmatch(file_path, pattern) for glob in globs for pattern in (glob, f"*/{glob}")
    )


def _refusal(result: ToolResult | None) -> str | None:
    found = _GATE_REFUSAL.match(result.text.strip()) if result else None
    if found is None:
        return None
    return found["reason"].strip() or found[0]


# -- One governed check -----------------------------------------------------------------------


def _trigger(
    check: GovernedCheck,
    declaration: MoveDeclaration,
    events: Sequence[Event],
    actions: Sequence[_Action],
) -> CheckTrigger:
    arrivals: dict[Channel, Arrival] = {
        channel: _arrival(channel, check, events, actions) for channel in _channels(declaration)
    }
    answered = [a for a in actions if a.result_at is not None]  # a call cut off says nothing
    return CheckTrigger(
        check.name,
        arrivals,
        _final(answered),
        _history(answered),
        tuple(a.refusal for a in answered if a.refusal is not None),
    )


def _channels(declaration: MoveDeclaration) -> tuple[Channel, ...]:
    return tuple(dict.fromkeys(delivery.channel for delivery in declaration.deliveries))


def _arrival(
    channel: Channel, check: GovernedCheck, events: Sequence[Event], actions: Sequence[_Action]
) -> Arrival:
    if channel == "project_gating":
        return Unknown()  # delivered by the project's state, which no session record witnesses
    carrying = [at for at, event in enumerate(events) if _carries(channel, event, check)]
    return Arrived(_timing(carrying[0], actions)) if carrying else NeverArrived()


def _carries(channel: Channel, event: Event, check: GovernedCheck) -> bool:
    arrival = arrival_of(event)
    return (
        arrival is not None and arrival[0] == channel and _holds_governing_text(arrival[1], check)
    )


def _holds_governing_text(text: str, check: GovernedCheck) -> bool:
    lowered = text.lower()
    return all(phrase.lower() in lowered for phrase in check.phrases or (check.section,))


def _timing(arrived_at: int, actions: Sequence[_Action]) -> ArrivalTiming:
    if not actions or arrived_at < actions[0].used_at:
        return "before composition"
    first = actions[0]
    if first.result_at is None or arrived_at <= first.result_at:
        return "before execution"
    return "after execution"


# -- What the session left --------------------------------------------------------------------


def _final(actions: Sequence[_Action]) -> Passed | Failed | None:
    if not actions:
        return None
    last = actions[-1]
    if last.refusal is not None:
        return Failed(f"the last governed action was refused by a gate: {last.refusal}")
    return Passed()


def _history(actions: Sequence[_Action]) -> History:
    if not actions:
        return "never_taken"
    if not actions[-1].ran:
        return "not_repaired"
    ran = [a for a in actions if a.ran]
    if any(earlier.amended_by(later) for i, later in enumerate(ran) for earlier in ran[:i]):
        return "repaired"
    return "right_first_time"


# -- The results file's words -----------------------------------------------------------------


def _wire(trigger: CheckTrigger) -> TriggerRecord:
    return TriggerRecord(
        trigger.check,
        {channel: _timing_word(arrival) for channel, arrival in trigger.arrivals.items()},
        _outcome_word(trigger.final),
        trigger.history,
        trigger.refusals,
    )


def _timing_word(arrival: Arrival) -> str:
    match arrival:
        case Arrived(timing=timing):
            return timing
        case NeverArrived():
            return "never"
        case Unknown():
            return "unknown"
        case _:
            assert_never(arrival)


def _outcome_word(final: Passed | Failed | None) -> str | None:
    match final:
        case None:
            return None
        case Passed():
            return "passed"
        case Failed():
            return "failed"
        case _:
            assert_never(final)
