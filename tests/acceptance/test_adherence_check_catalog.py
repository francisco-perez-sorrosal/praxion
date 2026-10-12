"""Every role is held to C1 to C6 and to its own row of the role check table.

Each check is declared mechanical or judged before any run, and names the rule it
enforces as a file and a section that exist in the repository; every judged check
documents the golden bad case it must rate a failure.
"""

from __future__ import annotations

import pytest

from tests.acceptance.drivers.adherence_eval import (
    COMMON_CHECKS,
    REPO_ROOT,
    ROLE_TABLE_CLAUSES,
    ROLES,
    check_catalog,
    markdown_headings,
)


@pytest.mark.parametrize("role", ROLES)
def test_every_role_carries_the_common_checks_and_one_check_per_clause_of_its_row(role):
    catalog = check_catalog(role)

    common = {c.name for c in catalog if c.common}
    own = [c for c in catalog if not c.common]

    assert common == set(COMMON_CHECKS), f"the {role}'s common checks are {sorted(common)}"
    assert len(own) >= ROLE_TABLE_CLAUSES[role], (
        f"the {role} has {len(own)} role-specific checks; its row lists"
        f" {ROLE_TABLE_CLAUSES[role]} clauses"
    )
    assert {c.kind for c in catalog} <= {"mechanical", "judged"}


def test_the_assumption_and_objection_check_is_judged_and_the_evidence_checks_are_mechanical():
    kinds = {c.name: c.kind for c in check_catalog("researcher") if c.common}

    assert kinds["C3"] == "judged"
    assert {kinds[name] for name in ("C1", "C2", "C4", "C5")} == {"mechanical"}


@pytest.mark.parametrize("role", ROLES)
def test_every_check_names_a_rule_section_that_exists_in_the_repository(role):
    missing = []
    for check in check_catalog(role):
        source = REPO_ROOT / check.rule_file
        if not source.is_file():
            missing.append(f"{check.name}: no file {check.rule_file}")
        elif not any(check.rule_section.strip("# ") in h for h in markdown_headings(source)):
            missing.append(f"{check.name}: no section {check.rule_section!r} in {check.rule_file}")

    assert missing == [], f"the {role}'s checks cite rules that do not exist:\n" + "\n".join(
        missing
    )


@pytest.mark.parametrize("role", ROLES)
def test_every_judged_check_documents_a_golden_bad_case(role):
    judged = [c for c in check_catalog(role) if c.kind == "judged"]

    undocumented = [c.name for c in judged if not (c.golden_bad_case or "").strip()]

    assert undocumented == [], (
        f"the {role}'s judged checks without a golden bad case: {undocumented}"
    )
