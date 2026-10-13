"""The adherence eval never mistakes a missing kernel for a role failure, nor a breach for noise.

It also carries, in every pilot task, a project convention written only in the
fixture's own instruction file, so a lean arm that lost that file shows as a
measured regression.
"""

from __future__ import annotations

import pytest

from tests.acceptance.drivers import lean_scoring
from tests.acceptance.drivers.kernel_sandbox import PILOT_ROLES
from tests.acceptance.drivers.lean_scoring import LeanSession


def test_a_lean_session_without_its_kernel_row_errors_its_pair_as_infrastructure() -> None:
    sessions = (
        LeanSession("task-1"),
        LeanSession("task-2", kernel_row=False),
        LeanSession("task-3"),
    )

    scoring = lean_scoring.score_lean_pairs("verifier", sessions)

    assert scoring.infrastructure_errors == {"task-2"}
    assert scoring.scored == {"task-1", "task-3"}
    assert "task-2" not in scoring.lean_failures


def test_an_isolation_breach_is_a_lean_failure_and_is_never_retried() -> None:
    sessions = (LeanSession("task-1"), LeanSession("task-2", read_user_instruction_file=True))

    scoring = lean_scoring.score_lean_pairs("verifier", sessions)

    assert "task-2" in scoring.lean_failures
    assert "task-2" not in scoring.infrastructure_errors
    assert scoring.retried == frozenset()


@pytest.mark.parametrize("role", PILOT_ROLES)
def test_a_pilot_task_writes_its_project_convention_only_in_the_fixture_instruction_file(
    role: str,
) -> None:
    fixture = lean_scoring.pilot_task_fixture(role, seed=7)

    assert fixture.convention in fixture.instructions
    assert [path for path, text in fixture.other_files.items() if fixture.convention in text] == []


@pytest.mark.parametrize("role", PILOT_ROLES)
def test_a_lean_session_that_did_not_receive_the_project_file_fails_the_convention_check(
    role: str,
) -> None:
    assert lean_scoring.convention_outcome(role, "lean", received_project_file=False) == "failed"


@pytest.mark.parametrize("arm", ["full", "lean"])
def test_the_convention_check_passes_in_either_arm_when_the_project_file_arrived(arm: str) -> None:
    assert (
        lean_scoring.convention_outcome("researcher", arm, received_project_file=True) == "passed"
    )
