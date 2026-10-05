"""Driver for whole step-loop journeys: the orchestrator's relay, with a substitute for the Agent tool.

The step-loop command and the double that stands in for a spawned implementer are
reached through the acceptance driver (`tests/acceptance/drivers/step_loop.py`), which
owns their bindings; this module adds only the relay loop the orchestrator runs --
`next`, execute the request, `record`, and again -- until the loop stops asking.
"""

from __future__ import annotations

from dataclasses import dataclass

from tests.acceptance.drivers.step_loop import (
    Envelope,
    LoopTask,
    Work,
    next_action,
    record,
    work_on,
)

_RELAY_LIMIT = 30  # far above any plan in these journeys; a loop past it never stops by itself


@dataclass(frozen=True)
class Journey:
    final: Envelope  # the first `next` that asked for no spawn
    returns: tuple[Envelope, ...]  # every `record` envelope, in order


def relay_until_stopped(task: LoopTask, work_by_step: dict[str, list[Work]]) -> Journey:
    """Relay as the orchestrator does; each spawn for a step takes that step's next `Work`."""
    queues = {step: list(works) for step, works in work_by_step.items()}
    returns: list[Envelope] = []
    for _ in range(_RELAY_LIMIT):
        asked = next_action(task)
        if asked.outcome != "spawn":
            return Journey(final=asked, returns=tuple(returns))
        request = asked.request
        queue = queues.get(str(request["step"]), [])
        work = queue.pop(0) if queue else Work()
        agent_id = work_on(task, request, work)
        returns.append(record(task, request["id"], agent_id=agent_id, marker=work.final_marker))
    raise AssertionError(f"the loop was still asking for spawns after {_RELAY_LIMIT} relays")
