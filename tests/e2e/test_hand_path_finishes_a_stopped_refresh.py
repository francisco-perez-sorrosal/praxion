"""After a refresh that stopped short, the hand path finishes the install, instructions included.

The first-session hook reports `[Praxion] Update refresh could not finish` and names
`/praxion-complete-install`. The person invokes it, runs the command it hands over in their own
terminal and answers its questions. When the earlier render no longer reads back, the run ends
with `~/.claude/CLAUDE.md` reading as the installed version's template filled with the values the
person gave; when it still reads back, filled with the values it carried, with nothing asked
about them. Either way the rules and scripts are linked from the installed version and the
closing report says the install is done.
"""

from __future__ import annotations

import os
import re

import pytest

from tests.acceptance.drivers import hand_path_command as hc
from tests.acceptance.drivers import hook_reports as hr
from tests.acceptance.drivers import plugin_update as pu
from tests.e2e.drivers import hand_path_journey as hj

pytestmark = pytest.mark.skipif(
    hasattr(os, "geteuid") and os.geteuid() == 0, reason="root ignores the permissions these break"
)
STOPPED = "[Praxion] Update refresh could not finish"
JOURNEYS = {
    "unreadable-render": hc.Person(values=hc.TYPED),
    "template-unreadable": hc.Person(),
}


@pytest.fixture(scope="module")
def sources(tmp_path_factory):
    root = tmp_path_factory.mktemp("sources")
    n = pu.shipped_tree(root / "n")
    n1 = pu.edited_template(pu.shipped_tree(root / "n1"), pu.with_release_notes)
    fresh = pu.fresh_install(root / "fresh", n1, pu.AFTER, pu.LATER)
    return n, n1, fresh


@pytest.fixture(scope="module")
def journeys(sources, tmp_path_factory) -> dict[str, hj.Journey]:
    return {
        how: hj.journey(tmp_path_factory.mktemp(how), sources, how, person)
        for how, person in JOURNEYS.items()
    }


@pytest.fixture(params=list(JOURNEYS))
def journey(request, journeys) -> hj.Journey:
    return journeys[request.param]


def test_the_first_session_reports_the_refresh_could_not_finish(journey):
    lines = hr.message_lines(journey.hook)

    assert len(lines) == 1, lines
    assert lines[0].startswith(STOPPED), lines[0]
    assert hr.FINISH_BY_HAND in lines[0], lines[0]


def test_the_skill_hands_over_the_installed_versions_command(journey):
    assert journey.handed_over is not None, "the skill ran no single check to take a root from"
    assert os.path.realpath(journey.handed_over) == os.path.realpath(journey.update.n1)


def test_an_unreadable_render_ends_filled_with_the_values_the_person_typed(journeys):
    j = journeys["unreadable-render"]
    expected = pu.render(hc.n1_template(j.update), hc.TYPED)

    assert j.finished is not None, f"no command was handed over: {j.handed_over}"
    assert j.update.machine.instructions.read_text(encoding="utf-8") == expected


def test_a_readable_render_ends_filled_with_the_values_it_carried_and_nothing_asked(journeys):
    j = journeys["template-unreadable"]
    expected = pu.render(hc.n1_template(j.update), j.update.n_values)

    assert j.finished is not None, f"no command was handed over: {j.handed_over}"
    assert j.finished.value_questions == [], [p.text for p in j.finished.value_questions]
    assert j.update.machine.instructions.read_text(encoding="utf-8") == expected


def test_the_rules_and_scripts_end_linked_from_the_installed_version(journey):
    assert journey.finished is not None, f"no command was handed over: {journey.handed_over}"

    assert hc.links_refreshed(journey.update) == []


def test_the_closing_report_says_the_install_is_done(journey):
    assert journey.finished is not None, f"no command was handed over: {journey.handed_over}"

    assert journey.finished.says_done, journey.finished.report
    assert re.search(r"claude\.md|instructions", journey.finished.instructions_report, re.I)
