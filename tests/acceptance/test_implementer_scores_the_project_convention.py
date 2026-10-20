"""The implementer's sessions score the project-convention check like the pilot roles'.

Every implementer task states a project convention only in its fixture's own `CLAUDE.md`,
observed by the line `Filed under the project house rules.` in a file the session writes;
a session passes when it wrote that line, fails when it did not, and is not applicable
when the task stopped the role early, exactly as a pilot role's session. Nothing else of
the implementer's kit moves: the same tasks, prompts, templates, fixtures, variants and
checks, and no task added.
"""

from __future__ import annotations

import pytest

from tests.acceptance.drivers import implementer_kit as kit
from tests.acceptance.drivers.flip_evidence import convention_check


@pytest.fixture(scope="module")
def current() -> dict:
    return kit.snapshot()


def test_every_implementer_task_states_a_project_convention_with_its_check(current):
    unstated = [t["task_id"] for t in current["tasks"] if t["convention"] is None]

    assert unstated == [], f"{len(unstated)} implementer tasks state no project convention"
    assert {t["convention"]["check"] for t in current["tasks"]} == {
        current["tasks"][0]["convention"]["check"]
    }
    assert current["tasks"][0]["convention"]["check"].startswith(f"{kit.ROLE}:")


def test_the_convention_is_stated_only_in_each_fixtures_instruction_file(current):
    misplaced = [
        (t["task_id"], path)
        for t in current["tasks"]
        if t["convention"] is not None
        for path, text in t["texts"].items()
        if t["convention"]["text"] in text and path != kit.INSTRUCTION_FILE
    ]
    unstated = [
        t["task_id"]
        for t in current["tasks"]
        if t["convention"] is None or t["convention"]["text"] not in (t["instructions"] or "")
    ]

    assert unstated == [], f"fixtures whose CLAUDE.md states no convention: {unstated[:3]}"
    assert misplaced == [], f"the convention also appears outside CLAUDE.md: {misplaced[:3]}"


def test_the_conventions_observance_is_the_house_rules_line(current):
    texts = {t["convention"]["text"] for t in current["tasks"] if t["convention"]}

    assert texts, "no implementer task states a convention"
    assert all(kit.OBSERVANCE_LINE in text for text in texts), texts


def test_the_convention_check_is_in_the_implementers_catalog(current):
    names = {name for name, _ in current["checks"]}

    assert convention_check(kit.ROLE) in names, sorted(names)


@pytest.mark.parametrize(
    ("wrote_line", "forced_stop", "expected"),
    [
        (True, False, "passed"),
        (False, False, "failed"),
        (False, True, "not applicable"),
    ],
    ids=["wrote the line", "wrote no such line", "stopped early"],
)
def test_an_implementer_session_is_scored_on_the_convention_like_a_pilot_role(
    wrote_line, forced_stop, expected
):
    pilot = kit.convention_outcome(
        wrote_line=wrote_line, forced_stop=forced_stop, role="researcher"
    )

    implementer = kit.convention_outcome(wrote_line=wrote_line, forced_stop=forced_stop)

    assert pilot == expected, f"the pilot role scored {pilot!r}; the oracle assumed {expected!r}"
    assert implementer == expected


# -- Everything else stays -------------------------------------------------------------------


def test_the_implementers_task_list_is_unchanged_and_gains_no_task(current):
    before = kit.frozen()

    assert current["task_ids"] == before["task_ids"]
    assert current["producible"] == before["producible"]


def test_each_implementer_task_keeps_its_prompt_template_variant_and_fixture(current):
    before = {t["task_id"]: kit.without_instruction_file(t) for t in kit.frozen()["tasks"]}
    now = {t["task_id"]: kit.without_instruction_file(t) for t in current["tasks"]}

    changed = sorted(task for task in before if now.get(task) != before[task])

    assert set(now) == set(before)
    assert changed == [], f"{len(changed)} tasks changed beyond CLAUDE.md, first: {changed[:1]}"


def test_the_implementers_other_checks_are_unchanged(current):
    others = [c for c in current["checks"] if c[0] != convention_check(kit.ROLE)]

    assert others == kit.frozen()["checks"]
