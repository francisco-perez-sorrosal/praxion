"""`plan_delivery` plans managed-only process text as self-labelled parts.

The planner is pure, so each test states a property of its output: the parts of
a unit rebuild the file body exactly, none passes the per-part ceiling, splits
fall on headings, the plan does not depend on who computes it, and the scope,
event and agent kind decide which units are planned at all.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

# Flat import, as the sibling hook tests do: the mutation sensor runs this
# directory's files side by side, so a package-qualified import would escape it.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _project_scope import Managed, Unmanaged  # noqa: E402
from _rule_delivery import (  # noqa: E402
    GIT_CONVENTIONS_ID,
    MANAGED_CORE_UNITS,
    MAX_PART_CHARS,
    ROUTING_RESIDENT_ID,
    AgentKind,
    DeliveryPart,
    Event,
    chunk_budget,
    parse_agent_kind,
    plan_delivery,
    split_unit,
)

# The sensor runs a copy of this file one directory deeper, so walk up to the
# checkout instead of counting parents.
REPO_ROOT = next(
    root
    for root in Path(__file__).resolve().parents
    if (root / "rules" / "_manifest.yaml").is_file()
)
FRONTMATTER = re.compile(r"\A---\s*\n.*?\n---\s*\n", re.DOTALL)

CORE_IDS = tuple(unit.unit_id for unit in MANAGED_CORE_UNITS)
SESSION_MANAGED_IDS = (GIT_CONVENTIONS_ID, ROUTING_RESIDENT_ID, *CORE_IDS)
MANAGED = Managed(Path("/project"), Path("/project/.ai-state"))
UNMANAGED = Unmanaged()


def _body_of(rule_path: str) -> str:
    return FRONTMATTER.sub("", (REPO_ROOT / rule_path).read_text(encoding="utf-8"), count=1)


def _real_units() -> dict[str, str]:
    """The five managed-only units and the git conventions, as the injector would read them."""
    paths = {unit.unit_id: unit.path for unit in MANAGED_CORE_UNITS}
    paths[GIT_CONVENTIONS_ID] = "rules/swe/vcs/git-conventions.md"
    paths[ROUTING_RESIDENT_ID] = "rules/swe/agent-model-routing-resident.md"
    return {unit_id: _body_of(path) for unit_id, path in paths.items()}


def _synthetic_units() -> dict[str, str]:
    return {unit_id: f"## {unit_id}\n\nbody of {unit_id}\n" for unit_id in SESSION_MANAGED_IDS}


def _plan(
    units, scope=MANAGED, event=Event.SESSION, agent=AgentKind.INHERITING, disabled=(), native=()
):
    return plan_delivery(units, scope, event, agent, frozenset(disabled), frozenset(native))


def _chunk(part: DeliveryPart) -> str:
    """The part's text without its label line and the blank line after it."""
    return part.text.partition("\n\n")[2]


def _rebuilt(parts, unit_id: str) -> str:
    return "".join(_chunk(p) for p in sorted(parts, key=lambda p: p.index) if p.unit_id == unit_id)


def _section(title: str, size: int) -> str:
    """A `##` section of exactly `size` characters made of two-line paragraphs."""
    head = f"## {title}\n\n"
    paragraph = "x" * 78 + "\n" + "y" * 60 + "\n\n"
    filler = (paragraph * (size // len(paragraph) + 1))[: size - len(head)]
    return (head + filler)[:-1] + "\n"  # a heading after it starts a line


# -- the parts of a unit rebuild its body --------------------------------------


@pytest.mark.parametrize("unit_id", SESSION_MANAGED_IDS)
def test_a_units_parts_in_index_order_rebuild_its_file_body_exactly(unit_id):
    units = _real_units()

    parts = split_unit(unit_id, units[unit_id])

    assert _rebuilt(parts, unit_id) == units[unit_id]


def test_the_coordination_protocol_needs_more_than_one_part():
    units = _real_units()

    parts = split_unit(
        "swe/swe-agent-coordination-protocol", units["swe/swe-agent-coordination-protocol"]
    )

    assert len(parts) >= 2


@pytest.mark.parametrize("unit_id", SESSION_MANAGED_IDS)
def test_every_part_of_every_real_unit_fits_the_ceiling(unit_id):
    units = _real_units()

    parts = split_unit(unit_id, units[unit_id])

    assert parts
    assert all(len(p.text) <= MAX_PART_CHARS for p in parts)


@pytest.mark.parametrize("unit_id", SESSION_MANAGED_IDS)
def test_a_split_falls_on_a_heading_boundary(unit_id):
    units = _real_units()

    parts = split_unit(unit_id, units[unit_id])

    for part in parts[1:]:
        assert re.match(r"#{2,3} ", _chunk(part)), part.text[:120]


def test_a_unit_that_fits_is_one_part_that_ends_with_the_whole_body():
    parts = split_unit("u", "## A\n\nshort\n")

    assert len(parts) == 1
    assert (parts[0].index, parts[0].total) == (1, 1)
    assert _chunk(parts[0]) == "## A\n\nshort\n"


def test_a_body_filling_the_budget_exactly_stays_one_part():
    budget = chunk_budget("u")
    body = _section("A", budget)

    parts = split_unit("u", body)

    assert len(body) == budget
    assert len(parts) == 1
    assert len(parts[0].text) <= MAX_PART_CHARS


def test_one_character_past_the_budget_splits_at_the_next_heading():
    budget = chunk_budget("u")
    first = _section("A", budget - 10)
    body = first + "\n## B\n\nsecond\n"

    parts = split_unit("u", body)

    assert [_chunk(p) for p in parts] == [first + "\n", "## B\n\nsecond\n"]


def test_sections_that_sum_to_the_budget_share_a_part_and_the_next_one_starts_a_new_part():
    budget = chunk_budget("u")
    first = _section("A", budget // 2)
    second = _section("B", budget - len(first))
    third = "## C\n\nlast\n"

    parts = split_unit("u", first + second + third)

    assert [_chunk(p) for p in parts] == [first + second, third]


def test_a_third_level_heading_is_a_boundary_and_a_fourth_level_is_not():
    budget = chunk_budget("u")
    filler = _section("A", budget - 40)

    split_at_third = split_unit("u", filler + "\n### B\n\n" + "y" * 60)
    kept_at_fourth = split_unit("u", filler + "\n#### B\n\n" + "y" * 60)

    assert [_chunk(p)[:5] for p in split_at_third] == ["## A\n", "### B"]
    assert all(not _chunk(p).startswith("#### ") for p in kept_at_fourth)


def test_a_heading_inside_a_code_fence_is_not_a_boundary():
    budget = chunk_budget("u")
    fenced = "```bash\n## not a heading\n```\n"
    body = _section("A", budget - 20) + "\n" + fenced + "\n## B\n\nend\n"

    parts = split_unit("u", body)

    assert _rebuilt(parts, "u") == body
    assert any(fenced in _chunk(p) for p in parts)
    assert _chunk(parts[-1]).startswith("## B")
    assert not any(_chunk(p).startswith("## not a heading") for p in parts)


def test_a_section_over_the_budget_splits_at_a_paragraph_never_inside_one():
    budget = chunk_budget("u")
    head = "## Big\n\n"
    first = "a" * (budget - len(head) - 40) + "\n" + "b" * 30 + "\n\n"
    second = "ccccc\n" + "d" * 50 + "\n\n"  # its first line alone would still fit
    body = head + first + second

    parts = split_unit("u", body)

    assert [_chunk(p) for p in parts] == [head + first, second]


def test_a_single_unbroken_line_over_the_budget_is_cut_but_still_rebuilds_and_fits():
    budget = chunk_budget("u")
    body = "z" * (budget * 2 + 7)

    parts = split_unit("u", body)

    assert [len(_chunk(p)) for p in parts] == [budget, budget, 7]
    assert _rebuilt(parts, "u") == body


def test_an_empty_body_plans_no_part():
    assert split_unit("u", "") == ()


# -- every part says which unit it belongs to and where it sits ---------------


def test_each_part_opens_with_one_label_line_naming_the_unit_and_its_place():
    body = _section("A", chunk_budget("swe/x") - 10) + "\n## B\n\nsecond\n"

    parts = split_unit("swe/x", body)

    assert len(parts) == 2
    for number, part in enumerate(parts, start=1):
        label = part.text.split("\n", 1)[0]
        assert label == f"## Praxion Rules (auto-injected): swe/x, part {number} of 2"
        assert part.text.startswith(label + "\n\n")
        assert (part.unit_id, part.index, part.total) == ("swe/x", number, 2)


def test_a_part_cannot_exceed_the_ceiling_or_sit_outside_its_unit():
    with pytest.raises(ValueError, match="ceiling"):
        DeliveryPart("u", 1, 1, "x" * (MAX_PART_CHARS + 1))
    with pytest.raises(ValueError, match="outside its unit"):
        DeliveryPart("u", 0, 1, "x")
    with pytest.raises(ValueError, match="outside its unit"):
        DeliveryPart("u", 2, 1, "x")
    assert DeliveryPart("u", 1, 1, "x" * MAX_PART_CHARS).total == 1


# -- which units are planned ---------------------------------------------------


def test_a_managed_session_plans_git_conventions_the_routing_resident_then_the_core_units():
    plan = _plan(_synthetic_units())

    assert tuple(p.unit_id for p in plan) == SESSION_MANAGED_IDS


def test_the_core_units_are_the_protocol_the_documents_rule_and_the_adr_resident_in_order():
    assert [(u.unit_id, u.path, u.order) for u in MANAGED_CORE_UNITS] == [
        ("swe/swe-agent-coordination-protocol", "rules/swe/swe-agent-coordination-protocol.md", 1),
        ("swe/agent-intermediate-documents", "rules/swe/agent-intermediate-documents.md", 2),
        ("swe/adr-conventions-resident", "rules/swe/adr-conventions-resident.md", 3),
    ]
    assert all((REPO_ROOT / u.path).is_file() for u in MANAGED_CORE_UNITS)


def test_an_unmanaged_session_plans_the_git_conventions_only():
    plan = _plan(_synthetic_units(), scope=UNMANAGED)

    assert tuple(p.unit_id for p in plan) == (GIT_CONVENTIONS_ID,)


def test_the_agent_kind_does_not_change_a_session_plan():
    units = _synthetic_units()

    plans = {kind: _plan(units, agent=kind) for kind in AgentKind}

    assert len(set(plans.values())) == 1


def test_an_inheriting_spawn_in_a_managed_scope_plans_the_three_core_units_only():
    plan = _plan(_synthetic_units(), event=Event.SUBAGENT)

    assert tuple(p.unit_id for p in plan) == CORE_IDS


@pytest.mark.parametrize(
    ("scope", "agent"),
    [
        (MANAGED, AgentKind.LEAN),
        (MANAGED, AgentKind.NO_INSTRUCTION_FILES),
        (UNMANAGED, AgentKind.INHERITING),
        (UNMANAGED, AgentKind.LEAN),
        (UNMANAGED, AgentKind.NO_INSTRUCTION_FILES),
    ],
)
def test_every_other_spawn_plans_nothing(scope, agent):
    assert _plan(_synthetic_units(), scope=scope, event=Event.SUBAGENT, agent=agent) == ()


def test_a_unit_that_is_still_natively_installed_is_skipped_so_nothing_arrives_twice():
    units = _synthetic_units()
    native = {GIT_CONVENTIONS_ID, CORE_IDS[0]}

    session = _plan(units, native=native)
    spawn = _plan(units, event=Event.SUBAGENT, native=native)

    assert tuple(p.unit_id for p in session) == (ROUTING_RESIDENT_ID, *CORE_IDS[1:])
    assert tuple(p.unit_id for p in spawn) == CORE_IDS[1:]


def test_the_disable_set_drops_a_blacklistable_unit_and_never_a_core_unit():
    units = _synthetic_units()

    plan = _plan(units, disabled={GIT_CONVENTIONS_ID, ROUTING_RESIDENT_ID, *CORE_IDS})
    spawn = _plan(units, event=Event.SUBAGENT, disabled=set(CORE_IDS))

    assert tuple(p.unit_id for p in plan) == CORE_IDS
    assert tuple(p.unit_id for p in spawn) == CORE_IDS


def test_a_unit_without_a_body_or_not_supplied_is_left_out_of_the_plan():
    units = _synthetic_units()
    units[ROUTING_RESIDENT_ID] = ""
    del units[CORE_IDS[1]]

    plan = _plan(units)

    assert tuple(p.unit_id for p in plan) == (GIT_CONVENTIONS_ID, CORE_IDS[0], CORE_IDS[2])


# -- the plan is the same wherever it is computed ------------------------------


def test_the_plan_is_identical_across_runs_and_does_not_depend_on_supply_order():
    units = _real_units()
    reordered = dict(reversed(list(units.items())))

    first = _plan(units)
    second = _plan(units)
    third = _plan(reordered)

    assert first == second == third
    assert all(isinstance(p, DeliveryPart) for p in first)


def test_a_real_managed_plan_reads_the_same_slot_by_slot_and_each_slot_prints_one_part():
    plan = _plan(_real_units())
    from_another_process = _plan(_real_units())

    assert len(plan) == len(from_another_process) >= len(SESSION_MANAGED_IDS) + 1
    assert [p.text for p in plan] == [p.text for p in from_another_process]
    assert all(len(p.text) <= MAX_PART_CHARS for p in plan)


# -- the agent kind is parsed once ---------------------------------------------


@pytest.mark.parametrize(
    ("agent_type", "omit_claude_md", "expected"),
    [
        ("Explore", False, AgentKind.NO_INSTRUCTION_FILES),
        ("Plan", None, AgentKind.NO_INSTRUCTION_FILES),
        ("Explore", True, AgentKind.NO_INSTRUCTION_FILES),
        ("researcher", True, AgentKind.LEAN),
        ("researcher", False, AgentKind.INHERITING),
        ("general-purpose", False, AgentKind.INHERITING),
        ("custom-agent", None, AgentKind.INHERITING),
        (None, None, AgentKind.INHERITING),
        ("", True, AgentKind.LEAN),
    ],
)
def test_an_agent_kind_comes_from_its_type_and_its_definitions_omit_flag(
    agent_type, omit_claude_md, expected
):
    assert parse_agent_kind(agent_type, omit_claude_md) is expected
