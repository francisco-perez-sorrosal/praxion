"""The git-conventions kit with staging by name governed again: the declaration the tests of the
staging grader, its fixture traps and runs over two checks are measured on.

The kit governs commit message form alone. Its floor showed sessions with no line of the rule
staging by name anyway, so that check had no room to fail there, and its lines stay resident in the
lean arm's kernel either way. The grader still grades it and a declaration file may govern it, so
the tests keep a declaration that does.
"""

from __future__ import annotations

from dataclasses import replace

from praxion_evals.adherence.moves import declaration
from praxion_evals.adherence.moves.checks_git import STAGING_BY_NAME
from praxion_evals.adherence.moves.model import (
    GovernedCheck,
    GovernedChecks,
    MoveDeclaration,
    RelPath,
)

STAGING_CHECK = GovernedCheck(
    name=STAGING_BY_NAME,
    rule_file=RelPath.parse("rules/swe/vcs/git-conventions.md"),
    section="Staging Discipline",
    phrases=("specific files by name", "git diff --staged", "accidental inclusions"),
)


def git_governing_staging() -> MoveDeclaration:
    """The kit's own declaration with staging by name as its second governed check."""
    kit = declaration.kit("git-conventions")
    return replace(kit, checks=GovernedChecks((*kit.checks.checks, STAGING_CHECK)))
