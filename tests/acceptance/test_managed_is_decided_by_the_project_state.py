"""Whether a start directory is managed is one answer, from `.ai-state/`, and every managed-only
behaviour follows it.

A directory is managed when it carries `.ai-state/` (a directory or a link to one), or a directory
above it inside the same repository checkout does; outside any repository only the start
directory counts. A managed start receives every managed-only procedure, its decision context
read from the governing project's own records; an unmanaged one receives none. The procedures,
the decision context, the reminder added to a non-trivial prompt, the preamble added to a
host-native spawn and the blacklist template are all on or all off for any start directory, and
a directory that changes kind gives the next session the matching set without a reinstall.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pytest

from tests.acceptance.drivers import process_text_oracles as oracles
from tests.acceptance.drivers import scratch_projects as places
from tests.acceptance.drivers import session_start_text as gate

TEXT_UNITS = tuple(oracles.MANAGED_ONLY_TEXTS)


@pytest.fixture(scope="module")
def template(tmp_path_factory) -> Path:
    return places.installed_home(tmp_path_factory.mktemp("install"))


@pytest.fixture
def machine(template, tmp_path) -> gate.Machine:
    return gate.new_machine(template, tmp_path / "machine")


@dataclass(frozen=True)
class Place:
    start: Path
    marker: str | None  # the governing project's decision marker; None: not managed
    root: Path | None = None  # the governing project's root


def _subdirectory(sandbox: Path) -> Place:
    root = places.repository(sandbox / "monorepo", state_marker="monorepo gating fixture")
    start = root / "packages" / "billing"
    start.mkdir(parents=True)
    return Place(start, "monorepo gating fixture", root)


def _linked_worktree(sandbox: Path) -> Place:
    main = places.repository(sandbox / "main-checkout", state_marker="worktree gating fixture")
    start = places.linked_worktree(main, sandbox / "linked")
    return Place(start, "worktree gating fixture", start)


def _linked_state(sandbox: Path) -> Place:
    elsewhere = places.plant_state(sandbox / "kept-state", "linked-state gating fixture")
    start = places.repository(sandbox / "linked-state-project")
    (start / ".ai-state").symlink_to(elsewhere / ".ai-state", target_is_directory=True)
    return Place(start, "linked-state gating fixture", start)


def _nested_repository_with_state(sandbox: Path) -> Place:
    outer = places.repository(sandbox / "outer", state_marker="outer gating fixture")
    start = places.repository(outer / "vendor" / "inner", state_marker="inner gating fixture")
    return Place(start, "inner gating fixture", start)


def _state_outside_a_repository(sandbox: Path) -> Place:
    start = places.plant_state(sandbox / "loose-project", "loose gating fixture")
    return Place(start, "loose gating fixture", start)


def _nested_repository_without_state(sandbox: Path) -> Place:
    outer = places.repository(sandbox / "outer", state_marker="outer gating fixture")
    return Place(places.repository(outer / "vendor" / "inner"), None)


def _below_state_outside_a_repository(sandbox: Path) -> Place:
    holder = places.plant_state(sandbox / "loose-holder", "loose gating fixture")
    start = holder / "child"
    start.mkdir()
    return Place(start, None)


def _repository_below_state_outside_it(sandbox: Path) -> Place:
    holder = places.plant_state(sandbox / "state-holder", "holder gating fixture")
    return Place(places.repository(holder / "repo"), None)


MANAGED_PLACES: dict[str, Callable[[Path], Place]] = {
    "a subdirectory of a managed project": _subdirectory,
    "a linked worktree carrying the project's state": _linked_worktree,
    "a project whose state is a link to a directory": _linked_state,
    "a nested repository carrying its own state": _nested_repository_with_state,
    "a directory outside any repository carrying state": _state_outside_a_repository,
}
UNMANAGED_PLACES: dict[str, Callable[[Path], Place]] = {
    "a nested repository without state": _nested_repository_without_state,
    "a directory outside any repository below one with state": _below_state_outside_a_repository,
    "a repository below state outside it": _repository_below_state_outside_it,
}
OUTER_MARKERS = ("outer gating fixture", "loose gating fixture", "holder gating fixture")


@pytest.fixture(params=sorted(MANAGED_PLACES))
def managed_place(request, machine) -> Place:
    return MANAGED_PLACES[request.param](machine.sandbox)


@pytest.fixture(params=sorted(UNMANAGED_PLACES))
def unmanaged_place(request, machine) -> Place:
    return UNMANAGED_PLACES[request.param](machine.sandbox)


# -- Which directories are managed ----------------------------------------------------------------


@pytest.mark.parametrize("unit", TEXT_UNITS)
def test_a_managed_start_receives_each_managed_only_text(machine, managed_place, unit):
    text = gate.session_start(machine, managed_place.start).process_text

    assert oracles.missing_statements(unit, text) == [], f"the {unit} is missing or cut"


def test_a_managed_start_receives_its_projects_decision_context(machine, managed_place):
    text = gate.session_start(machine, managed_place.start).process_text

    assert oracles.holds_decision_context(text, managed_place.marker), (
        "the governing project's decision context did not reach the session"
    )


@pytest.mark.parametrize("unit", TEXT_UNITS)
def test_an_unmanaged_start_receives_no_managed_only_text(machine, unmanaged_place, unit):
    text = gate.session_start(machine, unmanaged_place.start).process_text

    assert oracles.held_statements(unit, text) == [], f"the {unit} reached an unmanaged start"


def test_an_unmanaged_start_receives_no_decision_context_from_a_directory_above(
    machine, unmanaged_place
):
    text = gate.session_start(machine, unmanaged_place.start).process_text

    held = [m for m in OUTER_MARKERS if oracles.holds_decision_context(text, m)]

    assert held == [], f"an unmanaged start received decisions recorded above it: {held}"


# -- Every managed-only behaviour gives the same answer --------------------------------------------


@dataclass(frozen=True)
class Behaviours:
    procedures: bool
    decision_context: bool
    prompt_reminder: bool
    host_native_preamble: bool
    blacklist_template: bool


def _behaviours(machine: gate.Machine, place: Place) -> Behaviours:
    started = gate.session_start(machine, place.start)
    text = started.process_text
    template_root = place.root or place.start
    preamble = gate.spawn_start(machine, place.start, gate.HOST_NATIVE).hook_text
    return Behaviours(
        procedures=any(oracles.held_statements(u, text) for u in TEXT_UNITS),
        decision_context=any(
            oracles.holds_decision_context(text, m)
            for m in (place.marker, *OUTER_MARKERS)
            if m is not None
        ),
        prompt_reminder=bool(gate.prompt_reminder(machine, place.start).strip()),
        host_native_preamble=bool(preamble.strip()),
        blacklist_template=(template_root / places.TEMPLATE).exists()
        or (place.start / places.TEMPLATE).exists(),
    )


ALL_PLACES = {**MANAGED_PLACES, **UNMANAGED_PLACES}


@pytest.mark.parametrize("name", sorted(ALL_PLACES))
def test_every_managed_only_behaviour_is_on_or_off_together(machine, name):
    place = ALL_PLACES[name](machine.sandbox)
    expected = place.marker is not None

    observed = _behaviours(machine, place)

    assert observed == Behaviours(*(expected,) * 5), f"{name}: {observed}"


def test_a_subdirectory_session_receives_what_a_root_session_receives(machine):
    place = _subdirectory(machine.sandbox)
    tokens = {**machine.tokens(), place.start: "<start>", place.root: "<start>"}
    at_root = gate.session_start(machine, place.root).process_text

    in_subdirectory = gate.session_start(machine, place.start).process_text

    assert oracles.statements(oracles.mask(in_subdirectory, tokens)) == oracles.statements(
        oracles.mask(at_root, tokens)
    )


# -- A directory that changes kind ----------------------------------------------------------------


def test_a_directory_that_becomes_managed_gives_the_next_session_the_managed_set(machine):
    directory = places.repository(machine.sandbox / "adopting")
    before = gate.session_start(machine, directory).process_text
    places.plant_state(directory, "adopted gating fixture")

    after = gate.session_start(machine, directory).process_text

    assert not any(oracles.held_statements(u, before) for u in TEXT_UNITS), "unmanaged set first"
    assert all(oracles.missing_statements(u, after) == [] for u in TEXT_UNITS), "managed set next"
    assert oracles.holds_decision_context(after, "adopted gating fixture")


def test_a_directory_that_stops_being_managed_gives_the_next_session_the_unmanaged_set(machine):
    directory = places.repository(
        machine.sandbox / "leaving", state_marker="leaving gating fixture"
    )
    before = gate.session_start(machine, directory).process_text
    shutil.rmtree(directory / ".ai-state")

    after = gate.session_start(machine, directory).process_text

    assert oracles.holds_decision_context(before, "leaving gating fixture"), "managed set first"
    assert not any(oracles.held_statements(u, after) for u in TEXT_UNITS), "unmanaged set next"
