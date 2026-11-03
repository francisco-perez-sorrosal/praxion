"""The blacklist template is written only at a managed project's root; a user's blacklist keeps
working wherever it is.

A session start in a directory that is not managed, with no user-written blacklist, changes
nothing there. A session in a subdirectory of a managed project writes no template into the
subdirectory; the template appears at the project root when the root has neither it nor a
blacklist. A user-written `.claude/praxion-rules.yaml` is honoured as today in any start
directory: the rules it names stop loading at that start, a rule that cannot be switched off
keeps loading with today's warning, and an unmanaged directory changes only as today. A managed
project root's blacklist also reaches a subdirectory session unless the subdirectory carries its
own (provisional: the specification marks this behaviour as awaiting its own spec question).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.acceptance.drivers import session_start_text as gate


@pytest.fixture(scope="module")
def template(tmp_path_factory) -> Path:
    return gate.installed_home(tmp_path_factory.mktemp("install"))


@pytest.fixture
def machine(template, tmp_path) -> gate.Machine:
    return gate.new_machine(template, tmp_path / "machine")


def _monorepo(machine: gate.Machine) -> tuple[Path, Path]:
    root = gate.repository(machine.sandbox / "monorepo", managed=True)
    subdirectory = root / "services" / "api"
    subdirectory.mkdir(parents=True)
    return root, subdirectory


def _plain_directory(machine: gate.Machine) -> Path:
    directory = machine.sandbox / "plain"
    directory.mkdir()
    return directory


def _repository_without_state(machine: gate.Machine) -> Path:
    return gate.repository(machine.sandbox / "unmanaged-repo")


# -- The template ---------------------------------------------------------------------------------


@pytest.mark.parametrize("place", [_plain_directory, _repository_without_state])
def test_a_session_start_in_an_unmanaged_directory_changes_nothing_there(machine, place):
    directory = place(machine)

    started = gate.session_start(machine, directory)

    assert started.writes == {}, f"the start wrote into an unmanaged directory: {started.writes}"


def test_a_subdirectory_session_writes_no_template_into_the_subdirectory(machine):
    _, subdirectory = _monorepo(machine)

    gate.session_start(machine, subdirectory)

    assert not (subdirectory / gate.TEMPLATE).exists()


def test_a_subdirectory_session_puts_the_template_at_the_project_root(machine):
    root, subdirectory = _monorepo(machine)

    gate.session_start(machine, subdirectory)

    assert (root / gate.TEMPLATE).is_file(), "the managed root did not receive the template"


def test_a_root_session_puts_the_template_at_the_managed_root(machine):
    root, _ = _monorepo(machine)

    gate.session_start(machine, root)

    assert (root / gate.TEMPLATE).is_file()


def test_a_managed_root_with_a_user_blacklist_gets_no_template(machine):
    root, _ = _monorepo(machine)
    gate.write_blacklist(root, ["swe/vcs/git-conventions"])

    gate.session_start(machine, root)

    assert not (root / gate.TEMPLATE).exists()


# -- A user-written blacklist in an unmanaged directory -------------------------------------------


@pytest.fixture
def blacklisted(machine) -> tuple[Path, gate.Start]:
    directory = _plain_directory(machine)
    gate.write_blacklist(directory, gate.BLACKLIST_PATTERNS)
    return directory, gate.session_start(machine, directory)


def test_a_blacklisted_rule_stops_loading_in_an_unmanaged_directory(blacklisted):
    _, started = blacklisted

    held = gate.held_statements(gate.GIT_CONVENTIONS, started.process_text)

    assert held == [], f"the blacklisted git conventions still arrive ({len(held)} statements)"


def test_a_blacklisted_path_scoped_rule_is_excluded_as_today(blacklisted, machine):
    directory, _ = blacklisted
    settings = gate.mask((directory / ".claude" / "settings.json").read_text(), machine.tokens())

    assert json.loads(settings) == json.loads(gate.base_reading("unmanaged-blacklist-settings"))


def test_a_core_rule_in_a_blacklist_keeps_loading_with_todays_warning(blacklisted, machine):
    _, started = blacklisted
    warning = gate.base_reading("unmanaged-blacklist-warnings")

    assert gate.missing_statements(gate.BEHAVIOURAL_CONTRACT, started.process_text) == []
    assert warning, "the frozen reading holds no core-rule warning"
    assert warning in gate.mask(started.warnings, machine.tokens())


def test_honouring_a_blacklist_changes_an_unmanaged_directory_only_as_today(blacklisted, machine):
    _, started = blacklisted

    observed = {
        path: [gate.mask(str(side), machine.tokens()) for side in pair]
        for path, pair in started.writes.items()
    }

    assert observed == json.loads(gate.base_reading("unmanaged-blacklist-writes"))


def test_a_managed_roots_blacklist_switches_off_a_managed_only_procedure(machine):
    root, _ = _monorepo(machine)
    gate.write_blacklist(root, ["swe/agent-model-routing-resident"])

    text = gate.session_start(machine, root).process_text

    assert gate.held_statements(gate.ROUTING_RESIDENT, text) == []


# -- A managed root's blacklist and its subdirectories --------------------------------------------


def test_a_subdirectory_session_honours_the_project_roots_blacklist(machine):
    root, subdirectory = _monorepo(machine)
    gate.write_blacklist(root, ["swe/vcs/git-conventions"])

    text = gate.session_start(machine, subdirectory).process_text

    assert gate.held_statements(gate.GIT_CONVENTIONS, text) == [], "the root's opt-out was ignored"


def test_a_subdirectorys_own_blacklist_wins_over_the_roots(machine):
    root, subdirectory = _monorepo(machine)
    gate.write_blacklist(root, ["swe/vcs/git-conventions"])
    gate.write_blacklist(subdirectory, ["swe/agent-model-routing-resident"])

    text = gate.session_start(machine, subdirectory).process_text

    assert gate.missing_statements(gate.GIT_CONVENTIONS, text) == [], "the root's list applied"
    assert gate.held_statements(gate.ROUTING_RESIDENT, text) == [], "its own list was ignored"
