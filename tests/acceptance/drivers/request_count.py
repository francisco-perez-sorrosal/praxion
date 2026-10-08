"""Driver that hands one agent transcript to every reader that counts its requests.

A scenario asks the loop for an implementer, lets the Agent tool's double do the step's
work (the `step_loop` driver), then reshapes the agent's own transcript into a corpus
variant and reads its distinct-request count three ways:

- the turn-budget reminder, run as the harness runs a PreToolUse hook for a tool call
  that agent makes (the `turn_budget_reminder` driver); its line states the turns used;
- the loop's `record`, whose envelope carries the turns it derived;
- the context instrument's cap-out count (`context_baseline.py --json`, `cap_outs`).

Each reading is a count, or `None` when the reader declines to count. The first two are
bound. The instrument is not: the transcript layout and session shape it reads are not a
stated surface, so `instrument_reading` raises until a binding step places the corpus
where the instrument reads transcripts.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from tests.acceptance.drivers import step_loop as loop
from tests.acceptance.drivers import turn_budget_reminder as reminder

CUT_OFF_LINE = '{"type": "assistant", "requestId": "req_cut_off_mid_fl'
MALFORMED_LINE = "this line is not JSON at all"


def _clean(lines: list[str]) -> list[str]:
    return lines


def _every_line_twice(lines: list[str]) -> list[str]:
    """Every entry between the opening prompt and the final answer written twice."""
    return [lines[0], *[line for line in lines[1:-1] for _ in range(2)], lines[-1]]


def _an_earlier_request_again(lines: list[str]) -> list[str]:
    """The first request's entries appear once more just before the final answer."""
    return [*lines[:-1], *lines[1:3], lines[-1]]


def _a_cut_off_line(lines: list[str]) -> list[str]:
    return [*lines[:-1], CUT_OFF_LINE, lines[-1]]


def _a_malformed_line(lines: list[str]) -> list[str]:
    middle = len(lines) // 2
    return [*lines[:middle], MALFORMED_LINE, *lines[middle:]]


READABLE_VARIANTS: dict[str, Callable[[list[str]], list[str]]] = {
    "clean": _clean,
    "every-line-twice": _every_line_twice,
    "an-earlier-request-again": _an_earlier_request_again,
}
DAMAGED_VARIANTS: dict[str, Callable[[list[str]], list[str]]] = {
    "a-cut-off-line": _a_cut_off_line,
    "a-malformed-line": _a_malformed_line,
}
VARIANTS = {**READABLE_VARIANTS, **DAMAGED_VARIANTS}


def implementer_cap() -> int:
    return loop.implementer_max_turns()


def corpus_agent(task: loop.LoopTask, variant: str, requests: int) -> tuple[dict[str, Any], str]:
    """The loop's implement request and the id of an agent that did the step's work and
    left a transcript of `requests` distinct requests, reshaped as `variant`."""
    request = loop.next_action(task).request
    assert request is not None, "the loop asked for no implementer"
    agent_id = loop.work_on(task, request, loop.Work(requests=requests))
    transcript = loop.agent_transcript_path(task, agent_id)
    lines = transcript.read_text(encoding="utf-8").splitlines()
    transcript.write_text("\n".join(VARIANTS[variant](lines)) + "\n", encoding="utf-8")
    return request, agent_id


def _session_of(task: loop.LoopTask) -> reminder.Session:
    """The sandbox session the loop's transcripts live under, as the hook payload names it."""
    project_dir = loop.agent_transcript_path(task, "probe").parents[2]
    session = reminder.Session(project_dir, loop.SANDBOX_SESSION, task.root)
    session.transcript_path.touch(exist_ok=True)
    return session


def reminder_reading(task: loop.LoopTask, agent_id: str) -> int | None:
    """The turns the reminder says the agent has used; `None` when it says nothing."""
    session = _session_of(task)
    run = reminder.run_reminder(
        reminder.subagent_payload(session, agent_id, reminder.IMPLEMENTER_AGENT_TYPE),
        cwd=task.root,
    )
    if run.exit_code != 0:
        raise AssertionError(
            f"the reminder exited {run.exit_code}, never 0 as a hook must:\n{run.stderr}"
        )
    lines = run.reminders()
    return reminder.parse_line(lines[0])[0] if lines else None


def loop_reading(task: loop.LoopTask, request: dict[str, Any], agent_id: str) -> int | None:
    """The turns the loop's `record` derived for the agent; `None` when it could not."""
    recorded = loop.record(task, request["id"], agent_id=agent_id, marker="complete").recorded
    return (recorded or {}).get("turns")


def instrument_reading(task: loop.LoopTask, agent_id: str) -> str | None:
    """`capped` or `not-capped` as the context instrument judges this implementer spawn
    against its cap, or `None` when it leaves the spawn out of every aggregate."""
    raise NotImplementedError(
        "unbound: the context instrument reads an implementer's own transcript from a "
        "session layout no stated surface describes; bind where it finds a project's "
        "sessions and how it tells an implementer spawn, then read "
        "cap_outs.implementer.capped for this one spawn"
    )


def as_cap_judgement(count: int | None, cap: int) -> str | None:
    if count is None:
        return None
    return "capped" if count >= cap else "not-capped"


def workspace(tmp_path: Path) -> Path:
    return tmp_path / "loop"
