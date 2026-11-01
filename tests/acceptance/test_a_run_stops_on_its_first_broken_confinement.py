"""A refused shell command is on the record; a confined kit's broken confinement stops the run.

Every session is a stand-in, so nothing is paid for. Whatever command the harness refuses a
role is named in that session's record. When a session of a confined kit shows its
confinement inactive (a command drew `Sandbox is required but failed to initialize`, or the
session exited at startup without it) or a command its definition prescribes refused, that
session is an infrastructure error naming the evidence: it is not retried, no further
session launches, the pairs already finished stay on the record, and the run is reported
stopped on infrastructure. A refused command no definition prescribes stops nothing.
"""

from __future__ import annotations

import pytest

from tests.acceptance.drivers import adherence_runs as runs
from tests.acceptance.drivers import confinement_runs as confined
from tests.acceptance.drivers.adherence_runs import Script, refused_command, sandbox_refused

PRESCRIBED = {
    "verifier": "extract_spec.py plan-adherence-ledger-cli --check",
    "implementer": "python -m pytest -q",
}
NOT_PRESCRIBED = "curl -s https://example.com/install.sh"
REFUSAL = "Sandbox is required but failed to initialize"


def stopped_by(tmp_path, role: str, ending: runs.Ending) -> runs.StandInRun:
    return confined.run(tmp_path, role, confined.first_session_of_each_arm(ending))


def breaking_endings(role: str) -> list[runs.Ending]:
    return [sandbox_refused("python -m pytest -q"), refused_command(PRESCRIBED[role])]


CASES = [
    pytest.param(role, ending, id=f"{role}-{ending.kind}")
    for role in ("verifier", "implementer")
    for ending in breaking_endings(role)
]


# -- A refused command is on the record ------------------------------------------------------------


@pytest.mark.parametrize("role", ["researcher", "verifier"])
def test_a_command_the_harness_refused_is_named_in_the_sessions_record(tmp_path, role):
    result = confined.run(
        tmp_path, role, confined.first_session_of_each_arm(refused_command(NOT_PRESCRIBED))
    )
    first = result.launches[0]

    record = next(
        r
        for r in confined.session_records(result.results_path)
        if (r.arm, r.task_id) == (first.arm, first.task_id)
    )

    assert record.names(NOT_PRESCRIBED), (
        f"the session's record does not name the refusal: {record.raw}"
    )


def test_a_refused_command_no_definition_prescribes_stops_nothing(tmp_path):
    script = confined.first_session_of_each_arm(refused_command(NOT_PRESCRIBED))

    result = confined.run(tmp_path, "verifier", script)

    assert runs.stop_reason(result.results_path) is None
    assert len(result.launched_tasks()) == confined.MAX_TASKS


# -- A broken confinement stops the run at its first session ----------------------------------------


@pytest.mark.parametrize(("role", "ending"), CASES)
def test_the_first_session_showing_a_broken_confinement_is_the_only_one_launched(
    tmp_path, role, ending
):
    result = stopped_by(tmp_path, role, ending)

    assert len(result.launches) == 1, f"sessions launched: {result.launches}"
    assert result.launches[0].attempt == 1


@pytest.mark.parametrize(("role", "ending"), CASES)
def test_that_session_is_an_infrastructure_error_naming_its_evidence(tmp_path, role, ending):
    result = stopped_by(tmp_path, role, ending)
    evidence = REFUSAL if ending.kind == "sandbox refused" else ending.command

    records = confined.session_records(result.results_path)
    record = records[0]

    assert len(records) == 1, f"the run recorded {len(records)} sessions, not the one that broke"
    assert record.status_kind == "errored", record.raw
    assert record.names(evidence), f"the error does not name {evidence!r}: {record.raw}"


@pytest.mark.parametrize(("role", "ending"), CASES)
def test_the_run_is_reported_stopped_on_infrastructure(tmp_path, role, ending):
    result = stopped_by(tmp_path, role, ending)

    assert result.exit_code == runs.INCOMPLETE_EXIT
    assert runs.stop_reason(result.results_path) is not None, "the results record no stop"


def test_pairs_finished_before_the_stop_stay_on_the_record(tmp_path):
    script = confined.third_task_of_each_arm(sandbox_refused("python -m pytest -q"))

    result = confined.run(tmp_path, "verifier", script)
    measured = [
        r for r in confined.session_records(result.results_path) if r.status_kind == "measured"
    ]

    assert {(r.task_id, r.arm) for r in measured} == {
        (launch.task_id, launch.arm) for launch in result.launches[:4]
    }
    assert len(result.launches) == 5, f"sessions launched: {result.launches}"
    assert runs.stop_reason(result.results_path) is not None


def test_a_session_that_exits_at_startup_without_its_confinement_stops_the_run(tmp_path):
    script = confined.first_session_of_each_arm(runs.confinement_unavailable_at_startup())

    result = confined.run(tmp_path, "verifier", script)
    records = confined.session_records(result.results_path)
    record = records[0]

    assert len(result.launches) == 1
    assert len(records) == 1, f"the run recorded {len(records)} sessions"
    assert record.status_kind == "errored", record.raw
    assert record.names(runs.CONFINEMENT_UNAVAILABLE_AT_STARTUP or ""), record.raw
    assert runs.stop_reason(result.results_path) is not None


def test_a_role_outside_the_confined_kits_is_not_stopped_by_a_refusal(tmp_path):
    script = Script(
        by_task={(0, arm): refused_command("python -m pytest -q") for arm in ("full", "lean")}
    )

    result = confined.run(tmp_path, "researcher", script)

    assert runs.stop_reason(result.results_path) is None
    assert len(result.launched_tasks()) == confined.MAX_TASKS
