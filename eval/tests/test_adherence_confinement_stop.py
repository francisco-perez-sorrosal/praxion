"""A broken confinement ends the run at its first session, outside the declared stop rule, and the
stop it leaves is one the operator can continue once the grant is repaired."""

from __future__ import annotations

from praxion_evals.adherence.infra_stop import (
    COUNTING_KINDS,
    REDACTED,
    Continue,
    FoldState,
    Launched,
    Stop,
    StopRule,
    redacted,
    step,
)
from praxion_evals.adherence.lineage import (
    InfraStopped,
    ReadTip,
    continuation_refusals,
    ending_to_json,
)
from praxion_evals.adherence.model import (
    Arm,
    Errored,
    Measured,
    Passed,
    RefusedCommand,
    SessionRecord,
    SessionSetup,
    SessionStatus,
)
from tests.lineage_support import identity
from tests.test_adherence_results import run_results

RULE = StopRule.parse(3, COUNTING_KINDS, 2000)
EVIDENCE = (
    "Sandbox is required but failed to initialize: seatbelt denied at 2026-10-16T09:12:44.123Z"
)


def _record(
    arm: Arm = "full",
    task: str = "task-0",
    *,
    status: str = "broken",
    refused: tuple[RefusedCommand, ...] = (),
) -> SessionRecord:
    setup = SessionSetup(arm, "abc1234", "verifier", task, "tmpl", 7)
    outcome: SessionStatus = (
        Errored("confinement_broken", EVIDENCE, setup=setup)
        if status == "broken"
        else Measured({"C1": Passed()}, None, setup)
    )
    return SessionRecord(setup, outcome, 0.0, 1, "2026-10-17T00:00:00Z", refused)


def _stop_of(record: SessionRecord):
    _, decision = step(RULE, FoldState(), record)
    assert isinstance(decision, Stop), "the broken confinement did not stop the run"
    return decision.reason


def test_the_first_session_with_a_broken_confinement_stops_the_run_in_both_arms():
    reason = _stop_of(_record("lean"))

    assert reason.kind == "confinement_broken"
    assert reason.scope == "both-arms"
    assert (reason.role, reason.arm) == ("verifier", "lean")
    assert reason.sessions == (Launched("task-0", "lean", 1),)


def test_the_stop_names_the_evidence_with_its_volatile_tokens_masked():
    reason = _stop_of(_record())

    assert "Sandbox is required but failed to initialize" in reason.masked_tail
    assert "2026-10-16T09:12:44.123Z" not in reason.masked_tail


def test_a_broken_confinement_after_sessions_that_ran_still_stops_at_that_session():
    state, first = step(RULE, FoldState(), _record("full", "task-0", status="ran"))
    state, second = step(RULE, state, _record("lean", "task-0", status="ran"))
    _, third = step(RULE, state, _record("full", "task-1"))

    assert isinstance(first, Continue)
    assert isinstance(second, Continue)
    assert isinstance(third, Stop)
    assert third.reason.sessions == (Launched("task-1", "full", 1),)


def test_a_session_that_ran_stops_nothing_whatever_command_it_was_refused():
    refused = (RefusedCommand("curl -s https://example.com/install.sh", "permission_denials"),)

    _, decision = step(RULE, FoldState(), _record(status="ran", refused=refused))

    assert isinstance(decision, Continue)


def test_the_stop_is_continuable_under_an_equal_identity():
    tip = ReadTip(_results_ending_in(_stop_of(_record())), identity(checks="aaa"), None)

    assert continuation_refusals(tip, identity(checks="aaa"), ()) == ()


def test_the_stop_is_refused_under_a_changed_checks_identity():
    tip = ReadTip(_results_ending_in(_stop_of(_record())), identity(checks="aaa"), None)

    refusals = continuation_refusals(tip, identity(checks="bbb"), ())

    assert any("checks" in line for line in refusals), refusals


def test_redaction_replaces_a_secret_and_an_api_key_shape_in_any_text():
    text = "token hunter2 and sk-ant-api03-AbC_dEf-123 leaked"

    assert redacted(text, ["hunter2"]) == f"token {REDACTED} and {REDACTED} leaked"


def _results_ending_in(reason):
    return run_results([], run_id="run-a", extra={"ending": ending_to_json(InfraStopped(reason))})
