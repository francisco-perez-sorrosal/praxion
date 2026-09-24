"""Behavioral tests for the live scenario runner's outcome/result types.

Covers `praxion_evals.live.results`: the `Outcome` (`Passed` | `Failed` |
`Errored`) and `Capture` (`Captured` | `NotElicited`) sum types, the pure
aggregation functions that compute a scenario's pass rate and the canary
`lowered` verdict, and JSON serialization of a per-session record against
the documented `schema_version: 1` baseline JSON shape.

An errored session is never graded — `Errored` carries no `recorded` field,
so a caller cannot accidentally pass one to a grader. A not-elicited capture
maps straight to `Failed(kind="not_elicited")`, never to a grader either.

All production imports are deferred inside each test body so pytest
collection succeeds before the `praxion_evals.live` package exists
(RED-state handshake).
"""

from __future__ import annotations

import json

# ---------------------------------------------------------------------------
# Outcome / Capture — sum types construct and hold the invariant that an
# errored or not-elicited session never carries a graded `recorded` value
# ---------------------------------------------------------------------------


def test_passed_outcome_carries_recorded_value_and_findings():
    from praxion_evals.live.results import Passed

    outcome = Passed(recorded={"tier": "standard"}, findings=("matched",))

    assert outcome.recorded == {"tier": "standard"}
    assert outcome.findings == ("matched",)


def test_failed_outcome_distinguishes_graded_from_not_elicited():
    from praxion_evals.live.results import Failed

    graded = Failed(kind="graded", recorded="git commit -m x", findings=("missing -A guard",))
    not_elicited = Failed(kind="not_elicited", recorded=None, findings=())

    assert graded.kind == "graded"
    assert not_elicited.kind == "not_elicited"
    assert not_elicited.recorded is None


def test_errored_outcome_has_no_recorded_field():
    """The type itself makes 'grade an errored session' unrepresentable —
    there is no `recorded` attribute to accidentally read."""
    from praxion_evals.live.results import Errored

    outcome = Errored(kind="isolation_breach", detail="9 extra plugins, 5 MCP servers")

    assert outcome.kind == "isolation_breach"
    assert not hasattr(outcome, "recorded")


def test_not_elicited_capture_never_needs_a_grader_to_become_a_failed_outcome():
    """A `NotElicited` capture converts straight to
    `Failed(kind="not_elicited", recorded=None)` — the conversion function
    must not accept a grader argument, because none is ever called."""
    from praxion_evals.live.results import Failed, NotElicited, capture_to_outcome

    capture = NotElicited(reason="no staging command in any Bash tool_use", diagnostics={})

    outcome = capture_to_outcome(capture)

    assert outcome == Failed(
        kind="not_elicited",
        recorded=None,
        findings=(),
        reason="no staging command in any Bash tool_use",
    )


def test_a_not_elicited_failure_cannot_carry_a_recorded_value():
    """Nothing was elicited, so there is nothing recorded to carry."""
    import pytest

    from praxion_evals.live.results import Failed

    with pytest.raises(ValueError, match="not_elicited"):
        Failed(kind="not_elicited", recorded="git add -A", findings=())


def test_a_graded_failure_cannot_carry_a_not_elicited_reason():
    import pytest

    from praxion_evals.live.results import Failed

    with pytest.raises(ValueError, match="graded"):
        Failed(kind="graded", recorded="git add -A", findings=("f",), reason="never elicited")


def test_not_elicited_session_record_carries_the_reason():
    """The operator must see *why* a session elicited nothing."""
    from praxion_evals.live.results import NotElicited, capture_to_outcome, to_session_record

    outcome = capture_to_outcome(NotElicited(reason="no ADR file created", diagnostics={}))

    record = to_session_record(outcome, repeat=1)

    assert record["fail_kind"] == "not_elicited"
    assert record["reason"] == "no ADR file created"
    assert record["recorded"] is None


# ---------------------------------------------------------------------------
# Aggregation legal states
# ---------------------------------------------------------------------------


def test_pass_rate_is_none_only_when_pass_plus_fail_is_zero():
    from praxion_evals.live.results import compute_pass_rate

    assert compute_pass_rate(passed=0, failed=0) is None
    assert compute_pass_rate(passed=2, failed=1) == 2 / 3
    assert compute_pass_rate(passed=0, failed=3) == 0.0
    assert compute_pass_rate(passed=3, failed=0) == 1.0


def test_pass_rate_excludes_errors_from_the_denominator():
    """An all-error case (three sessions errored, none graded) must read as
    `pass_rate is None`, exactly like the zero-session case — errors carry
    no measurement, per the outcome algebra."""
    from praxion_evals.live.results import compute_pass_rate

    assert compute_pass_rate(passed=0, failed=0) is None


def test_lowered_is_none_when_either_rate_is_none():
    from praxion_evals.live.results import compute_lowered

    assert compute_lowered(head_rate=None, canary_rate=0.4) is None
    assert compute_lowered(head_rate=0.6, canary_rate=None) is None
    assert compute_lowered(head_rate=None, canary_rate=None) is None


def test_lowered_is_strict_less_than_not_less_or_equal():
    """An unmoved guard (canary_rate == head_rate) is honestly reported as
    NOT lowered — the canary is never tuned after the fact to claim a
    delta that k=3 did not actually produce."""
    from praxion_evals.live.results import compute_lowered

    assert compute_lowered(head_rate=0.6, canary_rate=0.4) is True
    assert compute_lowered(head_rate=0.6, canary_rate=0.6) is False
    assert compute_lowered(head_rate=0.4, canary_rate=0.6) is False


# ---------------------------------------------------------------------------
# JSON round-trip against the schema_version: 1 per-session record shape
# ---------------------------------------------------------------------------


def test_passed_session_record_matches_the_documented_shape():
    from praxion_evals.live.results import Passed, to_session_record

    record = to_session_record(
        Passed(recorded={"tier": "standard"}, findings=("matched",)), repeat=1
    )

    assert record["repeat"] == 1
    assert record["outcome"] == "pass"
    assert record["recorded"] == {"tier": "standard"}
    assert record["findings"] == ["matched"]
    assert "fail_kind" not in record
    assert "error_kind" not in record


def test_failed_session_record_carries_fail_kind_and_a_possibly_null_recorded():
    from praxion_evals.live.results import Failed, to_session_record

    graded = to_session_record(
        Failed(kind="graded", recorded="git add x", findings=("f",)), repeat=2
    )
    not_elicited = to_session_record(
        Failed(kind="not_elicited", recorded=None, findings=()), repeat=3
    )

    assert graded["outcome"] == "fail"
    assert graded["fail_kind"] == "graded"
    assert graded["recorded"] == "git add x"
    assert not_elicited["fail_kind"] == "not_elicited"
    assert not_elicited["recorded"] is None
    assert graded["findings"] == ["f"]
    assert not_elicited["findings"] == []
    assert "reason" not in graded


def test_errored_session_record_carries_error_kind_and_detail_but_no_recorded_key():
    """Per the schema example, an error record has no `recorded` key at
    all — not a `recorded: null`, an absent key — because no capture was
    ever attempted."""
    from praxion_evals.live.results import Errored, to_session_record

    record = to_session_record(Errored(kind="result_error", detail="max budget exceeded"), repeat=3)

    assert record["outcome"] == "error"
    assert record["error_kind"] == "result_error"
    assert record["detail"] == "max budget exceeded"
    assert "recorded" not in record


def test_every_outcome_kind_round_trips_through_json_unchanged():
    from praxion_evals.live.results import Errored, Failed, Passed, to_session_record

    records = [
        to_session_record(Passed(recorded={"a": 1}, findings=()), repeat=1),
        to_session_record(Failed(kind="graded", recorded=None, findings=("x",)), repeat=2),
        to_session_record(Errored(kind="timeout", detail="900s exceeded"), repeat=3),
    ]

    round_tripped = json.loads(json.dumps(records))

    assert round_tripped == records
