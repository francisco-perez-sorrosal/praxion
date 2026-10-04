"""Tests for the pure verdict policy (``scripts/_step_verdict.py``).

Four groups: a table pinning the verdict of every branch of the file-and-test
logic, the check-first table (including the golden bad
case: a claimed step whose check is unmet is never verified complete), the
attempt cap over every verdict, and the invariants of the one constructor.
Everything here is pure: no file, no process, no clock.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import _step_verdict as verdicts  # noqa: E402
from _loop_fields import (  # noqa: E402
    Attempt,
    Met,
    NoResult,
    Unmet,
    UnmetExpectation,
    UnreadableCheck,
)

STEP = f"Step {1}"
EARLIER = f"Step {0}"
FILES = ["a.py", "b.py"]
NO_AGENT = {"agent_stop_seen": False, "last_write": None}
STOPPED = {"agent_stop_seen": True, "last_write": "a.py"}


def evidence(**overrides: Any) -> verdicts.StepEvidence:
    """A step whose two files both changed with green tests, claim not yet complete."""
    fields: dict[str, Any] = {
        "step_id": STEP,
        "claim": "PENDING",
        "files": list(FILES),
        "changed": list(FILES),
        "unchanged": [],
        "test_status": "green",
        "tier2": dict(NO_AGENT),
    }
    return verdicts.StepEvidence(**{**fields, **overrides})


def untouched(**overrides: Any) -> verdicts.StepEvidence:
    """The same step with nothing changed yet."""
    return evidence(changed=[], unchanged=list(FILES), **overrides)


def half_done(**overrides: Any) -> verdicts.StepEvidence:
    """The same step with one of its two files changed."""
    return evidence(changed=["a.py"], unchanged=["b.py"], **overrides)


def unmet(key: str, op: str, expected: int, observed: int) -> Unmet:
    return Unmet((UnmetExpectation(key, op, expected, observed),))


def classify(ev: verdicts.StepEvidence, check=None, attempt: verdicts.AttemptRecord = None) -> dict:
    return verdicts.classify_step(ev, check, attempt)


# ---------------------------------------------------------------------------
# Pinned: every branch of the file-and-test logic, with explicit expectations
# ---------------------------------------------------------------------------

_NO_FILES = {"files": [], "changed": [], "unchanged": []}

PARITY_CASES = [
    pytest.param(
        evidence(claim="COMPLETE", **_NO_FILES),
        (
            "unknown",
            "step declares no Files: and cannot be tied to git changes — WIP claim=COMPLETE; surfaced for human verification",
            [],
            False,
        ),
        id="complete-claim-with-no-files",
    ),
    pytest.param(
        evidence(**_NO_FILES),
        ("pending", "step not started and declares no Files:", [], False),
        id="unclaimed-with-no-files",
    ),
    pytest.param(
        evidence(claim="COMPLETE", earlier_declarers=[EARLIER], **_NO_FILES),
        (
            "unknown",
            f"every declared file is also declared by {EARLIER} (earlier) — WIP claim=COMPLETE; "
            "surfaced for human verification",
            [],
            False,
        ),
        id="every-file-absorbed-by-an-earlier-declarer",
    ),
    pytest.param(
        evidence(),
        (
            "verified-complete",
            "all 2 declared file(s) changed; tests=green; WIP not marked COMPLETE — auto-mark on resume",
            [],
            True,
        ),
        id="all-changed-unclaimed-needs-the-mark",
    ),
    pytest.param(
        evidence(claim="COMPLETE", test_status="none"),
        ("verified-complete", "all 2 declared file(s) changed; tests=none", [], False),
        id="all-changed-claimed-needs-no-mark",
    ),
    pytest.param(
        evidence(claim="COMPLETE", test_status="red"),
        ("mismatch", "WIP=[COMPLETE] but tests red: a.py, b.py", ["a.py", "b.py"], False),
        id="claimed-with-red-tests",
    ),
    pytest.param(
        half_done(claim="COMPLETE"),
        (
            "mismatch",
            "WIP=[COMPLETE] but 1 declared file(s) show no git change: b.py",
            ["b.py"],
            False,
        ),
        id="claimed-with-an-unchanged-file",
    ),
    pytest.param(
        untouched(),
        ("pending", "step not started (no file changes)", ["a.py", "b.py"], False),
        id="unclaimed-nothing-changed",
    ),
    pytest.param(
        half_done(tier2=dict(STOPPED)),
        (
            "partial@a.py",
            "1 file(s) changed; agent stopped after a.py; remainder: b.py",
            ["b.py"],
            False,
        ),
        id="unclaimed-agent-stopped-mid-work",
    ),
    pytest.param(
        half_done(),
        (
            "in-flight",
            "1 file(s) changed, no terminal marker — possibly still running",
            ["b.py"],
            False,
        ),
        id="unclaimed-changed-no-stop-seen",
    ),
    pytest.param(
        evidence(test_status="red"),
        ("in-flight", "2 file(s) changed, no terminal marker — possibly still running", [], False),
        id="unclaimed-all-changed-with-red-tests",
    ),
    pytest.param(
        evidence(mutation_block="no Mutation: line recorded"),
        ("blocked", None, [], False),
        id="all-changed-with-a-mutation-blocker",
    ),
]


@pytest.mark.parametrize(("ev", "expected"), PARITY_CASES)
def test_the_file_and_test_logic_yields_the_pinned_verdict_for_each_branch(ev, expected) -> None:
    verdict, text, scope, needs_mark = expected

    result = classify(ev)

    assert result["verdict"] == verdict
    assert result["resume_scope"] == scope
    assert result["needs_mark"] is needs_mark
    if text is not None:
        assert result["evidence"] == text
    else:
        assert "mutation: on, no Mutation: line recorded" in result["evidence"]


def test_tier_one_names_the_files_changed_and_unchanged_and_the_test_status() -> None:
    result = classify(half_done(test_status="red"))

    assert result["tier1"] == {
        "files_changed": ["a.py"],
        "files_unchanged": ["b.py"],
        "tests": "red",
    }


# ---------------------------------------------------------------------------
# Check first: a declared check decides
# ---------------------------------------------------------------------------


def test_a_met_check_completes_a_step_the_files_alone_would_not() -> None:
    result = classify(untouched(), Met())

    assert result["verdict"] == "verified-complete"
    assert result["needs_mark"] is True
    assert (result["decided_by"], result["outcome_source"]) == ("check", "recorded")


def test_a_met_check_on_a_step_already_marked_needs_no_mark() -> None:
    result = classify(evidence(claim="COMPLETE"), Met())

    assert (result["verdict"], result["needs_mark"]) == ("verified-complete", False)


@pytest.mark.parametrize("claim", ["PENDING", "COMPLETE"])
def test_a_met_check_does_not_lift_a_completion_blocker(claim: str) -> None:
    result = classify(evidence(claim=claim, mutation_block="no Mutation: line recorded"), Met())

    assert result["verdict"] == "blocked"
    assert result["decided_by"] == "check"


@pytest.mark.parametrize(
    ("outcome", "text"),
    [
        (unmet("pending", "=", 0, 2), "pending=: expected =0, observed 2"),
        (unmet("pass", ">=", 6, 4), "pass=: expected >=6, observed 4"),
        (unmet("fail", "=", 0, 2), "fail=: expected =0, observed 2"),
        (unmet("skip", "=", 0, 1), "skip=: expected =0, observed 1"),
        (
            Unmet((UnmetExpectation("pass", ">=", 6, 4), UnmetExpectation("pending", "=", 0, 3))),
            "pass=: expected >=6, observed 4; pending=: expected =0, observed 3",
        ),
    ],
    ids=["pending", "pass", "fail", "skip", "two-keys"],
)
def test_a_claimed_step_with_an_unmet_check_is_a_mismatch_naming_each_unmet_key(
    outcome: Unmet, text: str
) -> None:
    result = classify(evidence(claim="COMPLETE"), outcome)

    assert result["verdict"] == "mismatch"
    assert result["evidence"] == f"WIP=[COMPLETE] but check unmet: {text}"
    assert result["resume_scope"] == FILES


def test_a_claimed_step_with_no_recorded_result_is_a_mismatch_saying_so() -> None:
    result = classify(evidence(claim="COMPLETE"), NoResult(f"no Result: recorded for {STEP}"))

    assert result["verdict"] == "mismatch"
    assert result["evidence"] == f"WIP=[COMPLETE] but no Result: recorded for {STEP}"
    assert (result["decided_by"], result["outcome_source"]) == ("check", "recorded")


def test_an_unclaimed_step_with_an_unmet_check_keeps_the_partial_and_in_flight_logic() -> None:
    outcome = unmet("pass", ">=", 6, 4)

    assert classify(half_done(tier2=dict(STOPPED)), outcome)["verdict"] == "partial@a.py"
    assert classify(half_done(), outcome)["verdict"] == "in-flight"


def test_an_unclaimed_untouched_step_with_an_unmet_check_is_pending_and_decided_by_nothing() -> (
    None
):
    result = classify(untouched(), NoResult("no Result: recorded"))

    assert (result["verdict"], result["decided_by"]) == ("pending", "none")
    assert "outcome_source" not in result


def test_an_unreadable_check_is_unknown_and_names_the_check() -> None:
    check = UnreadableCheck("missing required key(s): fail", "Check: `x` expects pass>=1")

    result = classify(evidence(claim="COMPLETE"), check)

    assert result["verdict"] == "unknown"
    assert "check cannot be read (missing required key(s): fail)" in result["evidence"]
    assert "Check: `x` expects pass>=1" in result["evidence"]
    assert result["decided_by"] == "check"
    assert "outcome_source" not in result


# ---------------------------------------------------------------------------
# The golden bad case: a claim never outranks a failed check
# ---------------------------------------------------------------------------

NOT_MET = [
    pytest.param(unmet("pass", ">=", 6, 4), id="unmet"),
    pytest.param(NoResult("no Result: recorded"), id="no-result"),
    pytest.param(UnreadableCheck("the command is empty", "Check: `` expects"), id="unreadable"),
]


@pytest.mark.parametrize("check", NOT_MET)
@pytest.mark.parametrize("claim", ["COMPLETE", "PENDING", "IN-PROGRESS", "AMBIGUOUS"])
def test_a_step_whose_check_is_not_met_is_never_verified_complete(claim: str, check) -> None:
    # Every file changed and the tests green: the file logic alone would say complete.
    result = classify(evidence(claim=claim), check)

    assert result["verdict"] != "verified-complete"
    assert result["needs_mark"] is False


def test_the_same_step_without_a_check_is_verified_complete_by_the_files() -> None:
    assert classify(evidence(claim="COMPLETE"))["verdict"] == "verified-complete"


# ---------------------------------------------------------------------------
# The attempt cap
# ---------------------------------------------------------------------------

NON_COMPLETE = [
    pytest.param(half_done(), None, id="in-flight"),
    pytest.param(half_done(tier2=dict(STOPPED)), None, id="partial"),
    pytest.param(half_done(claim="COMPLETE"), None, id="mismatch"),
    pytest.param(
        evidence(claim="COMPLETE", files=[], changed=[], unchanged=[]), None, id="unknown"
    ),
    pytest.param(untouched(), None, id="pending"),
    pytest.param(evidence(mutation_block="no Mutation: line recorded"), None, id="blocked"),
    pytest.param(evidence(claim="COMPLETE"), unmet("pass", ">=", 6, 4), id="unmet-check"),
]


@pytest.mark.parametrize(("ev", "check"), NON_COMPLETE)
def test_a_step_at_the_cap_goes_to_a_human_whatever_it_was(ev, check) -> None:
    underlying = classify(ev, check)

    capped = classify(ev, check, Attempt(2))

    assert capped["verdict"] == "attempts-exhausted"
    assert capped["verdict"] in verdicts.HUMAN_VERDICTS
    assert (
        f"underlying verdict {underlying['verdict']}: {underlying['evidence']}"
        in capped["evidence"]
    )
    assert capped["attempt"] == 2


@pytest.mark.parametrize(("ev", "check"), NON_COMPLETE)
def test_a_step_below_the_cap_is_classified_as_before(ev, check) -> None:
    below = classify(ev, check, Attempt(1))

    assert below["verdict"] == classify(ev, check)["verdict"]
    assert below["attempt"] == 1


def test_a_verified_complete_step_is_untouched_by_the_cap() -> None:
    result = classify(evidence(), Met(), Attempt(3))

    assert (result["verdict"], result["attempt"]) == ("verified-complete", 3)


def test_the_replan_request_is_carried_in_the_evidence() -> None:
    result = classify(half_done(), None, Attempt(2, "the first run hit the turn cap"))

    assert "replan requested: the first run hit the turn cap" in result["evidence"]


def test_a_missing_replan_request_is_said_not_omitted() -> None:
    assert "no replan request recorded" in classify(half_done(), None, Attempt(2))["evidence"]


def test_the_cap_keeps_the_resume_scope_of_the_verdict_it_replaced() -> None:
    assert classify(half_done(), None, Attempt(2))["resume_scope"] == ["b.py"]


# ---------------------------------------------------------------------------
# The one constructor: stamps follow from its inputs
# ---------------------------------------------------------------------------


def test_a_legacy_step_is_decided_by_the_fallback_and_carries_no_optional_key() -> None:
    result = classify(evidence())

    assert result["decided_by"] == "fallback"
    assert "outcome_source" not in result
    assert "attempt" not in result


def test_a_step_that_nothing_decided_is_decided_by_none_exactly_when_pending() -> None:
    cases = [classify(ev) for ev in (untouched(), evidence(files=[], changed=[], unchanged=[]))]

    assert [(c["verdict"], c["decided_by"]) for c in cases] == [("pending", "none")] * 2
    assert classify(half_done())["decided_by"] == "fallback"


def test_the_cap_over_a_pending_step_is_still_decided_by_none() -> None:
    result = classify(untouched(), None, Attempt(2))

    assert (result["verdict"], result["decided_by"]) == ("attempts-exhausted", "none")


def test_the_cap_over_a_checked_step_is_still_decided_by_the_check() -> None:
    result = classify(evidence(claim="COMPLETE"), unmet("pass", ">=", 6, 4), Attempt(2))

    assert (result["decided_by"], result["outcome_source"]) == ("check", "recorded")


def test_an_outcome_source_appears_only_when_a_check_outcome_decided() -> None:
    cases = [
        classify(evidence(claim="COMPLETE"), outcome)
        for outcome in (Met(), unmet("fail", "=", 0, 1), NoResult("none"))
    ]
    others = [classify(evidence()), classify(evidence(), UnreadableCheck("r", "l"))]

    assert all(c["outcome_source"] == "recorded" for c in cases)
    assert all("outcome_source" not in c for c in others)


def test_no_optional_key_is_ever_null() -> None:
    results = [classify(ev, check, attempt) for ev, check in ((evidence(), Met()), (untouched(), None)) for attempt in (None, Attempt(2))]  # fmt: skip

    assert [key for r in results for key, value in r.items() if value is None] == []


def test_a_cap_verdict_must_carry_the_verdict_it_replaced_and_only_it_may() -> None:
    with pytest.raises(ValueError, match="attempts-exhausted"):
        verdicts.Decision("attempts-exhausted", "text", [])
    with pytest.raises(ValueError, match="attempts-exhausted"):
        verdicts.Decision("pending", "text", [], underlying="in-flight")


def test_every_verdict_the_policy_produces_is_a_listed_word() -> None:
    scenarios = [(case.values[0], None) for case in PARITY_CASES]
    scenarios += [(case.values[0], case.values[1]) for case in NON_COMPLETE]
    produced = {
        classify(ev, check, attempt)["verdict"].split("@")[0]
        for ev, check in scenarios
        for attempt in (None, Attempt(2))
    }

    assert produced <= set(verdicts.VERDICT_WORDS)
    assert {"attempts-exhausted", "verified-complete", "partial", "blocked"} <= produced


def test_the_verdicts_a_human_must_decide_are_unknown_blocked_and_attempts_exhausted() -> None:
    assert verdicts.HUMAN_VERDICTS == ("unknown", "blocked", "attempts-exhausted")
    assert set(verdicts.HUMAN_VERDICTS) <= set(verdicts.VERDICT_WORDS)


def test_classifying_leaves_the_evidence_it_was_given_unchanged() -> None:
    ev = half_done(tier2=dict(STOPPED))
    before = (list(ev.files), list(ev.changed), list(ev.unchanged), dict(ev.tier2))

    classify(ev, unmet("pass", ">=", 6, 4), Attempt(2))

    assert (ev.files, ev.changed, ev.unchanged, ev.tier2) == before


# ---------------------------------------------------------------------------
# Exact wording the readers of the evidence depend on
# ---------------------------------------------------------------------------


def test_a_met_check_says_what_met_it_and_whether_the_mark_is_owed() -> None:
    owed = classify(untouched(), Met())["evidence"]
    marked = classify(evidence(claim="COMPLETE"), Met())["evidence"]

    assert owed == (
        "declared check met by the result recorded for the step; "
        "WIP not marked COMPLETE — auto-mark on resume"
    )
    assert marked == "declared check met by the result recorded for the step"


def test_a_blocked_step_names_the_missing_reading_and_the_two_ways_out() -> None:
    result = classify(evidence(mutation_block="no Mutation: line recorded"))

    assert result["evidence"] == (
        f"{STEP}: mutation: on, no Mutation: line recorded; restore the sensor "
        "(environment, network) and re-run it, or amend the plan to drop "
        "the tag with a recorded reason"
    )
    assert (result["needs_mark"], result["resume_scope"]) == (False, [])


def test_an_unreadable_check_is_worded_for_the_person_who_must_fix_it() -> None:
    check = UnreadableCheck("the command is empty", "Check: `` expects pass>=1 fail=0")

    assert classify(evidence(claim="COMPLETE"), check)["evidence"] == (
        "the step's declared check cannot be read (the command is empty): "
        "Check: `` expects pass>=1 fail=0 — WIP claim=COMPLETE; surfaced for human verification"
    )


def test_the_cap_evidence_leads_with_the_attempts_used_and_the_cap() -> None:
    result = classify(untouched(), None, Attempt(3, "split the step"))

    assert result["evidence"] == (
        "3 fresh attempt(s) used (cap 2) without verified completion; "
        "replan requested: split the step; "
        "underlying verdict pending: step not started (no file changes)"
    )


def test_a_claimed_step_with_an_unmet_check_resumes_only_the_files_not_yet_changed() -> None:
    result = classify(half_done(claim="COMPLETE"), unmet("pass", ">=", 6, 4))

    assert result["resume_scope"] == ["b.py"]


def test_a_step_whose_files_were_all_absorbed_by_earlier_steps_names_every_one() -> None:
    declarers = [STEP, EARLIER]

    pending = classify(evidence(earlier_declarers=declarers, **_NO_FILES))
    unknown = classify(evidence(claim="COMPLETE", earlier_declarers=declarers, **_NO_FILES))

    assert pending["evidence"] == (
        f"every declared file is also declared by {STEP}, {EARLIER} (earlier) — WIP claim=PENDING"
    )
    assert unknown["evidence"].endswith("WIP claim=COMPLETE; surfaced for human verification")


def test_an_agent_that_stopped_without_a_last_write_is_partial_at_an_unknown_point() -> None:
    stopped = {"agent_stop_seen": True, "last_write": None}

    result = classify(half_done(tier2=stopped))

    assert result["verdict"] == "partial@?"
    assert result["evidence"] == "1 file(s) changed; agent stopped after ?; remainder: b.py"


def test_the_remainder_of_a_stopped_agent_lists_every_unchanged_file() -> None:
    result = classify(
        evidence(
            files=["a.py", "b.py", "c.py"],
            changed=["a.py"],
            unchanged=["b.py", "c.py"],
            tier2=dict(STOPPED),
        )
    )

    assert result["evidence"].endswith("remainder: b.py, c.py")
    assert result["resume_scope"] == ["b.py", "c.py"]


def test_the_cap_error_names_the_rule_it_enforces() -> None:
    with pytest.raises(ValueError, match="^attempts-exhausted carries the verdict it replaced"):
        verdicts.Decision("attempts-exhausted", "text", [])


def test_an_unreadable_check_has_nothing_to_resume_and_nothing_to_mark() -> None:
    result = classify(evidence(), UnreadableCheck("the command is empty", "Check: ``"))

    assert (result["resume_scope"], result["needs_mark"]) == ([], False)


def test_a_blank_replan_request_reads_as_none_recorded() -> None:
    result = classify(half_done(), None, Attempt(2, ""))

    assert "no replan request recorded" in result["evidence"]


def test_the_cap_evidence_without_a_replan_request_says_so_between_the_two_halves() -> None:
    result = classify(untouched(), None, Attempt(2))

    assert result["evidence"] == (
        "2 fresh attempt(s) used (cap 2) without verified completion; "
        "no replan request recorded; "
        "underlying verdict pending: step not started (no file changes)"
    )


# ---------------------------------------------------------------------------
# The evidence's own invariant, and an attempt record that cannot be read
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "overrides",
    [
        {"changed": ["a.py"], "unchanged": []},
        {"changed": ["a.py", "b.py"], "unchanged": ["a.py"]},
        {"changed": ["a.py", "z.py"], "unchanged": ["b.py"]},
    ],
    ids=["a-file-in-neither", "a-file-in-both", "a-file-not-declared"],
)
def test_changed_and_unchanged_must_partition_the_files(overrides) -> None:
    with pytest.raises(
        ValueError, match=r"^changed and unchanged must partition the step's files$"
    ):
        evidence(**overrides)


UNREADABLE = verdicts.UnreadableAttempts("expected `Step <id> count=<n>` and an optional replan")


@pytest.mark.parametrize(
    ("ev", "check", "underlying"),
    [
        (half_done(), None, "in-flight"),
        (half_done(claim="COMPLETE"), None, "mismatch"),
        (untouched(), None, "pending"),
        (evidence(claim="COMPLETE"), unmet("pass", ">=", 6, 4), "mismatch"),
    ],
    ids=["in-flight", "mismatch", "pending", "unmet-check"],
)
def test_an_unreadable_attempt_record_surfaces_the_step_as_unknown(ev, check, underlying) -> None:
    verdict = classify(ev, check, UNREADABLE)

    assert verdict["verdict"] == "unknown"
    assert verdict["verdict"] in verdicts.HUMAN_VERDICTS
    assert f"{STEP}: the Attempts: line cannot be read ({UNREADABLE.reason})" in verdict["evidence"]
    assert f"underlying verdict {underlying}:" in verdict["evidence"]
    assert "attempt" not in verdict


def test_an_unreadable_attempt_record_never_demotes_a_verified_complete_step() -> None:
    assert classify(evidence(), None, UNREADABLE)["verdict"] == "verified-complete"


def test_an_unreadable_attempt_record_keeps_a_more_specific_human_verdict() -> None:
    blocked = classify(evidence(mutation_block="no Mutation: line recorded"), None, UNREADABLE)

    assert blocked == classify(evidence(mutation_block="no Mutation: line recorded"))


def test_an_unreadable_attempt_record_keeps_the_resume_scope_of_the_verdict_it_replaced() -> None:
    assert classify(half_done(), None, UNREADABLE)["resume_scope"] == ["b.py"]


def test_a_verdict_carries_exactly_the_evidence_it_was_built_from_under_its_documented_keys() -> (
    None
):
    ev = half_done(claim="IN-PROGRESS", tier2=dict(STOPPED))

    verdict = classify(ev)

    assert verdict == {
        "step": STEP,
        "wip_claim": "IN-PROGRESS",
        "verdict": "partial@a.py",
        "needs_mark": False,
        "tier1": {"files_changed": ["a.py"], "files_unchanged": ["b.py"], "tests": "green"},
        "tier2": STOPPED,
        "evidence": "1 file(s) changed; agent stopped after a.py; remainder: b.py",
        "resume_scope": ["b.py"],
        "decided_by": "fallback",
    }
