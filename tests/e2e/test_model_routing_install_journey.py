"""After an install a session opens without the tier table, and an author's touch loads it.

A user installs Praxion (fresh, or over an install made before the move) and opens a session:
the session-start text holds the routing text once and no tier-table row; the full routing rule
is linked into the user rules directory with its path scope, so touching an agent definition
delivers it; the session-start routing text is never linked; no link is stale; and the install
check finds nothing wrong with the rules. The marketplace first-session completion links the
same way.

The journey runs once per module and its tests only read it.
"""

from __future__ import annotations

import pytest

from tests.acceptance.drivers import model_routing_move as move
from tests.e2e.drivers.routing_install_journey import Installed, installed, marketplace_installed

FULL_RULE_LINK = "swe/agent-model-routing.md"


@pytest.fixture(scope="module")
def fresh(tmp_path_factory) -> Installed:
    return installed(tmp_path_factory.mktemp("fresh"))


@pytest.fixture(scope="module")
def reinstalled(tmp_path_factory) -> Installed:
    return installed(tmp_path_factory.mktemp("over-old"), over_an_old_install=True)


def _routing_links(journey: Installed) -> list[str]:
    """Links whose file carries the routing title."""
    return sorted(
        rel
        for rel, target in journey.links.items()
        if move.routing_section(target.read_text(encoding="utf-8"))
    )


def test_a_session_after_install_holds_no_row_of_the_tier_table(fresh):
    rows = move.tier_rows(move.fixture_text("base_rule.md"))

    assert [row for row in rows if row in fresh.session_start_text] == []


def test_a_session_after_install_holds_the_routing_text_exactly_once(fresh):
    titles = [
        line
        for line in fresh.session_start_text.splitlines()
        if line.startswith("#") and move.TITLE in line
    ]

    assert len(titles) == 1, titles


@pytest.mark.parametrize("journey", ["fresh", "reinstalled"])
def test_the_install_links_the_full_rule_and_not_the_session_start_text(journey, request):
    done: Installed = request.getfixturevalue(journey)

    assert _routing_links(done) == [FULL_RULE_LINK], _routing_links(done)
    assert done.links[FULL_RULE_LINK] == (move.REPO_ROOT / move.RULE).resolve()


def test_the_linked_full_rule_loads_on_a_touch_of_an_agent_definition(fresh):
    assert (fresh.rules / FULL_RULE_LINK).is_file(), "the full routing rule is not linked"
    scope = (
        move.frontmatter((fresh.rules / FULL_RULE_LINK).read_text(encoding="utf-8")).get("paths")
        or []
    )

    assert move.scope_takes(scope, "agents/verifier.md"), scope


def test_a_reinstall_over_an_old_install_leaves_no_stale_link(reinstalled, fresh):
    dangling = sorted(rel for rel, target in reinstalled.links.items() if not target.exists())

    assert dangling == []
    assert sorted(reinstalled.links) == sorted(fresh.links)


def test_the_install_check_finds_nothing_wrong_with_the_rules(fresh):
    assert move.install_check_rule_findings(fresh.check_output) == []


def test_the_marketplace_completion_links_the_full_rule_and_not_the_session_start_text(tmp_path):
    links = marketplace_installed(tmp_path)

    routing = sorted(
        rel
        for rel, target in links.items()
        if move.routing_section(target.read_text(encoding="utf-8"))
    )

    assert routing == [FULL_RULE_LINK], routing
