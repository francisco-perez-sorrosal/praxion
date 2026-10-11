"""Unbound drivers: contracts the scenarios need that no step has bound to a real interface yet.

Each function raises, in the words of the assumption it stands for, until a driver-binding step
replaces its body. Nothing here imports the system under test.
"""

from __future__ import annotations

from pathlib import Path


def plugin_eval_cases(skill: str) -> list[Path]:
    """The `claude plugin eval` case directories that probe whether `skill` triggers.

    Assumed contract: each case is a directory holding a `prompt.md` and graders, at the repository
    root outside every shipped skill directory, in an eval directory the runner finds from the
    checkout; a trigger check is a `tool_used` grader on the `Skill` tool naming the skill, a
    must-not-invoke check carries a zero ceiling, and every case runs in both arms with the `Skill`
    check read as the plugin-fired indicator beside the score.
    """
    raise NotImplementedError(
        "unbound: the location and grader file format of the plugin eval cases that probe a "
        "skill's triggering are a design decision not yet made"
    )
