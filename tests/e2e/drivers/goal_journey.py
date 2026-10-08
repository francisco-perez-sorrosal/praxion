"""Driver for whole goal journeys: the relay form of a goal loop, until it stops asking.

The step-loop command, the goal scaffold, the iteration double and the substitute headless
worker are reached through the acceptance drivers (`tests/acceptance/drivers/goal_loop.py`
and `tests/acceptance/drivers/headless_worker.py`), which own their bindings; this module
adds only the relay loop the in-session form runs -- `next`, the iteration, `record`, and
again -- until the loop stops asking for a spawn.
"""

from __future__ import annotations

from dataclasses import dataclass

from tests.acceptance.drivers.goal_loop import Iteration, Relayed, iterate_by_relay
from tests.acceptance.drivers.step_loop import Envelope, LoopTask, next_action

_RELAY_LIMIT = 20  # far above any goal budget in these journeys


@dataclass(frozen=True)
class GoalJourney:
    final: Envelope  # the first `next` that asked for no spawn
    iterations: tuple[Relayed, ...]


def relay_goal_until_stopped(task: LoopTask, script: list[Iteration]) -> GoalJourney:
    """Relay as `/praxion:step-loop` does; each spawn takes the script's next iteration."""
    queue = list(script)
    done: list[Relayed] = []
    for _ in range(_RELAY_LIMIT):
        asked = next_action(task)
        if asked.outcome != "spawn":
            return GoalJourney(final=asked, iterations=tuple(done))
        done.append(iterate_by_relay(task, queue.pop(0) if queue else Iteration()))
    raise AssertionError(f"the goal loop was still asking for spawns after {_RELAY_LIMIT} relays")
