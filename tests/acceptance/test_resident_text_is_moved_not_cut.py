"""Classifying guidance moves it to its audience; no rule or instruction-file text is cut.

The fixtures were frozen from the files as they stood before the change.
"""

from __future__ import annotations

import pytest

from tests.acceptance.drivers import kernel_sandbox, resident_sections
from tests.acceptance.drivers.kernel_sandbox import REPO_ROOT, frontmatter

# Paragraphs a ratified declaration rewords on purpose, each held by its move's own scenarios.
# The ADR-rule move reworded the reading order; the model-routing move rewords it again (it stops
# listing model routing as always-on) and restates the routing rule's spawn directive. The
# routing-facts change restates the resolution order and the alias paragraph to the harness's
# current behaviour, and the tier table and its pointer line for the L tier's alias. The lessons
# batch adds a bullet or a table row to a list or table of three path-scoped rules; the block is
# one paragraph, so it reads as reworded though every line it had is still there. Each index is
# the paragraph's position in the frozen fixture.
DECLARED_REWORDINGS = {
    ("CLAUDE.md", "## Agent reading order [1]", 0),
    ("rules/swe/agent-model-routing.md", "## Agent Model Routing [1]", 1),
    ("rules/swe/agent-model-routing.md", "## Agent Model Routing [1]", 2),
    ("rules/swe/agent-model-routing.md", "## Agent Model Routing [1]", 3),
    ("rules/swe/agent-model-routing.md", "### Tier Table [1]", 0),
    ("rules/swe/agent-model-routing.md", "### Tier Table [1]", 1),
    ("rules/swe/gate-liveness.md", "### Anti-patterns [1]", 0),
    ("rules/swe/id-citation-discipline.md", "### Narrow Exceptions (and their reasons) [1]", 0),
    ("rules/swe/testing-conventions.md", "### Cleanup [1]", 1),
    ("rules/swe/testing-conventions.md", "### Determinism [1]", 5),
    ("rules/swe/testing-conventions.md", "### Fixtures Under Gitignored Paths [1]", 1),
    ("rules/swe/testing-conventions.md", "### Mocking Boundaries [1]", 1),
    ("rules/swe/testing-conventions.md", "### Test Data [1]", 1),
}


def _frozen_with_declared_rewordings() -> dict[str, dict[str, list[str]]]:
    frozen = resident_sections.load("instruction_sections.json")
    for rel, sections in frozen.items():
        for key, prints in sections.items():
            declared = {index for r, k, index in DECLARED_REWORDINGS if (r, k) == (rel, key)}
            sections[key] = [p for i, p in enumerate(prints) if i not in declared]
    return frozen


def test_no_paragraph_of_any_rule_or_instruction_file_is_deleted_or_reworded() -> None:
    frozen = _frozen_with_declared_rewordings()

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
# A rule whose session-start text is delivered by the rule injection rather than a linked
# resident file; the model-routing move's own scenarios hold its path scope and that text.
DECLARED_HOOK_RESIDENT_MOVES = {"rules/swe/agent-model-routing.md": "agents/**"}


@pytest.mark.parametrize(
    "rule",
    [
        r
        for r in resident_sections.load("always_loaded_rules.json")
        if r not in DECLARED_MOVES and r not in DECLARED_HOOK_RESIDENT_MOVES
    ],
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
