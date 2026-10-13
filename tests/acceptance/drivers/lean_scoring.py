"""Driver for how the adherence eval scores a pilot role's lean sessions, not yet bound.

The eval's existing seams are reached through `adherence_eval`; what this change
adds to them is designed later: how a session's kernel row reaches the grader, how
an isolation breach counts in the lean arm, and the project convention a pilot
task's fixture writes only in its own `CLAUDE.md`. Every hook raises until a
binding step reaches the evaluation package.

Scenarios describe sessions by what happened in them; the full arm of every pair
is a clean measured session unless a scenario says otherwise.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from tests.acceptance.drivers.kernel_sandbox import UnboundDriverError


@dataclass(frozen=True)
class LeanSession:
    task_id: str
    kernel_row: bool = True  # the spawn left a kernel_injected row
    read_user_instruction_file: bool = False  # the role read ~/.claude/CLAUDE.md
    followed_project_convention: bool = True


@dataclass(frozen=True)
class LeanScoring:
    scored: frozenset[str]  # task ids whose pair was scored
    infrastructure_errors: frozenset[str]  # task ids whose pair errored as infrastructure
    lean_failures: frozenset[str]  # task ids whose lean session counts as a failure
    retried: frozenset[str]  # task ids the run launched again


def score_lean_pairs(role: str, sessions: tuple[LeanSession, ...]) -> LeanScoring:
    raise UnboundDriverError(
        "scoring a pilot role's pairs from synthetic lean sessions (kernel row present or "
        "absent, an isolation breach) through the adherence eval is not designed yet"
    )


@dataclass(frozen=True)
class PilotFixture:
    instructions: str  # the fixture's own CLAUDE.md
    other_files: Mapping[str, str]  # every other file of the fixture, by path
    convention: str  # the convention's wording as the fixture's CLAUDE.md states it
    convention_check: str  # the role check that reads whether the role followed it


def pilot_task_fixture(role: str, seed: int) -> PilotFixture:
    raise UnboundDriverError(
        "reading a pilot task's fixture and the project convention it writes only in its "
        "own CLAUDE.md is not designed yet"
    )


def convention_outcome(role: str, arm: str, *, received_project_file: bool) -> str:
    raise UnboundDriverError(
        "grading the role check that reads the fixture's project convention for a session "
        "that did or did not receive the fixture's CLAUDE.md is not designed yet"
    )
