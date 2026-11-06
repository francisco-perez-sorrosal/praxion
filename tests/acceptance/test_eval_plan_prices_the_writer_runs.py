"""The eval plan prices each writer role's paired run before anyone pays for it.

For the test-engineer and the systems-architect, `eval/EVAL_PLAN.md` states the estimated cost of
the paired run of 48 sessions, the comparable recorded runs it is derived from, the modes the run
covers with their spawn shares, and the run cap and per-session budget it would use, and whether
it bills through the session token file.
"""

from __future__ import annotations

import re

import pytest

from tests.acceptance.drivers import writer_kits as kits
from tests.acceptance.drivers.writer_kits import (
    COMPARABLE_RUNS,
    COVERED_MODES,
    PAIRED_SESSIONS,
    TOKEN_FILE_OPTION,
    WRITER_ROLES,
)

STATEMENTS = {
    "the paired run's session count": rf"\b{PAIRED_SESSIONS}\b",
    "a cost in dollars": r"(\$\s?\d+(\.\d+)?|\d+(\.\d+)?\s?(USD|dollars))",
    "the run cap with its value": r"--max-total-usd[`\s=]*\$?\d",
    "the per-session budget with its value": r"--session-budget-usd[`\s=]*\$?\d",
    "whether it bills through the token file": re.escape(TOKEN_FILE_OPTION),
    "a comparable recorded run": "|".join(map(re.escape, COMPARABLE_RUNS)),
    "a spawn share": r"\d+(\.\d+)?\s?(%|percent)",
}


def estimate(role: str) -> str:
    """The eval plan's section on `role` that states the paired run's session count."""
    sections = [s for s in kits.eval_plan_sections(role) if str(PAIRED_SESSIONS) in s]
    assert sections, f"no section of the eval plan names the {role} and its paired run's sessions"
    return sections[0]


@pytest.mark.parametrize("statement", sorted(STATEMENTS))
@pytest.mark.parametrize("role", WRITER_ROLES)
def test_the_writer_roles_estimate_states_what_a_paid_run_needs(role, statement):
    assert re.search(STATEMENTS[statement], estimate(role)), (
        f"the {role}'s estimate does not state {statement}"
    )


@pytest.mark.parametrize("role", WRITER_ROLES)
def test_the_writer_roles_estimate_names_each_covered_mode(role):
    text = estimate(role)

    unnamed = [mode for mode in COVERED_MODES[role] if mode not in text]

    assert unnamed == [], f"the {role}'s estimate does not name {unnamed}"
