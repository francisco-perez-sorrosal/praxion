"""A spawn of the implementer or the test-engineer whose delegation carries the refactoring phase
marker holds the refactoring skill's whole text from its first turn; no other spawn receives any
of it, and while a definition still preloads the skill nothing about its spawns changes.

Every scenario crosses the two boundaries a spawn passes through (the `Agent` tool call and the
subagent start) by running the registered hooks as separate processes against a copy of the
plugin, then reads what the spawn holds. "End state" means the role's definition preloads no part
of the skill; "interim" means it still preloads it, as at the base.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from tests.acceptance.drivers import refactoring_delivery as rd
from tests.acceptance.drivers.refactoring_delivery import MARKER, ROLES, Installation

MARKED = (
    "Task slug: widget-pricing\n\n"
    f"### Step 4: {MARKER} Extract the pricing rules into their own module\n\n"  # id-citation-discipline:ignore
    "Move the rules out of `orders.py` into `pricing.py`; keep every caller working."
)
UNMARKED = (
    "Task slug: widget-pricing\n\n"
    "### Step 4: Add the pricing rules module\n\n"  # id-citation-discipline:ignore
    "Write `pricing.py` with the discount rules the plan lists."
)
QUOTED = {
    "code-span": (
        "Task slug: widget-pricing\n\nImplement step 4: write `pricing.py`. The planner tags "
        f"restructuring steps `{MARKER}`; this one is not such a step."
    ),
    "fenced-block": (
        "Task slug: widget-pricing\n\nFor context, the plan's next step reads:\n\n"
        f"```markdown\n### Step 9: {MARKER} Split the orders module\n```\n\n"  # id-citation-discipline:ignore
        "Implement step 4 only: write `pricing.py`."
    ),
    "block-quote": (
        "Task slug: widget-pricing\n\nFor context, the plan's next step reads:\n\n"
        f"> ### Step 9: {MARKER} Split the orders module\n\n"  # id-citation-discipline:ignore
        "Implement step 4 only: write `pricing.py`."
    ),
}
OTHER_AGENTS = (
    "praxion:verifier",
    "praxion:systems-architect",
    "praxion:implementation-planner",
    "general-purpose",
)


def _agent(role: str) -> str:
    return f"praxion:{role}"


@pytest.fixture
def installation(tmp_path: Path) -> Installation:
    return rd.new_installation(tmp_path / "plugin")


@pytest.fixture
def end_state(installation: Installation) -> Installation:
    for role in ROLES:
        rd.without_preload(installation, role)
    return installation


@pytest.fixture
def interim(installation: Installation) -> Installation:
    for role in ROLES:
        rd.with_preload(installation, role)
    return installation


@pytest.fixture
def project(tmp_path: Path) -> Path:
    return rd.project_checkout(tmp_path / "project")


# -- A marked spawn holds the whole skill ------------------------------------------------------


@pytest.mark.parametrize("managed", [True, False], ids=["managed", "unmanaged"])
@pytest.mark.parametrize("role", ROLES)
def test_a_marked_spawn_holds_one_whole_copy_of_the_skill_from_its_start(
    end_state: Installation, tmp_path: Path, role: str, managed: bool
) -> None:
    project = rd.project_checkout(tmp_path / "work", managed=managed)

    spawned = rd.spawn(end_state, project, _agent(role), MARKED)

    assert rd.copies_held(spawned) == rd.Copies(whole=1, most=1), (
        f"a marked {role} spawn does not hold exactly one whole copy of the refactoring skill"
    )


@pytest.mark.parametrize("role", ROLES)
def test_the_delivered_skill_is_every_line_of_the_installed_body_unaltered_and_in_order(
    end_state: Installation, project: Path, role: str
) -> None:
    spawned = rd.spawn(end_state, project, _agent(role), MARKED)

    assert rd.delivered_in_order(spawned), (
        "what the marked spawn received is not the skill's body line for line, in order"
    )


@pytest.mark.parametrize(
    "spelling", ["[phase: refactoring]", "[PHASE:REFACTORING]", "[ Phase :  Refactoring ]"]
)
def test_the_marker_marks_a_delegation_whatever_its_case_and_inner_spacing(
    end_state: Installation, project: Path, spelling: str
) -> None:
    delegation = MARKED.replace(MARKER, spelling)

    spawned = rd.spawn(end_state, project, "praxion:implementer", delegation)

    assert rd.copies_held(spawned).whole == 1, f"a delegation carrying {spelling!r} was not marked"


def test_a_marker_in_the_delegations_own_words_marks_it_even_beside_a_quoted_one(
    end_state: Installation, project: Path
) -> None:
    delegation = QUOTED["fenced-block"] + "\n\n" + MARKED

    spawned = rd.spawn(end_state, project, "praxion:test-engineer", delegation)

    assert rd.copies_held(spawned) == rd.Copies(whole=1, most=1)


def test_an_edit_to_the_installed_skill_reaches_the_next_marked_spawn(
    end_state: Installation, project: Path
) -> None:
    added = "A paragraph added to the installed skill after the plugin was installed, kept whole."
    end_state.write(rd.SKILL, end_state.read(rd.SKILL).rstrip("\n") + f"\n\n{added}\n")

    spawned = rd.spawn(end_state, project, "praxion:implementer", MARKED)

    assert added in spawned.delivered, "the marked spawn received a stale copy of the skill"
    assert rd.copies_held(spawned).whole == 1


def test_no_single_context_string_of_a_marked_spawn_passes_the_channel_limit(
    end_state: Installation, project: Path
) -> None:
    spawned = rd.spawn(end_state, project, "praxion:implementer", MARKED)

    assert rd.copies_held(spawned).whole == 1, "the skill did not arrive at all"
    assert rd.longest_context_string(spawned) <= rd.CHANNEL_LIMIT, (
        f"a context string of {rd.longest_context_string(spawned)} characters passes the "
        f"{rd.CHANNEL_LIMIT}-character limit the channel places on one string"
    )


# -- Nobody else receives any of it --------------------------------------------------------------


@pytest.mark.parametrize("role", ROLES)
def test_an_unmarked_spawn_receives_none_of_the_skill(
    end_state: Installation, project: Path, role: str
) -> None:
    spawned = rd.spawn(end_state, project, _agent(role), UNMARKED)

    assert rd.copies_held(spawned) == rd.Copies(whole=0, most=0)


@pytest.mark.parametrize("role", ROLES)
@pytest.mark.parametrize("quoting", sorted(QUOTED))
def test_a_delegation_that_only_quotes_the_marker_receives_none_of_the_skill(
    end_state: Installation, project: Path, role: str, quoting: str
) -> None:
    spawned = rd.spawn(end_state, project, _agent(role), QUOTED[quoting])

    assert rd.copies_held(spawned) == rd.Copies(whole=0, most=0), (
        f"a marker inside a {quoting} pulled the skill"
    )


@pytest.mark.parametrize("agent_type", OTHER_AGENTS)
def test_no_other_role_receives_the_skill_even_with_a_marked_delegation(
    end_state: Installation, project: Path, agent_type: str
) -> None:
    spawned = rd.spawn(end_state, project, agent_type, MARKED)

    assert rd.copies_held(spawned).most == 0, f"{agent_type} received part of the skill"


# -- One copy, never two -------------------------------------------------------------------------


@pytest.mark.parametrize("role", ROLES)
def test_a_marked_spawn_of_a_role_that_still_preloads_the_skill_holds_one_copy(
    interim: Installation, project: Path, role: str
) -> None:
    spawned = rd.spawn(interim, project, _agent(role), MARKED)

    assert rd.copies_held(spawned) == rd.Copies(whole=1, most=1)


@pytest.mark.parametrize("role", ROLES)
def test_in_the_interim_a_marked_spawn_receives_exactly_what_an_unmarked_one_does(
    interim: Installation, project: Path, role: str
) -> None:
    marked = rd.spawn(interim, project, _agent(role), MARKED)
    unmarked = rd.spawn(interim, project, _agent(role), UNMARKED)

    assert marked.context == unmarked.context
    assert marked.prompt_additions == unmarked.prompt_additions


def test_a_resumed_marked_spawn_still_holds_one_copy(
    end_state: Installation, project: Path
) -> None:
    first = rd.spawn(end_state, project, "praxion:implementer", MARKED)

    resumed = rd.resume(end_state, project, first, "Continue the step: one caller is left.")

    assert rd.copies_held(resumed) == rd.Copies(whole=1, most=1)


def test_concurrent_spawns_of_one_role_each_receive_what_their_own_delegation_calls_for(
    end_state: Installation, project: Path
) -> None:
    delegations = [MARKED, UNMARKED, MARKED, QUOTED["block-quote"], UNMARKED, MARKED]

    with ThreadPoolExecutor(max_workers=len(delegations)) as pool:
        spawns = list(
            pool.map(lambda d: rd.spawn(end_state, project, "praxion:implementer", d), delegations)
        )

    assert [rd.copies_held(s).whole for s in spawns] == [1, 0, 1, 0, 0, 1]
    assert [rd.copies_held(s).most for s in spawns] == [1, 0, 1, 0, 0, 1]


# -- The delivery adds and never replaces ---------------------------------------------------------


@pytest.mark.parametrize("role", ROLES)
def test_a_marked_spawn_keeps_everything_an_unmarked_spawn_receives(
    end_state: Installation, project: Path, role: str
) -> None:
    unmarked = rd.spawn(end_state, project, _agent(role), UNMARKED)
    marked = rd.spawn(end_state, project, _agent(role), MARKED)

    assert rd.copies_held(marked).whole == 1, "the skill did not arrive at all"
    assert [c for c in unmarked.context if c not in marked.context] == []
    assert marked.preloaded == unmarked.preloaded
    assert marked.prompts_kept_delegation, "the delegation's own words did not reach the agent"


# -- A failed delivery -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "fault", [rd.unreadable_skill, rd.blocking_skill], ids=["unreadable", "read-never-ends"]
)
def test_a_spawn_whose_skill_cannot_be_read_still_starts_with_its_delegation(
    end_state: Installation, project: Path, fault
) -> None:
    fault(end_state)

    spawned = rd.spawn(end_state, project, "praxion:implementer", MARKED)

    assert spawned.refusals == [], f"a failed delivery refused the spawn: {spawned.refusals}"
    assert spawned.prompts_kept_delegation


def test_a_malformed_spawn_input_never_refuses_the_spawn(
    end_state: Installation, project: Path
) -> None:
    spawned = rd.spawn(end_state, project, "praxion:implementer", MARKED, raw_stdin='{"cut off mid')

    assert spawned.refusals == []


@pytest.mark.parametrize(
    "fault", [rd.unreadable_skill, rd.blocking_skill], ids=["unreadable", "read-never-ends"]
)
def test_a_delivery_that_cannot_read_the_skill_is_recorded_where_a_later_check_finds_it(
    end_state: Installation, project: Path, fault
) -> None:
    fault(end_state)

    rd.spawn(end_state, project, "praxion:implementer", MARKED)

    assert len(rd.delivery_failures(end_state, project)) >= 1, "the failure left no record"


def test_a_delivery_given_malformed_input_is_recorded_where_a_later_check_finds_it(
    end_state: Installation, project: Path
) -> None:
    rd.spawn(end_state, project, "praxion:implementer", MARKED, raw_stdin='{"cut off mid')

    assert len(rd.delivery_failures(end_state, project)) >= 1, "the failure left no record"


def test_a_successful_delivery_records_no_failure(end_state: Installation, project: Path) -> None:
    rd.spawn(end_state, project, "praxion:implementer", MARKED)

    assert rd.delivery_failures(end_state, project) == ()


# -- Arrival is provable from the spawn's own record ----------------------------------------------


@pytest.mark.parametrize("role", ROLES)
def test_a_delivered_spawns_own_record_shows_the_skill_arrived(
    end_state: Installation, project: Path, role: str
) -> None:
    spawned = rd.spawn(end_state, project, _agent(role), MARKED)

    assert rd.shows_arrival(spawned.own_record)


@pytest.mark.parametrize(
    ("prepare", "delegation"),
    [
        (rd.without_preload, UNMARKED),
        (rd.without_preload, QUOTED["code-span"]),
        (rd.with_preload, MARKED),
    ],
    ids=["unmarked", "quoted", "interim-marked"],
)
def test_a_spawn_the_delivery_did_not_serve_shows_no_arrival(
    installation: Installation, project: Path, prepare, delegation: str
) -> None:
    prepare(installation, "implementer")

    spawned = rd.spawn(installation, project, "praxion:implementer", delegation)

    assert not rd.shows_arrival(spawned.own_record)


# -- The canary ---------------------------------------------------------------------------------------


@pytest.mark.parametrize("role", ROLES)
def test_without_the_delivery_a_marked_spawn_holds_no_copy(
    end_state: Installation, project: Path, role: str
) -> None:
    rd.remove_delivery(end_state)

    spawned = rd.spawn(end_state, project, _agent(role), MARKED)

    assert rd.copies_held(spawned).most == 0, "the skill still arrived with the delivery removed"


# -- The move ------------------------------------------------------------------------------------------


@pytest.mark.parametrize("role", ROLES)
def test_the_move_drops_only_the_refactoring_preload_from_each_definition(
    installation: Installation, role: str
) -> None:
    rd.apply_the_move(installation)

    expected = tuple(s for s in rd.base_preloads()[role] if s != rd.SKILL_NAME)
    assert rd.preloaded_skills(installation.root, role) == expected


@pytest.mark.parametrize("role", ROLES)
def test_after_the_move_a_marked_spawn_holds_one_copy_and_an_unmarked_one_none(
    installation: Installation, project: Path, role: str
) -> None:
    rd.apply_the_move(installation)

    marked = rd.spawn(installation, project, _agent(role), MARKED)
    unmarked = rd.spawn(installation, project, _agent(role), UNMARKED)

    assert rd.copies_held(marked) == rd.Copies(whole=1, most=1)
    assert rd.copies_held(unmarked) == rd.Copies(whole=0, most=0)
