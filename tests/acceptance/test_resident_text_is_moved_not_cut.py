"""Classifying guidance moves it to its audience; no rule or instruction-file text is cut.

The fixtures were frozen from the files as they stood before the change.
"""

from __future__ import annotations

import pytest

from tests.acceptance.drivers import kernel_sandbox, resident_sections
from tests.acceptance.drivers.kernel_sandbox import REPO_ROOT, frontmatter


def test_no_paragraph_of_any_rule_or_instruction_file_is_deleted_or_reworded() -> None:
    frozen = resident_sections.load("instruction_sections.json")

    lost = resident_sections.lost_paragraphs(REPO_ROOT, frozen)

    assert lost == [], "paragraphs deleted or reworded:\n" + "\n".join(lost)


# A rule moved by a ratified, measured declaration leaves the always-loaded set on purpose: its
# path scope and the resident file that keeps its first line at session start.
DECLARED_MOVES = {
    "rules/swe/adr-conventions.md": (
        ".ai-state/decisions/**",
        "rules/swe/adr-conventions-resident.md",
    ),
}


@pytest.mark.parametrize(
    "rule",
    [r for r in resident_sections.load("always_loaded_rules.json") if r not in DECLARED_MOVES],
)
def test_every_rule_the_main_session_loaded_is_still_always_loaded(rule: str) -> None:
    path = REPO_ROOT / rule

    assert path.is_file(), f"{rule} is gone from the resident layer"
    assert "paths" not in frontmatter(path.read_text()), f"{rule} gained a path scope"


@pytest.mark.parametrize("rule", sorted(DECLARED_MOVES))
def test_a_rule_moved_by_declaration_is_path_scoped_and_keeps_an_always_loaded_resident(
    rule: str,
) -> None:
    scope, resident = DECLARED_MOVES[rule]

    paths = frontmatter((REPO_ROOT / rule).read_text()).get("paths") or []
    resident_path = REPO_ROOT / resident

    assert scope in paths, f"{rule} is not path-scoped to {scope}: {paths}"
    assert resident_path.is_file(), f"{resident} is missing"
    assert "paths" not in frontmatter(resident_path.read_text()), f"{resident} gained a path scope"


def test_the_contract_rule_still_carries_its_four_behaviors() -> None:
    text = (REPO_ROOT / kernel_sandbox.CONTRACT_RULE).read_text()

    names = [
        n
        for n in ("Surface Assumptions", "Register Objection", "Stay Surgical", "Simplicity First")
        if f"**{n}**" not in text
    ]

    assert names == [], f"the contract rule lost {names}"
