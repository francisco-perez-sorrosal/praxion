"""Every session the process-adherence eval launches receives today's process text at start.

In both arms and on every task fixture, each launched session, and the role it spawns, receives
the same process text as at the base, checked by content as in a managed project (the declared
edits excepted, provisionally), and the eval's checks grade what they grade today. No real
`claude` starts: every launch is answered by the stand-in, and the reading is taken from the
launch's own working directory, configuration directory and plugin copy.
"""

from __future__ import annotations

import pytest

from tests.acceptance.drivers import adherence_launch_texts as launches
from tests.acceptance.drivers import session_start_text as gate


@pytest.fixture(scope="module")
def run(tmp_path_factory) -> launches.LaunchTexts:
    return launches.run_recording_launch_texts(tmp_path_factory.mktemp("adherence"))


def _unexplained(pairs: dict[str, tuple[str, str]]) -> dict[str, gate.Changes]:
    found = {key: gate.unexplained_changes(today, now) for key, (today, now) in pairs.items()}
    return {key: changes for key, changes in found.items() if not changes.none}


@pytest.mark.parametrize("arm", ["full", "lean"])
def test_each_launched_session_receives_todays_process_text(run, arm):
    assert _unexplained(run.session_pairs(arm)) == {}


@pytest.mark.parametrize("arm", ["full", "lean"])
def test_the_role_each_session_spawns_receives_todays_process_text(run, arm):
    assert _unexplained(run.role_pairs(arm)) == {}


def test_the_eval_grades_the_same_checks_as_today(run):
    assert run.graded_checks() == run.todays_graded_checks()
